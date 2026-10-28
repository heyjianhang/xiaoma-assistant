import type { ChatMessage, ReplyEvent } from "./contracts";

/** A persisted snapshot and replayed events may overlap. Apply each sequence once. */
export function applyRunEvent(message: ChatMessage, sequence: number, event: ReplyEvent): ChatMessage {
  if (!Number.isSafeInteger(sequence) || sequence <= (message.eventSeq ?? 0)) return message;
  const next = { ...message, eventSeq: sequence };
  switch (event.type) {
    case "run": return { ...next, runId: event.run_id, modelId: event.model_id };
    case "status": return { ...next, status: event.status };
    case "delta": return { ...next, content: next.content + event.text };
    case "reasoning": {
      const parts = [...(next.reasoning ?? [])];
      const index = parts.findIndex(part => part.id === event.id);
      const part = index >= 0 ? parts[index] : { id: event.id, content: "", state: "streaming" as const };
      const updated = { ...part, content: part.content + (event.text ?? ""), state: event.state ?? part.state,
        startedAt: event.startedAt ?? part.startedAt, durationMs: event.durationMs ?? part.durationMs };
      if (index >= 0) parts[index] = updated; else parts.push(updated);
      return { ...next, reasoning: parts };
    }
    case "step": return { ...next, steps: [...(next.steps ?? []), event.text] };
    case "tool": return { ...next, tools: [...(next.tools ?? []).filter(item => item.id !== event.tool.id), event.tool] };
    case "todos": return { ...next, todos: event.todos };
    case "citations": return { ...next, citations: event.citations };
    case "presentation": {
      // A slot keeps its first position through loading, ready, and later updates.
      const slots = [...(next.presentations ?? [])];
      const index = slots.findIndex(slot => slot.id === event.slot.id);
      if (index < 0) slots.push(event.slot); else slots[index] = { ...slots[index], ...event.slot };
      return { ...next, presentations: slots };
    }
    case "complete": return { ...next, status: "completed" };
    case "stopped": return { ...next, status: "stopped", stopped: true, reasoning: next.reasoning?.map(part => part.state === "streaming" ? { ...part, state: "stopped" } : part) };
    case "error": return { ...next, status: "error", error: event.message, reasoning: next.reasoning?.map(part => part.state === "streaming" ? { ...part, state: "error" } : part) };
    default: return next;
  }
}

/** Prefer a newer local event snapshot over a response read earlier by the server. */
export function mergeRunSnapshot(local: ChatMessage | undefined, incoming: ChatMessage): ChatMessage {
  return local?.id === incoming.id && local.runId === incoming.runId && (local.eventSeq ?? 0) > (incoming.eventSeq ?? 0) ? local : incoming;
}
