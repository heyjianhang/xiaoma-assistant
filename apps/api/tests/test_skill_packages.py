import io
import json
import stat
import zipfile
from uuid import uuid4

import httpx
import pytest
from langchain_core.messages import AIMessage, ToolMessage
from test_access_agent import Device, ScriptedModel, invite
from test_access_agent import admin as admin
from test_access_agent import protected_app as protected_app

from xiaoma.agent.skill_packages import MAX_FILE, export_package, read_package


def archive(name="refund-check", rule="48自然小时", extra=None):
    meta = {
        "name": name,
        "description": "核对退款规则时使用",
        "metadata": {
            "xiaoma-display-name": "退款核对",
            "xiaoma-required-tools": "search_knowledge",
        },
    }
    files = {
        f"{name}/SKILL.md": "---\n" + json.dumps(meta, ensure_ascii=False) + "\n---\n\n"
        "SKILL_SELECTED_SENTINEL：请先读取 references/rules.md 再回答。",
        f"{name}/references/rules.md": rule,
        f"{name}/assets/template.md": "## 核对结果\n保留适用范围与缺失字段。",
    }
    files.update(extra or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for path, value in files.items():
            z.writestr(path, value)
    return output.getvalue()


def test_standard_package_roundtrip_preserves_resources():
    package = read_package(archive())
    assert package["id"] == "refund-check"
    assert package["manifest"]["frontmatter"]["metadata"]["xiaoma-display-name"] == "退款核对"
    assert "references/rules.md" in package["files"]
    assert (
        read_package(export_package(package))["manifest"]["sha256"] == package["manifest"]["sha256"]
    )


@pytest.mark.parametrize(
    "path",
    ["../escape", "/absolute", "refund-check/../escape", "C:/escape", "refund-check\\escape"],
)
def test_zip_path_escape_is_rejected(path):
    with pytest.raises(ValueError):
        read_package(archive(extra={path: "no"}))


def test_symlink_duplicate_and_large_resources_are_rejected():
    for mode in ["symlink", "duplicate", "large"]:
        content = io.BytesIO(archive())
        with zipfile.ZipFile(content, "a") as z:
            if mode == "symlink":
                info = zipfile.ZipInfo("refund-check/link")
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(info, "/etc/passwd")
            elif mode == "duplicate":
                z.writestr("refund-check/REFERENCES/rules.md", "duplicate case")
            else:
                z.writestr("refund-check/large.txt", "x" * (MAX_FILE + 1))
        with pytest.raises(ValueError):
            read_package(content.getvalue())


@pytest.mark.parametrize("name", ["Uppercase", "bad--name", "-bad", "x" * 65])
def test_invalid_standard_names_are_rejected(name):
    with pytest.raises(ValueError):
        read_package(archive(name=name))


async def upload(device, content, **data):
    path = "/api/v1/admin/skills/upload"
    request = httpx.Request(
        "POST",
        "http://test" + path,
        data=data,
        files={"file": ("skill.zip", content, "application/zip")},
    )
    body = request.read()
    headers = device.headers("POST", path, body)
    headers["Content-Type"] = request.headers["Content-Type"]
    return await device.client.post(path, content=body, headers=headers)


@pytest.mark.integration
async def test_upload_versioned_resources_explicit_selection_permissions_and_disabled_skill(
    protected_app, admin
):
    installed = await upload(admin, archive())
    assert installed.status_code == 200, installed.text
    assert installed.json() == {"id": "refund-check", "revision": 1}
    assert (await upload(admin, archive())).status_code == 409
    response = await admin.call("GET", "/api/v1/admin/skills/refund-check/package")
    assert response.status_code == 200 and read_package(response.content)["id"] == "refund-check"
    guest = Device(protected_app)
    try:
        assert (await guest.login((await invite(admin))["token"])).status_code == 200
        assert (await upload(guest, archive())).status_code == 403
        assert (
            await guest.call("GET", "/api/v1/admin/skills/refund-check/package")
        ).status_code == 403

        class SkillModel(ScriptedModel):
            def next(self, messages):
                if len(messages) == 1:  # Auxiliary title chain.
                    return AIMessage(content="退款核对")
                assert "SKILL_SELECTED_SENTINEL" in str(messages[0].content)
                last = next((m for m in reversed(messages) if isinstance(m, ToolMessage)), None)
                if last:
                    return AIMessage(content="退款期限：" + json.loads(last.content)["content"])
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_skill_resource",
                            "args": {"skill_name": "refund-check", "path": "references/rules.md"},
                            "id": str(uuid4()),
                        }
                    ],
                )

        async def resolve(name):
            return SkillModel(), {"id": "test-model", "profile": {}}

        protected_app.state.model_catalog.resolve = resolve
        body = {
            "conversation_id": str(uuid4()),
            "question": "核对退款期限",
            "skills": ["refund-check"],
            "tools": {"knowledge": True, "data": False},
        }
        response = await guest.call("POST", "/api/v1/agent/serve", body)
        assert response.status_code == 200 and "48自然小时" in response.text, response.text
        assert '"type": "complete"' in response.text
        closed = {
            **body,
            "conversation_id": str(uuid4()),
            "tools": {"knowledge": False, "data": False},
        }
        assert (await guest.call("POST", "/api/v1/agent/serve", closed)).status_code == 422
        changed = await upload(
            admin, archive(rule="72自然小时"), expected_revision="1", expected_id="refund-check"
        )
        assert changed.status_code == 200 and changed.json()["revision"] == 2
        store = protected_app.state.agent_store
        assert (await store.read_resource("refund-check", 1, "references/rules.md"))[
            "content"
        ] == "48自然小时"
        assert (await store.read_resource("refund-check", 2, "references/rules.md"))[
            "content"
        ] == "72自然小时"
        with pytest.raises(ValueError):
            await store.read_resource("refund-check", 2, "../other")
        assert (await upload(admin, archive(), expected_revision="1")).status_code == 409
        disabled = await admin.call(
            "PATCH", "/api/v1/admin/skills/refund-check/enabled", {"enabled": False, "revision": 2}
        )
        assert disabled.status_code == 200
        assert (
            await guest.call(
                "POST", "/api/v1/agent/serve", {**body, "conversation_id": str(uuid4())}
            )
        ).status_code == 422
    finally:
        await guest.client.aclose()


@pytest.mark.integration
async def test_builtin_delete_is_forbidden_even_after_package_replacement(protected_app, admin):
    response = await admin.call("DELETE", "/api/v1/admin/skills/sql?revision=1")
    assert response.status_code == 403
    replacement = await upload(admin, archive(name="sql"), expected_revision="1", expected_id="sql")
    assert replacement.status_code == 200
    rows = (await admin.call("GET", "/api/v1/admin/skills")).json()["items"]
    sql = next(row for row in rows if row["id"] == "sql")
    assert sql["builtin"] is True and sql["manifest"]["source"] == "uploaded"
    assert (await admin.call("DELETE", "/api/v1/admin/skills/sql?revision=2")).status_code == 403


@pytest.mark.integration
@pytest.mark.parametrize("enabled", [True, False])
async def test_skill_delete_restore_and_revision_checks(protected_app, admin, enabled):
    assert (await upload(admin, archive())).status_code == 200
    revision = 1
    if not enabled:
        toggled = await admin.call(
            "PATCH", "/api/v1/admin/skills/refund-check/enabled", {"revision": 1, "enabled": False}
        )
        revision = toggled.json()["revision"]
    deleted = await admin.call("DELETE", f"/api/v1/admin/skills/refund-check?revision={revision}")
    assert deleted.status_code == 200
    revision = deleted.json()["revision"]
    rows = (await admin.call("GET", "/api/v1/admin/skills")).json()["items"]
    assert "refund-check" not in {row["id"] for row in rows}
    rows = (await admin.call("GET", "/api/v1/admin/skills?include_deleted=true")).json()["items"]
    removed = next(row for row in rows if row["id"] == "refund-check")
    assert removed["deleted_at"] and not removed["builtin"] and not removed["enabled"]
    assert "refund-check" not in {
        row["id"] for row in (await admin.call("GET", "/api/v1/agent/skills")).json()["items"]
    }
    assert (await admin.call("GET", "/api/v1/admin/skills/refund-check/package")).status_code == 404
    assert (await upload(admin, archive(), expected_revision=str(revision))).status_code == 409
    assert (
        await admin.call(
            "PATCH",
            "/api/v1/admin/skills/refund-check/enabled",
            {"revision": revision, "enabled": True},
        )
    ).status_code == 404
    # Existing runs retain their pinned resources; deleting affects future runs.
    assert (
        await protected_app.state.agent_store.read_resource(
            "refund-check", 1, "references/rules.md"
        )
    )["content"] == "48自然小时"
    restored = await admin.call(
        "POST", "/api/v1/admin/skills/refund-check/restore", {"revision": revision}
    )
    assert restored.status_code == 200
    rows = (await admin.call("GET", "/api/v1/admin/skills")).json()["items"]
    current = next(row for row in rows if row["id"] == "refund-check")
    assert current["enabled"] == enabled and current["revision"] == revision + 1
    assert (
        await admin.call("DELETE", f"/api/v1/admin/skills/refund-check?revision={revision}")
    ).status_code == 409


@pytest.mark.integration
async def test_guest_cannot_delete_or_restore_skills(protected_app, admin):
    guest = Device(protected_app)
    try:
        assert (await guest.login((await invite(admin))["token"])).status_code == 200
        assert (
            await guest.call("DELETE", "/api/v1/admin/skills/sql?revision=1")
        ).status_code == 403
        assert (
            await guest.call("POST", "/api/v1/admin/skills/sql/restore", {"revision": 1})
        ).status_code == 403
    finally:
        await guest.client.aclose()
