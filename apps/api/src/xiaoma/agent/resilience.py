"""Bounded LangChain retries, with a guard against repeating partial streamed output."""

import json
import math

import httpx
from langchain.agents.middleware import AgentMiddleware, ModelRetryMiddleware, ToolRetryMiddleware
from langchain_core.callbacks import AsyncCallbackHandler, AsyncCallbackManager
from langchain_core.exceptions import ModelError
from langchain_core.messages import ToolMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.utils.function_calling import convert_to_openai_tool
from openai import APIConnectionError, APIStatusError
from sqlalchemy.exc import DBAPIError

READ_TOOLS = ["search_knowledge", "list_tables", "get_table_schema", "execute_readonly_sql"]


class RepeatedToolFailure(Exception):
    pass


class ContextBudgetExceeded(ValueError):
    pass


class ToolFailureLoopGuard(AgentMiddleware):
    def __init__(self, limit):
        self.limit, self.failures = limit, {}

    async def awrap_tool_call(self, request, handler):
        signature = (
            request.tool_call["name"],
            json.dumps(request.tool_call.get("args", {}), sort_keys=True, default=str),
        )
        result = await handler(request)
        if isinstance(result, ToolMessage) and result.status == "error":
            self.failures[signature] = self.failures.get(signature, 0) + 1
            if self.failures[signature] >= self.limit:
                raise RepeatedToolFailure(
                    "同一工具参数多次失败，已停止重复尝试；已有结果保留，请调整查询条件后继续"
                )
        else:
            self.failures.pop(signature, None)
        return result


def is_transient(exc):
    if isinstance(exc, ModelError):
        return exc.is_retryable
    if isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
            APIConnectionError,
            ConnectionError,
            TimeoutError,
        ),
    ):
        return True
    if isinstance(exc, (httpx.HTTPStatusError, APIStatusError)):
        status = exc.response.status_code
        return status in (408, 429) or 500 <= status <= 599
    if isinstance(exc, DBAPIError):
        code = getattr(exc.orig, "sqlstate", "") or ""
        return (
            exc.connection_invalidated
            or code.startswith("08")
            or code in ("40001", "40P01", "53300", "57P01", "57P02", "57P03")
        )
    return False


def context_budget(settings, profile):
    window = context_window(settings, profile)
    trigger = min(
        settings.chat_summary_trigger_tokens
        or int(window * settings.chat_summary_trigger_fraction),
        int(window * settings.chat_summary_trigger_fraction),
    )
    keep = settings.chat_summary_keep_tokens or int(window * settings.chat_summary_keep_fraction)
    return trigger, min(keep, max(1, trigger // 2))


def context_window(settings, profile):
    declared = profile.get("max_input_tokens") or settings.chat_context_fallback_tokens
    return (
        min(declared, settings.chat_context_window_tokens)
        if settings.chat_context_window_tokens
        else declared
    )


def output_limit(settings, profile):
    declared = profile.get("max_output_tokens")
    cap = settings.chat_max_output_tokens
    return min(cap, declared) if cap and declared else cap or declared


class OutputBudgetMiddleware(AgentMiddleware):
    """Reserve actual request space while allowing the declared model output limit."""

    def __init__(self, settings):
        self.settings = settings

    async def awrap_model_call(self, request, handler):
        profile = request.model.profile or {}
        window = context_window(self.settings, profile)
        messages = list(request.messages)
        if request.system_message:
            messages.insert(0, request.system_message)
        used = count_tokens_approximately(messages, chars_per_token=1.5)
        schemas = [convert_to_openai_tool(tool) for tool in request.tools]
        used += math.ceil(len(json.dumps(schemas, ensure_ascii=False)) / 1.5)
        available = window - used - max(2048, int(window * 0.02))
        if available < 256:
            raise ContextBudgetExceeded("本次输入超过模型上下文预算，请拆分问题或选择更大窗口模型")
        limit = output_limit(self.settings, profile)
        if limit:
            request = request.override(
                model_settings={**request.model_settings, "max_tokens": min(limit, available)}
            )
        return await handler(request)


class StreamGuard(AsyncCallbackHandler):
    def __init__(self):
        self.emitted = False

    async def on_llm_new_token(self, token, *, chunk=None, **kwargs):
        message = getattr(chunk, "message", None)
        if token or (message and (message.content or message.tool_call_chunks)):
            self.emitted = True


class StreamSafeModelRetry(AgentMiddleware):
    def __init__(self, settings, emit):
        self.settings, self.emit = settings, emit

    async def awrap_model_call(self, request, handler):
        guard = StreamGuard()
        callbacks = AsyncCallbackManager.configure(
            inheritable_callbacks=request.model.callbacks, local_callbacks=[guard]
        )
        request = request.override(model=request.model.model_copy(update={"callbacks": callbacks}))
        failures = 0

        def retry_on(exc):
            nonlocal failures
            failures += 1
            retryable = not guard.emitted and is_transient(exc)
            if retryable and failures <= self.settings.chat_model_max_retries:
                self.emit(
                    {
                        "type": "step",
                        "text": "模型服务打了个盹，正在重试"
                        f"（{failures}/{self.settings.chat_model_max_retries}）",
                    }
                )
            return retryable

        retry = ModelRetryMiddleware(
            max_retries=self.settings.chat_model_max_retries,
            retry_on=retry_on,
            on_failure="error",
            initial_delay=self.settings.chat_retry_initial_delay,
            max_delay=4,
            backoff_factor=2,
            jitter=True,
        )
        return await retry.awrap_model_call(request, handler)


class TransientToolRetry(AgentMiddleware):
    def __init__(self, settings, emit):
        self.settings, self.emit = settings, emit

    async def awrap_tool_call(self, request, handler):
        failures = 0

        def retry_on(exc):
            nonlocal failures
            failures += 1
            retryable = is_transient(exc)
            if retryable and failures <= self.settings.chat_tool_max_retries:
                self.emit(
                    {
                        "type": "step",
                        "text": "查询连接有点忙，再试一次"
                        f"（{failures}/{self.settings.chat_tool_max_retries}）",
                    }
                )
            return retryable

        retry = ToolRetryMiddleware(
            max_retries=self.settings.chat_tool_max_retries,
            tools=READ_TOOLS,
            retry_on=retry_on,
            on_failure="error",
            initial_delay=self.settings.chat_retry_initial_delay,
            max_delay=4,
            backoff_factor=2,
            jitter=True,
        )
        return await retry.awrap_tool_call(request, handler)
