import asyncio
import json
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select, text

from xiaoma.database import utcnow
from xiaoma.errors import IngestionError

pytestmark = pytest.mark.integration
CONTENT = (
    "# 退款时效\n\n"
    + "银行卡退款处理期限为三个工作日。" * 12
    + "\n\n## 注释\n\n"
    + "从验收完成时起算。" * 20
)
CONTENT_BYTES = CONTENT.encode()
OPTIONS = json.dumps({"target_chars": 100, "max_chars": 200, "min_chars": 0})


async def upload(client, filename="政策.md", content=CONTENT_BYTES):
    response = await client.post(
        "/api/v1/documents", files={"file": (filename, content)}, data={"chunk_options": OPTIONS}
    )
    assert response.status_code == 202, response.text
    return response.json()


async def test_document_lifecycle_and_retrieval_filter(api):
    client, service, db = api
    created = await upload(client)
    doc_id, job_id = created["document_id"], created["job_id"]
    assert await service.run_once()
    job = (await client.get(f"/api/v1/jobs/{job_id}")).json()
    assert job["status"] == "done", job
    chunks = (await client.get(f"/api/v1/documents/{doc_id}/chunks")).json()
    assert chunks["revision"] == 1 and chunks["total"] >= 2
    assert "银行卡退款" in chunks["items"][0]["content"]
    assert (await client.get(f"/api/v1/documents/{doc_id}/source")).content == CONTENT.encode()
    search = (
        await client.post(
            "/api/v1/retrieval/search",
            json={
                "query": "退款",
                "document_id": doc_id,
            },
        )
    ).json()
    assert len(search["documents"]) == chunks["total"]
    assert search["documents"][0]["type"] == "Document"
    # Same topology as Agent Server: graph worker loop -> app-owned async resources.
    cross_loop = await asyncio.to_thread(lambda: asyncio.run(db.search("退款", 5)))
    assert len(cross_loop) == chunks["total"]
    chunk_id = chunks["items"][0]["id"]
    response = await client.patch(
        f"/api/v1/documents/{doc_id}/chunks/{chunk_id}", json={"enabled": False}
    )
    assert response.status_code == 200
    remaining = (await client.post("/api/v1/retrieval/search", json={"query": "退款"})).json()
    assert chunk_id not in [item["id"] for item in remaining["documents"]]
    await client.post(f"/api/v1/documents/{doc_id}/reprocess")
    assert await service.run_once()
    result = (await client.get(f"/api/v1/documents/{doc_id}/chunks")).json()
    assert result["revision"] == 2 and result["total"] == chunks["total"]
    async with db.engine.connect() as conn:
        count = (
            await conn.execute(text(f"SELECT count(*) FROM {db.vector_table} WHERE active"))
        ).scalar()
    assert count == result["total"]
    assert (await client.delete(f"/api/v1/documents/{doc_id}")).status_code == 200
    assert (await client.get(f"/api/v1/documents/{doc_id}")).status_code == 404
    assert (await client.post("/api/v1/retrieval/search", json={"query": "退款"})).json()[
        "documents"
    ] == []


async def test_partial_vector_failure_preserves_old_index_and_retry(api, monkeypatch):
    client, service, db = api
    created = await upload(client)
    doc_id = created["document_id"]
    await service.run_once()
    original = (await client.post("/api/v1/retrieval/search", json={"query": "退款"})).json()
    original_ids = {item["id"] for item in original["documents"]}
    write = db.store.aadd_documents

    async def fail_after_first(documents, **kwargs):
        await write(documents[:1])
        raise RuntimeError("injected failure after a committed vector row")

    monkeypatch.setattr(db.store, "aadd_documents", fail_after_first)
    reprocess = (await client.post(f"/api/v1/documents/{doc_id}/reprocess")).json()
    await service.run_once()
    failed = (await client.get(f"/api/v1/jobs/{reprocess['job_id']}")).json()
    assert failed["status"] == "failed"
    visible = (await client.post("/api/v1/retrieval/search", json={"query": "退款"})).json()
    assert {item["id"] for item in visible["documents"]} == original_ids
    monkeypatch.setattr(db.store, "aadd_documents", write)
    await client.post(f"/api/v1/documents/{doc_id}/reprocess")
    await service.run_once()
    latest = (await client.get(f"/api/v1/documents/{doc_id}")).json()
    assert latest["status"] == "ready" and latest["active_revision"] == 3
    visible = (await client.post("/api/v1/retrieval/search", json={"query": "退款"})).json()
    assert len(visible["documents"]) == len(original_ids)
    assert all(item["metadata"]["revision"] == 3 for item in visible["documents"])


async def test_expired_lease_and_cancelled_attempt_are_fenced(api):
    client, service, db = api
    created = await upload(client)
    stale = await service.claim()
    async with db.engine.begin() as conn:
        await conn.execute(
            db.jobs.update()
            .where(db.jobs.c.id == stale["id"])
            .values(
                lease_until=utcnow() - timedelta(seconds=1),
            )
        )
    async with db.engine.begin() as conn:
        await db.queue.renew(conn, "ingestion", stale["queue_message_id"], 0)
    current = await service.claim()
    assert current["index_id"] != stale["index_id"]
    with pytest.raises(IngestionError, match="取消或接管"):
        await service.process(stale)
    await service.process(current)
    doc = (await client.get(f"/api/v1/documents/{created['document_id']}")).json()
    assert doc["status"] == "ready" and doc["active_index_id"] == str(current["index_id"])
    queued = await upload(client)
    cancelled = await service.claim()
    await client.delete(f"/api/v1/documents/{queued['document_id']}")
    with pytest.raises(IngestionError):
        await service.process(cancelled)
    job = (await client.get(f"/api/v1/jobs/{queued['job_id']}")).json()
    assert job["status"] == "cancelled"


async def test_invalid_upload_and_missing_mineru_key(api):
    client, service, db = api
    for filename, content in [("bad.pdf", b"not pdf"), ("empty.md", b""), ("bad.exe", b"x")]:
        response = await client.post("/api/v1/documents", files={"file": (filename, content)})
        assert response.status_code == 400
    from pydantic import SecretStr

    db.settings.mineru_api_key = SecretStr("")
    created = await upload(client, "test.pdf", b"%PDF-test")
    await service.run_once()
    job = (await client.get(f"/api/v1/jobs/{created['job_id']}")).json()
    assert job["status"] == "failed" and job["error_code"] == "mineru_not_configured"
    async with db.engine.connect() as conn:
        assert (
            await conn.execute(
                select(func.count())
                .select_from(db.chunks)
                .where(
                    db.chunks.c.document_id == UUID(created["document_id"]),
                )
            )
        ).scalar() == 0
