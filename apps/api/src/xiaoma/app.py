import asyncio
import time
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from .access import ADMIN_ID, AccessStore, Principal
from .access_routes import router as access_router
from .activity import ActivityStore
from .activity_routes import router as activity_router
from .agent.background import BackgroundRuns
from .agent.models import ModelCatalog
from .agent.routes import router as agent_router
from .agent.service import AgentService
from .agent.store import AgentStore
from .business import BusinessDatabase
from .database import Database, utcnow
from .errors import IngestionError
from .ingestion.service import IngestionService
from .ingestion.types import ChunkOptions
from .settings import ROOT, Settings


class EnabledRequest(BaseModel):
    enabled: bool


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)
    document_id: UUID | None = None


def create_app(
    settings: Settings | None = None,
    *,
    start_worker: bool = True,
    auth_test_mode: bool = False,
    start_chat_worker: bool = True,
) -> FastAPI:
    holder = {}

    @asynccontextmanager
    async def lifespan(application):
        load_dotenv(ROOT / ".env", override=False)
        configuration = settings or Settings()
        db = Database(configuration)
        business = BusinessDatabase(configuration)
        auth = AccessStore(db)
        agents = AgentStore(db)
        activity = ActivityStore(db, auth, agents)
        models = ModelCatalog(configuration)
        agent_service = AgentService(db, business, auth, agents, models)
        background = BackgroundRuns(db, agent_service)
        if auth_test_mode and not configuration.knowledge_schema.startswith("test_"):
            raise RuntimeError("Authentication bypass is restricted to isolated test schemas")
        try:
            await db.initialize()
            await auth.bootstrap()
            await agents.seed()
            service = IngestionService(db)
            holder.update(
                db=db,
                service=service,
                business=business,
                auth=auth,
                agents=agents,
                activity=activity,
                models=models,
                agent_service=agent_service,
                background_runs=background,
            )
            application.state.access = auth
            application.state.activity = activity
            application.state.agent_store = agents
            application.state.model_catalog = models
            application.state.db = db
            application.state.ingestion = service
            application.state.background_runs = background
            if start_chat_worker and configuration.background_workers_enabled:
                background.start()
            workers = (
                [
                    asyncio.create_task(service.worker())
                    for _ in range(configuration.ingestion_worker_concurrency)
                ]
                if (start_worker and configuration.background_workers_enabled)
                else []
            )
            await service.migrate_queue()
            try:
                yield
            finally:
                for worker in workers:
                    worker.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
                await background.close()
        finally:
            await business.close()
            await db.close()

    app = FastAPI(
        title="小马助手 · Agent 服务",
        version="0.2.0",
        description="PDF / Markdown → 结构分块 → LangChain Document → PGVectorStore",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )

    public_paths = {
        "/api/health",
        "/api/docs",
        "/api/openapi.json",
        "/api/docs/oauth2-redirect",
        "/api/v1/auth/challenge",
        "/api/v1/auth/admin-login",
        "/api/v1/auth/redeem",
    }

    @app.middleware("http")
    async def access_boundary(request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        try:
            configuration = holder.get("db")
            if not configuration:
                return JSONResponse({"message": "服务正在启动"}, status_code=503)
            settings = configuration.settings
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != settings.web_origin.rstrip("/"):
                raise HTTPException(403, "请求来源不被允许")
            if (
                request.headers.get("content-length", "").isdigit()
                and int(request.headers["content-length"]) > settings.upload_max_bytes + 1024 * 1024
            ):
                raise HTTPException(413, "请求体过大")
            if request.url.path not in public_paths:
                if auth_test_mode:
                    request.state.principal = Principal(ADMIN_ID, ADMIN_ID, "admin", "测试管理员")
                else:
                    request.state.principal = await holder["auth"].authenticate(request)
                principal = request.state.principal
                path = request.url.path
                if principal.role != "admin" and (
                    path.startswith("/api/v1/admin/")
                    or (
                        request.method not in ("GET", "HEAD")
                        and path.startswith("/api/v1/documents")
                    )
                ):
                    raise HTTPException(403, "仅管理员可以管理共享资料")
            response = await call_next(request)
            if "Cache-Control" not in response.headers:
                response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            return response
        except HTTPException as exc:
            return JSONResponse({"message": str(exc.detail)}, status_code=exc.status_code)

    app.include_router(access_router(holder))
    app.include_router(activity_router(holder))
    app.include_router(agent_router(holder))

    @app.exception_handler(IngestionError)
    async def ingestion_error(request, exc):
        status = (
            404
            if exc.code == "not_found"
            else 503
            if exc.code.startswith("business_")
            else 409
            if exc.code == "job_in_progress"
            else 400
        )
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=status)

    @app.get("/api/health", tags=["服务"])
    async def health():
        db = holder["db"]
        async with db.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "database": "ok",
            "providers": {
                "embedding_configured": bool(
                    db.settings.model_base_url and db.settings.model_api_key.get_secret_value()
                ),
                "mineru_configured": bool(db.settings.mineru_api_key.get_secret_value()),
            },
        }

    @app.get("/api/v1/business/tables", tags=["业务数据"])
    async def business_tables():
        try:
            return await holder["business"].catalog()
        except SQLAlchemyError as exc:
            raise IngestionError(
                "business_unavailable", "业务数据库连接失败，请检查服务配置"
            ) from exc

    @app.get("/api/v1/business/tables/{name}/rows", tags=["业务数据"])
    async def business_rows(
        name: str,
        q: Annotated[str, Query(max_length=200)] = "",
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        try:
            return await holder["business"].rows(name, q, limit, offset)
        except SQLAlchemyError as exc:
            raise IngestionError("business_unavailable", "业务数据查询失败，请稍后重试") from exc

    @app.post("/api/v1/documents", status_code=202, tags=["文档"])
    async def upload_document(
        file: Annotated[UploadFile, File(description="PDF 或 UTF-8 Markdown")],
        chunk_options: Annotated[str | None, Form(description="可选 ChunkOptions JSON")] = None,
    ):
        service = holder["service"]
        settings = holder["db"].settings
        try:
            options = (
                ChunkOptions.model_validate_json(chunk_options)
                if chunk_options
                else ChunkOptions(
                    target_chars=settings.chunk_target_chars,
                    max_chars=settings.chunk_max_chars,
                    min_chars=settings.chunk_min_chars,
                )
            )
        except ValidationError as exc:
            raise IngestionError(
                "invalid_chunk_options", "分块参数需满足 min ≤ target ≤ max"
            ) from exc
        content = bytearray()
        try:
            while part := await file.read(64 * 1024):
                content.extend(part)
                if len(content) > settings.upload_max_bytes:
                    return JSONResponse(
                        {"code": "file_too_large", "message": "文件超过上传大小限制"},
                        status_code=413,
                    )
        finally:
            await file.close()
        return await service.upload(file.filename or "", bytes(content), options)

    @app.get("/api/v1/knowledge/config", tags=["知识库"])
    async def knowledge_config():
        settings = holder["db"].settings
        return {
            "chunk_options": {
                "target_chars": settings.chunk_target_chars,
                "max_chars": settings.chunk_max_chars,
                "min_chars": settings.chunk_min_chars,
            },
            "retrieval": {
                "candidate_count": settings.retrieval_candidates,
                "result_count": 5,
                "rerank": settings.rerank_enabled,
                "rerank_model": settings.rerank_model if settings.rerank_enabled else None,
            },
            "upload_max_bytes": settings.upload_max_bytes,
        }

    @app.get("/api/v1/documents", tags=["文档"])
    async def list_documents(
        q: str = "",
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        db = holder["db"]
        d = db.documents
        condition = d.c.deleted_at.is_(None)
        if q:
            condition &= d.c.filename.icontains(q, autoescape=True)
        counts = (
            select(func.count())
            .select_from(db.chunks)
            .where(
                db.chunks.c.index_id == d.c.active_index_id,
            )
            .correlate(d)
            .scalar_subquery()
        )
        async with db.engine.connect() as conn:
            total = (
                await conn.execute(select(func.count()).select_from(d).where(condition))
            ).scalar()
            rows = (
                (
                    await conn.execute(
                        select(d, counts.label("chunk_count"))
                        .where(
                            condition,
                        )
                        .order_by(d.c.created_at.desc())
                        .limit(limit)
                        .offset(offset)
                    )
                )
                .mappings()
                .all()
            )
        return {"items": [dict(row) for row in rows], "total": total}

    @app.get("/api/v1/documents/{document_id}", tags=["文档"])
    async def get_document(document_id: UUID):
        db = holder["db"]
        async with db.engine.connect() as conn:
            doc = await holder["service"].get_document(conn, document_id)
            latest = (
                (
                    await conn.execute(
                        select(db.jobs)
                        .where(
                            db.jobs.c.document_id == document_id,
                        )
                        .order_by(db.jobs.c.revision.desc())
                        .limit(1)
                    )
                )
                .mappings()
                .one()
            )
        return {**doc, "latest_job": dict(latest)}

    @app.get("/api/v1/documents/{document_id}/source", tags=["文档"])
    async def source(document_id: UUID):
        service, db = holder["service"], holder["db"]
        async with db.engine.connect() as conn:
            doc = await service.get_document(conn, document_id)
        return FileResponse(
            service.source_path(document_id),
            filename=doc["filename"],
            content_disposition_type="inline",
            media_type="application/pdf" if doc["format"] == "pdf" else "text/markdown",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @app.get("/api/v1/documents/{document_id}/chunks", tags=["分块"])
    async def chunks(
        document_id: UUID,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        db = holder["db"]
        async with db.engine.connect() as conn:
            doc = await holder["service"].get_document(conn, document_id)
            condition = db.chunks.c.index_id == doc["active_index_id"]
            total = (
                await conn.execute(
                    select(func.count())
                    .select_from(db.chunks)
                    .where(
                        condition,
                    )
                )
            ).scalar()
            rows = (
                (
                    await conn.execute(
                        select(db.chunks)
                        .where(condition)
                        .order_by(
                            db.chunks.c.sequence,
                        )
                        .limit(limit)
                        .offset(offset)
                    )
                )
                .mappings()
                .all()
            )
        return {
            "items": [dict(row) for row in rows],
            "total": total,
            "revision": doc["active_revision"],
            "processing_status": doc["status"],
        }

    @app.patch("/api/v1/documents/{document_id}/chunks/{chunk_id}", tags=["分块"])
    async def set_enabled(document_id: UUID, chunk_id: UUID, body: EnabledRequest):
        db = holder["db"]
        async with db.engine.begin() as conn:
            doc = await holder["service"].get_document(conn, document_id, lock=True)
            changed = await conn.execute(
                db.chunks.update()
                .where(
                    db.chunks.c.id == chunk_id,
                    db.chunks.c.index_id == doc["active_index_id"],
                )
                .values(enabled=body.enabled)
            )
            if not changed.rowcount:
                raise IngestionError("not_found", "分块不存在或属于旧版本")
            await conn.execute(
                text(f"UPDATE {db.vector_table} SET enabled = :enabled WHERE langchain_id = :id"),
                {"enabled": body.enabled, "id": chunk_id},
            )
        return {"id": chunk_id, "enabled": body.enabled}

    @app.post("/api/v1/documents/{document_id}/reprocess", status_code=202, tags=["文档"])
    async def reprocess(document_id: UUID, body: ChunkOptions | None = None):
        return await holder["service"].reprocess(document_id, body)

    @app.delete("/api/v1/documents/{document_id}", tags=["文档"])
    async def delete_document(document_id: UUID):
        db = holder["db"]
        async with db.engine.begin() as conn:
            await holder["service"].get_document(conn, document_id, lock=True)
            await conn.execute(
                db.documents.update()
                .where(db.documents.c.id == document_id)
                .values(
                    deleted_at=utcnow(),
                    status="deleted",
                    updated_at=utcnow(),
                )
            )
            await conn.execute(
                db.jobs.update()
                .where(
                    db.jobs.c.document_id == document_id,
                    db.jobs.c.status.in_(["queued", "running"]),
                )
                .values(
                    status="cancelled", stage="cancelled", lease_until=None, updated_at=utcnow()
                )
            )
            await db.vector_visibility(conn, document_id)
        return {"id": document_id, "status": "deleted"}

    @app.get("/api/v1/jobs/{job_id}", tags=["任务"])
    async def job(job_id: UUID):
        db = holder["db"]
        async with db.engine.connect() as conn:
            row = (
                (await conn.execute(select(db.jobs).where(db.jobs.c.id == job_id)))
                .mappings()
                .first()
            )
        if row is None:
            raise IngestionError("not_found", "任务不存在")
        return dict(row)

    @app.post("/api/v1/retrieval/search", tags=["检索测试"])
    async def search(body: SearchRequest):
        if not body.query.strip():
            raise IngestionError("invalid_query", "请输入检索问题")
        start = time.monotonic()
        try:
            results = await holder["db"].search(body.query, body.top_k, body.document_id)
        except IngestionError:
            raise
        except Exception:
            return JSONResponse({"code": "retrieval_failed", "message": "检索服务请求失败"}, 502)
        return {"documents": results, "elapsed_ms": round((time.monotonic() - start) * 1000)}

    return app


app = create_app()
