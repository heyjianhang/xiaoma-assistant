import assert from "node:assert/strict";
import test from "node:test";
import { processView } from "../src/features/chat/process-view.ts";

const thought = (id, startedAt, state = "completed") => ({ id, startedAt, content: "模型返回的思考", state, durationMs: 500 });
const tool = (id, startedAt, state = "output-available") => ({ id, startedAt, title: "执行只读 SQL", name: "execute_readonly_sql", state, input: {} });
const base = () => ({ id: "message", role: "assistant", content: "", status: "running" });

test("interleaved reasoning and tools follow their actual start times", () => {
  const view = processView({ ...base(),
    reasoning: [thought("r1", "2026-10-28T00:00:01Z"), thought("r2", "2026-10-28T00:00:03Z")],
    tools: [tool("t1", "2026-10-28T00:00:02Z"), tool("t2", "2026-10-28T00:00:04Z"), { ...tool("todo"), name: "write_todos" }],
  }, true);
  assert.deepEqual(view.entries.map(entry => entry.id), ["r1", "t1", "r2", "t2"]);
});

test("one current stage wins over old thought and tool records", () => {
  const view = processView({ ...base(), reasoning: [thought("r1", undefined, "streaming")],
    tools: [tool("t1", undefined, "input-available")],
  }, true);
  assert.equal(view.label, "执行只读 SQL…");
  assert.equal(view.automaticOpen, true);
});

test("live work opens, the answer and successful history close, and failure reveals details", () => {
  const running = { ...base(), reasoning: [thought("r1", undefined, "streaming")] };
  assert.equal(processView(running, true).automaticOpen, true);
  const speaking = { ...running, content: "正文", reasoning: [thought("r1")] };
  assert.equal(processView(speaking, true).automaticOpen, false);
  assert.equal(processView({ ...speaking, status: "completed" }, false).automaticOpen, false);
  assert.equal(processView({ ...speaking, status: "error" }, false).automaticOpen, true);
  assert.equal(processView({ ...speaking, status: "stopped" }, false).automaticOpen, false);
});

test("plain text has a waiting line but never an empty dropdown or invented reasoning", () => {
  assert.equal(processView(base(), true).waiting, true);
  const answer = processView({ ...base(), content: "你好" }, true);
  assert.equal(answer.waiting, false);
  assert.equal(answer.details, false);
  assert.equal(answer.entries.length, 0);
  assert.equal(processView({ ...base(), status: "queued" }, true).label, "已排队，等待处理");
});
