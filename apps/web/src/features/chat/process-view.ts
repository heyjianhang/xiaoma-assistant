import type { ChatMessage, ChatReasoning, ChatToolCall } from "../../lib/services/contracts";

export type ProcessEntry =
  | { kind: "reasoning"; id: string; value: ChatReasoning }
  | { kind: "tool"; id: string; value: ChatToolCall };

/** New records have actual start times. Legacy history keeps its stable grouping. */
export function processView(message: ChatMessage, generating: boolean) {
  const thoughts = (message.reasoning ?? []).filter(part => part.content);
  const tools = (message.tools ?? []).filter(tool => tool.name !== "write_todos");
  const entries: ProcessEntry[] = [
    ...thoughts.map(value => ({ kind: "reasoning" as const, id: value.id, value })),
    ...tools.map(value => ({ kind: "tool" as const, id: value.id, value })),
  ];
  if (entries.every(item => Number.isFinite(Date.parse(item.value.startedAt ?? "")))) {
    entries.sort((a, b) => Date.parse(a.value.startedAt!) - Date.parse(b.value.startedAt!));
  }
  const activeTools = generating ? tools.filter(tool => tool.state === "input-available") : [];
  const thinking = generating && thoughts.some(part => part.state === "streaming");
  const failed = message.status === "error" || !!message.error;
  const stopped = message.status === "stopped";
  const duration = thoughts.reduce((total, part) => total + (part.durationMs ?? 0), 0);
  const details = entries.length > 0;
  const counts = [duration > 0 ? duration < 1000 ? "思考不到 1 秒" : `思考 ${Math.round(duration / 1000)} 秒` : "",
    tools.length ? `${tools.length} 次工具调用` : ""].filter(Boolean).join(" · ");
  let label: string;
  if (message.status === "queued") label = "已排队，等待处理";
  else if (failed) label = "处理遇到问题";
  else if (stopped) label = counts ? `已停止 · ${counts}` : "已停止";
  else if (activeTools.length) label = activeTools.length > 1 ? `正在执行 ${activeTools.length} 项工具` : `${activeTools[0].title}…`;
  else if (thinking) label = "正在思考…";
  else if (generating) label = details ? "正在整理结果…" : message.steps?.at(-1) ?? "正在等待模型响应";
  else label = counts ? `处理完成 · ${counts}` : "处理完成";
  return {
    entries, label, details, failed, stopped,
    automaticOpen: details && (failed || (generating && !stopped && (thinking || !!activeTools.length || !message.content))),
    waiting: generating && !message.content && !details,
  };
}
