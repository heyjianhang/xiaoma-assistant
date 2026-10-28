"""Owner-attributed, bounded activity events and administrator usage summaries."""

import json
import re
from datetime import timedelta
from functools import lru_cache
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    case,
    cast,
    func,
    literal,
    select,
    union_all,
)
from sqlalchemy.dialects.postgresql import JSONB, JSONPATH
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from .access import Principal, digest, key_fingerprint
from .database import utcnow
from .settings import ROOT

PAGES = {
    "/chat": "对话",
    "/knowledge": "知识库",
    "/data-sources": "数据源",
    "/agents": "Agent 配置",
    "/project": "项目介绍",
    "/admin": "管理后台",
}
PROJECT_TABS = {
    "overview": "整体架构",
    "dataset": "数据集介绍",
    "memory": "记忆与上下文",
    "rag": "RAG",
    "text2sql": "Text2SQL",
    "evidence": "证据核对",
}
CLIENT_KINDS = {"page_view", "document_view", "sql_view", "test_case_view"}
EVENT_KINDS = CLIENT_KINDS | {"login", "invite_activated", "question", "answer"}


class ActivityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    kind: str
    path: str = "/chat"
    tab: str | None = None
    document_id: UUID | None = None
    target_id: str | None = None


@lru_cache(maxsize=1)
def case_names():
    return {
        c["id"]: c.get("title", c["id"])
        for c in json.loads((ROOT / "tests/acceptance/cases.json").read_text())["cases"]
    }


def browser_label(ua):
    # Store only a coarse browser/OS label, not arbitrary User-Agent contents.
    browser = next(
        (
            name
            for pattern, name in (
                ("Edg/", "Edge"),
                ("Firefox/", "Firefox"),
                ("Chrome/", "Chrome"),
                ("Safari/", "Safari"),
            )
            if pattern in ua
        ),
        "其他浏览器",
    )
    os = next(
        (
            name
            for pattern, name in (
                ("Android", "Android"),
                ("iPhone", "iOS"),
                ("iPad", "iOS"),
                ("Windows", "Windows"),
                ("Mac OS", "macOS"),
                ("Linux", "Linux"),
            )
            if pattern in ua
        ),
        "其他系统",
    )
    return f"{browser} / {os}"


class ActivityStore:
    def __init__(self, db, auth, agents):
        self.db, self.auth, self.agents = db, auth, agents
        self.visits = Table(
            "access_visits",
            db.metadata,
            Column("id", PGUUID(as_uuid=True), primary_key=True),
            Column("user_id", PGUUID(as_uuid=True), ForeignKey(auth.users.c.id), nullable=False),
            Column("browser_key", String(64), nullable=False),
            Column("device", String(80), nullable=False),
            Column("started_at", DateTime(timezone=True), nullable=False),
            Column("last_seen_at", DateTime(timezone=True), nullable=False),
        )
        Index("ix_access_visits_owner_seen", self.visits.c.user_id, self.visits.c.last_seen_at)
        self.events = Table(
            "access_events",
            db.metadata,
            Column("user_id", PGUUID(as_uuid=True), ForeignKey(auth.users.c.id), primary_key=True),
            Column("id", PGUUID(as_uuid=True), primary_key=True),
            Column("visit_id", PGUUID(as_uuid=True), ForeignKey(self.visits.c.id), nullable=False),
            Column("kind", String(24), nullable=False),
            Column("label", String(300), nullable=False),
            Column("path", String(100), nullable=False),
            Column("details", JSONB, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )
        Index("ix_access_events_created", self.events.c.created_at)
        Index("ix_access_events_owner_created", self.events.c.user_id, self.events.c.created_at)

    async def _record(self, conn, principal, event_id, kind, label, path, details, ua):
        # Lock the stable owner row so simultaneous tabs/retries share one visit.
        await conn.execute(
            select(self.auth.users.c.id)
            .where(self.auth.users.c.id == principal.user_id)
            .with_for_update()
        )
        old = (
            await conn.execute(
                select(self.events.c.visit_id).where(
                    self.events.c.user_id == principal.user_id, self.events.c.id == event_id
                )
            )
        ).scalar_one_or_none()
        if old:
            return old
        jwk = (
            await conn.execute(
                select(self.auth.sessions.c.public_key).where(
                    self.auth.sessions.c.id == principal.session_id
                )
            )
        ).scalar_one()
        key, now = key_fingerprint(jwk), utcnow()
        visit = (
            await conn.execute(
                select(self.visits.c.id)
                .where(
                    self.visits.c.user_id == principal.user_id,
                    self.visits.c.browser_key == key,
                    self.visits.c.last_seen_at >= now - timedelta(minutes=30),
                )
                .order_by(self.visits.c.last_seen_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        device = browser_label(ua)
        if visit is None:
            visit = uuid4()
            await conn.execute(
                self.visits.insert().values(
                    id=visit,
                    user_id=principal.user_id,
                    browser_key=key,
                    device=device,
                    started_at=now,
                    last_seen_at=now,
                )
            )
        else:
            await conn.execute(
                self.visits.update().where(self.visits.c.id == visit).values(last_seen_at=now)
            )
        await conn.execute(
            self.events.insert().values(
                user_id=principal.user_id,
                id=event_id,
                visit_id=visit,
                kind=kind,
                label=label[:300],
                path=path,
                details={**details, "device": device},
                created_at=now,
            )
        )
        return visit

    async def login(self, token, ua, *, activated=False):
        async with self.db.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        select(
                            self.auth.sessions.c.id,
                            self.auth.sessions.c.user_id,
                            self.auth.users.c.role,
                            self.auth.users.c.name,
                        )
                        .join(self.auth.users, self.auth.users.c.id == self.auth.sessions.c.user_id)
                        .where(self.auth.sessions.c.token_hash == digest(token))
                    )
                )
                .mappings()
                .one()
            )
            principal = Principal(row["user_id"], row["id"], row["role"], row["name"])
            kind = "invite_activated" if activated and principal.role == "guest" else "login"
            await self._record(
                conn,
                principal,
                uuid4(),
                kind,
                "激活邀请，绑定浏览器" if kind == "invite_activated" else "登录",
                "/access",
                {},
                ua,
            )

    async def record(self, principal, body, ua):
        if (
            body.kind not in CLIENT_KINDS
            or len(body.path) > 100
            or (body.target_id and len(body.target_id) > 100)
        ):
            raise HTTPException(422, "不支持的访问事件")
        details = {}
        async with self.db.engine.begin() as conn:
            if body.kind == "page_view":
                if body.path in PAGES:
                    label = f"查看{PAGES[body.path]}"
                elif re.fullmatch(r"/knowledge/[0-9a-fA-F-]{36}", body.path):
                    try:
                        document = UUID(body.path.rsplit("/", 1)[-1])
                    except ValueError as exc:
                        raise HTTPException(422, "文档标识不合法") from exc
                    name = await self.document_name(conn, document)
                    label = f"查看文档 · {name}"
                    details["document_id"] = str(document)
                else:
                    raise HTTPException(422, "不支持的页面")
                if body.tab:
                    if body.path != "/project" or body.tab not in PROJECT_TABS:
                        raise HTTPException(422, "不支持的页面标签")
                    label += " · " + PROJECT_TABS[body.tab]
                    details["tab"] = body.tab
            elif body.kind == "document_view":
                if not body.document_id:
                    raise HTTPException(422, "缺少文档")
                label = f"打开原文 · {await self.document_name(conn, body.document_id)}"
                details["document_id"] = str(body.document_id)
            elif body.kind == "test_case_view":
                if body.target_id not in case_names():
                    raise HTTPException(422, "用例不存在")
                label = f"查看测试用例 · {body.target_id}"
                details["case_id"] = body.target_id
            elif body.path == "/project" and body.target_id is None:
                label = "查看项目示例 · 数据与 SQL"
            else:
                # Real queries are looked up only in the caller's persisted answers.
                if not body.target_id or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", body.target_id):
                    raise HTTPException(422, "查询标识不合法")
                m = self.agents.messages
                found = (
                    await conn.execute(
                        select(m.c.id)
                        .where(
                            m.c.owner_id == principal.user_id,
                            m.c.role == "assistant",
                            func.jsonb_path_exists(
                                m.c.payload,
                                cast("$.presentations[*].payload.result ? (@.id == $id)", JSONPATH),
                                func.jsonb_build_object("id", body.target_id),
                            ),
                        )
                        .limit(1)
                    )
                ).first()
                if not found:
                    raise HTTPException(404, "查询结果不存在")
                label = "查看数据与 SQL"
                details["result_id"] = body.target_id
            if body.path not in PAGES and not re.fullmatch(
                r"/knowledge/[0-9a-fA-F-]{36}", body.path
            ):
                raise HTTPException(422, "不支持的页面")
            visit = await self._record(
                conn, principal, body.event_id, body.kind, label, body.path, details, ua
            )
        return {"ok": True, "visit_id": str(visit)}

    async def document_name(self, conn, id):
        name = (
            await conn.execute(
                select(self.db.documents.c.filename).where(
                    self.db.documents.c.id == id, self.db.documents.c.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        if name is None:
            raise HTTPException(404, "文档不存在")
        return name

    async def invitation_stats(self):
        u, v, r = self.auth.users, self.visits, self.agents.runs
        async with self.db.engine.connect() as conn:
            users = (
                (
                    await conn.execute(
                        select(u.c.invite_id, func.min(u.c.created_at).label("first_activated_at"))
                        .where(u.c.invite_id.is_not(None))
                        .group_by(u.c.invite_id)
                    )
                )
                .mappings()
                .all()
            )
            visits = (
                (
                    await conn.execute(
                        select(
                            u.c.invite_id,
                            func.count(v.c.id).label("visit_count"),
                            func.max(v.c.last_seen_at).label("last_visited_at"),
                        )
                        .join(v, v.c.user_id == u.c.id)
                        .where(u.c.invite_id.is_not(None))
                        .group_by(u.c.invite_id)
                    )
                )
                .mappings()
                .all()
            )
            questions = (
                (
                    await conn.execute(
                        select(
                            u.c.invite_id,
                            func.count(r.c.id).label("question_count"),
                            func.max(r.c.started_at).label("last_question_at"),
                        )
                        .join(r, r.c.owner_id == u.c.id)
                        .where(u.c.invite_id.is_not(None))
                        .group_by(u.c.invite_id)
                    )
                )
                .mappings()
                .all()
            )
        result = {}
        for row in [*users, *visits, *questions]:
            result.setdefault(row["invite_id"], {}).update(
                {k: val for k, val in row.items() if k != "invite_id"}
            )
        for data in result.values():
            last = [
                data[k]
                for k in ("last_visited_at", "last_question_at", "first_activated_at")
                if data.get(k)
            ]
            data["last_visited_at"] = max(last) if last else None
        return result

    def timeline(self):
        e, u, r, m = self.events, self.auth.users, self.agents.runs, self.agents.messages
        columns = [u.c.id.label("user_id"), u.c.name.label("name"), u.c.invite_id]
        stored = select(
            e.c.id,
            e.c.kind,
            e.c.label,
            e.c.created_at,
            e.c.details,
            literal("browser").label("source"),
            *columns,
        ).join(u, u.c.id == e.c.user_id)
        question = select(
            r.c.id,
            literal("question"),
            literal("发送问题"),
            r.c.started_at,
            func.jsonb_build_object("run_id", r.c.id),
            literal("server"),
            *columns,
        ).join(u, u.c.id == r.c.owner_id)
        answer = (
            select(
                r.c.id,
                literal("answer"),
                case(
                    (r.c.status == "completed", "回答完成"),
                    (r.c.status == "stopped", "已停止回答"),
                    (r.c.status == "error", "回答失败"),
                    else_="回答中断",
                ),
                r.c.finished_at,
                func.jsonb_build_object(
                    "run_id",
                    r.c.id,
                    "status",
                    r.c.status,
                    "tool_names",
                    func.jsonb_path_query_array(m.c.payload, cast("$.tools[*].name", JSONPATH)),
                ),
                literal("server"),
                *columns,
            )
            .join(u, u.c.id == r.c.owner_id)
            .join(m, (m.c.run_id == r.c.id) & (m.c.role == "assistant"))
            .where(r.c.finished_at.is_not(None))
        )
        return union_all(stored, question, answer).subquery()

    async def list_events(
        self, invite_id=None, kind=None, start=None, end=None, offset=0, limit=30
    ):
        t = self.timeline()
        conditions = [t.c.invite_id.is_not(None)]
        if invite_id:
            conditions.append(t.c.invite_id == invite_id)
        if kind:
            if kind not in EVENT_KINDS:
                raise HTTPException(422, "不支持的行为筛选")
            conditions.append(t.c.kind == kind)
        if start:
            conditions.append(t.c.created_at >= start)
        if end:
            conditions.append(t.c.created_at < end)
        if start and end and end <= start:
            raise HTTPException(422, "结束时间应晚于开始时间")
        async with self.db.engine.connect() as conn:
            total = (
                await conn.execute(select(func.count()).select_from(t).where(*conditions))
            ).scalar_one()
            rows = (
                (
                    await conn.execute(
                        select(t)
                        .where(*conditions)
                        .order_by(t.c.created_at.desc(), t.c.id.desc(), t.c.kind)
                        .offset(offset)
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        return {
            "items": [dict(row) for row in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }
