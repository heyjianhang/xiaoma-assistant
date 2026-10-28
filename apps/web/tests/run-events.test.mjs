import assert from "node:assert/strict";
import test from "node:test";
import { applyRunEvent, mergeRunSnapshot } from "../src/lib/services/run-events.ts";

const message = () => ({ id: "assistant-1", role: "assistant", runId: "run-1", status: "running", content: "first ", eventSeq: 5 });

test("reconnection does not append persisted text twice", () => {
  const snapshot = message();
  assert.equal(applyRunEvent(snapshot, 5, { type: "delta", text: "first " }), snapshot);
  const next = applyRunEvent(snapshot, 6, { type: "delta", text: "second" });
  assert.equal(next.content, "first second");
  assert.equal(applyRunEvent(next, 6, { type: "delta", text: "second" }), next);
  assert.equal(applyRunEvent(next, 7, { type: "complete" }).status, "completed");
});

test("task and citation updates replay with their original meaning", () => {
  let state = { ...message(), status: "queued", content: "", eventSeq: 0 };
  state = applyRunEvent(state, 1, { type: "status", status: "running" });
  state = applyRunEvent(state, 2, { type: "tool", tool: { id: "tool-1", state: "input-available", name: "search_knowledge", title: "query", input: {} } });
  state = applyRunEvent(state, 3, { type: "tool", tool: { id: "tool-1", state: "output-available", name: "search_knowledge", title: "query", input: {}, output: { found: true } } });
  state = applyRunEvent(state, 4, { type: "citations", citations: [{ documentId: "doc", chunkId: "chunk", title: "policy", clause: "1" }] });
  state = applyRunEvent(state, 5, { type: "todos", todos: [{ id: "0", title: "check", status: "completed" }] });
  assert.equal(state.tools.length, 1);
  assert.equal(state.tools[0].state, "output-available");
  assert.equal(state.citations[0].chunkId, "chunk");
  assert.equal(state.todos[0].status, "completed");
});

test("run states are independent and stopping is an explicit event", () => {
  const first = message();
  const second = { ...message(), id: "assistant-2", runId: "run-2" };
  const stopped = applyRunEvent(first, 6, { type: "stopped" });
  assert.equal(stopped.status, "stopped");
  assert.equal(stopped.content, "first ");
  assert.equal(second.status, "running");
  assert.equal(first.status, "running");
  assert.equal(applyRunEvent(second, Number.NaN, { type: "complete" }), second);
});

test("an older list response cannot regress a live message", () => {
  const local = applyRunEvent(message(), 6, { type: "delta", text: "second" });
  assert.equal(mergeRunSnapshot(local, message()), local);
  const final = { ...local, eventSeq: 7, status: "completed" };
  assert.equal(mergeRunSnapshot(local, final), final);
  const other = { ...message(), runId: "different-run", eventSeq: 1 };
  assert.equal(mergeRunSnapshot(local, other), other);
});


test("reasoning replays independently from answer text and stops without a spinner", () => {
  let message = { id: "a", role: "assistant", content: "", status: "running" };
  message = applyRunEvent(message, 1, { type: "reasoning", id: "model-1", text: "核对口径", state: "streaming" });
  message = applyRunEvent(message, 1, { type: "reasoning", id: "model-1", text: "核对口径", state: "streaming" });
  assert.equal(message.reasoning[0].content, "核对口径");
  assert.equal(message.content, "");
  message = applyRunEvent(message, 2, { type: "reasoning", id: "model-1", state: "completed", durationMs: 500 });
  message = applyRunEvent(message, 3, { type: "delta", text: "正文结论" });
  message = applyRunEvent(message, 4, { type: "reasoning", id: "model-2", text: "复核", state: "streaming" });
  message = applyRunEvent(message, 5, { type: "stopped" });
  assert.equal(message.content, "正文结论");
  assert.equal(message.reasoning[0].durationMs, 500);
  assert.equal(message.reasoning[1].state, "stopped");
});


test("parallel presentation updates retain their first position and replay without duplicates", () => {
  let state = { ...message(), content: "", eventSeq: 0 };
  state = applyRunEvent(state, 1, { type: "presentation", slot: { id: "metrics", title: "指标", status: "loading" } });
  state = applyRunEvent(state, 2, { type: "presentation", slot: { id: "review", title: "核对", status: "loading" } });
  state = applyRunEvent(state, 3, { type: "delta", text: "继续说明" });
  const ready = { type: "presentation", slot: { id: "metrics", title: "指标", status: "ready", payload: { type: "data_view", view: "metrics" } } };
  state = applyRunEvent(state, 4, ready);
  assert.deepEqual(state.presentations.map(slot => slot.id), ["metrics", "review"]);
  assert.equal(state.presentations[0].status, "ready");
  assert.equal(state.presentations[1].status, "loading");
  assert.equal(state.content, "继续说明");
  assert.equal(applyRunEvent(state, 4, ready), state);
  const replay = { ...state, presentations: structuredClone(state.presentations) };
  state = applyRunEvent(replay, 5, { type: "presentation", slot: { id: "review", title: "核对", status: "ready" } });
  state = applyRunEvent(state, 6, ready);
  assert.deepEqual(state.presentations.map(slot => slot.id), ["metrics", "review"]);
  assert.equal(state.presentations.length, 2);
});
