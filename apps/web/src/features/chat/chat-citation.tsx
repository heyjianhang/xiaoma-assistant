"use client";

import { useRef, useState } from "react";
import { ArrowUpRightIcon, FileTextIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MarkdownPreview } from "@/components/markdown-preview";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { RetrievalPreviewDialog } from "@/features/knowledge/retrieval-preview-dialog";
import type { Citation } from "@/lib/services/contracts";
import { useWorkspace } from "@/lib/services/provider";

export function ChatCitation({ citation, number }: { citation: Citation; number: number }) {
  const { documents, repository, detailErrors } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [hoverOpen, setHoverOpen] = useState(false);
  const returnFocusRef = useRef<HTMLButtonElement>(null);
  // Dialog restores focus to the citation. That is not a new preview request.
  const previewDismissed = useRef(false);
  const { documentId, chunkId } = citation;
  const document = documents.find(item => item.id === documentId);
  const chunk = document?.chunks.find(item => item.id === chunkId);
  const pages = [...new Set(document?.blocks.filter(block => chunk?.blockIds.includes(block.id)).map(block => block.page) ?? [])];
  const title = document?.title ?? citation.title ?? "来源文档";
  const hits = [{ documentId, chunkId, title, text: chunk?.text ?? "", pages }];
  const preview = chunk?.text ?? (detailErrors[documentId] ? "引用加载失败，请打开原文重试。" : document?.chunksLoaded ? "文档可能已更新或移除，当前引用片段已不可用。" : "正在加载引用…");
  function showSource() { previewDismissed.current = true; setHoverOpen(false); setOpen(true); }
  function closeSource() { previewDismissed.current = true; setHoverOpen(false); setOpen(false); }

  return <>
    <HoverCard openDelay={200} open={!open && hoverOpen} onOpenChange={value => { if (value && (open || previewDismissed.current)) return; setHoverOpen(value); if (value) void repository.loadDocument(documentId); }}>
      <HoverCardTrigger asChild><Button ref={returnFocusRef} variant="link" className="citation-anchor" aria-label={`查看引用 ${number}：${title}`} aria-haspopup="dialog" aria-expanded={open} onPointerMove={() => { if (!open) previewDismissed.current = false; }} onFocus={() => { if (!open && !previewDismissed.current) { setHoverOpen(true); void repository.loadDocument(documentId); } }} onBlur={event => { if (!open) previewDismissed.current = false; if (!(event.relatedTarget instanceof HTMLElement) || !event.relatedTarget.closest('[data-slot="hover-card-content"]')) setHoverOpen(false); }} onKeyDown={event => { if (event.key === "Escape") setHoverOpen(false); }} onClick={showSource}>{number}</Button></HoverCardTrigger>
      <HoverCardContent className="w-96 max-w-[calc(100vw-2rem)]"><div className="flex flex-col gap-3">
        <div className="flex items-center gap-2 text-sm font-medium"><FileTextIcon className="size-4 shrink-0" />{title}</div>
        {citation.clause && <p className="text-xs text-muted-foreground">{citation.clause}</p>}
        <MarkdownPreview content={preview} className="max-h-64 overflow-auto text-xs leading-6" />
        <Button variant="outline" size="sm" onClick={showSource}>查看原文<ArrowUpRightIcon data-icon="inline-end" /></Button>
      </div></HoverCardContent>
    </HoverCard>
    {open && <RetrievalPreviewDialog hits={hits} index={0} onIndexChange={() => {}} onClose={closeSource} returnFocusRef={returnFocusRef} />}
  </>;
}
