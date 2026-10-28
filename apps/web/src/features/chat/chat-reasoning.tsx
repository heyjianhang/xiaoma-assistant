"use client";

import { useEffect, useRef } from "react";
import { Reasoning, ReasoningContent, ReasoningTrigger } from "@/components/ai-elements/reasoning";
import type { ChatReasoning as ReasoningPart } from "@/lib/services/contracts";
import { useDisclosurePreference } from "@/lib/services/provider";

export function ChatReasoning({ part, messageId, generating, automaticOpen, onInspect }: {
  part: ReasoningPart; messageId: string; generating: boolean;
  automaticOpen: boolean; onInspect: () => void;
}) {
  const streaming = generating && part.state === "streaming";
  // Finishing a model thought resets its running disclosure preference.
  // Reopening a finished thought is still allowed and remembered separately.
  const phase = streaming ? "streaming" : "finished";
  const [open, setOpen] = useDisclosurePreference(`${messageId}:reasoning:${part.id}:${phase}`, automaticOpen && streaming);
  const viewport = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  useEffect(() => {
    if (streaming && open && following.current && viewport.current) {
      viewport.current.scrollTop = viewport.current.scrollHeight;
    }
  }, [streaming, open, part.content]);
  const seconds = part.durationMs === undefined ? undefined : Math.round(part.durationMs / 1000);
  return <Reasoning className="w-full" open={open} onOpenChange={next => {
    setOpen(next); if (next) onInspect();
  }} autoOpen={false} autoClose={false} isStreaming={streaming} duration={streaming ? undefined : seconds}>
    <ReasoningTrigger aria-label="模型思考详情" getThinkingMessage={active => active ? "思考中…"
      : part.state === "stopped" ? "思考已停止"
      : part.state === "error" ? "思考中断"
      : seconds === undefined ? "思考记录"
      : seconds < 1 ? "已思考不到 1 秒" : `已思考 ${seconds} 秒`} />
    <ReasoningContent ref={viewport} className="max-h-48 overflow-y-auto" onScroll={event => {
      const element = event.currentTarget;
      following.current = element.scrollHeight - element.scrollTop - element.clientHeight < 24;
      if (streaming && !following.current) { setOpen(true); onInspect(); }
    }}>{part.content}</ReasoningContent>
  </Reasoning>;
}
