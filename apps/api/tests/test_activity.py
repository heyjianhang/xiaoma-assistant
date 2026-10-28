import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from test_access_agent import Device, invite
from test_access_agent import admin as admin
from test_access_agent import protected_app as protected_app

from xiaoma.database import utcnow

pytestmark = pytest.mark.integration


def event(kind="page_view", **extra):
    return {"event_id": str(uuid4()), "kind": kind, "path": "/chat", **extra}


async def test_activity_identity_dedup_visit_and_filters(protected_app, admin):
    link = await invite(admin, "技术评审")
    guest = Device(protected_app)
    try:
        assert (await guest.login(link["token"])).status_code == 200
        body = event(path="/project", tab="rag")
        replies = await asyncio.gather(
            *(guest.call("POST", "/api/v1/activity/events", body) for _ in range(3))
        )
        assert all(r.status_code == 200 for r in replies)
        assert len({r.json()["visit_id"] for r in replies}) == 1
        assert (await guest.call("POST", "/api/v1/activity/events", event())).status_code == 200
        row = next(
            r
            for r in (await admin.call("GET", "/api/v1/admin/invitations")).json()["items"]
            if r["id"] == link["id"]
        )
        assert row["visit_count"] == 1 and row["question_count"] == 0
        assert row["first_activated_at"] and row["last_visited_at"]
        assert (await guest.login(link["token"])).status_code == 200
        logins = (
            await admin.call("GET", f"/api/v1/admin/activity?invite_id={link['id']}&kind=login")
        ).json()
        assert logins["total"] == 1
        response = await admin.call(
            "GET", f"/api/v1/admin/activity?invite_id={link['id']}&kind=page_view&limit=1"
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 2 and len(response.json()["items"]) == 1
        assert (await guest.call("GET", "/api/v1/admin/activity")).status_code == 403
        assert (await guest.client.get("/api/v1/activity/events")).status_code == 401
        activity = protected_app.state.activity
        async with activity.db.engine.begin() as c:
            await c.execute(
                activity.visits.update()
                .where(activity.visits.c.user_id == UUID(row["bound_user_id"]))
                .values(last_seen_at=utcnow() - timedelta(minutes=31))
            )
        await guest.call("POST", "/api/v1/activity/events", event(path="/knowledge"))
        row = next(
            r
            for r in (await admin.call("GET", "/api/v1/admin/invitations")).json()["items"]
            if r["id"] == link["id"]
        )
        assert row["visit_count"] == 2
    finally:
        await guest.client.aclose()


async def test_activity_rejects_spoofed_and_secret_targets(protected_app, admin):
    link = await invite(admin)
    guest = Device(protected_app)
    try:
        await guest.login(link["token"])
        for body in [
            event(user_id=str(uuid4())),
            event("answer"),
            event(path="/chat?invite=secret"),
            event(tab="secret"),
            event("test_case_view", target_id="missing"),
            event("document_view", document_id=str(uuid4())),
        ]:
            assert (await guest.call("POST", "/api/v1/activity/events", body)).status_code in (
                404,
                422,
            )
        response = await guest.call(
            "POST", "/api/v1/activity/events", event("test_case_view", target_id="A01")
        )
        assert response.status_code == 200, response.text
        events = (await admin.call("GET", f"/api/v1/admin/activity?invite_id={link['id']}")).json()
        assert all("secret" not in str(e) for e in events["items"])
        assert "token_hash" not in str(events) and "public_key" not in str(events)
        assert (await admin.call("GET", "/api/v1/admin/activity?kind=bad")).status_code == 422
        assert (await admin.call("GET", "/api/v1/admin/activity?limit=101")).status_code == 422
        assert (
            await admin.call(
                "GET", "/api/v1/admin/activity?start=2026-10-29T00:00:00Z&end=2026-10-28T00:00:00Z"
            )
        ).status_code == 422
    finally:
        await guest.client.aclose()


async def test_activity_chat_counts_and_query_ownership(protected_app, admin):
    link = await invite(admin)
    guest = Device(protected_app)
    other = Device(protected_app)
    try:
        await guest.login(link["token"])
        await other.login((await invite(admin, "其他评审"))["token"])
        owner = UUID((await guest.call("GET", "/api/v1/auth/me")).json()["id"])
        store = protected_app.state.agent_store
        prepared = await store.begin(
            owner,
            uuid4(),
            "private-question-do-not-log",
            {"model_id": "test", "tools": {"knowledge": False, "data": True}},
        )
        result_id = "query_" + uuid4().hex
        payload = {
            **prepared[3],
            "status": "completed",
            "tools": [{"name": "execute_readonly_sql"}],
            "presentations": [{"payload": {"result": {"id": result_id}}}],
        }
        await store.save(prepared[0], prepared[1], owner, payload, final=True)
        response = await guest.call(
            "POST", "/api/v1/activity/events", event("sql_view", target_id=result_id)
        )
        assert response.status_code == 200, response.text
        assert (
            await other.call(
                "POST", "/api/v1/activity/events", event("sql_view", target_id=result_id)
            )
        ).status_code == 404
        data = (await admin.call("GET", f"/api/v1/admin/activity?invite_id={link['id']}")).json()
        assert {"question", "answer", "sql_view"}.issubset({e["kind"] for e in data["items"]})
        assert "private-question-do-not-log" not in str(data)
        answer = next(e for e in data["items"] if e["kind"] == "answer")
        assert answer["details"]["tool_names"] == ["execute_readonly_sql"]
        row = next(
            r
            for r in (await admin.call("GET", "/api/v1/admin/invitations")).json()["items"]
            if r["id"] == link["id"]
        )
        assert row["question_count"] == 1
    finally:
        await guest.client.aclose()
        await other.client.aclose()


async def test_activity_document_target_and_device_reset_history(protected_app, admin):
    link = await invite(admin)
    guest = Device(protected_app)
    next_guest = Device(protected_app)
    try:
        await guest.login(link["token"])
        activity = protected_app.state.activity
        doc = uuid4()
        async with activity.db.engine.begin() as c:
            await c.execute(
                activity.db.documents.insert().values(
                    id=doc,
                    filename="退款制度.md",
                    format="md",
                    sha256="a" * 64,
                    byte_size=10,
                    status="ready",
                    chunk_options={},
                )
            )
        assert (
            await guest.call(
                "POST", "/api/v1/activity/events", event("document_view", document_id=str(doc))
            )
        ).status_code == 200
        reset = (
            await admin.call("POST", f"/api/v1/admin/invitations/{link['id']}/reset-device")
        ).json()
        token = reset["url"].split("invite=", 1)[1]
        assert (await next_guest.login(token)).status_code == 200
        assert (await guest.call("GET", "/api/v1/auth/me")).status_code == 401
        row = next(
            r
            for r in (await admin.call("GET", "/api/v1/admin/invitations")).json()["items"]
            if r["id"] == link["id"]
        )
        assert row["visit_count"] == 2
        async with activity.db.engine.connect() as c:
            count = (
                await c.execute(
                    select(func.count())
                    .select_from(activity.events)
                    .where(activity.events.c.kind == "invite_activated")
                )
            ).scalar_one()
        assert count == 2
        data = (
            await admin.call(
                "GET", f"/api/v1/admin/activity?invite_id={link['id']}&kind=document_view"
            )
        ).json()
        assert data["total"] == 1 and "退款制度.md" in data["items"][0]["label"]
    finally:
        await guest.client.aclose()
        await next_guest.client.aclose()


async def test_activity_logging_failure_does_not_block_login(protected_app, monkeypatch):
    async def unavailable(*args, **kwargs):
        raise RuntimeError("telemetry storage unavailable")

    monkeypatch.setattr(protected_app.state.activity, "login", unavailable)
    device = Device(protected_app)
    try:
        assert (await device.login("test-only-password", admin=True)).status_code == 200
        assert (await device.call("GET", "/api/v1/auth/me")).status_code == 200
    finally:
        await device.client.aclose()
