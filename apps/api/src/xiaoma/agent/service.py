"""LangChain create_agent execution, real event streaming, and durable run records."""

import asyncio
import contextlib
import hashlib
import json
import logging
import time

from fastapi import HTTPException
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from ..errors import IngestionError
from .builder import build_agent, build_system_prompt
from .resilience import (
    ContextBudgetExceeded,
    RepeatedToolFailure,
    context_budget,
    context_window,
    output_limit,
)
from .title import generate_conversation_title
from .tools import allowed_names

TOOL_TITLES = {
    "load_skill": "加载专业技能",
    "read_skill_resource": "读取技能资源",
    "search_knowledge": "检索知识库",
    "list_tables": "查看业务表目录",
    "get_table_schema": "查看候选表字段",
    "link_schema": "选表与字段链接",
    "execute_readonly_sql": "执行只读 SQL",
    "render_chart": "生成结果视图",
    "present_evidence_review": "核对文档与数据",
    "ask_clarification": "澄清问题",
    "write_todos": "更新任务清单",
}

TOOL_PROGRESS = {
    "load_skill": "先看看这类问题的处理方法",
    "read_skill_resource": "看看技能里附带的参考资料",
    "search_knowledge": "翻翻知识库，找找原文依据",
    "list_tables": "看看业务数据都放在哪些表里",
    "get_table_schema": "找到了候选表，再核对一下字段",
    "link_schema": "把问题和表字段对上号",
    "execute_readonly_sql": "去查一下真实数据，马上回来",
    "render_chart": "把查到的数据画成图",
    "present_evidence_review": "对照文档和数据，看看差异在哪里",
    "ask_clarification": "有个口径还要和你确认一下",
}


class AgentService:
    def __init__(self, db, business, auth, store, models):
        self.db = db
        self.business = business
        self.auth = auth
        self.store = store
        self.models = models

    async def prepare(self, principal, body):
        await self.auth.assert_active(principal)
        await self.auth.rate_limit(str(principal.user_id), "agent-run", 20)
        model, description = await self.models.resolve(body.model_id)
        names = allowed_names(body.tools)
        skills = await self.store.active_skills(names)
        import re

        slash = re.match(r"^/([a-z0-9]+(?:-[a-z0-9]+)*)(?:\s|$)", body.question)
        requested = list(dict.fromkeys(body.skills + ([slash[1]] if slash else [])))
        if len(requested) > 5 or not set(requested).issubset({s["id"] for s in skills}):
            raise HTTPException(422, "所选 Skill 已停用、不存在或依赖的查询工具已关闭")
        body.skills = requested
        trigger, keep = context_budget(self.db.settings, description["profile"])
        system_prompt = build_system_prompt(skills, requested)
        snapshot = {
            "system_prompt": system_prompt,
            "system_prompt_sha256": hashlib.sha256(system_prompt.encode()).hexdigest(),
            "model_id": description["id"],
            "model_profile": description["profile"],
            "selected_skills": requested,
            "tools": body.tools.model_dump(),
            "skills": [
                {
                    "id": s["id"],
                    "revision": s["revision"],
                    "body": s["body"],
                    "sha256": (s.get("manifest") or {}).get("sha256"),
                }
                for s in skills
            ],
            "context_policy": {
                "trigger_tokens": trigger,
                "keep_tokens": keep,
                "model_call_limit": self.db.settings.chat_model_call_limit,
                "tool_call_limit": self.db.settings.chat_tool_call_limit,
                "window_tokens": context_window(self.db.settings, description["profile"]),
                "trigger_fraction": self.db.settings.chat_summary_trigger_fraction,
                "keep_fraction": self.db.settings.chat_summary_keep_fraction,
            },
            "runtime_policy": {
                "graph_steps": self.db.settings.chat_max_steps,
                "run_timeout_seconds": self.db.settings.chat_timeout_seconds,
                "model_timeout_seconds": self.db.settings.chat_model_timeout_seconds,
                "max_output_tokens": output_limit(self.db.settings, description["profile"]),
                "temperature": self.db.settings.chat_temperature,
                "model_retries": self.db.settings.chat_model_max_retries,
                "tool_retries": self.db.settings.chat_tool_max_retries,
                "sdk_retries": 0,
                "repeated_tool_failure_limit": self.db.settings.chat_repeated_tool_failure_limit,
            },
        }
        run_id, message_id, history, payload = await self.store.begin(
            principal.user_id, body.conversation_id, body.question, snapshot
        )
        return model, skills, run_id, message_id, history, payload

    async def stream(self, principal, body, prepared, request):
        model, skills, run_id, message_id, history, payload = prepared
        queue = asyncio.Queue(maxsize=512)

        def emit(value):
            queue.put_nowait(value)

        agent = build_agent(
            model=model,
            db=self.db,
            business=self.business,
            auth=self.auth,
            store=self.store,
            body=body,
            principal=principal,
            skills=skills,
            emit=emit,
        )
        records = {}
        final_context = {}
        speaking = set()
        last_check = 0
        last_save = 0

        async def name_conversation():
            try:
                title = await generate_conversation_title(
                    model,
                    body.question,
                    {
                        "owner_id": str(principal.user_id),
                        "conversation_id": str(body.conversation_id),
                        "app_run_id": str(run_id),
                    },
                )
                await self.auth.assert_active(principal)
                await self.store.update_title(principal.user_id, body.conversation_id, title)
                await queue.put(
                    {
                        "type": "conversation",
                        "conversation_id": str(body.conversation_id),
                        "title": title,
                    }
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                # The initial question remains the fallback title. Naming must
                # not fail an otherwise valid answer or leak provider errors.
                pass

        async def produce():
            title_task = asyncio.create_task(name_conversation()) if not history else None
            try:
                async with asyncio.timeout(self.db.settings.chat_timeout_seconds):
                    async for event in agent.astream_events(
                        {"messages": history + [{"role": "user", "content": body.question}]},
                        config={
                            "recursion_limit": self.db.settings.chat_max_steps,
                            "run_name": "xiaoma-chat",
                            "metadata": {
                                "owner_id": str(principal.user_id),
                                "conversation_id": str(body.conversation_id),
                                "app_run_id": str(run_id),
                            },
                        },
                        version="v2",
                    ):
                        kind = event["event"]
                        name = event.get("name", "")
                        id = str(event["run_id"])
                        data = event.get("data", {})
                        summarizing = event.get("metadata", {}).get("lc_source") == "summarization"
                        if summarizing:
                            if kind == "on_chat_model_start":
                                await queue.put(
                                    {"type": "step", "text": "把前面的重点收进小本本，马上继续"}
                                )
                            elif kind == "on_chat_model_end":
                                await queue.put(
                                    {"type": "step", "text": "重点记好了，带着近期消息继续"}
                                )
                            # Internal summary tokens must never become the answer.
                            continue
                        if kind == "on_chain_end" and not event.get("parent_ids"):
                            output = data.get("output")
                            if isinstance(output, dict) and "messages" in output:
                                final_context["messages"] = output["messages"]
                        elif kind == "on_chat_model_start":
                            if any(r["name"] != "write_todos" for r in records.values()):
                                await queue.put({"type": "step", "text": "正在核对结果，继续处理"})
                        elif kind == "on_chat_model_end":
                            response = data.get("output")
                            if (
                                getattr(response, "response_metadata", {}).get("finish_reason")
                                == "length"
                            ):
                                raise IngestionError(
                                    "answer_truncated",
                                    "回答达到本次输出上限，已有内容已保留，可以继续追问",
                                )
                        elif kind == "on_chat_model_stream":
                            chunk = data["chunk"]
                            content = chunk.content
                            text = (
                                content
                                if isinstance(content, str)
                                else "".join(
                                    p.get("text", "")
                                    for p in content
                                    if isinstance(p, dict) and p.get("type") == "text"
                                )
                            )
                            if text:
                                if id not in speaking:
                                    speaking.add(id)
                                    await queue.put(
                                        {"type": "step", "text": "线索收到了，正在组织回答"}
                                    )
                                await queue.put({"type": "delta", "text": text})
                        elif kind == "on_tool_start":
                            if name != "write_todos":
                                await queue.put(
                                    {
                                        "type": "step",
                                        "text": TOOL_PROGRESS.get(name, "正在核对这一步的结果"),
                                    }
                                )
                            record = {
                                "id": id,
                                "name": name,
                                "title": TOOL_TITLES.get(name, name),
                                "state": "input-available",
                                "input": data.get("input", {}),
                            }
                            records[id] = record
                            await queue.put({"type": "tool", "tool": dict(record)})
                        elif kind == "on_tool_error" and id in records:
                            error = data.get("error")
                            message = (
                                error.message
                                if isinstance(error, IngestionError)
                                else str(error)
                                if isinstance(error, ValueError)
                                else str(error.detail)
                                if isinstance(error, HTTPException)
                                else "工具执行失败"
                            )
                            record = {
                                **records[id],
                                "state": "output-error",
                                "errorText": message,
                                "output": {"error": message},
                            }
                            records[id] = record
                            await queue.put({"type": "tool", "tool": record})
                        elif kind == "on_tool_end" and id in records:
                            output = data.get("output")
                            failed = False
                            if isinstance(output, Command):
                                todos = (
                                    output.update.get("todos", [])
                                    if isinstance(output.update, dict)
                                    else []
                                )
                                if isinstance(output.update, dict) and "todos" in output.update:
                                    await queue.put(
                                        {
                                            "type": "todos",
                                            "todos": [
                                                {
                                                    "id": str(i),
                                                    "title": t["content"],
                                                    "status": t["status"],
                                                }
                                                for i, t in enumerate(todos)
                                            ],
                                        }
                                    )
                                output = {"todos": todos}
                            elif isinstance(output, ToolMessage):
                                failed = output.status == "error"
                                output = output.content
                                if isinstance(output, str):
                                    try:
                                        output = json.loads(output)
                                    except (ValueError, TypeError):
                                        pass
                            record = {
                                **records[id],
                                "state": "output-error" if failed else "output-available",
                                "output": output,
                            }
                            if failed:
                                record["errorText"] = (
                                    str(output.get("error", "工具失败"))
                                    if isinstance(output, dict)
                                    else str(output)
                                )
                            records[id] = record
                            await queue.put({"type": "tool", "tool": record})
                    if title_task:
                        await title_task
                await queue.put({"type": "complete"})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logging.getLogger(__name__).warning("Agent run failed: %s", type(exc).__name__)
                if isinstance(exc, HTTPException):
                    message = str(exc.detail)
                elif isinstance(exc, IngestionError):
                    message = exc.message
                elif isinstance(exc, (RepeatedToolFailure, ContextBudgetExceeded)):
                    message = str(exc)
                elif isinstance(exc, TimeoutError):
                    message = "本次运行超时，请缩小问题范围后重试"
                elif isinstance(exc, (ModelCallLimitExceededError, ToolCallLimitExceededError)):
                    message = "已达到本轮模型或工具调用上限，保留已有结果，请缩小问题后继续"
                else:
                    message = "模型或工具调用失败，请检查模型服务或调整问题后重试"
                for record in records.values():
                    if record["state"] == "input-available":
                        record.update(state="output-error", errorText=message)
                        await queue.put({"type": "tool", "tool": dict(record)})
                await queue.put({"type": "error", "message": message})
            finally:
                if title_task:
                    title_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await title_task

        producer = asyncio.create_task(produce())

        def encode(event):
            return "data: " + json.dumps(event, ensure_ascii=False, default=str) + "\n\n"

        try:
            yield encode(
                {
                    "type": "run",
                    "run_id": str(run_id),
                    "assistant_id": str(message_id),
                    "model_id": payload["modelId"],
                }
            )
            yield encode({"type": "step", "text": "小马开工啦，先理理思路"})
            while True:
                if await request.is_disconnected():
                    payload["status"] = "stopped"
                    break
                now = time.monotonic()
                if now - last_check > 1:
                    await self.auth.assert_active(principal)
                    last_check = now
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1)
                except TimeoutError:
                    event = {"type": "heartbeat"}
                kind = event["type"]
                if kind == "delta":
                    payload["content"] += event["text"]
                elif kind == "step":
                    payload["steps"].append(event["text"])
                elif kind == "tool":
                    values = {t["id"]: t for t in payload["tools"]}
                    values[event["tool"]["id"]] = event["tool"]
                    payload["tools"] = list(values.values())
                elif kind == "todos":
                    payload["todos"] = event["todos"]
                elif kind == "citations":
                    payload["citations"] = event["citations"]
                elif kind == "presentation":
                    values = {s["id"]: s for s in payload["presentations"]}
                    values[event["slot"]["id"]] = event["slot"]
                    payload["presentations"] = list(values.values())
                elif kind == "error":
                    payload.update(status="error", error=event["message"])
                    yield encode(event)
                    break
                elif kind == "complete":
                    if "messages" in final_context:
                        await self.store.save_context(
                            run_id, message_id, principal.user_id, final_context["messages"]
                        )
                    payload["status"] = "completed"
                    yield encode(event)
                    break
                yield encode(event)
                if now - last_save > 1:
                    await self.store.save(run_id, message_id, principal.user_id, payload)
                    last_save = now
        except HTTPException as exc:
            payload.update(status="error", error=str(exc.detail))
            yield encode({"type": "error", "message": str(exc.detail)})
        except asyncio.CancelledError:
            payload["status"] = "stopped"
            raise
        finally:
            producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer
            if payload["status"] == "running":
                payload["status"] = "stopped"
            if payload["status"] in ("stopped", "error"):
                for record in payload["tools"]:
                    if record["state"] == "input-available":
                        record.update(state="output-error", errorText="本轮已停止，未取得完整结果")
            # Persist partial output and release the lease even when a browser stops generation.
            await asyncio.shield(
                self.store.save(run_id, message_id, principal.user_id, payload, final=True)
            )
