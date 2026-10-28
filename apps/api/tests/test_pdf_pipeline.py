import httpx
import pytest
import respx
from test_mineru import archive_bytes

pytestmark = pytest.mark.integration


@respx.mock
async def test_pdf_contract_to_real_pgvector(api):
    client, service, db = api
    base = db.settings.mineru_base_url
    respx.post(f"{base}/api/v4/file-urls/batch").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"batch_id": "batch", "file_urls": ["https://signed.test/upload"]},
            },
        )
    )
    respx.put("https://signed.test/upload").mock(return_value=httpx.Response(200))
    respx.get(f"{base}/api/v4/extract-results/batch/batch").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "extract_result": [
                        {
                            "state": "done",
                            "full_zip_url": "https://signed.test/result.zip",
                        }
                    ]
                },
            },
        )
    )
    respx.get("https://signed.test/result.zip").mock(
        return_value=httpx.Response(
            200,
            content=archive_bytes(
                [
                    {"type": "text", "text": "退款", "text_level": 1, "page_idx": 0},
                    {
                        "type": "table",
                        "table_body": "<table><tr><td>银行卡</td><td>3日</td></tr></table>",
                        "table_footnote": ["注：工作日"],
                        "page_idx": 0,
                    },
                ]
            ),
        )
    )
    # Let the real HTTP OpenAIEmbeddings request reach the local test server.
    respx.post(db.settings.model_base_url + "/embeddings").pass_through()
    created = (
        await client.post(
            "/api/v1/documents",
            files={
                "file": ("政策.pdf", b"%PDF-test-contract"),
            },
        )
    ).json()
    await service.run_once()
    job = (await client.get(f"/api/v1/jobs/{created['job_id']}")).json()
    assert job["status"] == "done", (
        job,
        [
            (str(call.request.url), call.response.status_code, call.response.text[:100])
            for call in respx.calls
        ],
    )
    chunks = (await client.get(f"/api/v1/documents/{created['document_id']}/chunks")).json()
    assert "<table>" in chunks["items"][0]["content"]
    assert "工作日" in chunks["items"][0]["content"]
    assert chunks["items"][0]["metadata"]["source_refs"][0]["page_index"] == 0
