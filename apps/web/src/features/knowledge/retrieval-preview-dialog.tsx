"use client";

import Link from "next/link";
import { useEffect, useState, type RefObject } from "react";
import { ChevronLeftIcon, ChevronRightIcon, ExternalLinkIcon, FileTextIcon, XIcon } from "lucide-react";
import { MarkdownPreview } from "@/components/markdown-preview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import type { RetrievalHit } from "@/lib/services/contracts";
import { useWorkspace } from "@/lib/services/provider";
import { cn } from "@/lib/utils";
import { SourceViewer } from "./source-viewer";

interface RetrievalPreviewDialogProps {
  hits: RetrievalHit[];
  index: number;
  onIndexChange: (index: number) => void;
  onClose: () => void;
  returnFocusRef: RefObject<HTMLButtonElement | null>;
}

export function RetrievalPreviewDialog({ hits, index, onIndexChange, onClose, returnFocusRef }: RetrievalPreviewDialogProps) {
  const { documents, repository, detailErrors } = useWorkspace();
  const [mobilePanel, setMobilePanel] = useState("source");
  const hit = hits[index];
  const document = documents.find(document => document.id === hit.documentId);
  const chunk = document?.chunks.find(chunk => chunk.id === hit.chunkId);
  const sourceBlocks = document?.blocks.filter(block => chunk?.blockIds.includes(block.id)) ?? [];
  const clause = sourceBlocks.map(block => block.clause).filter(Boolean).join("、");
  const available = !!document?.activeRevision && !!chunk;
  const loading = !document?.chunksLoaded && !detailErrors[hit.documentId];
  useEffect(() => { void repository.loadDocument(hit.documentId); }, [repository, hit.documentId]);

  return <Dialog open onOpenChange={open => !open && onClose()}>
    <DialogContent id="retrieval-preview" showCloseButton={false}
      className="flex h-[88dvh] max-h-[960px] flex-col gap-0 overflow-hidden p-0 sm:max-w-[calc(100%-3rem)] xl:max-w-7xl"
      onCloseAutoFocus={event => { event.preventDefault(); returnFocusRef.current?.focus({ preventScroll: true }); }}>
      <div className="flex shrink-0 items-center justify-between gap-4 border-b px-4 py-3 sm:px-5">
        <DialogHeader className="min-w-0 gap-1.5">
          <DialogTitle className="flex min-w-0 items-center gap-2"><FileTextIcon className="size-4 shrink-0 text-muted-foreground" /><span className="truncate">{document?.filename ?? hit.title}</span></DialogTitle>
          <DialogDescription className="sr-only">检索片段与原文预览</DialogDescription>
          <p className="truncate text-xs text-muted-foreground">{hit.pages.length ? `第 ${hit.pages.join("、")} 页` : "Markdown"}{clause && ` · ${clause}`}</p>
        </DialogHeader>
        <div className="flex shrink-0 items-center gap-2">
          <nav aria-label="命中片段切换" className="flex items-center gap-1">
            <Button variant="ghost" size="icon" aria-label="上一个命中片段" disabled={index === 0} onClick={() => onIndexChange(index - 1)}><ChevronLeftIcon /></Button>
            <span className="min-w-11 text-center text-xs tabular-nums text-muted-foreground">{index + 1} / {hits.length}</span>
            <Button variant="ghost" size="icon" aria-label="下一个命中片段" disabled={index === hits.length - 1} onClick={() => onIndexChange(index + 1)}><ChevronRightIcon /></Button>
          </nav>
          <DialogClose asChild><Button variant="ghost" size="icon" aria-label="关闭原文预览"><XIcon /></Button></DialogClose>
        </div>
      </div>
      {loading ? <div role="status" aria-label="正在加载原文" className="flex flex-1 flex-col gap-4 p-5"><Skeleton className="h-12 w-2/3" /><Skeleton className="h-64 w-full" /></div> : !available ? <Empty className="flex-1"><EmptyHeader><EmptyTitle>当前片段已不可用</EmptyTitle><EmptyDescription>{detailErrors[hit.documentId] ?? "文档可能已更新或移除，关闭预览后重新检索。"}</EmptyDescription></EmptyHeader></Empty> : <>
        <Tabs value={mobilePanel} onValueChange={setMobilePanel} className="shrink-0 px-4 py-2 md:hidden"><TabsList className="w-full"><TabsTrigger value="source">原文</TabsTrigger><TabsTrigger value="chunk">命中片段</TabsTrigger></TabsList></Tabs>
        <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[minmax(0,1.4fr)_minmax(280px,1fr)]">
          <div className={cn("min-h-0 min-w-0 flex-col border-r md:flex", mobilePanel === "source" ? "flex" : "hidden")}>
            <SourceViewer document={document} selectedBlockIds={chunk.blockIds} navigationRequest={index} highlight onBlockSelect={blockId => {
              const next = hits.findIndex(candidate => candidate.documentId === document.id && document.chunks.find(item => item.id === candidate.chunkId)?.blockIds.includes(blockId));
              if (next >= 0) onIndexChange(next);
            }} />
          </div>
          <div className={cn("min-h-0 min-w-0 flex-col md:flex", mobilePanel === "chunk" ? "flex" : "hidden")}>
            <div className="flex h-12 shrink-0 items-center justify-between gap-3 border-b px-5"><h2 className="text-sm font-medium">命中片段</h2><div className="flex items-center gap-2">{hit.score !== undefined && <Badge variant="outline" className="tabular-nums">{hit.scoreKind === "distance" ? "向量距离" : "重排分数"} {hit.score.toFixed(3)}</Badge>}<Badge variant="secondary">{index + 1}</Badge></div></div>
            <div role="region" aria-label="命中片段全文" tabIndex={0} className="min-h-0 flex-1 overflow-y-auto p-5">
              {!/^#{1,6}\s/.test(chunk.text.trimStart()) && <h3 className="mb-4 text-sm font-medium">{chunk.title}</h3>}
              <MarkdownPreview content={chunk.text} />
            </div>
            <div className="flex shrink-0 justify-end border-t px-4 py-3"><Button variant="outline" size="sm" asChild><Link href={`/knowledge/${hit.documentId}?chunk=${hit.chunkId}`} onClick={onClose}>打开文档详情<ExternalLinkIcon data-icon="inline-end" /></Link></Button></div>
          </div>
        </div>
      </>}
    </DialogContent>
  </Dialog>;
}
