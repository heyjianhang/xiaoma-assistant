"""Durable, owner-scoped conversations, run snapshots, and configurable skills."""

from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from langchain_core.messages import messages_from_dict, messages_to_dict
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, insert

from ..database import utcnow
from ..settings import ROOT
from .skill_packages import make_package, package_from_legacy, safe_path


class AgentStore:
    def __init__(self, db):
        self.db = db
        m = db.metadata
        schema = db.schema
        self.skills = Table(
            "agent_skills",
            m,
            Column("id", String(64), primary_key=True),
            Column("name", String(100), nullable=False),
            Column("description", String(500), nullable=False),
            Column("body", Text, nullable=False),
            Column("required_tools", JSONB, nullable=False),
            Column("enabled", Boolean, nullable=False),
            Column("revision", Integer, nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )
        self.skill_packages = Table(
            "agent_skill_packages",
            m,
            Column("skill_id", String(64), primary_key=True),
            Column("revision", Integer, primary_key=True),
            Column("manifest", JSONB, nullable=False),
            Column("files", JSONB, nullable=False),
        )
        self.skill_trash = Table(
            "agent_skill_trash",
            m,
            Column("skill_id", String(64), primary_key=True),
            Column("revision", Integer, nullable=False),
            Column("was_enabled", Boolean, nullable=False),
            Column("deleted_at", DateTime(timezone=True), nullable=False),
        )
        self.conversations = Table(
            "chat_conversations",
            m,
            Column("id", UUID(as_uuid=True), primary_key=True),
            Column(
                "owner_id",
                UUID(as_uuid=True),
                ForeignKey(f"{schema}.access_users.id"),
                nullable=False,
            ),
            Column("title", String(120), nullable=False),
            Column("deleted_at", DateTime(timezone=True)),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )
        self.runs = Table(
            "chat_runs",
            m,
            Column("id", UUID(as_uuid=True), primary_key=True),
            Column(
                "conversation_id",
                UUID(as_uuid=True),
                ForeignKey(f"{schema}.chat_conversations.id"),
                nullable=False,
            ),
            Column("owner_id", UUID(as_uuid=True), nullable=False),
            Column("status", String(20), nullable=False),
            Column("snapshot", JSONB, nullable=False),
            Column("started_at", DateTime(timezone=True), nullable=False),
            Column("heartbeat_at", DateTime(timezone=True), nullable=False),
            Column("finished_at", DateTime(timezone=True)),
        )
        self.messages = Table(
            "chat_messages",
            m,
            Column("id", UUID(as_uuid=True), primary_key=True),
            Column(
                "conversation_id",
                UUID(as_uuid=True),
                ForeignKey(f"{schema}.chat_conversations.id"),
                nullable=False,
            ),
            Column("owner_id", UUID(as_uuid=True), nullable=False),
            Column("run_id", UUID(as_uuid=True), nullable=False),
            Column("role", String(20), nullable=False),
            Column("payload", JSONB, nullable=False),
            Column("position", Integer, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )
        self.contexts = Table(
            "chat_contexts",
            m,
            Column(
                "conversation_id",
                UUID(as_uuid=True),
                ForeignKey(f"{schema}.chat_conversations.id"),
                primary_key=True,
            ),
            Column("owner_id", UUID(as_uuid=True), nullable=False),
            Column("through_position", Integer, nullable=False),
            Column("messages", JSONB, nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )

    async def seed(self):
        async with self.db.engine.begin() as c:
            builtins = {}
            for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
                package = make_package(
                    {
                        p.relative_to(path.parent).as_posix(): p.read_bytes()
                        for p in path.parent.rglob("*")
                        if p.is_file()
                    },
                    "builtin",
                )
                meta = package["manifest"]["frontmatter"]
                builtins[package["id"]] = package
                extra = meta.get("metadata", {})
                skill = dict(
                    id=package["id"],
                    name=extra.get("xiaoma-display-name", package["id"]),
                    description=meta["description"][:500],
                    body=package["body"],
                    required_tools=extra.get("xiaoma-required-tools", "").split(),
                )
                await c.execute(
                    insert(self.skills)
                    .values(**skill, revision=1, enabled=True, updated_at=utcnow())
                    .on_conflict_do_nothing()
                )
            # Backfill legacy SOPs as standard packages, preserving admin changes.
            rows = (await c.execute(select(self.skills))).mappings().all()
            for row in rows:
                original = builtins.get(row["id"], {})
                package = package_from_legacy(
                    dict(row),
                    files=original.get("files"),
                    frontmatter=original.get("manifest", {}).get("frontmatter"),
                )
                await c.execute(
                    insert(self.skill_packages)
                    .values(
                        skill_id=row["id"],
                        revision=row["revision"],
                        manifest=package["manifest"],
                        files=package["files"],
                    )
                    .on_conflict_do_nothing()
                )

    async def active_skills(self, allowed):
        async with self.db.engine.connect() as c:
            rows = (
                (
                    await c.execute(
                        select(self.skills, self.skill_packages.c.manifest)
                        .outerjoin(
                            self.skill_packages,
                            (self.skill_packages.c.skill_id == self.skills.c.id)
                            & (self.skill_packages.c.revision == self.skills.c.revision),
                        )
                        .where(
                            self.skills.c.enabled.is_(True),
                            ~self.skills.c.id.in_(select(self.skill_trash.c.skill_id)),
                        )
                        .order_by(self.skills.c.id)
                    )
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows if set(row["required_tools"]).issubset(allowed)]

    async def package(self, id, revision):
        async with self.db.engine.connect() as c:
            row = (
                (
                    await c.execute(
                        select(self.skill_packages).where(
                            self.skill_packages.c.skill_id == id,
                            self.skill_packages.c.revision == revision,
                        )
                    )
                )
                .mappings()
                .first()
            )
        if not row:
            raise HTTPException(404, "技能版本不存在")
        return {**dict(row), "id": id}

    async def read_resource(self, id, revision, path):
        import base64

        path = safe_path(path)
        package = await self.package(id, revision)
        value = package["files"].get(path)
        entry = next((f for f in package["manifest"]["files"] if f["path"] == path), None)
        if value is None or not entry:
            raise ValueError("技能资源不存在")
        if not entry["text"] or entry["size"] > 100000:
            raise ValueError("此资源是二进制文件或超过100KB，不能作为文本加载")
        return {
            "skill": id,
            "revision": revision,
            "path": path,
            "content": base64.b64decode(value).decode("utf-8-sig"),
        }

    async def install_package(self, package, expected_revision=None):
        meta = package["manifest"]["frontmatter"]
        extra = meta.get("metadata", {})
        tools = extra.get("xiaoma-required-tools", "").split()
        from .tools import OUTPUT_NAMES, SQL_TOOL_NAMES

        if not set(tools).issubset(
            OUTPUT_NAMES
            | SQL_TOOL_NAMES
            | {"search_knowledge", "load_skill", "read_skill_resource", "write_todos"}
        ):
            raise ValueError("xiaoma-required-tools 包含未注册工具")
        async with self.db.engine.begin() as c:
            # Serializes same-name installs across tabs and API workers.
            from sqlalchemy import text

            await c.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:id))"),
                {"id": "skill:" + package["id"]},
            )
            if await c.scalar(
                select(self.skill_trash.c.skill_id).where(
                    self.skill_trash.c.skill_id == package["id"]
                )
            ):
                raise HTTPException(409, "技能已删除，请先从最近删除中恢复")
            old = (
                (
                    await c.execute(
                        select(self.skills)
                        .where(self.skills.c.id == package["id"])
                        .with_for_update()
                    )
                )
                .mappings()
                .first()
            )
            if old and expected_revision != old["revision"]:
                raise HTTPException(409, "同名技能已存在，请从该技能上传新版本")
            if not old and expected_revision is not None:
                raise HTTPException(409, "技能版本已变化，请刷新")
            revision = old["revision"] + 1 if old else 1
            values = dict(
                name=extra.get("xiaoma-display-name", package["id"])[:100],
                description=meta["description"][:500],
                body=package["body"],
                required_tools=tools,
                revision=revision,
                enabled=old["enabled"] if old else True,
                updated_at=utcnow(),
            )
            if old:
                await c.execute(
                    self.skills.update().where(self.skills.c.id == package["id"]).values(**values)
                )
            else:
                await c.execute(insert(self.skills).values(id=package["id"], **values))
            await c.execute(
                insert(self.skill_packages).values(
                    skill_id=package["id"],
                    revision=revision,
                    manifest=package["manifest"],
                    files=package["files"],
                )
            )
        return {"id": package["id"], "revision": revision}

    async def skill_catalog(self, include_deleted=False):
        current, original = (
            self.skill_packages.alias("current_package"),
            self.skill_packages.alias("original_package"),
        )
        query = (
            select(
                self.skills,
                current.c.manifest,
                self.skill_trash.c.deleted_at,
                original.c.manifest["source"].as_string().label("origin"),
            )
            .select_from(self.skills)
            .outerjoin(
                current,
                (current.c.skill_id == self.skills.c.id)
                & (current.c.revision == self.skills.c.revision),
            )
            .outerjoin(
                original, (original.c.skill_id == self.skills.c.id) & (original.c.revision == 1)
            )
            .outerjoin(self.skill_trash, self.skill_trash.c.skill_id == self.skills.c.id)
            .order_by(self.skills.c.id)
        )
        if not include_deleted:
            query = query.where(self.skill_trash.c.skill_id.is_(None))
        builtins = {p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")}
        async with self.db.engine.connect() as c:
            rows = (await c.execute(query)).mappings().all()
        return [
            {**dict(row), "builtin": row["id"] in builtins or row["origin"] == "builtin"}
            for row in rows
        ]

    async def set_skill_deleted(self, id, revision, restore=False):
        from sqlalchemy import text

        async with self.db.engine.begin() as c:
            await c.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:id))"), {"id": "skill:" + id}
            )
            skill = (
                (
                    await c.execute(
                        select(self.skills).where(self.skills.c.id == id).with_for_update()
                    )
                )
                .mappings()
                .first()
            )
            if not skill:
                raise HTTPException(404, "技能不存在")
            original = await c.scalar(
                select(self.skill_packages.c.manifest).where(
                    self.skill_packages.c.skill_id == id, self.skill_packages.c.revision == 1
                )
            )
            builtins = {p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")}
            if id in builtins or (original or {}).get("source") == "builtin":
                raise HTTPException(403, "内置技能不能删除")
            if skill["revision"] != revision:
                raise HTTPException(409, "技能已变化，请刷新后再操作")
            removed = (
                (await c.execute(select(self.skill_trash).where(self.skill_trash.c.skill_id == id)))
                .mappings()
                .first()
            )
            if restore != bool(removed):
                raise HTTPException(409, "技能已恢复" if restore else "技能已删除")
            package = (
                (
                    await c.execute(
                        select(self.skill_packages).where(
                            self.skill_packages.c.skill_id == id,
                            self.skill_packages.c.revision == revision,
                        )
                    )
                )
                .mappings()
                .one()
            )
            if restore:
                await c.execute(self.skill_trash.delete().where(self.skill_trash.c.skill_id == id))
            else:
                await c.execute(
                    insert(self.skill_trash).values(
                        skill_id=id,
                        revision=revision + 1,
                        was_enabled=skill["enabled"],
                        deleted_at=utcnow(),
                    )
                )
            await c.execute(
                self.skills.update()
                .where(self.skills.c.id == id)
                .values(
                    revision=revision + 1,
                    enabled=removed["was_enabled"] if restore else False,
                    updated_at=utcnow(),
                )
            )
            await c.execute(
                insert(self.skill_packages).values(
                    skill_id=id,
                    revision=revision + 1,
                    manifest=package["manifest"],
                    files=package["files"],
                )
            )
        return {"ok": True, "revision": revision + 1}

    async def list_conversations(self, owner):
        async with self.db.engine.connect() as c:
            rows = (
                (
                    await c.execute(
                        select(self.conversations)
                        .where(
                            self.conversations.c.owner_id == owner,
                            self.conversations.c.deleted_at.is_(None),
                        )
                        .order_by(self.conversations.c.updated_at.desc())
                        .limit(100)
                    )
                )
                .mappings()
                .all()
            )
            result = []
            for row in rows:
                messages = (
                    await c.execute(
                        select(
                            self.messages.c.payload, self.runs.c.status, self.runs.c.heartbeat_at
                        )
                        .join(self.runs, self.runs.c.id == self.messages.c.run_id)
                        .where(
                            self.messages.c.conversation_id == row["id"],
                            self.messages.c.owner_id == owner,
                        )
                        .order_by(self.messages.c.position)
                    )
                ).all()
                payloads = []
                for payload, run_status, heartbeat in messages:
                    value = dict(payload)
                    if value.get("status") == "running" and (
                        run_status != "running" or heartbeat < utcnow() - timedelta(seconds=45)
                    ):
                        value["status"] = run_status if run_status != "running" else "stopped"
                    payloads.append(value)
                result.append({"id": str(row["id"]), "title": row["title"], "messages": payloads})
        return result

    async def require_conversation(self, conn, owner, id, include_deleted=False):
        row = (
            (
                await conn.execute(
                    select(self.conversations)
                    .where(self.conversations.c.id == id, self.conversations.c.owner_id == owner)
                    .with_for_update()
                )
            )
            .mappings()
            .first()
        )
        if not row or (row["deleted_at"] and not include_deleted):
            raise HTTPException(404, "对话不存在")
        return row

    async def remove(self, owner, id, restore=False):
        async with self.db.engine.begin() as c:
            await self.require_conversation(c, owner, id, include_deleted=restore)
            if not restore:
                active = await c.execute(
                    select(self.runs.c.id).where(
                        self.runs.c.conversation_id == id,
                        self.runs.c.owner_id == owner,
                        self.runs.c.status == "running",
                        self.runs.c.heartbeat_at >= utcnow() - timedelta(seconds=45),
                    )
                )
                if active.first():
                    raise HTTPException(409, "对话正在运行，请停止后再归档")
            await c.execute(
                self.conversations.update()
                .where(self.conversations.c.id == id)
                .values(deleted_at=None if restore else utcnow())
            )

    async def debug_conversation(self, owner, id):
        async with self.db.engine.begin() as c:
            row = await self.require_conversation(c, owner, id, include_deleted=True)
            messages = (
                (
                    await c.execute(
                        select(self.messages)
                        .where(
                            self.messages.c.conversation_id == id,
                            self.messages.c.owner_id == owner,
                        )
                        .order_by(self.messages.c.position)
                    )
                )
                .mappings()
                .all()
            )
            context = (
                (
                    await c.execute(
                        select(self.contexts).where(
                            self.contexts.c.conversation_id == id,
                            self.contexts.c.owner_id == owner,
                        )
                    )
                )
                .mappings()
                .first()
            )
        return {
            "conversation": dict(row),
            "messages": [dict(m) for m in messages],
            "latest_context": dict(context) if context else None,
        }

    async def debug_run(self, owner, id):
        async with self.db.engine.connect() as c:
            run = (
                (
                    await c.execute(
                        select(self.runs).where(
                            self.runs.c.id == id,
                            self.runs.c.owner_id == owner,
                        )
                    )
                )
                .mappings()
                .first()
            )
            if not run:
                raise HTTPException(404, "运行不存在")
            messages = (
                (
                    await c.execute(
                        select(self.messages)
                        .where(
                            self.messages.c.run_id == id,
                            self.messages.c.owner_id == owner,
                        )
                        .order_by(self.messages.c.position)
                    )
                )
                .mappings()
                .all()
            )
        return {"run": dict(run), "messages": [dict(m) for m in messages]}

    async def begin(self, owner, conversation_id, question, snapshot):
        async with self.db.engine.begin() as c:
            # Serialize run allocation per owner, including starts in separate tabs/workers.
            users = self.db.metadata.tables[f"{self.db.schema}.access_users"]
            await c.execute(select(users.c.id).where(users.c.id == owner).with_for_update())
            await c.execute(
                self.runs.update()
                .where(
                    self.runs.c.owner_id == owner,
                    self.runs.c.status == "running",
                    self.runs.c.heartbeat_at < utcnow() - timedelta(seconds=45),
                )
                .values(status="stopped", finished_at=utcnow())
            )
            count = (
                await c.execute(
                    select(func.count())
                    .select_from(self.runs)
                    .where(self.runs.c.owner_id == owner, self.runs.c.status == "running")
                )
            ).scalar_one()
            if count >= 2:
                raise HTTPException(429, "最多同时运行两个对话，请先停止现有任务")
            # An unguessable UUID is an identifier; ownership is always checked independently.
            await c.execute(
                insert(self.conversations)
                .values(
                    id=conversation_id,
                    owner_id=owner,
                    title=question[:80],
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
                .on_conflict_do_nothing()
            )
            await self.require_conversation(c, owner, conversation_id)
            cutoff = utcnow() - timedelta(seconds=45)
            await c.execute(
                self.runs.update()
                .where(
                    self.runs.c.conversation_id == conversation_id,
                    self.runs.c.status == "running",
                    self.runs.c.heartbeat_at < cutoff,
                )
                .values(status="stopped", finished_at=utcnow())
            )
            active = (
                await c.execute(
                    select(self.runs.c.id).where(
                        self.runs.c.conversation_id == conversation_id,
                        self.runs.c.status == "running",
                    )
                )
            ).first()
            if active:
                raise HTTPException(409, "这个对话仍在运行，请先停止或稍后重试")
            rows = (
                await c.execute(
                    select(self.messages.c.payload, self.messages.c.position)
                    .where(
                        self.messages.c.conversation_id == conversation_id,
                        self.messages.c.owner_id == owner,
                    )
                    .order_by(self.messages.c.position)
                )
            ).all()
            context = (
                (
                    await c.execute(
                        select(self.contexts).where(
                            self.contexts.c.conversation_id == conversation_id,
                            self.contexts.c.owner_id == owner,
                        )
                    )
                )
                .mappings()
                .first()
            )
            # LangChain's compacted message state is independent from the full UI
            # transcript. Never discard old turns before the middleware can summarize.
            history = messages_from_dict(context["messages"]) if context else []
            history += [
                {"role": r.payload["role"], "content": r.payload.get("content", "")}
                for r in rows
                if r.payload.get("content")
                and (not context or r.position > context["through_position"])
            ]
            position = rows[-1].position + 1 if rows else 0
            run_id = uuid4()
            assistant_id = uuid4()
            now = utcnow()
            user = {
                "id": str(uuid4()),
                "role": "user",
                "content": question,
                "selectedSkills": snapshot.get("selected_skills", []),
            }
            assistant = {
                "id": str(assistant_id),
                "role": "assistant",
                "content": "",
                "steps": [],
                "tools": [],
                "todos": [],
                "presentations": [],
                "status": "running",
                "modelId": snapshot["model_id"],
                "toolAccess": snapshot["tools"],
            }
            await c.execute(
                self.runs.insert().values(
                    id=run_id,
                    owner_id=owner,
                    conversation_id=conversation_id,
                    status="running",
                    snapshot=snapshot,
                    started_at=now,
                    heartbeat_at=now,
                )
            )
            await c.execute(
                self.messages.insert(),
                [
                    dict(
                        id=user["id"],
                        conversation_id=conversation_id,
                        owner_id=owner,
                        run_id=run_id,
                        role="user",
                        payload=user,
                        position=position,
                        created_at=now,
                    ),
                    dict(
                        id=assistant_id,
                        conversation_id=conversation_id,
                        owner_id=owner,
                        run_id=run_id,
                        role="assistant",
                        payload=assistant,
                        position=position + 1,
                        created_at=now,
                    ),
                ],
            )
            await c.execute(
                self.conversations.update()
                .where(self.conversations.c.id == conversation_id)
                .values(updated_at=now)
            )
        return run_id, assistant_id, history, assistant

    async def save_context(self, run_id, assistant_id, owner, messages):
        import json

        serialized = json.loads(json.dumps(messages_to_dict(messages), default=str))
        async with self.db.engine.begin() as c:
            row = (
                await c.execute(
                    select(self.messages.c.conversation_id, self.messages.c.position).where(
                        self.messages.c.id == assistant_id,
                        self.messages.c.run_id == run_id,
                        self.messages.c.owner_id == owner,
                    )
                )
            ).first()
            if not row:
                raise HTTPException(404, "对话不存在")
            await self.require_conversation(c, owner, row.conversation_id)
            values = dict(
                owner_id=owner,
                through_position=row.position,
                messages=serialized,
                updated_at=utcnow(),
            )
            await c.execute(
                insert(self.contexts)
                .values(conversation_id=row.conversation_id, **values)
                .on_conflict_do_update(
                    index_elements=[self.contexts.c.conversation_id],
                    set_=values,
                    where=self.contexts.c.owner_id == owner,
                )
            )

    async def update_title(self, owner, conversation_id, title):
        async with self.db.engine.begin() as c:
            await self.require_conversation(c, owner, conversation_id)
            await c.execute(
                self.conversations.update()
                .where(
                    self.conversations.c.id == conversation_id,
                    self.conversations.c.owner_id == owner,
                )
                .values(title=title, updated_at=utcnow())
            )

    async def save(self, run_id, assistant_id, owner, payload, final=False):
        async with self.db.engine.begin() as c:
            await c.execute(
                self.messages.update()
                .where(
                    self.messages.c.id == assistant_id,
                    self.messages.c.owner_id == owner,
                    self.messages.c.run_id == run_id,
                )
                .values(payload=payload)
            )
            values = {"heartbeat_at": utcnow()}
            if final:
                values.update(status=payload["status"], finished_at=utcnow())
            await c.execute(
                self.runs.update()
                .where(self.runs.c.id == run_id, self.runs.c.owner_id == owner)
                .values(**values)
            )
