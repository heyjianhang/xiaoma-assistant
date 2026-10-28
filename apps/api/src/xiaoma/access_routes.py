from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select

from .access import COOKIE
from .activity_routes import record_login
from .database import utcnow


class LoginProof(BaseModel):
    challenge: str = Field(min_length=20, max_length=64)
    public_key: dict
    signature: str = Field(min_length=40, max_length=180)


class AdminLogin(LoginProof):
    password: str = Field(min_length=1, max_length=256)


class Redeem(LoginProof):
    token: str = Field(min_length=32, max_length=80)


class InviteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    valid_from: AwareDatetime
    expires_at: AwareDatetime


class SkillUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=100000)
    enabled: bool
    revision: int = Field(ge=1)


class SkillRevision(BaseModel):
    revision: int = Field(ge=1)


class SkillStatus(SkillRevision):
    enabled: bool


def router(holder):
    r = APIRouter(prefix="/api/v1")

    def auth():
        return holder["auth"]

    def set_session(response, token):
        response.set_cookie(
            COOKIE,
            token,
            max_age=holder["db"].settings.session_hours * 3600,
            httponly=True,
            secure=holder["db"].settings.auth_cookie_secure,
            samesite="strict",
            path="/",
        )
        response.headers["Cache-Control"] = "no-store"

    def admin(request):
        principal = request.state.principal
        if principal.role != "admin":
            raise HTTPException(403, "仅管理员可以执行此操作")
        return principal

    @r.get("/auth/challenge", tags=["访问认证"])
    async def challenge(request: Request):
        await auth().rate_limit(request.client.host, "challenge", 60)
        return {"challenge": await auth().challenge()}

    @r.post("/auth/admin-login", tags=["访问认证"])
    async def login(body: AdminLogin, request: Request, response: Response):
        await auth().rate_limit(request.client.host, "admin-login", 10)
        await auth().prove_login(body.challenge, body.public_key, body.signature, body.password)
        token = await auth().admin_login(body.password, body.public_key)
        await record_login(holder, token, request)
        set_session(response, token)
        return {"ok": True}

    @r.post("/auth/redeem", tags=["访问认证"])
    async def redeem(body: Redeem, request: Request, response: Response):
        await auth().rate_limit(request.client.host, "redeem", 20)
        await auth().prove_login(body.challenge, body.public_key, body.signature, body.token)
        token, activated = await auth().redeem(body.token, body.public_key, with_activation=True)
        await record_login(holder, token, request, activated=activated)
        set_session(response, token)
        return {"ok": True}

    @r.get("/auth/me", tags=["访问认证"])
    async def me(request: Request):
        principal = request.state.principal
        return {"id": str(principal.user_id), "name": principal.name, "role": principal.role}

    @r.post("/auth/logout", tags=["访问认证"])
    async def logout(request: Request, response: Response):
        async with holder["db"].engine.begin() as c:
            await c.execute(
                auth()
                .sessions.update()
                .where(auth().sessions.c.id == request.state.principal.session_id)
                .values(revoked_at=utcnow())
            )
        response.delete_cookie(
            COOKIE,
            path="/",
            httponly=True,
            samesite="strict",
            secure=holder["db"].settings.auth_cookie_secure,
        )
        return {"ok": True}

    @r.get("/admin/invitations", tags=["邀请管理"])
    async def invites(request: Request):
        admin(request)
        async with holder["db"].engine.connect() as c:
            rows = (
                (
                    await c.execute(
                        select(auth().invites)
                        .order_by(auth().invites.c.created_at.desc())
                        .limit(200)
                    )
                )
                .mappings()
                .all()
            )
        stats = await holder["activity"].invitation_stats()
        return {
            "items": [
                {k: v for k, v in dict(row).items() if k not in ("token_hash", "bound_key")}
                | {
                    "bound": bool(row["bound_key"]),
                    "first_activated_at": None,
                    "last_visited_at": None,
                    "visit_count": 0,
                    "question_count": 0,
                }
                | stats.get(row["id"], {})
                for row in rows
            ]
        }

    @r.post("/admin/invitations", tags=["邀请管理"])
    async def create(body: InviteCreate, request: Request):
        admin(request)
        return await auth().create_invite(body.name, body.valid_from, body.expires_at)

    @r.patch("/admin/invitations/{id}", tags=["邀请管理"])
    async def dates(id: UUID, body: InviteCreate, request: Request):
        admin(request)
        if body.expires_at <= body.valid_from or body.expires_at <= utcnow():
            raise HTTPException(422, "结束时间必须晚于开始和当前时间")
        async with holder["db"].engine.begin() as c:
            result = await c.execute(
                auth()
                .invites.update()
                .where(auth().invites.c.id == id)
                .values(**body.model_dump())
                .returning(auth().invites.c.id)
            )
            if not result.first():
                raise HTTPException(404, "邀请不存在")
        return {"ok": True}

    @r.post("/admin/invitations/{id}/revoke", tags=["邀请管理"])
    async def revoke(id: UUID, request: Request):
        admin(request)
        async with holder["db"].engine.begin() as c:
            result = await c.execute(
                auth()
                .invites.update()
                .where(auth().invites.c.id == id)
                .values(revoked_at=utcnow())
                .returning(auth().invites.c.id)
            )
            if not result.first():
                raise HTTPException(404, "邀请不存在")
        return {"ok": True}

    @r.post("/admin/invitations/{id}/reset-device", tags=["邀请管理"])
    async def reset(id: UUID, request: Request):
        admin(request)
        import secrets

        from .access import digest

        token = secrets.token_urlsafe(32)
        async with holder["db"].engine.begin() as c:
            row = (
                (
                    await c.execute(
                        select(auth().invites).where(auth().invites.c.id == id).with_for_update()
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise HTTPException(404, "邀请不存在")
            auth().check_invite(row)
            if row["bound_user_id"]:
                await c.execute(
                    auth()
                    .sessions.update()
                    .where(auth().sessions.c.user_id == row["bound_user_id"])
                    .values(revoked_at=utcnow())
                )
            await c.execute(
                auth()
                .invites.update()
                .where(auth().invites.c.id == id)
                .values(token_hash=digest(token), bound_key=None, bound_user_id=None)
            )
        return {
            "url": f"{holder['db'].settings.web_origin}/access#invite={token}",
            "notice": "旧链接和旧设备已失效。新设备建立独立访客身份，不继承原访客聊天。",
        }

    @r.get("/admin/skills", tags=["技能管理"])
    async def skills(request: Request, include_deleted: bool = False):
        admin(request)
        return {"items": await holder["agents"].skill_catalog(include_deleted)}

    @r.put("/admin/skills/{id}", tags=["技能管理"])
    async def update_skill(id: str, body: SkillUpdate, request: Request):
        admin(request)
        from .agent.skill_packages import package_from_legacy

        table = holder["agents"].skills
        async with holder["db"].engine.begin() as c:
            old = (
                (await c.execute(select(table).where(table.c.id == id).with_for_update()))
                .mappings()
                .first()
            )
            if not old or old["revision"] != body.revision:
                raise HTTPException(409, "技能已被修改，请刷新后再保存")
            if await c.scalar(
                select(holder["agents"].skill_trash.c.skill_id).where(
                    holder["agents"].skill_trash.c.skill_id == id
                )
            ):
                raise HTTPException(404, "技能已删除，请先恢复")
            package = await holder["agents"].package(id, body.revision)
            updated = {
                **dict(old),
                "name": body.name,
                "description": body.description,
                "body": body.body,
            }
            new_package = package_from_legacy(
                updated,
                package["manifest"]["source"],
                files=package["files"],
                frontmatter=package["manifest"]["frontmatter"],
            )
            result = await c.execute(
                table.update()
                .where(table.c.id == id, table.c.revision == body.revision)
                .values(
                    name=body.name,
                    description=body.description,
                    body=body.body,
                    enabled=body.enabled,
                    revision=body.revision + 1,
                    updated_at=utcnow(),
                )
                .returning(table.c.id)
            )
            if not result.first():
                raise HTTPException(409, "技能已被修改，请刷新后再保存")
            await c.execute(
                holder["agents"]
                .skill_packages.insert()
                .values(
                    skill_id=id,
                    revision=body.revision + 1,
                    manifest=new_package["manifest"],
                    files=new_package["files"],
                )
            )
        return {"ok": True, "revision": body.revision + 1}

    @r.post("/admin/skills/upload", tags=["技能管理"])
    async def upload_skill(
        request: Request,
        file: Annotated[UploadFile, File()],
        expected_revision: Annotated[int | None, Form()] = None,
        expected_id: Annotated[str | None, Form()] = None,
    ):
        admin(request)
        from asyncio import to_thread

        from .agent.skill_packages import MAX_ARCHIVE, read_package

        content = await file.read(MAX_ARCHIVE + 1)
        try:
            package = await to_thread(read_package, content)
            if expected_id is not None and package["id"] != expected_id:
                raise ValueError("新版本 Skill 名称与当前技能不一致")
            return await holder["agents"].install_package(package, expected_revision)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @r.patch("/admin/skills/{id}/enabled", tags=["技能管理"])
    async def enable_skill(id: str, body: SkillStatus, request: Request):
        admin(request)
        table = holder["agents"].skills
        async with holder["db"].engine.begin() as c:
            if await c.scalar(
                select(holder["agents"].skill_trash.c.skill_id).where(
                    holder["agents"].skill_trash.c.skill_id == id
                )
            ):
                raise HTTPException(404, "技能已删除，请先恢复")
            changed = await c.execute(
                table.update()
                .where(table.c.id == id, table.c.revision == body.revision)
                .values(enabled=body.enabled, revision=body.revision + 1, updated_at=utcnow())
                .returning(table.c.id)
            )
            if not changed.first():
                raise HTTPException(409, "技能已变化，请刷新后再操作")
            package = await holder["agents"].package(id, body.revision)
            await c.execute(
                holder["agents"]
                .skill_packages.insert()
                .values(
                    skill_id=id,
                    revision=body.revision + 1,
                    manifest=package["manifest"],
                    files=package["files"],
                )
            )
        return {"ok": True, "revision": body.revision + 1}

    @r.delete("/admin/skills/{id}", tags=["技能管理"])
    async def delete_skill(id: str, revision: int, request: Request):
        admin(request)
        return await holder["agents"].set_skill_deleted(id, revision)

    @r.post("/admin/skills/{id}/restore", tags=["技能管理"])
    async def restore_skill(id: str, body: SkillRevision, request: Request):
        admin(request)
        return await holder["agents"].set_skill_deleted(id, body.revision, restore=True)

    @r.get("/admin/skills/{id}/package", tags=["技能管理"])
    async def download_skill(id: str, request: Request):
        admin(request)
        from .agent.skill_packages import export_package

        async with holder["db"].engine.connect() as c:
            revision = (
                await c.execute(
                    select(holder["agents"].skills.c.revision).where(
                        holder["agents"].skills.c.id == id,
                        ~holder["agents"].skills.c.id.in_(
                            select(holder["agents"].skill_trash.c.skill_id)
                        ),
                    )
                )
            ).scalar_one_or_none()
        if revision is None:
            raise HTTPException(404, "技能不存在")
        package = await holder["agents"].package(id, revision)
        return Response(
            export_package(package),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{id}.zip"'},
        )

    @r.get("/admin/skills/{id}/resource", tags=["技能管理"])
    async def skill_resource(id: str, revision: int, path: str, request: Request):
        admin(request)
        async with holder["db"].engine.connect() as c:
            if await c.scalar(
                select(holder["agents"].skill_trash.c.skill_id).where(
                    holder["agents"].skill_trash.c.skill_id == id
                )
            ):
                raise HTTPException(404, "技能已删除，请先恢复")
        try:
            return await holder["agents"].read_resource(id, revision, path)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    return r
