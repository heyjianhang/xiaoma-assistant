import base64
import hashlib
import json
import time
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import PrivateAttr, SecretStr
from sqlalchemy import select, text

from xiaoma.access import password_hash
from xiaoma.app import create_app
from xiaoma.database import utcnow

pytestmark = pytest.mark.integration


async def test_debug_inspection_prompt_snapshot_ownership_and_active_archive(protected_app, admin):
    from xiaoma.access import ADMIN_ID

    async def resolve(name):
        return ScriptedModel(), {"id": "test-model", "profile": {}}

    protected_app.state.model_catalog.resolve = resolve
    conversation = str(uuid4())
    response = await admin.call(
        "POST",
        "/api/v1/agent/serve",
        {
            "conversation_id": conversation,
            "question": "调试一次",
            "model_id": "test-model",
            "tools": {"knowledge": False, "data": False},
        },
    )
    assert response.status_code == 200
    events = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    run_id = next(e["run_id"] for e in events if e["type"] == "run")
    result = await admin.call("GET", f"/api/v1/admin/debug/runs/{run_id}")
    assert result.status_code == 200
    run = result.json()["run"]
    assert run["status"] == "completed"
    snapshot = run["snapshot"]
    assert (
        snapshot["system_prompt_sha256"]
        == hashlib.sha256(snapshot["system_prompt"].encode()).hexdigest()
    )
    assert len(result.json()["messages"]) == 2
    assert (
        await admin.call("GET", f"/api/v1/admin/debug/conversations/{conversation}")
    ).status_code == 200

    store = protected_app.state.agent_store
    running_conversation = uuid4()
    prepared = await store.begin(
        ADMIN_ID,
        running_conversation,
        "运行中",
        {
            "model_id": "test",
            "tools": {"knowledge": False, "data": False},
        },
    )
    assert (
        await admin.call("DELETE", f"/api/v1/conversations/{running_conversation}")
    ).status_code == 409
    await store.save(
        prepared[0], prepared[1], ADMIN_ID, {**prepared[3], "status": "completed"}, final=True
    )
    assert (
        await admin.call("DELETE", f"/api/v1/conversations/{running_conversation}")
    ).status_code == 200
    assert (
        await admin.call("POST", f"/api/v1/conversations/{running_conversation}/restore")
    ).status_code == 200

    guest = Device(protected_app)
    try:
        assert (await guest.login((await invite(admin))["token"])).status_code == 200
        assert (await guest.call("GET", f"/api/v1/admin/debug/runs/{run_id}")).status_code == 403
        owner = UUID((await guest.call("GET", "/api/v1/auth/me")).json()["id"])
        other = await store.begin(owner, uuid4(), "其他身份", {"model_id": "test", "tools": {}})
        assert (await admin.call("GET", f"/api/v1/admin/debug/runs/{other[0]}")).status_code == 404
    finally:
        await guest.client.aclose()


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


class Device:
    def __init__(self, app):
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )
        self.key = ec.generate_private_key(ec.SECP256R1())
        n = self.key.public_key().public_numbers()
        self.jwk = {
            "kty": "EC",
            "crv": "P-256",
            "x": b64(n.x.to_bytes(32, "big")),
            "y": b64(n.y.to_bytes(32, "big")),
        }

    def sign(self, message):
        der = self.key.sign(message.encode(), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))

    async def login(self, credential, admin=False):
        challenge = (await self.client.get("/api/v1/auth/challenge")).json()["challenge"]
        proof = self.sign(
            f"xiaoma-login\n{challenge}\n{hashlib.sha256(credential.encode()).hexdigest()}"
        )
        return await self.client.post(
            "/api/v1/auth/admin-login" if admin else "/api/v1/auth/redeem",
            json={
                "challenge": challenge,
                "public_key": self.jwk,
                "signature": proof,
                **({"password": credential} if admin else {"token": credential}),
            },
        )

    def headers(self, method, path, body):
        stamp = str(int(time.time()))
        nonce = str(uuid4())
        proof = self.sign(f"{method}\n{path}\n{stamp}\n{nonce}\n{hashlib.sha256(body).hexdigest()}")
        return {
            "X-Device-Time": stamp,
            "X-Device-Nonce": nonce,
            "X-Device-Proof": proof,
            "Content-Type": "application/json",
        }

    async def call(self, method, path, value=None, headers=None):
        body = (
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
            if value is not None
            else b""
        )
        return await self.client.request(
            method, path, content=body, headers=headers or self.headers(method, path, body)
        )


@pytest.fixture
async def protected_app(provider_settings):
    settings = provider_settings.model_copy(
        update={"admin_password_hash": SecretStr(password_hash("test-only-password"))}
    )
    app = create_app(settings, start_worker=False)
    async with app.router.lifespan_context(app):
        yield app
        db = app.state.db
        await app.state.background_runs.close()
        await db.queue.drop_test_queues()
        async with db.engine.begin() as c:
            await c.execute(text(f'DROP SCHEMA "{db.schema}" CASCADE'))


@pytest.fixture
async def admin(protected_app):
    d = Device(protected_app)
    response = await d.login("test-only-password", admin=True)
    assert response.status_code == 200, response.text
    yield d
    await d.client.aclose()


async def invite(admin, name="访客", start=None, end=None):
    response = await admin.call(
        "POST",
        "/api/v1/admin/invitations",
        {
            "name": name,
            "valid_from": (start or utcnow() - timedelta(minutes=1)).isoformat(),
            "expires_at": (end or utcnow() + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_device_binding_cookie_copy_signature_replay_and_admin_boundary(protected_app, admin):
    a, b = Device(protected_app), Device(protected_app)
    try:
        token = (await invite(admin))["token"]
        assert (await a.login(token)).status_code == 200
        assert (await b.login(token)).status_code == 403
        b.client.cookies.update(a.client.cookies)
        assert (await b.call("GET", "/api/v1/auth/me")).status_code == 401
        headers = a.headers("GET", "/api/v1/auth/me", b"")
        assert (await a.call("GET", "/api/v1/auth/me", headers=headers)).status_code == 200
        assert (await a.call("GET", "/api/v1/auth/me", headers=headers)).status_code == 401
        assert (await a.call("GET", "/api/v1/admin/invitations")).status_code == 403
        assert (await a.call("POST", "/api/v1/documents", {})).status_code == 403
        assert (await a.client.get("/api/v1/documents")).status_code == 401
    finally:
        await a.client.aclose()
        await b.client.aclose()


async def test_activation_expiration_revocation_and_reset_take_effect(protected_app, admin):
    a, b = Device(protected_app), Device(protected_app)
    try:
        future = await invite(admin, start=utcnow() + timedelta(hours=1))
        assert (await a.login(future["token"])).status_code == 403
        data = await invite(admin)
        assert (await a.login(data["token"])).status_code == 200
        old = (await a.call("GET", "/api/v1/auth/me")).json()["id"]
        reset = await admin.call("POST", f"/api/v1/admin/invitations/{data['id']}/reset-device")
        assert reset.status_code == 200
        assert (await a.call("GET", "/api/v1/auth/me")).status_code == 401
        assert (await b.login(data["token"])).status_code == 403
        assert (await b.login(reset.json()["url"].split("invite=")[1])).status_code == 200
        assert (await b.call("GET", "/api/v1/auth/me")).json()["id"] != old
        assert (
            await admin.call("POST", f"/api/v1/admin/invitations/{data['id']}/revoke")
        ).status_code == 200
        assert (await b.call("GET", "/api/v1/auth/me")).status_code == 403
        active = await invite(admin)
        assert (await a.login(active["token"])).status_code == 200
        auth = protected_app.state.access
        async with protected_app.state.db.engine.begin() as c:
            await c.execute(
                auth.invites.update()
                .where(auth.invites.c.id == UUID(active["id"]))
                .values(expires_at=utcnow() - timedelta(seconds=1))
            )
        assert (await a.call("GET", "/api/v1/auth/me")).status_code == 403
    finally:
        await a.client.aclose()
        await b.client.aclose()


async def test_signed_multipart_preserves_upload_body_and_rejects_tampering(protected_app, admin):
    path = "/api/v1/documents"
    request = admin.client.build_request(
        "POST",
        path,
        files={
            "file": ("签名上传.md", "# 签名上传\n\n这是隔离测试文档。".encode(), "text/markdown")
        },
    )
    body = await request.aread()
    headers = admin.headers("POST", path, body)
    headers["Content-Type"] = request.headers["Content-Type"]
    response = await admin.client.post(path, content=body, headers=headers)
    assert response.status_code == 202, response.text
    assert (await admin.call("GET", "/api/v1/documents")).json()["total"] == 1

    headers = admin.headers("POST", path, body)
    headers["Content-Type"] = request.headers["Content-Type"]
    tampered = body.replace("隔离测试".encode(), "篡改内容".encode())
    assert tampered != body
    response = await admin.client.post(path, content=tampered, headers=headers)
    assert response.status_code == 401
    assert (await admin.call("GET", "/api/v1/documents")).json()["total"] == 1


class ScriptedModel(BaseChatModel):
    _names: set = PrivateAttr(default_factory=set)

    @property
    def _llm_type(self):
        return "integration-script"

    def bind_tools(self, tools, **kwargs):
        self._names = {t.name if hasattr(t, "name") else t["function"]["name"] for t in tools}
        return self

    def next(self, messages):
        if "list_tables" not in self._names:
            return AIMessage(content="业务查询已关闭，本轮没有调用数据库。")
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        last = tool_messages[-1] if tool_messages else None
        if last is None:
            name, args = "list_tables", {}
        elif last.name == "list_tables":
            name, args = "get_table_schema", {"tables": ["orders"]}
        elif last.name == "get_table_schema":
            name, args = (
                "link_schema",
                {
                    "question": "订单总数",
                    "tables": {"orders": ["order_id"]},
                    "joins": [],
                    "grain": "一行一订单",
                },
            )
        elif last.name == "link_schema":
            name, args = (
                "execute_readonly_sql",
                {
                    "context_id": json.loads(last.content)["context_id"],
                    "sql": "SELECT COUNT(order_id) AS order_count FROM orders",
                },
            )
        else:
            value = json.loads(last.content)
            return AIMessage(content=f"数据库中共有 {value['rows'][0]['order_count']} 条订单。")
        return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": str(uuid4())}])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=self.next(messages))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        message = self.next(messages)
        yield ChatGenerationChunk(
            message=AIMessageChunk(content=message.content, tool_calls=message.tool_calls)
        )


async def test_real_langchain_sql_loop_stream_persistence_switches_and_owner_isolation(
    protected_app, admin
):
    a, b = Device(protected_app), Device(protected_app)
    try:
        assert (await a.login((await invite(admin, "甲"))["token"])).status_code == 200
        assert (await b.login((await invite(admin, "乙"))["token"])).status_code == 200

        async def resolve(name):
            return ScriptedModel(), {"id": "test-model", "profile": {}}

        protected_app.state.model_catalog.resolve = resolve
        conversation = str(uuid4())
        request = {
            "conversation_id": conversation,
            "question": "订单一共有多少条？",
            "model_id": "test-model",
            "tools": {"knowledge": False, "data": True},
        }
        response = await a.call("POST", "/api/v1/agent/serve", request)
        assert response.status_code == 200, response.text
        assert "5000" in response.text and "schema" in response.text, response.text[-3000:]
        events = [
            json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
        ]
        steps = [event["text"] for event in events if event["type"] == "step"]
        assert steps.count("小马开工啦，先理理思路") == 1
        assert "正在理清问题，整理已有线索" not in steps
        assert "正在核对结果，继续处理" in steps
        messages = (await a.call("GET", "/api/v1/conversations")).json()["items"][0]["messages"]
        assert messages[-1]["status"] == "completed" and "5000" in messages[-1]["content"]
        assert any(t["name"] == "link_schema" for t in messages[-1]["tools"])
        assert (await b.call("GET", "/api/v1/conversations")).json()["items"] == []
        assert (await b.call("DELETE", f"/api/v1/conversations/{conversation}")).status_code == 404
        assert (await b.call("POST", "/api/v1/agent/serve", request)).status_code == 404
        assert (await a.call("DELETE", f"/api/v1/conversations/{conversation}")).status_code == 200
        assert (await a.call("GET", "/api/v1/conversations")).json()["items"] == []
        assert (
            await a.call("POST", f"/api/v1/conversations/{conversation}/restore")
        ).status_code == 200
        request.update(conversation_id=str(uuid4()), tools={"knowledge": False, "data": False})
        response = await a.call("POST", "/api/v1/agent/serve", request)
        assert "业务查询已关闭" in response.text
        assert "execute_readonly_sql" not in response.text
    finally:
        await a.client.aclose()
        await b.client.aclose()


async def test_revocation_stops_an_inflight_agent_and_persists_partial_state(protected_app, admin):
    import asyncio

    class SlowModel(ScriptedModel):
        def _stream(self, messages, stop=None, run_manager=None, **kwargs):
            for _ in range(30):
                time.sleep(0.1)
                yield ChatGenerationChunk(message=AIMessageChunk(content="正在回答。"))

    guest = Device(protected_app)
    data = await invite(admin)
    assert (await guest.login(data["token"])).status_code == 200

    async def resolve(name):
        return SlowModel(), {"id": "test-model", "profile": {}}

    protected_app.state.model_catalog.resolve = resolve
    task = asyncio.create_task(
        guest.call(
            "POST",
            "/api/v1/agent/serve",
            {
                "conversation_id": str(uuid4()),
                "question": "请继续回答",
                "model_id": "test-model",
                "tools": {"knowledge": False, "data": False},
            },
        )
    )
    try:
        async with asyncio.timeout(8):
            while True:
                items = (await guest.call("GET", "/api/v1/conversations")).json()["items"]
                if items and items[0]["messages"][-1].get("content"):
                    break
                await asyncio.sleep(0.03)
        assert (
            await admin.call("POST", f"/api/v1/admin/invitations/{data['id']}/revoke")
        ).status_code == 200
        response = await asyncio.wait_for(task, timeout=5)
        assert "邀请已撤销" in response.text
        table = protected_app.state.agent_store.runs
        async with asyncio.timeout(5):
            while True:
                async with protected_app.state.db.engine.connect() as conn:
                    statuses = (await conn.execute(select(table.c.status))).scalars().all()
                if statuses == ["error"]:
                    break
                await asyncio.sleep(0.03)
        assert statuses == ["error"]
    finally:
        task.cancel()
        await guest.client.aclose()


async def test_skill_updates_are_versioned_and_never_grant_tools(protected_app, admin):
    response = await admin.call("GET", "/api/v1/admin/skills")
    skill = next(row for row in response.json()["items"] if row["id"] == "sql")
    updated = {
        **skill,
        "body": skill["body"] + "\n测试补充：保持只读。",
        "required_tools": ["arbitrary_shell"],
    }
    assert (await admin.call("PUT", "/api/v1/admin/skills/sql", updated)).status_code == 200
    assert (await admin.call("PUT", "/api/v1/admin/skills/sql", updated)).status_code == 409
    rows = (await admin.call("GET", "/api/v1/admin/skills")).json()["items"]
    current = next(row for row in rows if row["id"] == "sql")
    assert current["revision"] == skill["revision"] + 1
    assert current["required_tools"] == skill["required_tools"]
    from xiaoma.agent.routes import ToolAccess
    from xiaoma.agent.tools import allowed_names

    available = await protected_app.state.agent_store.active_skills(
        allowed_names(ToolAccess(knowledge=True, data=False))
    )
    assert "sql" not in {s["id"] for s in available}


async def test_native_todos_and_tokens_arrive_before_generation_finishes(protected_app):
    import asyncio
    import socket

    import uvicorn

    release = asyncio.Event()

    class PlanningModel(ScriptedModel):
        def next(self, messages):
            calls = sum(
                1
                for m in messages
                if isinstance(m, AIMessage)
                for t in m.tool_calls
                if t["name"] == "write_todos"
            )
            if calls < 2:
                statuses = ["in_progress", "pending"] if not calls else ["completed", "completed"]
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_todos",
                            "id": str(uuid4()),
                            "args": {
                                "todos": [
                                    {"content": title, "status": status}
                                    for title, status in zip(
                                        ["核对需求", "整理结论"], statuses, strict=True
                                    )
                                ]
                            },
                        }
                    ],
                )
            return AIMessage(content="第一段。第二段。")

        async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
            message = self.next(messages)
            if message.tool_calls:
                yield ChatGenerationChunk(
                    message=AIMessageChunk(content="", tool_calls=message.tool_calls)
                )
            else:
                yield ChatGenerationChunk(message=AIMessageChunk(content="第一段。"))
                await release.wait()
                yield ChatGenerationChunk(message=AIMessageChunk(content="第二段。"))

    async def resolve(name):
        return PlanningModel(), {"id": "test-model", "profile": {}}

    protected_app.state.model_catalog.resolve = resolve
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(protected_app, lifespan="off", log_level="error", access_log=False)
    )
    task = asyncio.create_task(server.serve(sockets=[sock]))
    device = Device(protected_app)
    await device.client.aclose()
    device.client = httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=3)
    try:
        async with asyncio.timeout(3):
            while not server.started:
                await asyncio.sleep(0.01)
        assert (await device.login("test-only-password", admin=True)).status_code == 200
        path = "/api/v1/agent/serve"
        body = json.dumps(
            {
                "conversation_id": str(uuid4()),
                "question": "请分两步核对后回答",
                "model_id": "test-model",
                "tools": {"knowledge": False, "data": False},
            }
        ).encode()
        events = []
        async with device.client.stream(
            "POST", path, content=body, headers=device.headers("POST", path, body)
        ) as response:
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store, no-transform"
            assert response.headers["x-accel-buffering"] == "no"
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                events.append(event)
                if event["type"] == "delta" and not release.is_set():
                    assert event["text"] == "第一段。"
                    assert not any(e["type"] == "complete" for e in events)
                    # The provider cannot finish until the client receives part one.
                    release.set()
        todos = [e["todos"] for e in events if e["type"] == "todos"]
        assert [t["status"] for t in todos[0]] == ["in_progress", "pending"]
        assert all(t["status"] == "completed" for t in todos[-1])
        assert [e["text"] for e in events if e["type"] == "delta"] == ["第一段。", "第二段。"]
        assert events[-1]["type"] == "complete"
        stored = (await device.call("GET", "/api/v1/conversations")).json()["items"][0]["messages"][
            -1
        ]
        assert stored["todos"] == todos[-1]
    finally:
        release.set()
        await device.client.aclose()
        server.should_exit = True
        await asyncio.wait_for(task, 3)
        sock.close()


async def test_native_summary_is_private_persists_and_survives_service_restart(
    protected_app, admin
):
    settings = protected_app.state.db.settings
    settings.chat_summary_trigger_tokens = 800
    settings.chat_summary_keep_tokens = 128
    summary_calls = []

    class SummaryModel(ScriptedModel):
        def next(self, messages):
            if len(messages) == 1 and "会话上下文压缩器" in str(messages[0].content):
                summary_calls.append(True)
                return AIMessage(
                    content="INTERNAL_SUMMARY：用户确认预算800元，采用退款政策2.0；缺少验收时间，仍待核实。"
                )
            remembered = any("INTERNAL_SUMMARY" in str(m.content) for m in messages)
            return AIMessage(
                content="预算800元，退款政策2.0；验收时间缺失，不能补算。"
                if remembered
                else "未找到历史摘要"
            )

    async def resolve(name):
        return SummaryModel(), {"id": "test-model", "profile": {}}

    protected_app.state.model_catalog.resolve = resolve
    owner = UUID((await admin.call("GET", "/api/v1/auth/me")).json()["id"])
    conversation = uuid4()
    store = protected_app.state.agent_store
    for i in range(6):
        run, message_id, _, payload = await store.begin(
            owner,
            conversation,
            f"历史{i}：预算800元、政策2.0。" + "业务背景说明。" * 100,
            {"model_id": "test-model", "tools": {}},
        )
        payload.update(
            status="completed", content="已确认，验收时间仍待核实。" + "补充业务说明。" * 50
        )
        await store.save(run, message_id, owner, payload, final=True)
    request = {
        "conversation_id": str(conversation),
        "question": "继续使用之前确认的预算和版本。",
        "model_id": "test-model",
        "tools": {"knowledge": False, "data": False},
    }
    response = await admin.call("POST", "/api/v1/agent/serve", request)
    assert response.status_code == 200, response.text
    assert summary_calls and "预算800元" in response.text
    assert "INTERNAL_SUMMARY" not in response.text
    async with protected_app.state.db.engine.connect() as c:
        context = (
            (
                await c.execute(
                    select(store.contexts).where(store.contexts.c.conversation_id == conversation)
                )
            )
            .mappings()
            .one()
        )
    assert "INTERNAL_SUMMARY" in json.dumps(context["messages"], ensure_ascii=False)
    assert len(context["messages"]) < 14
    items = (await admin.call("GET", "/api/v1/conversations")).json()["items"]
    assert len(items[0]["messages"]) == 14  # Full UI transcript was not compressed/deleted.

    summary_calls.clear()
    restarted = create_app(settings, start_worker=False)
    async with restarted.router.lifespan_context(restarted):
        restarted.state.model_catalog.resolve = resolve
        new_client = Device(restarted)
        try:
            assert (await new_client.login("test-only-password", admin=True)).status_code == 200
            response = await new_client.call("POST", "/api/v1/agent/serve", request)
            assert "预算800元" in response.text and "未找到历史摘要" not in response.text
            assert not summary_calls
        finally:
            await new_client.client.aclose()


@pytest.mark.parametrize("limit", ["chat_model_call_limit", "chat_tool_call_limit"])
async def test_native_run_limits_stop_and_persist_partial_work(protected_app, admin, limit):
    setattr(protected_app.state.db.settings, limit, 2)

    async def resolve(name):
        return ScriptedModel(), {"id": "test-model", "profile": {}}

    protected_app.state.model_catalog.resolve = resolve
    response = await admin.call(
        "POST",
        "/api/v1/agent/serve",
        {
            "conversation_id": str(uuid4()),
            "question": "查询订单总数",
            "model_id": "test-model",
            "tools": {"knowledge": False, "data": True},
        },
    )
    assert "调用上限" in response.text
    last = (await admin.call("GET", "/api/v1/conversations")).json()["items"][0]["messages"][-1]
    assert last["status"] == "error"
    assert not any(t["name"] == "execute_readonly_sql" for t in last["tools"])


@pytest.mark.parametrize("fail", [False, True])
async def test_ai_title_uses_only_first_question_and_failure_preserves_chat(
    protected_app, admin, monkeypatch, fail
):
    calls = []

    async def title(model, question, metadata):
        calls.append(question)
        if fail:
            raise TimeoutError("test-only title timeout")
        return "退款政策与到账时限"

    async def resolve(name):
        return ScriptedModel(), {"id": "test-model", "profile": {}}

    monkeypatch.setattr("xiaoma.agent.service.generate_conversation_title", title)
    protected_app.state.model_catalog.resolve = resolve
    request = {
        "conversation_id": str(uuid4()),
        "question": "请解释退款政策以及银行卡到账时限",
        "model_id": "test-model",
        "tools": {"knowledge": False, "data": False},
    }
    first = await admin.call("POST", "/api/v1/agent/serve", request)
    assert '"type": "complete"' in first.text
    if not fail:
        assert '"type": "conversation"' in first.text
    request["question"] = "第二轮换一个话题"
    assert (await admin.call("POST", "/api/v1/agent/serve", request)).status_code == 200
    assert calls == ["请解释退款政策以及银行卡到账时限"]
    item = (await admin.call("GET", "/api/v1/conversations")).json()["items"][0]
    assert item["title"] == (calls[0] if fail else "退款政策与到账时限")


async def test_recoverable_tool_error_is_streamed_and_does_not_stay_running(protected_app, admin):
    class CorrectingModel(ScriptedModel):
        def next(self, messages):
            if not any(isinstance(m, AIMessage) and m.tool_calls for m in messages):
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "link_schema",
                            "id": str(uuid4()),
                            "args": {
                                "question": "订单总数",
                                "tables": {"orders": ["order_id"]},
                                "joins": [],
                                "grain": "一行一订单",
                            },
                        }
                    ],
                )
            last = next((m for m in reversed(messages) if isinstance(m, ToolMessage)), None)
            if last and last.status == "error":
                return AIMessage(
                    content="", tool_calls=[{"name": "list_tables", "args": {}, "id": str(uuid4())}]
                )
            return super().next(messages)

    async def resolve(name):
        return CorrectingModel(), {"id": "test-model", "profile": {}}

    protected_app.state.model_catalog.resolve = resolve
    response = await admin.call(
        "POST",
        "/api/v1/agent/serve",
        {
            "conversation_id": str(uuid4()),
            "question": "查询订单总数",
            "model_id": "test-model",
            "tools": {"knowledge": False, "data": True},
        },
    )
    assert '"type": "complete"' in response.text and "5000" in response.text
    last = (await admin.call("GET", "/api/v1/conversations")).json()["items"][0]["messages"][-1]
    failed = [t for t in last["tools"] if t["state"] == "output-error"]
    assert failed and failed[0]["name"] == "link_schema"
    assert all(t["state"] != "input-available" for t in last["tools"])
