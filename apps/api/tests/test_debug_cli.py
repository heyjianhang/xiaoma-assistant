import hashlib
import json
from uuid import uuid4

import httpx
import pytest

from xiaoma.access import verify
from xiaoma.debug_cli.__main__ import archive, capture, parser
from xiaoma.debug_cli.client import CliError, DebugClient, origin_url
from xiaoma.debug_cli.report import sse_events


def test_device_login_signature_persistence_and_origin_isolation(tmp_path):
    jwk = None
    nonces = set()

    def handle(request):
        nonlocal jwk
        if request.url.path.endswith("challenge"):
            return httpx.Response(200, json={"challenge": "test-challenge"})
        if request.url.path.endswith("admin-login"):
            body = json.loads(request.content)
            jwk = body["public_key"]
            verify(
                jwk,
                body["signature"],
                "xiaoma-login\ntest-challenge\n" + hashlib.sha256(b"test-password").hexdigest(),
            )
            return httpx.Response(
                200,
                json={"ok": True},
                headers={"set-cookie": "xiaoma_session=test-session; HttpOnly; Path=/"},
            )
        assert request.headers["cookie"] == "xiaoma_session=test-session"
        nonce = request.headers["x-device-nonce"]
        assert nonce not in nonces
        nonces.add(nonce)
        verify(
            jwk,
            request.headers["x-device-proof"],
            "\n".join(
                [
                    request.method,
                    request.url.raw_path.decode(),
                    request.headers["x-device-time"],
                    nonce,
                    hashlib.sha256(request.content).hexdigest(),
                ]
            ),
        )
        return httpx.Response(200, json={"role": "admin"})

    transport = httpx.MockTransport(handle)
    client = DebugClient("http://127.0.0.1:2025", tmp_path, transport=transport)
    try:
        assert client.login("test-password")["role"] == "admin"
        client.request("POST", "/api/v1/check?key=%E4%B8%AD%E6%96%87", {"问题": "测试"})
        assert client.state_file.stat().st_mode & 0o777 == 0o600
        assert "test-password" not in client.state_file.read_text()
    finally:
        client.close()
    restored = DebugClient("http://127.0.0.1:2025/", tmp_path, transport=transport)
    another = DebugClient("http://127.0.0.1:2026", tmp_path, transport=transport)
    try:
        assert restored.request("GET", "/api/v1/auth/me")["role"] == "admin"
        assert restored.state_file != another.state_file
        assert another.http.cookies.get("xiaoma_session") is None
    finally:
        restored.close()
        another.close()


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "file:///tmp/x",
        "https://user:secret@example.com",
        "https://example.com?key=secret",
        "https://example.com/bad",
        "https://example.com:bad",
    ],
)
def test_credentials_are_not_sent_to_invalid_or_cleartext_remote_origins(url):
    with pytest.raises(CliError):
        origin_url(url)


def test_sse_multiline_unicode_comments_and_broken_frame():
    assert list(sse_events([": ping", 'data: {"type": "delta",', 'data: "text": "中文"}', ""])) == [
        {"type": "delta", "text": "中文"}
    ]
    with pytest.raises(CliError, match="连接已断开"):
        list(sse_events(['data: {"type": "complete"}']))


def test_capture_success_saves_real_events_and_runtime(tmp_path, capsys):
    run = str(uuid4())
    events = [
        {"type": "run", "run_id": run, "model_id": "test-model"},
        {"type": "step", "text": "查询数据"},
        {
            "type": "tool",
            "tool": {
                "id": "sql-1",
                "name": "execute_readonly_sql",
                "state": "input-available",
                "input": {"sql": "SELECT 1"},
            },
        },
        {
            "type": "tool",
            "tool": {
                "id": "sql-1",
                "name": "execute_readonly_sql",
                "state": "output-available",
                "output": {"rows": [[1]]},
            },
        },
        {"type": "delta", "text": "结果为 1"},
        {"type": "complete"},
    ]

    def handle(request):
        if request.method == "GET":
            return httpx.Response(
                200, json={"run": {"status": "completed", "snapshot": {"selected_skills": ["sql"]}}}
            )
        body = json.loads(request.content)
        assert body["skills"] == ["sql"] and not body["tools"]["knowledge"]
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text="".join("data: " + json.dumps(e) + "\n\n" for e in events),
        )

    client = DebugClient(
        "http://localhost:2025", tmp_path / "identity", transport=httpx.MockTransport(handle)
    )
    args = parser().parse_args(
        [
            "--json",
            "--artifacts-dir",
            str(tmp_path / "runs"),
            "chat",
            "测试",
            "--skill",
            "sql",
            "--no-knowledge",
        ]
    )
    try:
        assert capture(client, args) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["status"] == "completed" and result["answer"] == "结果为 1"
        assert result["runtime_saved"] is True and len(result["tools"]) == 1
        paths = list((tmp_path / "runs").iterdir())
        assert len(paths) == 1
        assert (paths[0] / "answer.md").read_text() == "结果为 1"
        assert len((paths[0] / "events.jsonl").read_text().splitlines()) == len(events)
        assert (paths[0] / "result.json").stat().st_mode & 0o777 == 0o600
    finally:
        client.close()


@pytest.mark.parametrize("tail", [[], [{"type": "error", "message": "工具失败"}]])
def test_missing_complete_or_server_error_preserves_partial_answer(tmp_path, capsys, tail):
    events = [{"type": "delta", "text": "部分回答"}] + tail
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text="".join("data: " + json.dumps(e) + "\n\n" for e in events),
        )
    )
    client = DebugClient("http://localhost:2025", tmp_path / "identity", transport=transport)
    args = parser().parse_args(
        ["--json", "--artifacts-dir", str(tmp_path / "runs"), "chat", "测试"]
    )
    try:
        assert capture(client, args) == 1
        result = json.loads(capsys.readouterr().out)
        assert result["answer"] == "部分回答" and result["status"] == "error"
    finally:
        client.close()


def test_archive_exports_before_mutation_skips_running_and_is_recoverable(tmp_path):
    deleted = set()
    items = [
        {"id": "done", "title": "测试", "messages": [{"content": "保留", "status": "completed"}]},
        {"id": "running", "messages": [{"status": "running"}]},
    ]

    def handle(request):
        if request.method == "GET":
            return httpx.Response(
                200, json={"items": [item for item in items if item["id"] not in deleted]}
            )
        manifests = list((tmp_path / "runs").glob("archive-*.json"))
        assert (
            manifests
            and json.loads(manifests[0].read_text())["conversations"][0]["messages"][0]["content"]
            == "保留"
        )
        assert request.method == "DELETE" and request.url.path.endswith("done")
        deleted.add("done")
        return httpx.Response(200, json={"ok": True})

    client = DebugClient(
        "http://localhost:2025", tmp_path / "identity", transport=httpx.MockTransport(handle)
    )
    try:
        with pytest.raises(CliError, match="--yes"):
            archive(client, tmp_path / "runs", yes=False)
        result = archive(client, tmp_path / "runs", yes=True)
        assert result["archived"] == 1 and result["skipped"][0]["id"] == "running"
    finally:
        client.close()
