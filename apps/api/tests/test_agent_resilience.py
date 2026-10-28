import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatGenerationChunk
from openai import InternalServerError
from pydantic import PrivateAttr

from xiaoma.agent.models import ModelCatalog
from xiaoma.agent.resilience import (
    StreamSafeModelRetry,
    TransientToolRetry,
    context_budget,
    is_transient,
)
from xiaoma.embeddings import ProviderEmbeddings


class FlakyStream(BaseChatModel):
    mode: str = "recover"
    _calls: list = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self):
        return "retry-stream-probe"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise NotImplementedError

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        self._calls.append(True)
        if self.mode == "invalid":
            raise ValueError("invalid model request")
        if self.mode == "partial":
            yield ChatGenerationChunk(message=AIMessageChunk(content="保留这段"))
            raise ConnectionError("stream disconnected")
        if self.mode == "always" or len(self._calls) == 1:
            raise ConnectionError("temporary outage")
        yield ChatGenerationChunk(message=AIMessageChunk(content="恢复完成"))


@pytest.mark.parametrize(
    "mode,attempts,expected",
    [
        ("recover", 2, "恢复完成"),
        ("always", 3, ""),
        ("invalid", 1, ""),
        ("partial", 1, "保留这段"),
    ],
)
async def test_real_stream_retries_before_output_only(provider_settings, mode, attempts, expected):
    settings = provider_settings.model_copy(update={"chat_retry_initial_delay": 0})
    model, progress, chunks = FlakyStream(mode=mode), [], []
    agent = create_agent(model, middleware=[StreamSafeModelRetry(settings, progress.append)])
    error = None
    try:
        async for event in agent.astream_events({"messages": [("human", "test")]}, version="v2"):
            if event["event"] == "on_chat_model_stream":
                chunks.append(event["data"]["chunk"].content)
    except (ConnectionError, ValueError) as exc:
        error = exc
    assert len(model._calls) == attempts
    assert "".join(chunks) == expected
    assert (error is None) == (mode == "recover")
    assert len(progress) == (attempts - 1 if mode in ("recover", "always") else 0)


@pytest.mark.parametrize(
    "name,transient,attempts",
    [
        ("search_knowledge", True, 3),
        ("execute_readonly_sql", True, 3),
        ("execute_readonly_sql", False, 1),
        ("render_chart", True, 1),
    ],
)
async def test_only_read_tools_retry_transient_failures(
    provider_settings, name, transient, attempts
):
    settings = provider_settings.model_copy(update={"chat_retry_initial_delay": 0})
    progress, calls = [], []
    request = SimpleNamespace(tool_call={"name": name, "id": "probe"}, tool=None)

    async def handler(request):
        calls.append(True)
        if not transient:
            raise ValueError("fix SQL rather than repeating it")
        if len(calls) < 3:
            raise httpx.ConnectError("temporary outage")
        return ToolMessage(content="ok", tool_call_id="probe")

    if attempts == 3:
        result = await TransientToolRetry(settings, progress.append).awrap_tool_call(
            request, handler
        )
        assert result.content == "ok" and len(progress) == 2
    else:
        with pytest.raises((ValueError, httpx.ConnectError)):
            await TransientToolRetry(settings, progress.append).awrap_tool_call(request, handler)
        assert not progress
    assert len(calls) == attempts


@pytest.mark.parametrize(
    "status,retry",
    [(401, False), (403, False), (422, False), (408, True), (429, True), (503, True)],
)
def test_status_classification_never_retries_bad_credentials(status, retry):
    response = httpx.Response(status, request=httpx.Request("POST", "https://example.test"))
    assert (
        is_transient(httpx.HTTPStatusError("safe", request=response.request, response=response))
        == retry
    )


def test_model_settings_and_small_window_budget(provider_settings):
    settings = provider_settings.model_copy(
        update={
            "chat_summary_trigger_tokens": 32000,
            "chat_summary_keep_tokens": 12000,
            "chat_max_output_tokens": 8192,
            "chat_temperature": 0.3,
        }
    )
    assert context_budget(settings, {}) == (32000, 12000)
    assert context_budget(settings, {"max_input_tokens": 16000}) == (12000, 6000)
    model = ModelCatalog(settings).model("test-model", {"max_output_tokens": 2048})
    assert model.max_tokens == 2048 and model.max_retries == 0
    assert model.temperature == 0.3 and model.request_timeout == settings.chat_model_timeout_seconds


async def test_embedding_query_does_not_multiply_tool_retries(provider_settings):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            calls.append(True)
            body = b'{"error":{"message":"temporary outage"}}'
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    worker.start()
    settings = provider_settings.model_copy(
        update={"model_base_url": f"http://127.0.0.1:{server.server_port}/v1"}
    )
    provider = ProviderEmbeddings(settings)
    try:
        with pytest.raises(InternalServerError):
            await provider.aembed_query("test")
        assert len(calls) == 1
        assert provider.client.max_retries == 2
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=1)
