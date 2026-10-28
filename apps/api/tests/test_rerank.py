import json

import httpx
import pytest
import respx
from langchain_core.documents import Document
from pydantic import SecretStr

from xiaoma.errors import IngestionError
from xiaoma.rerank import rerank_runnable


@respx.mock
async def test_rerank_uses_input_indices_and_retains_complete_documents(provider_settings):
    provider_settings.model_base_url = "https://dashscope.test/compatible-mode/v1"
    provider_settings.model_api_key = SecretStr("rerank-test")
    request = respx.post(provider_settings.rerank_endpoint).mock(
        return_value=httpx.Response(
            200,
            json={
                "output": {
                    "results": [
                        {"index": 1, "relevance_score": 0.9},
                        {"index": 0, "relevance_score": 0.2},
                    ]
                }
            },
        )
    )
    documents = [
        Document(id="one", page_content="普通说明", metadata={"source_refs": [{"page_index": 0}]}),
        Document(id="two", page_content="<table>完整表格</table>\n\n注：工作日。"),
    ]
    result = await rerank_runnable(provider_settings).ainvoke(
        {
            "documents": documents,
            "query": "退款多久",
            "top_k": 2,
        }
    )
    assert [item.id for item in result] == ["two", "one"]
    assert result[0].page_content == documents[1].page_content
    assert "rerank_score" not in documents[0].metadata
    assert result[1].metadata["source_refs"] == [{"page_index": 0}]
    payload = json.loads(request.calls.last.request.content)
    assert request.calls.last.request.headers["Authorization"] == "Bearer rerank-test"
    assert payload["input"]["documents"][1] == documents[1].page_content
    request.mock(
        return_value=httpx.Response(
            200,
            json={
                "output": {"results": [{"index": 99, "relevance_score": 0.5}]},
            },
        )
    )
    with pytest.raises(IngestionError, match="索引或分数"):
        await rerank_runnable(provider_settings).ainvoke(
            {
                "documents": documents,
                "query": "退款",
                "top_k": 2,
            }
        )
