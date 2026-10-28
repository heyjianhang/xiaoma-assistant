"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeftIcon, FileTextIcon, HighlighterIcon, LayersIcon, MoreHorizontalIcon, SearchIcon, Trash2Icon, ExternalLinkIcon } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ExpandableMarkdown } from "@/components/expandable-markdown";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/services/provider";
import { strategyLabels } from "@/lib/services/knowledge-config";
import { DocumentStatusBadge } from "./document-status";
import { SourceViewer } from "./source-viewer";
import { RemoveDocumentDialog } from "./document-actions";

const EMPTY_BLOCK_IDS: string[] = [];

import { useAccess } from "@/lib/access/provider";
import { authFetch } from "@/lib/access/client";

export function DocumentDetail({ documentId, initialChunkId }: { documentId: string; initialChunkId?: string }) {
  const { user } = useAccess();
  const { documents, repository, detailErrors } = useWorkspace();
  const router = useRouter();
  const document = documents.find(document => document.id === documentId);
  const firstChunk = document?.chunks.find(chunk => chunk.id === initialChunkId) ?? document?.chunks[0];
  const [selectedId, setSelectedId] = useState(firstChunk?.id);
  const [navigationRequest, setNavigationRequest] = useState(0);
  const [highlight, setHighlight] = useState(true);
  const [query, setQuery] = useState("");
  const [mobilePanel, setMobilePanel] = useState("chunks");
  const [removeOpen, setRemoveOpen] = useState(false);
  const [savingChunks, setSavingChunks] = useState<Set<string>>(new Set());
  const selectedChunk = document?.chunks.find(chunk => chunk.id === selectedId) ?? firstChunk;
  const selectedBlockIds = selectedChunk?.blockIds ?? EMPTY_BLOCK_IDS;
  useEffect(() => {
    if (initialChunkId) globalThis.document.getElementById(`chunk-${initialChunkId}`)?.scrollIntoView({ block: "center" });
  }, [initialChunkId, document?.chunksLoaded, document?.activeIndexId]);
  useEffect(() => { void repository.loadDocument(documentId); }, [repository, documentId, document?.activeIndexId, document?.status, document?.sourceMapAvailable]);
  const loadError = detailErrors[documentId];
  if ((!document || !document.chunksLoaded) && !loadError) return <div role="status" aria-label="正在加载文档分块" className="flex flex-1 flex-col gap-5 p-6"><Skeleton className="h-12 w-2/3" /><Skeleton className="h-64 w-full" /></div>;
  if (!document || loadError) return <Empty className="flex-1"><EmptyHeader><EmptyMedia variant="icon"><FileTextIcon /></EmptyMedia><EmptyTitle>文档暂时无法加载</EmptyTitle><EmptyDescription>{loadError ?? "文档已不存在。"}</EmptyDescription></EmptyHeader><Button variant="outline" onClick={() => void repository.loadDocument(documentId)}>重试</Button><Button asChild variant="ghost"><Link href="/knowledge">返回知识库</Link></Button></Empty>;
  function selectChunk(id: string) {
    if (!document) return;
    const chunk = document.chunks.find(chunk => chunk.id === id);
    if (!chunk) return;
    setSelectedId(id);
    setNavigationRequest(value => value + 1);
  }
  const filtered = document.chunks.filter(chunk => (chunk.title + chunk.text).includes(query));
  const ready = document.activeRevision !== null;
  async function toggleChunk(id: string, enabled: boolean) {
    if (savingChunks.has(id)) return;
    setSavingChunks(previous => new Set(previous).add(id));
    try { await repository.setChunkEnabled(documentId, id, enabled); toast.success(enabled ? "分块已启用" : "分块已停用"); }
    catch (error) { toast.error(error instanceof Error ? error.message : "更新失败"); }
    finally { setSavingChunks(previous => { const next = new Set(previous); next.delete(id); return next; }); }
  }
  return <section className="flex min-h-0 flex-1 flex-col">
    <header className="flex shrink-0 items-center justify-between gap-4 border-b px-5 pb-4 pt-16 md:px-6 md:pt-4">
      <div className="flex min-w-0 items-center gap-3">
        <Button variant="ghost" size="icon" asChild><Link href="/knowledge" aria-label="返回知识库"><ArrowLeftIcon /></Link></Button>
        <div className="min-w-0"><h1 className="truncate text-base font-semibold">{document.filename}</h1><p className="mt-1 text-xs text-muted-foreground">{strategyLabels[document.strategy]}<span className="mx-2">·</span>版本 {document.activeRevision ?? document.revision}<span className="mx-2">·</span>{document.chunks.length} 个分块</p></div>
        <div className="hidden shrink-0 sm:block"><DocumentStatusBadge status={document.status} /></div>
      </div>
      <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon" aria-label="文档操作"><MoreHorizontalIcon /></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuGroup><DropdownMenuItem disabled={!document.sourceUrl} onClick={() => { if (document.sourceUrl) void authFetch(document.sourceUrl).then(async response => { if (!response.ok) throw new Error("无法读取原文件"); const url = URL.createObjectURL(await response.blob()); const link = globalThis.document.createElement("a"); link.href = url; link.download = document.filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }).catch(() => toast.error("原文件下载失败")); }}><ExternalLinkIcon />打开原文件</DropdownMenuItem></DropdownMenuGroup><DropdownMenuSeparator /><DropdownMenuGroup><DropdownMenuItem variant="destructive" disabled={user?.role !== "admin"} onClick={() => setRemoveOpen(true)}><Trash2Icon />删除文档</DropdownMenuItem></DropdownMenuGroup></DropdownMenuContent></DropdownMenu>
    </header>
    {ready && document.activeRevision !== document.revision && <Alert className="rounded-none border-x-0 border-t-0"><AlertDescription>新版本{document.status === "failed" ? "处理失败" : "正在处理"}，以下保留版本 {document.activeRevision} 的可用分块。{document.error}</AlertDescription></Alert>}
    {initialChunkId && !document.chunks.some(chunk => chunk.id === initialChunkId) && <p role="status" className="border-b px-7 py-3 text-xs text-muted-foreground">引用对应的分块已变更。当前展示这份文档的最新分块。</p>}
    {!ready ? <Empty className="flex-1"><EmptyHeader><EmptyMedia variant="icon"><LayersIcon /></EmptyMedia><EmptyTitle>{document.status === "failed" ? "文档处理失败" : "正在准备文档分块"}</EmptyTitle><EmptyDescription>{document.error ?? "后台正在解析、分块与向量化，完成后会自动更新。"}</EmptyDescription></EmptyHeader><DocumentStatusBadge status={document.status} /></Empty> : <>
      <Tabs value={mobilePanel} onValueChange={setMobilePanel} className="shrink-0 px-5 py-2 lg:hidden"><TabsList className="w-full"><TabsTrigger value="source">原文</TabsTrigger><TabsTrigger value="chunks">分块</TabsTrigger></TabsList></Tabs>
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1.06fr)_minmax(0,1fr)]">
        <div className={cn("min-h-0 min-w-0 flex-col border-r lg:flex", mobilePanel === "source" ? "flex" : "hidden")}><div className="flex h-12 shrink-0 items-center justify-between border-b px-5"><h2 className="flex items-center gap-2 text-sm font-medium"><FileTextIcon className="size-4 text-muted-foreground" />原文</h2><div className="flex items-center gap-2"><HighlighterIcon className="size-3.5 text-muted-foreground" /><label htmlFor="source-highlight" className="text-xs text-muted-foreground">高亮</label><Switch id="source-highlight" size="sm" checked={highlight && document.sourceMapAvailable} disabled={!document.sourceMapAvailable} onCheckedChange={setHighlight} /></div></div><SourceViewer document={document} selectedBlockIds={selectedBlockIds} navigationRequest={navigationRequest} highlight={highlight} onBlockSelect={blockId => { const chunk = document.chunks.find(chunk => chunk.blockIds.includes(blockId)); if (chunk) { selectChunk(chunk.id); globalThis.document.getElementById(`chunk-${chunk.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }); } }} /></div>
        <div className={cn("min-h-0 min-w-0 flex-col lg:flex", mobilePanel === "chunks" ? "flex" : "hidden")}><div className="flex h-12 shrink-0 items-center justify-between border-b px-5"><h2 className="text-sm font-medium">文档分块<span className="ml-2 font-normal text-muted-foreground">{document.chunks.length}</span></h2><span className="text-xs text-muted-foreground">{document.chunks.filter(chunk => chunk.enabled).length} 个已启用</span></div><div className="shrink-0 border-b px-5 py-3"><InputGroup><InputGroupInput aria-label="搜索分块" placeholder="搜索分块内容…" value={query} onChange={event => setQuery(event.target.value)} /><InputGroupAddon><SearchIcon /></InputGroupAddon></InputGroup></div><div className="min-h-0 flex-1 overflow-y-auto p-4 lg:p-5">
          <div className="flex flex-col gap-3">{filtered.map(chunk => { const index = document.chunks.indexOf(chunk); const sourceBlocks = document.blocks.filter(block => chunk.blockIds.includes(block.id)); const pages = [...new Set(sourceBlocks.map(block => block.page))]; return <article id={`chunk-${chunk.id}`} key={chunk.id} className={cn("chunk-card overflow-hidden rounded-xl border transition-colors", selectedChunk?.id === chunk.id && "chunk-card-selected", !chunk.enabled && "opacity-60")}>
            <button type="button" onClick={() => selectChunk(chunk.id)} className="flex w-full items-center gap-2 p-4 text-left outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring" aria-pressed={selectedChunk?.id === chunk.id} aria-label={`分块 ${index + 1}：${chunk.title}`}><span className="text-xs font-medium tabular-nums text-muted-foreground">{String(index + 1).padStart(2, "0")}</span><span className="min-w-0 flex-1 truncate text-sm font-medium">{chunk.title}</span>{chunk.kind === "table" && <Badge variant="outline">完整表格</Badge>}<span className="shrink-0 text-[11px] text-muted-foreground">{chunk.text.length} 字符</span></button>
            <div className="px-4 pb-4" onClick={() => selectChunk(chunk.id)}><ExpandableMarkdown content={chunk.text} /></div>
            <footer className="flex items-center justify-between gap-3 border-t border-border/60 px-4 py-2.5"><span className="truncate text-[11px] text-muted-foreground">{document.format === "pdf" ? (pages.length ? `第 ${pages.join("、")} 页` : "页码不可用") : "Markdown"}<span className="mx-1.5">·</span>{sourceBlocks.map(block => block.clause).filter(Boolean).join("、") || `段落 ${index + 1}`}</span><div className="flex shrink-0 items-center gap-2"><label htmlFor={`enable-${chunk.id}`} className="text-[11px] text-muted-foreground">{chunk.enabled ? "已启用" : "已停用"}</label><Switch id={`enable-${chunk.id}`} size="sm" checked={chunk.enabled} disabled={user?.role !== "admin" || savingChunks.has(chunk.id)} onCheckedChange={enabled => void toggleChunk(chunk.id, enabled)} /></div></footer>
          </article>; })}</div>
          {!filtered.length && <Empty><EmptyHeader><EmptyTitle>没有匹配的分块</EmptyTitle><EmptyDescription>试试更短的关键词。</EmptyDescription></EmptyHeader></Empty>}
        </div></div>
      </div>
    </>}
    {removeOpen && <RemoveDocumentDialog document={document} onClose={() => setRemoveOpen(false)} onRemoved={() => router.push("/knowledge")} />}
  </section>;
}
