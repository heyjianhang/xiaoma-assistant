"""Durable run dispatch, fenced workers and owner-scoped replayable SSE events."""

import asyncio
import contextlib
import hashlib
import json
import logging
from dataclasses import asdict
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from langchain_core.messages import convert_to_messages, messages_from_dict, messages_to_dict
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from ..access import Principal
from ..database import utcnow
from ..task_queue import RunLeaseLost
from .reasoning import close_reasoning

logger = logging.getLogger(__name__)
ACTIVE = {"queued", "running"}


def encode(event, sequence=None):
    prefix = f"id: {sequence}\n" if sequence is not None else ""
    return prefix + "data: " + json.dumps(event, ensure_ascii=False, default=str) + "\n\n"


class ExistingRun(Exception):
    def __init__(self, run_id):
        self.run_id = run_id


class BackgroundRuns:
    def __init__(self, db, service):
        self.db, self.service, self.store = db, service, service.store
        self.tasks = []
        self.jobs = Table(
            "chat_run_jobs",
            db.metadata,
            Column(
                "run_id", PGUUID(as_uuid=True), ForeignKey(self.store.runs.c.id), primary_key=True
            ),
            Column("owner_id", PGUUID(as_uuid=True), nullable=False),
            Column("request_id", PGUUID(as_uuid=True)),
            Column("request_hash", String(64), nullable=False),
            Column("request", JSONB, nullable=False),
            Column("principal", JSONB, nullable=False),
            Column("skills", JSONB, nullable=False),
            Column("history", JSONB, nullable=False),
            Column("assistant_id", PGUUID(as_uuid=True), nullable=False),
            Column("phase", String(20), nullable=False),
            Column("cancel_requested", Boolean, nullable=False, default=False),
            Column("lease_token", PGUUID(as_uuid=True)),
            Column("lease_until", DateTime(timezone=True)),
            Column("queue_message_id", BigInteger, nullable=False),
            Column("sequence", Integer, nullable=False, default=0),
            Column("created_at", DateTime(timezone=True), nullable=False),
            UniqueConstraint("owner_id", "request_id"),
        )
        self.events = Table(
            "chat_run_events",
            db.metadata,
            Column(
                "run_id", PGUUID(as_uuid=True), ForeignKey(self.jobs.c.run_id), primary_key=True
            ),
            Column("sequence", Integer, primary_key=True),
            Column("event", JSONB, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )

    async def submit(self, principal, body):
        request_hash = hashlib.sha256(
            json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()

        async def check_idempotency(conn):
            if body.request_id:
                existing = (
                    await conn.execute(
                        select(self.jobs.c.run_id, self.jobs.c.request_hash).where(
                            self.jobs.c.owner_id == principal.user_id,
                            self.jobs.c.request_id == body.request_id,
                        )
                    )
                ).first()
                if existing:
                    if existing.request_hash != request_hash:
                        raise HTTPException(409, "Idempotency key belongs to a different request")
                    raise ExistingRun(existing.run_id)

        async def enqueue(conn, run_id, assistant_id, history, payload, skills):
            message_id = await self.db.queue.send(conn, "chat", run_id)
            serialized_principal = {k: str(v) for k, v in asdict(principal).items()}
            await conn.execute(
                self.jobs.insert().values(
                    run_id=run_id,
                    owner_id=principal.user_id,
                    request_id=body.request_id,
                    request_hash=request_hash,
                    request={**body.model_dump(mode="json"), "model_id": payload["modelId"]},
                    principal=serialized_principal,
                    skills=json.loads(json.dumps(skills, default=str)),
                    history=json.loads(
                        json.dumps(messages_to_dict(convert_to_messages(history)), default=str)
                    ),
                    assistant_id=assistant_id,
                    phase="queued",
                    sequence=0,
                    cancel_requested=False,
                    queue_message_id=message_id,
                    created_at=utcnow(),
                )
            )
            await self.append(
                conn,
                run_id,
                {
                    "type": "run",
                    "run_id": str(run_id),
                    "assistant_id": str(assistant_id),
                    "model_id": payload["modelId"],
                },
                payload=payload,
            )
            await self.append(
                conn, run_id, {"type": "step", "text": "已排队，稍后开工"}, payload=payload
            )

        try:
            prepared = await self.service.prepare(
                principal, body, enqueue=enqueue, before_begin=check_idempotency
            )
        except ExistingRun as existing:
            return await self.describe(principal.user_id, existing.run_id)
        return await self.describe(principal.user_id, prepared[2])

    async def describe(self, owner, run_id):
        async with self.db.engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        select(
                            self.jobs.c.phase,
                            self.jobs.c.sequence,
                            self.jobs.c.assistant_id,
                            self.store.messages.c.payload,
                            self.store.runs.c.conversation_id,
                        )
                        .join(
                            self.store.messages,
                            self.store.messages.c.id == self.jobs.c.assistant_id,
                        )
                        .join(self.store.runs, self.store.runs.c.id == self.jobs.c.run_id)
                        .where(self.jobs.c.run_id == run_id, self.jobs.c.owner_id == owner)
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise HTTPException(404, "运行不存在")
        return {
            "run_id": str(run_id),
            "conversation_id": str(row["conversation_id"]),
            "assistant_id": str(row["assistant_id"]),
            "status": row["phase"],
            "event_sequence": row["sequence"],
            "message": row["payload"],
        }

    async def append(self, conn, run_id, event, *, token=None, payload=None):
        if token is not None:
            await self.store.guard_run(conn, run_id, token)
        sequence = await conn.scalar(
            self.jobs.update()
            .where(self.jobs.c.run_id == run_id)
            .values(sequence=self.jobs.c.sequence + 1)
            .returning(self.jobs.c.sequence)
        )
        await conn.execute(
            self.events.insert().values(
                run_id=run_id, sequence=sequence, event=event, created_at=utcnow()
            )
        )
        if payload is not None:
            payload["eventSeq"] = sequence
            await conn.execute(
                self.store.messages.update()
                .where(
                    self.store.messages.c.run_id == run_id,
                    self.store.messages.c.role == "assistant",
                )
                .values(payload=payload)
            )

    @staticmethod
    def stop_payload(payload, message):
        payload.update(status="stopped", stopped=True)
        close_reasoning(payload, "stopped")
        if message:
            payload["error"] = message
        for todo in payload.get("todos", []):
            if todo["status"] == "in_progress":
                todo["status"] = "blocked" if message else "pending"
        for slot in payload.get("presentations", []):
            if slot["status"] == "loading":
                slot.update(status="stopped", error=message)
        for tool in payload.get("tools", []):
            if tool["state"] == "input-available":
                tool.update(state="output-denied", errorText=message)
        return payload

    async def finish(self, conn, job, payload, phase, event):
        await self.append(conn, job["run_id"], event, payload=payload)
        await conn.execute(
            self.store.runs.update()
            .where(self.store.runs.c.id == job["run_id"])
            .values(status=payload["status"], heartbeat_at=utcnow(), finished_at=utcnow())
        )
        await conn.execute(
            self.jobs.update()
            .where(self.jobs.c.run_id == job["run_id"])
            .values(phase=phase, lease_token=None, lease_until=None)
        )
        await self.db.queue.archive(conn, "chat", job["queue_message_id"])

    async def cancel(self, owner, run_id):
        async with self.db.engine.begin() as conn:
            job = (
                (
                    await conn.execute(
                        select(self.jobs)
                        .where(self.jobs.c.run_id == run_id, self.jobs.c.owner_id == owner)
                        .with_for_update()
                    )
                )
                .mappings()
                .first()
            )
            if job is None:
                raise HTTPException(404, "运行不存在")
            if job["phase"] in ACTIVE:
                await conn.execute(
                    self.jobs.update()
                    .where(self.jobs.c.run_id == run_id)
                    .values(cancel_requested=True)
                )
                payload = await conn.scalar(
                    select(self.store.messages.c.payload).where(
                        self.store.messages.c.id == job["assistant_id"]
                    )
                )
                await self.finish(
                    conn,
                    job,
                    self.stop_payload(dict(payload), None),
                    "stopped",
                    {"type": "stopped"},
                )
        return {"ok": True}

    async def claim(self):
        message = await self.db.queue.reserve("chat")
        if not message:
            return None
        async with self.db.engine.begin() as conn:
            run_id = UUID(message["message"]["id"])
            # Lock owner before run, matching admission and enforcing account concurrency.
            owner = await conn.scalar(
                select(self.jobs.c.owner_id).where(self.jobs.c.run_id == run_id)
            )
            if owner:
                users = self.service.auth.users
                await conn.execute(select(users.c.id).where(users.c.id == owner).with_for_update())
            job = (
                (
                    await conn.execute(
                        select(self.jobs).where(self.jobs.c.run_id == run_id).with_for_update()
                    )
                )
                .mappings()
                .first()
            )
            if not job or job["phase"] not in ACTIVE:
                await self.db.queue.archive(conn, "chat", message["msg_id"])
                return None
            job = dict(job)
            if job["phase"] == "running":
                if job["lease_until"] > utcnow():
                    await self.db.queue.renew(conn, "chat", message["msg_id"])
                else:
                    payload = await conn.scalar(
                        select(self.store.messages.c.payload).where(
                            self.store.messages.c.id == job["assistant_id"]
                        )
                    )
                    # The final snapshot can commit before the queue acknowledgement.
                    # Recover that terminal result rather than relabeling it as interrupted.
                    if payload["status"] in {"completed", "error", "stopped"}:
                        status = payload["status"]
                        event = {"type": "complete" if status == "completed" else status}
                        if status == "error":
                            event["message"] = payload.get("error", "后台运行失败")
                        await self.finish(conn, job, dict(payload), status, event)
                    else:
                        explanation = (
                            "后台执行已中断，已保留部分结果，请重新发送问题；未自动重复执行"
                        )
                        await self.finish(
                            conn,
                            job,
                            self.stop_payload(dict(payload), explanation),
                            "interrupted",
                            {"type": "error", "message": explanation},
                        )
                return None
            running = await conn.scalar(
                select(func.count())
                .select_from(self.jobs)
                .where(self.jobs.c.owner_id == owner, self.jobs.c.phase == "running")
            )
            if running >= self.db.settings.chat_owner_concurrency:
                await self.db.queue.renew(conn, "chat", message["msg_id"], 1)
                return None
            token = uuid4()
            await conn.execute(
                self.jobs.update()
                .where(self.jobs.c.run_id == run_id)
                .values(
                    phase="running",
                    lease_token=token,
                    lease_until=utcnow() + timedelta(seconds=self.db.settings.job_lease_seconds),
                )
            )
            payload = dict(
                await conn.scalar(
                    select(self.store.messages.c.payload).where(
                        self.store.messages.c.id == job["assistant_id"]
                    )
                )
            )
            payload["status"] = "running"
            await conn.execute(
                self.store.runs.update()
                .where(self.store.runs.c.id == run_id)
                .values(status="running", heartbeat_at=utcnow())
            )
            await self.append(
                conn, run_id, {"type": "status", "status": "running"}, token=token, payload=payload
            )
            return {**job, "lease_token": token, "payload": payload}

    async def execute(self, job):
        from .routes import ChatRequest

        run_id, token = job["run_id"], job["lease_token"]
        principal = Principal(
            **{
                **job["principal"],
                "user_id": UUID(job["principal"]["user_id"]),
                "session_id": UUID(job["principal"]["session_id"]),
            }
        )
        body = ChatRequest.model_validate(job["request"])
        payload = job["payload"]

        async def disconnected():
            async with self.db.engine.connect() as conn:
                await self.store.guard_run(conn, run_id, token)
                return bool(
                    await conn.scalar(
                        select(self.jobs.c.cancel_requested).where(self.jobs.c.run_id == run_id)
                    )
                )

        class WorkerConnection:
            is_disconnected = staticmethod(disconnected)

        async def heartbeat():
            while True:
                await asyncio.sleep(min(5, self.db.settings.job_lease_seconds / 3))
                async with self.db.engine.begin() as conn:
                    await self.store.guard_run(conn, run_id, token)
                    await conn.execute(
                        self.jobs.update()
                        .where(self.jobs.c.run_id == run_id)
                        .values(
                            lease_until=utcnow()
                            + timedelta(seconds=self.db.settings.job_lease_seconds)
                        )
                    )
                    await self.db.queue.renew(conn, "chat", job["queue_message_id"])

        beat = asyncio.create_task(heartbeat())
        terminal = {"type": "stopped"}
        try:
            await self.service.auth.assert_active(principal)
            model, _ = await self.service.models.resolve(body.model_id)
            await disconnected()
            await self.service.auth.assert_active(principal)
            prepared = (
                model,
                job["skills"],
                run_id,
                job["assistant_id"],
                messages_from_dict(job["history"]),
                payload,
            )
            async for frame in self.service.stream(
                principal, body, prepared, WorkerConnection(), lease_token=token
            ):
                event = json.loads(frame.split("data: ", 1)[1])
                if event["type"] in {"error", "complete"}:
                    terminal = event
                    continue
                if event["type"] in {"heartbeat", "run"}:
                    continue
                async with self.db.engine.begin() as conn:
                    await self.append(conn, run_id, event, token=token, payload=payload)
        except RunLeaseLost:
            return
        except asyncio.CancelledError:
            payload = self.stop_payload(payload, "后台服务已重启，部分结果已保存，请重新发送问题")
            terminal = {"type": "error", "message": payload["error"]}
            raise
        except Exception as exc:
            message = (
                str(exc.detail) if isinstance(exc, HTTPException) else "后台运行失败，请稍后重试"
            )
            payload.update(status="error", error=message)
            terminal = {"type": "error", "message": message}
        finally:
            beat.cancel()
            with contextlib.suppress(asyncio.CancelledError, RunLeaseLost):
                await beat

            async def finalize():
                try:
                    async with self.db.engine.begin() as conn:
                        await self.store.guard_run(conn, run_id, token)
                        await self.finish(conn, job, payload, payload["status"], terminal)
                except RunLeaseLost:
                    pass

            await asyncio.shield(finalize())

    async def worker(self):
        while True:
            try:
                job = await self.claim()
                if job:
                    await self.execute(job)
                else:
                    await asyncio.sleep(self.db.settings.worker_poll_interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Chat worker failed: %s", type(exc).__name__)
                await asyncio.sleep(self.db.settings.worker_poll_interval)

    def start(self):
        self.tasks = [
            asyncio.create_task(self.worker())
            for _ in range(self.db.settings.chat_worker_concurrency)
        ]

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def stream(self, principal, run_id, after=0):
        sequence = after
        try:
            while True:
                await self.service.auth.assert_active(principal)
                async with self.db.engine.connect() as conn:
                    info = (
                        (
                            await conn.execute(
                                select(self.jobs.c.phase, self.jobs.c.sequence).where(
                                    self.jobs.c.run_id == run_id,
                                    self.jobs.c.owner_id == principal.user_id,
                                )
                            )
                        )
                        .mappings()
                        .first()
                    )
                    if info is None:
                        raise HTTPException(404, "Run not found")
                    events = (
                        (
                            await conn.execute(
                                select(self.events)
                                .where(
                                    self.events.c.run_id == run_id,
                                    self.events.c.sequence > sequence,
                                )
                                .order_by(self.events.c.sequence)
                                .limit(200)
                            )
                        )
                        .mappings()
                        .all()
                    )
                for row in events:
                    sequence = row["sequence"]
                    yield encode(row["event"], sequence)
                if info["phase"] not in ACTIVE and sequence >= info["sequence"]:
                    return
                if not events:
                    yield ": waiting\n\n"
                    await asyncio.sleep(self.db.settings.run_event_poll_interval)
        except HTTPException as exc:
            yield encode({"type": "error", "message": str(exc.detail)})
