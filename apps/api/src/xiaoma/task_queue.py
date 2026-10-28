"""PGMQ transport. Jobs/results live in application tables; messages carry IDs only."""

import hashlib
import json

from sqlalchemy import text


class RunLeaseLost(RuntimeError):
    """A stale worker must neither publish output nor overwrite a successor."""


class PgQueue:
    def __init__(self, db):
        self.db = db
        prefix = "xm_" + hashlib.sha256(db.schema.encode()).hexdigest()[:20]
        self.names = {kind: f"{prefix}_{kind}" for kind in ("chat", "ingestion")}

    async def initialize(self):
        async with self.db.engine.begin() as conn:
            installed = await conn.scalar(text("SELECT to_regnamespace('pgmq')"))
            if not installed:
                raise RuntimeError("PGMQ尚未安装，请先运行 scripts/init_queue.py")
            # Queue DDL is serialized across API/worker instances.
            await conn.execute(text("SELECT pg_advisory_xact_lock(6102802)"))
            for name in self.names.values():
                await conn.execute(text("SELECT pgmq.create(:name)"), {"name": name})

    async def send(self, conn, kind, identifier):
        return await conn.scalar(
            text("SELECT pgmq.send(:name, CAST(:message AS jsonb))"),
            {"name": self.names[kind], "message": json.dumps({"id": str(identifier)})},
        )

    async def reserve(self, kind):
        # Commit the visibility reservation before locking application rows.
        # Cancellation/heartbeats may lock job rows before acknowledging PGMQ.
        async with self.db.engine.begin() as conn:
            row = await self.read(conn, kind)
            return dict(row) if row else None

    async def read(self, conn, kind):
        return (
            (
                await conn.execute(
                    text("SELECT * FROM pgmq.read(:name, :lease, 1)"),
                    {"name": self.names[kind], "lease": self.db.settings.job_lease_seconds},
                )
            )
            .mappings()
            .first()
        )

    async def renew(self, conn, kind, message_id, seconds=None):
        await conn.execute(
            text(
                "SELECT pgmq.set_vt(CAST(:name AS text), "
                "CAST(:id AS bigint), CAST(:lease AS integer))"
            ),
            {
                "name": self.names[kind],
                "id": message_id,
                "lease": seconds if seconds is not None else self.db.settings.job_lease_seconds,
            },
        )

    async def archive(self, conn, kind, message_id):
        await conn.execute(
            text("SELECT pgmq.archive(CAST(:name AS text), CAST(:id AS bigint))"),
            {"name": self.names[kind], "id": message_id},
        )

    async def drop_test_queues(self):
        if not self.db.schema.startswith("test_"):
            raise RuntimeError("Only isolated test queues may be removed")
        async with self.db.engine.begin() as conn:
            for name in self.names.values():
                await conn.execute(text("SELECT pgmq.drop_queue(:name)"), {"name": name})
