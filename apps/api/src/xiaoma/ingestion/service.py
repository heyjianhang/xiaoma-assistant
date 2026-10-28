import asyncio
import contextlib
import hashlib
import logging
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from langsmith import traceable
from sqlalchemy import and_, select, text

from xiaoma.database import Database, utcnow
from xiaoma.errors import IngestionError

from .chunker import StructureChunker, as_documents
from .markdown import parse_markdown
from .mineru import MinerUParser
from .types import ChunkOptions

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, db: Database):
        self.db = db
        self.settings = db.settings
        self.root = self.settings.storage_root

    def source_path(self, document_id: UUID) -> Path:
        return self.root / str(document_id) / "source"

    async def upload(self, filename: str, content: bytes, options: ChunkOptions):
        filename = filename.replace("\\", "/").split("/")[-1].strip()
        if not filename or len(filename) > 255 or any(ord(c) < 32 for c in filename):
            raise IngestionError("invalid_filename", "文件名无效")
        suffix = Path(filename).suffix.lower()
        if suffix not in {".pdf", ".md", ".markdown"}:
            raise IngestionError("unsupported_format", "当前支持 PDF 与 UTF-8 Markdown")
        if not content or len(content) > self.settings.upload_max_bytes:
            raise IngestionError("invalid_size", "文件为空或超过上传大小限制")
        if suffix == ".pdf" and not content.startswith(b"%PDF-"):
            raise IngestionError("invalid_pdf", "文件不是有效的 PDF")
        if suffix != ".pdf":
            try:
                decoded = content.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise IngestionError("invalid_encoding", "Markdown 需要 UTF-8 编码") from exc
            if "\x00" in decoded or not decoded.strip():
                raise IngestionError("invalid_markdown", "Markdown 内容无效或为空")
        document_id, job_id = uuid4(), uuid4()
        path = self.source_path(document_id)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)
        try:
            async with self.db.engine.begin() as conn:
                await conn.execute(
                    self.db.documents.insert().values(
                        id=document_id,
                        filename=filename,
                        format="pdf" if suffix == ".pdf" else "md",
                        sha256=hashlib.sha256(content).hexdigest(),
                        byte_size=len(content),
                        revision=1,
                        status="queued",
                        chunk_options=options.model_dump(),
                    )
                )
                await conn.execute(
                    self.db.jobs.insert().values(
                        id=job_id,
                        document_id=document_id,
                        revision=1,
                        status="queued",
                    )
                )
                await self.db.queue.send(conn, "ingestion", job_id)
        except BaseException:
            await asyncio.to_thread(path.unlink, missing_ok=True)
            raise
        return {"document_id": document_id, "job_id": job_id, "status": "queued"}

    async def get_document(self, conn, document_id, lock=False):
        stmt = select(self.db.documents).where(
            self.db.documents.c.id == document_id,
            self.db.documents.c.deleted_at.is_(None),
        )
        if lock:
            stmt = stmt.with_for_update()
        row = (await conn.execute(stmt)).mappings().one_or_none()
        if row is None:
            raise IngestionError("not_found", "文档不存在")
        return dict(row)

    async def reprocess(self, document_id: UUID, options: ChunkOptions | None = None):
        d, j = self.db.documents, self.db.jobs
        async with self.db.engine.begin() as conn:
            doc = await self.get_document(conn, document_id, lock=True)
            if doc["status"] in {"queued", "parsing", "chunking", "indexing"}:
                raise IngestionError("job_in_progress", "文档正在处理，请等待当前任务完成")
            revision = doc["revision"] + 1
            job_id = uuid4()
            await conn.execute(
                d.update()
                .where(d.c.id == document_id)
                .values(
                    revision=revision,
                    status="queued",
                    updated_at=utcnow(),
                    chunk_options=options.model_dump() if options else doc["chunk_options"],
                )
            )
            await conn.execute(
                j.insert().values(
                    id=job_id,
                    document_id=document_id,
                    revision=revision,
                    status="queued",
                )
            )
            await self.db.queue.send(conn, "ingestion", job_id)
        return {"document_id": document_id, "job_id": job_id, "status": "queued"}

    async def migrate_queue(self):
        """One-time bridge for jobs created before PGMQ was installed."""
        async with self.db.engine.begin() as conn:
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:name))"),
                {"name": self.db.schema + ":ingestion-pgmq"},
            )
            await conn.execute(select(self.db.config).with_for_update())
            done = await conn.scalar(
                select(self.db.config.c.value).where(self.db.config.c.key == "pgmq_ingestion_v1")
            )
            if done:
                return
            rows = await conn.scalars(
                select(self.db.jobs.c.id).where(self.db.jobs.c.status.in_(["queued", "running"]))
            )
            for job_id in rows:
                await self.db.queue.send(conn, "ingestion", job_id)
            await conn.execute(self.db.config.insert().values(key="pgmq_ingestion_v1", value=True))

    async def claim(self):
        j = self.db.jobs
        message = await self.db.queue.reserve("ingestion")
        if not message:
            return None
        async with self.db.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        select(j)
                        .where(
                            j.c.id == UUID(message["message"]["id"]),
                        )
                        .with_for_update()
                        .limit(1)
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                await self.db.queue.archive(conn, "ingestion", message["msg_id"])
                return None
            job = dict(row)
            if job["status"] not in {"queued", "running"}:
                await self.db.queue.archive(conn, "ingestion", message["msg_id"])
                return None
            if job["status"] == "running" and job["lease_until"] > utcnow():
                await self.db.queue.renew(conn, "ingestion", message["msg_id"])
                return None
            job["queue_message_id"] = message["msg_id"]
            # Every attempt has its own inactive index: an expired worker cannot alter a successor.
            job["index_id"] = uuid4()
            await conn.execute(
                j.update()
                .where(j.c.id == job["id"])
                .values(
                    status="running",
                    stage="parsing",
                    index_id=job["index_id"],
                    attempts=j.c.attempts + 1,
                    lease_until=self.lease(),
                    updated_at=utcnow(),
                    error_code=None,
                    error_message=None,
                )
            )
        return job

    def lease(self):
        return utcnow() + timedelta(seconds=self.settings.job_lease_seconds)

    def owns(self, job):
        j = self.db.jobs
        return and_(j.c.id == job["id"], j.c.index_id == job["index_id"], j.c.status == "running")

    async def heartbeat(self, job):
        while True:
            await asyncio.sleep(self.settings.job_lease_seconds / 3)
            async with self.db.engine.begin() as conn:
                updated = await conn.execute(
                    self.db.jobs.update()
                    .where(self.owns(job))
                    .values(
                        lease_until=self.lease(),
                        updated_at=utcnow(),
                    )
                )
                if not updated.rowcount:
                    return
                await self.db.queue.renew(conn, "ingestion", job["queue_message_id"])

    async def stage(self, job, stage):
        async with self.db.engine.begin() as conn:
            # Keep the same lock order as publish/delete, including intermediate stages.
            await self.get_document(conn, job["document_id"], lock=True)
            changed = await conn.execute(
                self.db.jobs.update()
                .where(self.owns(job))
                .values(
                    stage=stage,
                    lease_until=self.lease(),
                    updated_at=utcnow(),
                )
            )
            if not changed.rowcount:
                raise IngestionError("job_superseded", "任务已被取消或接管")
            await conn.execute(
                self.db.documents.update()
                .where(
                    self.db.documents.c.id == job["document_id"],
                    self.db.documents.c.revision == job["revision"],
                    self.db.documents.c.deleted_at.is_(None),
                )
                .values(status=stage, updated_at=utcnow())
            )

    @traceable(
        name="document_ingestion",
        run_type="chain",
        process_inputs=lambda values: {"job": values["job"]},
    )
    async def process(self, job):
        beat = asyncio.create_task(self.heartbeat(job))
        try:
            async with self.db.engine.connect() as conn:
                doc = await self.get_document(conn, job["document_id"])
            await self.stage(job, "parsing")
            content = await asyncio.to_thread(self.source_path(doc["id"]).read_bytes)
            artifact_dir = self.root / str(doc["id"]) / str(job["index_id"])
            await asyncio.to_thread(artifact_dir.mkdir, parents=True, exist_ok=True)
            if doc["format"] == "pdf":
                parsed, archive = await MinerUParser(self.settings).parse(content, str(doc["id"]))
                await asyncio.to_thread((artifact_dir / "mineru.zip").write_bytes, archive)
            else:
                parsed = await asyncio.to_thread(parse_markdown, content.decode("utf-8-sig"))
            await asyncio.to_thread(
                (artifact_dir / "parsed.json").write_text,
                parsed.model_dump_json(indent=2),
                encoding="utf-8",
            )
            await self.stage(job, "chunking")
            chunks = StructureChunker(ChunkOptions.model_validate(doc["chunk_options"])).split(
                parsed.blocks,
            )
            if not chunks:
                raise IngestionError("empty_document", "解析后没有可入库正文")
            documents = as_documents(
                chunks,
                parsed,
                doc["id"],
                job["revision"],
                job["index_id"],
                doc["filename"],
            )
            await self.stage(job, "indexing")
            # Sole vector-write entry: LangChain handles embedding and persistence.
            await self.db.store.aadd_documents(documents)
            async with self.db.engine.begin() as conn:
                current = await self.get_document(conn, doc["id"], lock=True)
                owner = (
                    await conn.execute(
                        select(self.db.jobs.c.id)
                        .where(
                            self.owns(job),
                        )
                        .with_for_update()
                    )
                ).first()
                if not owner or current["revision"] != job["revision"]:
                    raise IngestionError("job_superseded", "任务已被取消或接管")
                await conn.execute(
                    self.db.chunks.insert(),
                    [
                        {
                            "id": UUID(item.id),
                            "document_id": doc["id"],
                            "revision": job["revision"],
                            "index_id": job["index_id"],
                            "sequence": item.metadata["sequence"],
                            "content": item.page_content,
                            "metadata": {
                                key: value
                                for key, value in item.metadata.items()
                                if key not in {"active", "enabled"}
                            },
                            "enabled": True,
                        }
                        for item in documents
                    ],
                )
                await self.db.vector_visibility(conn, doc["id"], job["index_id"])
                await conn.execute(
                    self.db.documents.update()
                    .where(
                        self.db.documents.c.id == doc["id"],
                    )
                    .values(
                        status="ready",
                        active_revision=job["revision"],
                        active_index_id=job["index_id"],
                        pages=parsed.pages,
                        source_map_available=parsed.source_map_available,
                        updated_at=utcnow(),
                    )
                )
                await conn.execute(
                    self.db.jobs.update()
                    .where(self.owns(job))
                    .values(
                        status="done",
                        stage="ready",
                        lease_until=None,
                        updated_at=utcnow(),
                    )
                )
            return {"status": "ready", "chunks": len(documents), "revision": job["revision"]}
        except Exception as exc:
            if isinstance(exc, IngestionError):
                code, message = exc.code, exc.message
            elif isinstance(exc, (TimeoutError, httpx.TimeoutException)):
                code, message = "provider_timeout", "解析或向量服务请求超时，可重新处理"
            elif isinstance(exc, httpx.HTTPError):
                code, message = "provider_http_error", "外部服务请求失败，请检查配置与配额"
            else:
                code, message = "ingestion_failed", "入库失败，请检查服务配置、向量维度与解析产物"
            # Log only exception type: provider exceptions may contain signed URLs or credentials.
            logger.warning(
                "Ingestion failed: job=%s code=%s type=%s", job["id"], code, type(exc).__name__
            )
            async with self.db.engine.begin() as conn:
                # Lock order matches publish/delete: document, then job.
                await conn.execute(
                    select(self.db.documents.c.id)
                    .where(
                        self.db.documents.c.id == job["document_id"],
                    )
                    .with_for_update()
                )
                changed = await conn.execute(
                    self.db.jobs.update()
                    .where(self.owns(job))
                    .values(
                        status="failed",
                        stage="failed",
                        error_code=code,
                        error_message=message,
                        lease_until=None,
                        updated_at=utcnow(),
                    )
                )
                if changed.rowcount:
                    await conn.execute(
                        self.db.documents.update()
                        .where(
                            self.db.documents.c.id == job["document_id"],
                            self.db.documents.c.revision == job["revision"],
                            self.db.documents.c.deleted_at.is_(None),
                        )
                        .values(status="failed", updated_at=utcnow())
                    )
            # Trace records a safe error, while the durable job retains its public error code.
            raise IngestionError(code, message) from None
        finally:
            beat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await beat
            async with self.db.engine.begin() as conn:
                # A superseded worker cannot acknowledge the successor's message.
                finished = await conn.scalar(
                    select(self.db.jobs.c.status)
                    .where(
                        self.db.jobs.c.id == job["id"], self.db.jobs.c.index_id == job["index_id"]
                    )
                    .with_for_update()
                )
                if finished in {"ready", "failed", "cancelled"}:
                    await self.db.queue.archive(conn, "ingestion", job["queue_message_id"])

    async def run_once(self):
        job = await self.claim()
        if job:
            try:
                await self.process(job)
            except IngestionError:
                pass  # Failure is already persisted; the next job can run.
        return job is not None

    async def worker(self):
        while True:
            try:
                if not await self.run_once():
                    await asyncio.sleep(self.settings.worker_poll_interval)
            except Exception as exc:
                logger.warning("Worker poll failed: %s", type(exc).__name__)
                await asyncio.sleep(self.settings.worker_poll_interval)
