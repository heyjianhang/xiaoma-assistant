from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from xiaoma.agent.models import ModelCatalog
from xiaoma.agent.resilience import (
    OutputBudgetMiddleware,
    RepeatedToolFailure,
    ToolFailureLoopGuard,
    context_budget,
    output_limit,
)


def test_percentage_budget_and_provider_output_limit(provider_settings):
    settings = provider_settings.model_copy(
        update={
            "chat_max_output_tokens": 0,
            "chat_summary_trigger_tokens": 0,
            "chat_summary_keep_tokens": 0,
            "chat_context_window_tokens": 0,
        }
    )
    profile = {"max_input_tokens": 1000000, "max_output_tokens": 131072}
    assert context_budget(settings, profile) == (750000, 250000)
    assert output_limit(settings, profile) == 131072
    assert ModelCatalog(settings).model("test", profile).max_tokens == 131072
    assert ModelCatalog(settings).model("unknown").max_tokens is None
    assert context_budget(settings, {}) == (96000, 32000)
    settings.chat_context_window_tokens = 128000
    assert context_budget(settings, profile) == (96000, 32000)
    settings.chat_max_output_tokens = 32768
    assert output_limit(settings, profile) == 32768


async def test_output_budget_counts_system_tools_and_input(provider_settings):
    settings = provider_settings.model_copy(
        update={"chat_max_output_tokens": 0, "chat_context_window_tokens": 0}
    )
    base = dict(
        model=SimpleNamespace(profile={"max_input_tokens": 10000, "max_output_tokens": 9000}),
        messages=[HumanMessage(content="问" * 3000)],
        system_message=SystemMessage(content="系统指令"),
        tools=[],
        model_settings={},
    )
    request = SimpleNamespace(**base)
    request.override = lambda **changes: SimpleNamespace(**{**base, **changes})
    calls = []

    async def handler(value):
        calls.append(value.model_settings["max_tokens"])
        return "ok"

    assert await OutputBudgetMiddleware(settings).awrap_model_call(request, handler) == "ok"
    assert 256 < calls[0] < 9000
    request.messages = [HumanMessage(content="问" * 20000)]
    with pytest.raises(ValueError, match="上下文预算"):
        await OutputBudgetMiddleware(settings).awrap_model_call(request, handler)
    assert len(calls) == 1


async def test_identical_failed_tools_stop_without_spinning():
    guard = ToolFailureLoopGuard(3)
    request = SimpleNamespace(
        tool_call={"name": "execute_readonly_sql", "id": "test", "args": {"sql": "bad"}}
    )

    async def failed(value):
        return ToolMessage(content="SQL错误", tool_call_id="test", status="error")

    await guard.awrap_tool_call(request, failed)
    await guard.awrap_tool_call(request, failed)
    with pytest.raises(RepeatedToolFailure):
        await guard.awrap_tool_call(request, failed)
