import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text

from xiaoma.app import create_app
from xiaoma.settings import Settings


@pytest.fixture(scope="session")
def embedding_server():
    """Local HTTP fixture, not a semantic model. Exercises real OpenAIEmbeddings requests."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert self.path == "/v1/embeddings"
            assert self.headers["Authorization"] == "Bearer integration-only"
            inputs = body["input"]
            inputs = [inputs] if isinstance(inputs, str) else inputs
            rows = []
            for index, value in enumerate(inputs):
                assert isinstance(value, str), "Compatible provider should receive plain text"
                digest = hashlib.sha256(value.encode()).digest()
                vector = [(byte + 1) / 256 for byte in digest[:8]]
                rows.append({"object": "embedding", "index": index, "embedding": vector})
            encoded = json.dumps(
                {
                    "object": "list",
                    "data": rows,
                    "model": "test-hash",
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    server.server_close()
    worker.join(timeout=2)


@pytest.fixture
def provider_settings(tmp_path, embedding_server):
    return Settings().model_copy(
        update={
            "knowledge_schema": "test_" + uuid4().hex,
            "storage_root": tmp_path / "documents",
            "model_base_url": embedding_server,
            "embedding_model": "test-hash",
            "model_api_key": SecretStr("integration-only"),
            "embedding_dimensions": 8,
            "mineru_api_key": SecretStr("mineru-test"),
            "mineru_poll_interval": 0.01,
            "rerank_enabled": False,
        }
    )


@pytest.fixture
async def api(provider_settings):
    app = create_app(provider_settings, start_worker=False, auth_test_mode=True)
    db = None
    try:
        async with app.router.lifespan_context(app):
            db = app.state.db
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app),
                base_url="http://test",
            ) as client:
                yield client, app.state.ingestion, db
    finally:
        if db:
            # Only a fresh randomly named test schema; never the application's knowledge schema.
            assert db.schema.startswith("test_") and len(db.schema) == 37
            async with db.engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{db.schema}" CASCADE'))
            await db.close()
