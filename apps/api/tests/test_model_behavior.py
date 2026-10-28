import json

import httpx2
import pytest
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from xiaoma.agent.model_behavior import is_greeting, plain_response_settings
from xiaoma.agent.models import ModelCatalog
from xiaoma.agent.resilience import GreetingLatencyMiddleware


@pytest.mark.parametrize(
    "question, greeting",
    [
        ("你好！", True),
        ("Hello", True),
        ("谢谢", True),
        ("你好，请查询退款记录", False),
        ("继续刚才的任务", False),
    ],
)
def test_only_exact_greetings_use_the_fast_path(question, greeting):
    assert is_greeting(question) is greeting


@pytest.mark.parametrize("question, fast", [("你好", True), ("核对退款制度与订单", False)])
async def test_greeting_middleware_sends_verified_provider_switch_only(
    provider_settings, question, fast
):
    base = "https://test.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    settings = provider_settings.model_copy(update={"model_base_url": base})
    bodies = []

    async def respond(request):
        bodies.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "completion",
                "object": "chat.completion",
                "model": "qwen3.8-flash",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "你好"},
                    }
                ],
            },
        )

    # The installed OpenAI SDK uses HTTPX2; inject its actual transport rather
    # than allowing a mismatched HTTPX mock to make an external network call.
    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(respond), trust_env=False
    ) as client:
        model = ChatOpenAI(
            model="qwen3.8-flash",
            base_url=base,
            api_key="test-only-key",
            http_async_client=client,
            max_retries=0,
        )
        agent = create_agent(model, middleware=[GreetingLatencyMiddleware(question)])
        await agent.ainvoke({"messages": [("human", question)]})
    assert len(bodies) == 1
    assert bodies[0].get("enable_thinking") is (False if fast else None)
    assert "thinking_budget" not in bodies[0]
    assert plain_response_settings(ModelCatalog(settings).model("glm-5.3")) == {}
