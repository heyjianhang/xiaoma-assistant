"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Maximize2Icon, FlaskConicalIcon, LoaderCircleIcon, SearchIcon } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { useKnowledgeViewState, useWorkspace } from "@/lib/services/provider";
import { ExpandableMarkdown } from "@/components/expandable-markdown";
import { RetrievalPreviewDialog } from "./retrieval-preview-dialog";

export function RetrievalTestPanel() {
  const { repository, retrieval } = useWorkspace();
  const { retrievalSession, setRetrievalSession } = useKnowledgeViewState();
  const { question, hits } = retrievalSession;
  const [loading, setLoading] = useState(false);
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const initialScrollRef = useRef(retrievalSession.scrollTop);
  const returnFocusRef = useRef<HTMLButtonElement>(null);

  useEffect(() => () => abortRef.current?.abort(), []);
  useLayoutEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = initialScrollRef.current;
  }, []);

  async function search(query: string) {
    if (!query.trim()) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setPreviewIndex(null);
    setRetrievalSession(previous => ({ ...previous, question: query, hits: null, scrollTop: 0 }));
    scrollRef.current?.scrollTo({ top: 0 });
    setLoading(true);
    try {
      const result = await repository.retrieve(query, controller.signal);
      if (!controller.signal.aborted) setRetrievalSession(previous => ({ ...previous, hits: result }));
    } catch (error) {
      if (!controller.signal.aborted) toast.error(error instanceof Error ? error.message : "检索失败");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  return <div className="flex min-h-0 flex-1 flex-col gap-4">
    <form onSubmit={event => { event.preventDefault(); void search(question); }} className="flex shrink-0 gap-2">
      <InputGroup className="min-w-0 flex-1"><InputGroupInput aria-label="检索测试问题" placeholder="输入检索问题" value={question} onChange={event => setRetrievalSession(previous => ({ ...previous, question: event.target.value }))} /><InputGroupAddon><SearchIcon /></InputGroupAddon></InputGroup>
      <Button className="shrink-0" type="submit" disabled={loading || !question.trim()}>{loading ? <LoaderCircleIcon className="animate-spin" data-icon="inline-start" /> : <SearchIcon data-icon="inline-start" />}测试检索</Button>
    </form>
    <div className="flex shrink-0 flex-wrap gap-2"><Badge variant="secondary">向量检索</Badge><Badge variant="secondary">最多 {retrieval.resultCount} 条</Badge>{retrieval.rerank && <Badge variant="secondary">重排开启</Badge>}</div>
    <div ref={scrollRef} role="region" aria-label="检索结果" className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1" onScroll={event => {
      const scrollTop = event.currentTarget.scrollTop;
      setRetrievalSession(previous => previous.scrollTop === scrollTop ? previous : { ...previous, scrollTop });
    }}>
      {loading ? <div role="status" className="flex min-h-56 items-center justify-center gap-2 text-sm text-muted-foreground"><LoaderCircleIcon className="size-4 animate-spin" />正在检索…</div> : hits === null || hits.length === 0 ? <Empty className="min-h-64 rounded-xl border border-dashed"><EmptyHeader><EmptyMedia variant="icon"><FlaskConicalIcon /></EmptyMedia><EmptyTitle>{hits === null ? "输入一个业务问题" : "没有找到相关分块"}</EmptyTitle><EmptyDescription>{hits !== null && "试试调整问题，或检查文档及分块是否可检索。"}</EmptyDescription></EmptyHeader></Empty> : <div className="flex flex-col gap-3">{hits.map((hit, index) => <article key={`${hit.documentId}-${hit.chunkId}`} className="flex min-w-0 flex-col gap-4 rounded-xl border p-4">
        <div className="flex flex-wrap items-center gap-2 text-xs"><Badge variant="secondary">{index + 1}</Badge><span className="font-medium">{hit.title}</span><span className="text-muted-foreground">{hit.pages.length ? `第 ${hit.pages.join("、")} 页` : "Markdown"}</span>
          <div className="ml-auto flex items-center gap-2">{hit.score !== undefined && <Badge variant="outline" className="tabular-nums">{hit.scoreKind === "distance" ? "向量距离" : "重排分数"} {hit.score.toFixed(3)}</Badge>}<Button variant="ghost" size="sm" aria-haspopup="dialog" aria-controls="retrieval-preview" aria-label={`查看检索片段 ${index + 1}：${hit.title}`} onClick={event => { returnFocusRef.current = event.currentTarget; setPreviewIndex(index); }}>查看原文<Maximize2Icon data-icon="inline-end" /></Button></div>
        </div>
        <ExpandableMarkdown content={hit.text} />
      </article>)}</div>}
    </div>
    {previewIndex !== null && hits?.[previewIndex] && <RetrievalPreviewDialog hits={hits} index={previewIndex} onIndexChange={setPreviewIndex} onClose={() => setPreviewIndex(null)} returnFocusRef={returnFocusRef} />}
  </div>;
}
