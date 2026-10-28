"use client";

import { useState } from "react";
import { ChainOfThought, ChainOfThoughtContent, ChainOfThoughtHeader } from "@/components/ai-elements/chain-of-thought";
import { Tool, ToolContent, ToolHeader, ToolInput, ToolOutput } from "@/components/ai-elements/tool";
import { Spinner } from "@/components/ui/spinner";
import { MarkdownPreview } from "@/components/markdown-preview";
import type { ChatMessage } from "@/lib/services/contracts";

function retrievedChunks(output: unknown) {
  if (!output || typeof output !== "object" || !("chunks" in output) || !Array.isArray(output.chunks)) return undefined;
  const chunks = output.chunks.filter((item): item is { chunkId: string; title: string; text: string } => !!item && typeof item === "object" && typeof item.chunkId === "string" && typeof item.title === "string" && typeof item.text === "string");
  if (!chunks.length) return undefined;
  return <div className="flex min-w-0 flex-col gap-4 p-3">{chunks.map(chunk => <div key={chunk.chunkId} className="flex min-w-0 flex-col gap-3"><p className="text-sm font-medium">{chunk.title}</p><MarkdownPreview content={chunk.text} /></div>)}</div>;
}

export function ChatRun({ message, generating }: { message: ChatMessage; generating: boolean }) {
  const [processOpen, setProcessOpen] = useState<boolean | undefined>();
  const tools = (message.tools ?? []).filter(tool => tool.name !== "write_todos");
  const hasError = message.status === "error";
  const interrupted = message.status === "stopped";
  const summary = generating ? (message.steps?.at(-1) ?? "小马开工啦，先理理思路")
    : hasError ? "这一步卡住了" : interrupted ? "先停在这里" : tools.length ? `这轮查好了 · ${tools.length} 次工具调用` : "这轮聊完啦";

  if (!tools.length) return generating && !message.content ? <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status"><Spinner aria-hidden="true" className="size-3.5 shrink-0" /><span>{summary}</span></div> : null;

  return <div className="flex w-full min-w-0 flex-col gap-4">
    <ChainOfThought open={processOpen ?? (hasError || interrupted)} onOpenChange={setProcessOpen}>
      <ChainOfThoughtHeader aria-label="处理过程">
        <span className="flex min-w-0 items-center gap-2" role={generating ? "status" : undefined}>{generating && <Spinner aria-hidden="true" className="size-3.5 shrink-0" />}<span className="truncate">{summary}</span></span>
      </ChainOfThoughtHeader>
      <ChainOfThoughtContent className="gap-2">
        {tools.map(tool => <Tool key={tool.id} className="mb-0" defaultOpen={tool.state === "output-error"}>
          <ToolHeader type="dynamic-tool" toolName={tool.name} title={tool.title} state={tool.state} />
          <ToolContent><ToolInput input={tool.input} /><ToolOutput output={tool.name === "search_knowledge_base" ? retrievedChunks(tool.output) ?? tool.output : tool.output} errorText={tool.errorText} /></ToolContent>
        </Tool>)}
      </ChainOfThoughtContent>
    </ChainOfThought>
  </div>;
}
