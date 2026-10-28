import asyncio
import json
import socket
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
import uvicorn
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from sqlalchemy import func, select, text
from test_access_agent import Device, ScriptedModel, invite
from test_access_agent import admin as admin
from test_access_agent import protected_app as protected_app

from xiaoma.app import create_app
from xiaoma.database import utcnow
from xiaoma.task_queue import RunLeaseLost

pytestmark = pytest.mark.integration


def gated(app):
    release = asyncio.Event()

    class GatedModel(ScriptedModel):
        def _generate(self, messages, **kwargs):
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="test title"))])

        async def _astream(self, messages, **kwargs):
            yield ChatGenerationChunk(message=AIMessageChunk(content="first "))
            await release.wait()
            yield ChatGenerationChunk(message=AIMessageChunk(content="second"))

    async def resolve(name):
        return GatedModel(), {"id": "test-model", "profile": {}}

    app.state.model_catalog.resolve = resolve
    return release


async def submit(device, conversation=None, request=None, question="test"):
    response = await device.call(
        "POST",
        "/api/v1/agent/runs",
        {
            "conversation_id": str(conversation or uuid4()),
            "request_id": str(request or uuid4()),
            "question": question,
            "model_id": "test-model",
            "tools": {"knowledge": False, "data": False},
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


async def wait_for(device, run_id, predicate):
    async with asyncio.timeout(8):
        while True:
            response = await device.call("GET", f"/api/v1/agent/runs/{run_id}")
            assert response.status_code == 200
            info = response.json()
            if predicate(info):
                return info
            await asyncio.sleep(0.03)


async def test_multiple_runs_survive_without_subscriber_and_replay(protected_app, admin):
    release = gated(protected_app)
    try:
        first = await submit(admin)
        second = await submit(admin)
        for item in (first, second):
            info = await wait_for(
                admin, item["run_id"], lambda r: r["message"]["content"] == "first "
            )
            assert info["status"] == "running"
        # No client has ever opened an SSE stream, yet both agents are executing.
        release.set()
        complete = await wait_for(admin, first["run_id"], lambda r: r["status"] == "completed")
        await wait_for(admin, second["run_id"], lambda r: r["status"] == "completed")
        assert complete["message"]["content"] == "first second"
        path = f"/api/v1/agent/runs/{first['run_id']}/events"
        response = await admin.call("GET", path + "?after=0")
        frames = response.text.strip().split("\n\n")
        sequences = [int(f.splitlines()[0][4:]) for f in frames]
        assert sequences == list(range(1, len(sequences) + 1))
        replay = await admin.call("GET", path + f"?after={sequences[-2]}")
        assert len([line for line in replay.text.splitlines() if line.startswith("id:")]) == 1
        assert '"type": "complete"' in replay.text
        assert (await admin.call("GET", path + "?after=999999")).status_code == 422
    finally:
        release.set()


async def test_owner_limit_queue_and_explicit_stop_are_independent(protected_app, admin):
    release = gated(protected_app)
    try:
        first = await submit(admin)
        second = await submit(admin)
        await wait_for(admin, first["run_id"], lambda r: r["message"]["content"] == "first ")
        await wait_for(admin, second["run_id"], lambda r: r["message"]["content"] == "first ")
        third = await submit(admin)
        info = (await admin.call("GET", f"/api/v1/agent/runs/{third['run_id']}")).json()
        assert info["status"] == "queued"
        assert (
            await admin.call("POST", f"/api/v1/agent/runs/{third['run_id']}/stop")
        ).status_code == 200
        assert (
            await admin.call("POST", f"/api/v1/agent/runs/{first['run_id']}/stop")
        ).status_code == 200
        stopped = await wait_for(admin, first["run_id"], lambda r: r["status"] == "stopped")
        assert stopped["message"]["content"] == "first "
        assert (await admin.call("GET", f"/api/v1/agent/runs/{second['run_id']}")).json()[
            "status"
        ] == "running"
        release.set()
        await wait_for(admin, second["run_id"], lambda r: r["status"] == "completed")
        # Releasing the old model must not resurrect a stopped run or append late tokens.
        stopped = (await admin.call("GET", f"/api/v1/agent/runs/{first['run_id']}")).json()
        assert stopped["status"] == "stopped" and stopped["message"]["content"] == "first "
    finally:
        release.set()


async def test_submit_idempotency_and_same_conversation_serialization(protected_app, admin):
    release = gated(protected_app)
    conversation, request = uuid4(), uuid4()
    try:
        first, retry = await asyncio.gather(
            submit(admin, conversation, request), submit(admin, conversation, request)
        )
        assert first["run_id"] == retry["run_id"]
        conflict = await admin.call(
            "POST",
            "/api/v1/agent/runs",
            {
                "conversation_id": str(conversation),
                "question": "another",
                "tools": {"knowledge": False, "data": False},
            },
        )
        assert conflict.status_code == 409
        changed_request = await admin.call(
            "POST",
            "/api/v1/agent/runs",
            {
                "conversation_id": str(conversation),
                "request_id": str(request),
                "question": "different request",
                "model_id": "test-model",
                "tools": {"knowledge": False, "data": False},
            },
        )
        assert changed_request.status_code == 409
        rows = (await admin.call("GET", "/api/v1/conversations")).json()["items"]
        assert len(next(r for r in rows if r["id"] == str(conversation))["messages"]) == 2
    finally:
        release.set()


async def test_run_events_and_cancel_require_ownership(protected_app, admin):
    release = gated(protected_app)
    guest = Device(protected_app)
    try:
        assert (await guest.login((await invite(admin))["token"])).status_code == 200
        run = await submit(admin)
        for suffix in ("", "/events?after=0"):
            assert (
                await guest.call("GET", f"/api/v1/agent/runs/{run['run_id']}{suffix}")
            ).status_code == 404
        assert (
            await guest.call("POST", f"/api/v1/agent/runs/{run['run_id']}/stop")
        ).status_code == 404
    finally:
        release.set()
        await guest.client.aclose()


async def test_lease_expiry_fences_old_worker_and_preserves_partial_result(protected_app, admin):
    bg = protected_app.state.background_runs
    await bg.close()
    gated(protected_app)
    run = await submit(admin)
    job = await bg.claim()
    assert job
    async with bg.db.engine.begin() as conn:
        payload = {**job["payload"], "content": "saved partial"}
        await bg.append(
            conn,
            job["run_id"],
            {"type": "delta", "text": "saved partial"},
            token=job["lease_token"],
            payload=payload,
        )
        await conn.execute(
            bg.jobs.update()
            .where(bg.jobs.c.run_id == job["run_id"])
            .values(lease_until=utcnow() - timedelta(seconds=1))
        )
        await bg.db.queue.renew(conn, "chat", job["queue_message_id"], 0)
    assert await bg.claim() is None
    info = (await admin.call("GET", f"/api/v1/agent/runs/{run['run_id']}")).json()
    assert info["status"] == "interrupted"
    assert info["message"]["content"] == "saved partial"
    with pytest.raises(RunLeaseLost):
        await bg.store.save(
            job["run_id"],
            job["assistant_id"],
            job["owner_id"],
            {**payload, "content": "stale overwrite"},
            lease_token=job["lease_token"],
        )


async def test_terminal_snapshot_is_acknowledged_after_worker_crash(protected_app, admin):
    bg = protected_app.state.background_runs
    await bg.close()
    gated(protected_app)
    run = await submit(admin)
    job = await bg.claim()
    payload = {**job["payload"], "content": "committed final answer", "status": "completed"}
    await bg.store.save(
        job["run_id"],
        job["assistant_id"],
        job["owner_id"],
        payload,
        final=True,
        lease_token=job["lease_token"],
    )
    async with bg.db.engine.begin() as conn:
        await conn.execute(
            bg.jobs.update()
            .where(bg.jobs.c.run_id == job["run_id"])
            .values(
                lease_until=utcnow() - timedelta(seconds=1),
            )
        )
        await bg.db.queue.renew(conn, "chat", job["queue_message_id"], 0)
    assert await bg.claim() is None
    info = await bg.describe(job["owner_id"], UUID(run["run_id"]))
    assert info["status"] == "completed"
    assert info["message"]["content"] == "committed final answer"


async def test_revoked_queued_identity_never_starts_model(protected_app, admin):
    bg = protected_app.state.background_runs
    await bg.close()
    release = gated(protected_app)
    guest = Device(protected_app)
    try:
        invitation = await invite(admin)
        assert (await guest.login(invitation["token"])).status_code == 200
        run = await submit(guest)
        await admin.call("POST", f"/api/v1/admin/invitations/{invitation['id']}/revoke")
        job = await bg.claim()
        assert job
        await bg.execute(job)
        info = await bg.describe(job["owner_id"], UUID(run["run_id"]))
        assert info["status"] == "error" and info["message"]["content"] == ""
    finally:
        release.set()
        await guest.client.aclose()


async def test_tcp_disconnect_does_not_cancel_and_cursor_reconnects(protected_app):
    release = gated(protected_app)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(
        uvicorn.Config(protected_app, lifespan="off", log_level="error", access_log=False)
    )
    task = asyncio.create_task(server.serve(sockets=[sock]))
    device = Device(protected_app)
    await device.client.aclose()
    device.client = httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{sock.getsockname()[1]}", timeout=5
    )
    try:
        async with asyncio.timeout(3):
            while not server.started:
                await asyncio.sleep(0.01)
        assert (await device.login("test-only-password", admin=True)).status_code == 200
        run = await submit(device)
        path = f"/api/v1/agent/runs/{run['run_id']}/events?after=0"
        sequence = 0
        async with device.client.stream(
            "GET", path, headers=device.headers("GET", path, b"")
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("id: "):
                    sequence = int(line[4:])
                if line.startswith("data: ") and json.loads(line[6:])["type"] == "delta":
                    break
        await asyncio.sleep(0.1)
        assert (await device.call("GET", f"/api/v1/agent/runs/{run['run_id']}")).json()[
            "status"
        ] == "running"
        release.set()
        await wait_for(device, run["run_id"], lambda r: r["status"] == "completed")
        replay = await device.call(
            "GET", f"/api/v1/agent/runs/{run['run_id']}/events?after={sequence}"
        )
        deltas = [
            json.loads(line[6:])["text"]
            for line in replay.text.splitlines()
            if line.startswith("data: ") and json.loads(line[6:])["type"] == "delta"
        ]
        assert deltas == ["second"]
    finally:
        release.set()
        await device.client.aclose()
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        sock.close()


async def test_queued_run_survives_application_restart(protected_app, admin):
    original = protected_app.state.background_runs
    await original.close()
    gated(protected_app)
    created = await submit(admin)
    restarted = create_app(original.db.settings, start_worker=False, start_chat_worker=False)
    async with restarted.router.lifespan_context(restarted):

        async def resolve(name):
            return ScriptedModel(), {"id": "test-model", "profile": {}}

        restarted.state.model_catalog.resolve = resolve
        bg = restarted.state.background_runs
        job = await bg.claim()
        assert str(job["run_id"]) == created["run_id"]
        await bg.execute(job)
        info = await bg.describe(job["owner_id"], job["run_id"])
        assert info["status"] == "completed" and info["message"]["content"]


async def test_enqueue_and_run_allocation_are_one_transaction(protected_app, admin, monkeypatch):
    bg = protected_app.state.background_runs
    gated(protected_app)

    async def fail_after_send(*args, **kwargs):
        raise RuntimeError("controlled transaction failure")

    monkeypatch.setattr(bg, "append", fail_after_send)
    with pytest.raises(RuntimeError, match="controlled transaction failure"):
        await submit(admin)
    async with bg.db.engine.connect() as conn:
        assert await conn.scalar(select(func.count()).select_from(bg.store.runs)) == 0
        assert await conn.scalar(select(func.count()).select_from(bg.store.messages)) == 0
        name = bg.db.queue.names["chat"]
        assert await conn.scalar(text(f'SELECT count(*) FROM pgmq."q_{name}"')) == 0


@pytest.mark.parametrize("partial", ["", "unfinished long answer"])
async def test_stopped_turn_is_not_left_as_an_unanswered_instruction(protected_app, admin, partial):
    bg = protected_app.state.background_runs
    await bg.close()
    gated(protected_app)
    conversation = uuid4()
    first = await submit(admin, conversation, question="write a 5000 word document")
    job = await bg.claim()
    assert job
    if partial:
        async with bg.db.engine.begin() as conn:
            await bg.append(
                conn,
                job["run_id"],
                {"type": "delta", "text": partial},
                token=job["lease_token"],
                payload={**job["payload"], "content": partial},
            )
    await admin.call("POST", f"/api/v1/agent/runs/{first['run_id']}/stop")
    second = await submit(admin, conversation, question="你好")
    async with bg.db.engine.connect() as conn:
        history = await conn.scalar(
            select(bg.jobs.c.history).where(bg.jobs.c.run_id == UUID(second["run_id"]))
        )
    assert [m["type"] for m in history] == ["human", "ai"]
    assert "已停止" in history[-1]["data"]["content"]
    assert partial in history[-1]["data"]["content"]
    original = (await admin.call("GET", f"/api/v1/agent/runs/{first['run_id']}")).json()
    assert original["message"]["content"] == partial  # UI transcript stays intact.


@pytest.mark.parametrize("stop", [False, True])
async def test_reasoning_stream_persists_replays_and_stops_independently(
    protected_app, admin, stop
):
    release = asyncio.Event()

    class ThinkingModel(ScriptedModel):
        async def _astream(self, messages, **kwargs):
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="", additional_kwargs={"reasoning_content": "先核对"}
                )
            )
            await release.wait()
            yield ChatGenerationChunk(
                message=AIMessageChunk(content="", additional_kwargs={"reasoning_content": "金额"})
            )
            yield ChatGenerationChunk(message=AIMessageChunk(content="正文结论"))

    async def resolve(name):
        return ThinkingModel(), {"id": "test-model", "profile": {}}

    protected_app.state.model_catalog.resolve = resolve
    try:
        run = await submit(admin)
        info = await wait_for(admin, run["run_id"], lambda r: bool(r["message"].get("reasoning")))
        assert info["message"]["content"] == ""
        assert info["message"]["reasoning"][0]["state"] == "streaming"
        if stop:
            await admin.call("POST", f"/api/v1/agent/runs/{run['run_id']}/stop")
        release.set()
        final = await wait_for(
            admin, run["run_id"], lambda r: r["status"] in {"completed", "stopped"}
        )
        assert final["message"]["reasoning"][0]["state"] == ("stopped" if stop else "completed")
        assert final["message"]["content"] == ("" if stop else "正文结论")
        replay = await admin.call("GET", f"/api/v1/agent/runs/{run['run_id']}/events?after=0")
        events = [
            json.loads(line[6:]) for line in replay.text.splitlines() if line.startswith("data: ")
        ]
        assert any(e["type"] == "reasoning" for e in events)
        assert "先核对" not in "".join(e["text"] for e in events if e["type"] == "delta")
        if not stop:
            store = protected_app.state.agent_store
            async with store.db.engine.connect() as conn:
                saved = await conn.scalar(
                    select(store.contexts.c.messages).where(
                        store.contexts.c.conversation_id == UUID(run["conversation_id"])
                    )
                )
            assert "reasoning_content" not in json.dumps(saved)
    finally:
        release.set()
