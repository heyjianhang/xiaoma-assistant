import math

import httpx
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

from .errors import IngestionError
from .settings import Settings


def rerank_runnable(settings: Settings) -> RunnableLambda:
    """Rank existing Documents; preserve original text, IDs and source metadata."""

    async def rank(data: dict) -> list[Document]:
        documents = data["documents"]
        if not documents:
            return []
        key = settings.model_api_key.get_secret_value()
        if not key or not settings.rerank_endpoint:
            raise IngestionError("rerank_not_configured", "请配置百炼 URL 与 API Key")
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                settings.rerank_endpoint,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": settings.rerank_model,
                    "input": {
                        "query": data["query"],
                        "documents": [doc.page_content for doc in documents],
                    },
                    "parameters": {"top_n": min(data["top_k"], len(documents))},
                },
            )
            response.raise_for_status()
            body = response.json()
        rows = body.get("output", {}).get("results")
        if body.get("code") or not isinstance(rows, list):
            raise IngestionError("rerank_invalid_response", "重排服务返回格式不兼容")
        seen, result = set(), []
        for row in rows:
            index, score = row.get("index"), row.get("relevance_score")
            if (
                type(index) is not int
                or index < 0
                or index >= len(documents)
                or index in seen
                or not isinstance(score, (float, int))
                or not math.isfinite(score)
                or not 0 <= score <= 1
            ):
                raise IngestionError("rerank_invalid_response", "重排服务返回索引或分数无效")
            seen.add(index)
            doc = documents[index].model_copy(deep=True)
            doc.metadata["rerank_score"] = score
            result.append(doc)
        return sorted(result, key=lambda doc: doc.metadata["rerank_score"], reverse=True)[
            : data["top_k"]
        ]

    return RunnableLambda(rank, name="dashscope_rerank")
