import json

import httpx2
from langchain_core.messages import AIMessageChunk

from xiaoma.agent.compatible_model import GatewayChatOpenAI, reasoning_text


def test_gateway_preserves_thinking_without_corrupting_tool_arguments():
    model = GatewayChatOpenAI(model="test", api_key="test-only-key")
    piece = model._convert_chunk_to_generation_chunk(
        {
            "choices": [
                {
                    "delta": {
                        "role": "assistant",
                        "reasoning_content": "核对字段",
                        "content": None,
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call1",
                                "type": "function",
                                "function": {"name": "list_tables", "arguments": "{}"},
                            }
                        ],
                    }
                }
            ]
        },
        AIMessageChunk,
        None,
    )
    assert reasoning_text(piece.message) == "核对字段"
    assert piece.message.content == ""
    assert piece.message.tool_call_chunks[0]["name"] == "list_tables"
    result = model._create_chat_result(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "最终答案",
                        "reasoning_content": "模型返回的说明",
                    },
                    "finish_reason": "stop",
                }
            ],
            "model": "test",
        }
    )
    assert result.generations[0].message.content == "最终答案"
    assert reasoning_text(result.generations[0].message) == "模型返回的说明"


async def test_real_sdk_stream_keeps_thinking_separate_from_answer():
    chunks = [
        {"role": "assistant", "content": "", "reasoning_content": "先核对"},
        {"reasoning_content": "金额"},
        {"content": "正文结论"},
    ]
    wire = "".join(
        "data: "
        + json.dumps(
            {
                "id": "r1",
                "object": "chat.completion.chunk",
                "model": "test",
                "choices": [{"index": 0, "delta": part, "finish_reason": None}],
            },
            ensure_ascii=False,
        )
        + "\n\n"
        for part in chunks
    )
    wire += (
        'data: {"id":"r1","model":"test","choices":'
        '[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    )

    async def respond(request):
        return httpx2.Response(
            200, content=wire.encode(), headers={"content-type": "text/event-stream"}
        )

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(respond), trust_env=False
    ) as client:
        model = GatewayChatOpenAI(
            model="test",
            api_key="test-only-key",
            base_url="https://model.test/v1",
            http_async_client=client,
            max_retries=0,
        )
        received = [chunk async for chunk in model.astream("test")]
    assert "".join(reasoning_text(chunk) for chunk in received) == "先核对金额"
    assert "".join(chunk.content for chunk in received) == "正文结论"
