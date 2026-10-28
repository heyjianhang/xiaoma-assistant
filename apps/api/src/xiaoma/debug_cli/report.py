"""SSE parsing and private, interruption-safe debug artifacts."""

import json
import time
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from .client import CliError, private_json, private_write, secure_directory


def sse_events(lines):
    data = []
    size = 0
    for line in lines:
        if line == "":
            if data:
                event = json.loads("\n".join(data))
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    raise CliError("收到不符合格式的流式事件")
                yield event
            data, size = [], 0
        elif line.startswith("data:"):
            value = line[5:].removeprefix(" ")
            size += len(value)
            if size > 2_000_000:
                raise CliError("单个流式事件超过调试客户端限制")
            data.append(value)
    if data:
        raise CliError("流式事件尚未结束，连接已断开")


class RunReport:
    def __init__(self, directory, request):
        name = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d-%H%M%S")
        self.path = secure_directory(directory / f"{name}-{uuid4().hex[:8]}")
        private_json(self.path / "request.json", request)
        private_write(self.path / "events.jsonl", "")
        self.started = time.monotonic()
        self.result = {
            "conversation_id": request["conversation_id"],
            "run_id": None,
            "status": "running",
            "answer": "",
            "steps": [],
            "tools": [],
            "todos": [],
            "citations": [],
            "presentations": [],
        }
        self.tool_starts = {}
        self.first_token = None

    def record(self, event):
        elapsed = round(time.monotonic() - self.started, 3)
        with (self.path / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps({"elapsed_seconds": elapsed, "event": event}, ensure_ascii=False) + "\n"
            )
        kind = event["type"]
        if kind == "run":
            self.result.update({key: value for key, value in event.items() if key != "type"})
        elif kind == "delta":
            self.result["answer"] += event["text"]
            if event["text"] and self.first_token is None:
                self.first_token = elapsed
        elif kind == "step":
            self.result["steps"].append(event["text"])
        elif kind == "tool":
            tool = dict(event["tool"])
            self.tool_starts.setdefault(tool["id"], elapsed)
            tool["elapsed_seconds"] = round(elapsed - self.tool_starts[tool["id"]], 3)
            existing = {item["id"]: item for item in self.result["tools"]}
            existing[tool["id"]] = tool
            self.result["tools"] = list(existing.values())
        elif kind in {"todos", "citations"}:
            self.result[kind] = event[kind]
        elif kind == "presentation":
            existing = {item["id"]: item for item in self.result["presentations"]}
            existing[event["slot"]["id"]] = event["slot"]
            self.result["presentations"] = list(existing.values())
        elif kind == "complete":
            self.result["status"] = "completed"
        elif kind == "error":
            self.result.update(status="error", error=event["message"])

    def finish(self):
        if self.result["status"] == "running":
            self.result.update(status="error", error="未收到完成事件，回答可能不完整")
        self.result.update(
            elapsed_seconds=round(time.monotonic() - self.started, 3),
            first_token_seconds=self.first_token,
            artifacts=str(self.path),
        )
        private_json(self.path / "result.json", self.result)
        private_write(self.path / "answer.md", self.result["answer"])
        return self.result
