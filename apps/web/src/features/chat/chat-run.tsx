"use client";

import { useEffect, useRef } from "react";
import { CircleAlertIcon, CirclePauseIcon, LoaderCircleIcon } from "lucide-react";
import { ChainOfThought, ChainOfThoughtContent, ChainOfThoughtHeader } from "@/components/ai-elements/chain-of-thought";
import { Tool, ToolContent, ToolHeader, ToolInput, ToolOutput } from "@/components/ai-elements/tool";
import { Spinner } from "@/components/ui/spinner";
import { MarkdownPreview } from "@/components/markdown-preview";
import type { ChatMessage, ChatToolCall } from "@/lib/services/contracts";
import { useDisclosurePreference } from "@/lib/services/provider";
import { ChatReasoning } from "./chat-reasoning";
import { processView } from "./process-view";

function retrievedChunks(output: unknown) {
  if (!output || typeof output !== "object" || !("chunks" in output) || !Array.isArray(output.chunks)) return undefined;
  const chunks = output.chunks.filter((item): item is { chunkId: string; title: string; text: string } => !!item && typeof item === "object" && typeof item.chunkId === "string" && typeof item.title === "string" && typeof item.text === "string");
  if (!chunks.length) return undefined;
  return <div className="flex min-w-0 flex-col gap-4 p-3">{chunks.map(chunk => <div key={chunk.chunkId} className="flex min-w-0 flex-col gap-3"><p className="text-sm font-medium">{chunk.title}</p><MarkdownPreview content={chunk.text} /></div>)}</div>;
}

export function ChatRun({ message, generating }: { message: ChatMessage; generating: boolean }) {
  const view = processView(message, generating);
  // Running inspection must not pin the process open after completion.
  // A separate finished scope still lets users reopen completed details.
  const disclosurePhase = generating ? "running" : view.failed ? "failed" : "finished";
  const [open, setOpen, inspected] = useDisclosurePreference(`${message.id}:process:${disclosurePhase}`, view.automaticOpen);
  const viewport = useRef<HTMLDivElement>(null);
  const latestEntry = view.entries.at(-1)?.id;
  useEffect(() => {
    if (generating && open && !inspected && viewport.current) {
      viewport.current.scrollTop = viewport.current.scrollHeight;
    }
  }, [generating, open, inspected, latestEntry]);
  if (!view.details) return view.waiting ? <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status"><Spinner aria-hidden="true" className="size-3.5 shrink-0" /><span>{view.label}</span></div> : null;
  const active = generating && !view.failed && !view.stopped;
  return <ChainOfThought open={open} onOpenChange={setOpen}>
    <ChainOfThoughtHeader aria-label={`${view.label}，${open ? "收起" : "展开"}处理过程`}
      icon={active ? LoaderCircleIcon : view.failed ? CircleAlertIcon : view.stopped ? CirclePauseIcon : null}
      iconClassName={active ? "animate-spin" : undefined}>
      <span role={active ? "status" : undefined}>{view.label}</span>
    </ChainOfThoughtHeader>
    <ChainOfThoughtContent ref={viewport} className="max-h-96 overflow-y-auto pr-1" aria-label="处理过程详情" onScroll={event => {
      const element = event.currentTarget;
      if (generating && !inspected && element.scrollHeight - element.scrollTop - element.clientHeight > 24) setOpen(true);
    }}>
      {view.entries.map(entry => entry.kind === "reasoning"
        ? <ChatReasoning key={`reason:${entry.id}`} part={entry.value} messageId={message.id} generating={generating}
            automaticOpen={view.automaticOpen} onInspect={() => setOpen(true)} />
        : <ChatToolStep key={`tool:${entry.id}`} tool={entry.value} messageId={message.id}
            failed={view.failed} onInspect={() => setOpen(true)} />)}
    </ChainOfThoughtContent>
  </ChainOfThought>;
}

function ChatToolStep({ tool, messageId, failed, onInspect }: {
  tool: ChatToolCall; messageId: string; failed: boolean; onInspect: () => void;
}) {
  const [open, setOpen] = useDisclosurePreference(`${messageId}:tool:${tool.id}`, failed && tool.state === "output-error");
  return <Tool className="mb-0" open={open} onOpenChange={next => {
    setOpen(next); if (next) onInspect();
  }}>
    <ToolHeader type="dynamic-tool" toolName={tool.name} title={tool.title} state={tool.state} />
    <ToolContent><ToolInput input={tool.input} /><ToolOutput output={tool.name === "search_knowledge" || tool.name === "search_knowledge_base" ? retrievedChunks(tool.output) ?? tool.output : tool.output} errorText={tool.errorText} /></ToolContent>
  </Tool>;
}
