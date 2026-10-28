import httpx
import respx
from pydantic import SecretStr

from xiaoma.agent.models import ModelCatalog


@respx.mock
async def test_gateway_availability_and_exact_provider_profiles_keep_key_private(provider_settings):
    base = "https://test.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    settings = provider_settings.model_copy(
        update={
            "model_base_url": base,
            "model_api_key": SecretStr("private-model-key"),
            "chat_model_ids": "qwen3.8-flash,missing",
        }
    )
    gateway = respx.get(base + "/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "qwen3.8-flash"}]})
    )
    registry = respx.get("https://models.dev/api.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "alibaba-cn": {
                    "models": {
                        "qwen3.8-flash": {
                            "limit": {"context": 1000000, "output": 131072},
                            "tool_call": True,
                        }
                    }
                },
                "unrelated": {
                    "models": {"qwen3.8-flash": {"limit": {"context": 123}, "tool_call": False}}
                },
            },
        )
    )
    items = await ModelCatalog(settings).list()
    assert [m["id"] for m in items] == ["qwen3.8-flash"]
    assert items[0]["profile"]["max_input_tokens"] == 1000000
    assert items[0]["profile"]["tool_calling"] is True
    assert items[0]["profile_source"] == "models.dev:alibaba-cn"
    assert gateway.calls.last.request.headers["Authorization"] == "Bearer private-model-key"
    assert "Authorization" not in registry.calls.last.request.headers
