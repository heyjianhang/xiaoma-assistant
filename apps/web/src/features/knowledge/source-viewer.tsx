"use client";

import { useEffect, useMemo, useRef } from "react";
import { Badge } from "@/components/ui/badge";
import { MarkdownPreview } from "@/components/markdown-preview";
import { cn } from "@/lib/utils";
import type { KnowledgeDocument } from "@/lib/services/contracts";
import { PdfScrollViewer } from "./pdf-scroll-viewer";

export interface SourceViewerProps {
  document: KnowledgeDocument;
  selectedBlockIds: string[];
  navigationRequest: number;
  highlight: boolean;
  onBlockSelect: (blockId: string) => void;
}

export function SourceViewer(props: SourceViewerProps) {
  if (props.document.format === "md") return <MarkdownSourceViewer {...props} />;
  return <PdfScrollViewer key={props.document.sourceUrl} {...props} />;
}

function MarkdownSourceViewer({ document, selectedBlockIds, navigationRequest, highlight, onBlockSelect }: SourceViewerProps) {
  const selectedRef = useRef<HTMLDivElement>(null);
  const segments = useMemo(() => {
    const lines = (document.sourceText ?? "").split(/\r?\n/);
    const spans = [...document.blocks].filter(block => block.lineStart && block.lineEnd)
      .sort((a, b) => a.lineStart! - b.lineStart!);
    const result: { id: string; text: string; selectable: boolean }[] = [];
    let cursor = 0;
    for (const block of spans) {
      const start = block.lineStart! - 1;
      if (start < cursor) continue;
      if (start > cursor) result.push({ id: `gap:${cursor}`, text: lines.slice(cursor, start).join("\n"), selectable: false });
      result.push({ id: block.id, text: lines.slice(start, block.lineEnd).join("\n"), selectable: true });
      cursor = block.lineEnd!;
    }
    if (cursor < lines.length) result.push({ id: `gap:${cursor}`, text: lines.slice(cursor).join("\n"), selectable: false });
    return result.filter(segment => segment.text.trim());
  }, [document.sourceText, document.blocks]);
  useEffect(() => { selectedRef.current?.scrollIntoView({ behavior: navigationRequest > 0 ? "smooth" : "auto", block: "center" }); }, [selectedBlockIds, navigationRequest, segments]);
  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="viewer-toolbar"><span className="text-xs font-medium">Markdown 原文</span><Badge variant="outline">段落定位</Badge></div>
    <div role="region" aria-label="Markdown 原文滚动区域" className="min-h-0 flex-1 overflow-y-auto bg-muted/40 p-5 lg:p-7">
      <div className="mx-auto flex max-w-3xl flex-col gap-3 rounded-sm border bg-background px-5 py-8 shadow-sm lg:px-8">
        {segments.map(segment => <div key={segment.id} ref={selectedBlockIds[0] === segment.id ? selectedRef : undefined}
          role={segment.selectable ? "button" : undefined} tabIndex={segment.selectable ? 0 : undefined}
          aria-label={segment.selectable ? "定位对应分块" : undefined}
          className={cn("rounded-md p-3", segment.selectable && "source-paragraph cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring", highlight && selectedBlockIds.includes(segment.id) && "source-paragraph-selected")}
          onClick={() => segment.selectable && onBlockSelect(segment.id)}
          onKeyDown={event => { if (segment.selectable && event.target === event.currentTarget && ["Enter", " "].includes(event.key)) { event.preventDefault(); onBlockSelect(segment.id); } }}>
          <MarkdownPreview content={segment.text} />
        </div>)}
      </div>
    </div>
  </div>;
}
