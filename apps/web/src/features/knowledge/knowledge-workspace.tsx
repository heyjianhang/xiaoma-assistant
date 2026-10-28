"use client";

import Link from "next/link";
import { useState } from "react";
import { BookOpenIcon, ChevronLeftIcon, ChevronRightIcon, FileTextIcon, FileTypeIcon, MoreHorizontalIcon, SearchIcon, UploadIcon, RefreshCwIcon, Trash2Icon, ArrowUpRightIcon, CircleAlertIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WorkspacePage, WorkspaceToolbar } from "@/components/workspace-page";
import { useKnowledgeViewState, useWorkspace } from "@/lib/services/provider";
import type { KnowledgeDocument } from "@/lib/services/contracts";
import { processingStatuses, strategyLabels } from "@/lib/services/knowledge-config";
import { DocumentStatusBadge } from "./document-status";
import { UploadDialog } from "./upload-dialog";
import { RemoveDocumentDialog, ReprocessDialog } from "./document-actions";
import { RetrievalTestPanel } from "./retrieval-panels";

export function formatBytes(bytes: number) { return bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`; }

import { useAccess } from "@/lib/access/provider";

export function KnowledgeWorkspace() {
  const { user } = useAccess();
  const canManage = user?.role === "admin";
  const { documents, loading, connectionError, repository } = useWorkspace();
  const { activeTab, setActiveTab: setTab } = useKnowledgeViewState();
  const tab = activeTab === "testing" ? "testing" : "documents";
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [remove, setRemove] = useState<KnowledgeDocument>();
  const [reprocess, setReprocess] = useState<KnowledgeDocument>();
  const [failed, setFailed] = useState<string>();
  const filtered = documents.filter(document => document.filename.toLowerCase().includes(query.toLowerCase()) && (status === "all" || (status === "processing" ? !["ready", "failed"].includes(document.status) : status === document.status)));
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const visibleDocuments = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  return <WorkspacePage title="知识库">
      {connectionError && <Alert variant="destructive"><AlertDescription className="flex items-center justify-between gap-3">{connectionError}<Button variant="outline" size="sm" onClick={() => void repository.refresh()}>重试连接</Button></AlertDescription></Alert>}
      <Tabs value={tab} onValueChange={setTab} className="min-h-0 flex-1 gap-4 overflow-hidden">
        <WorkspaceToolbar>
          <TabsList aria-label="知识库功能"><TabsTrigger value="documents" className="px-3">文档管理</TabsTrigger><TabsTrigger value="testing" className="px-3">检索测试</TabsTrigger></TabsList>
          <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
            {tab === "documents" && <><InputGroup className="w-28 lg:w-44 xl:w-60"><InputGroupInput aria-label="搜索文档" placeholder="搜索文档" value={query} onChange={event => { setQuery(event.target.value); setPage(1); }} /><InputGroupAddon><SearchIcon /></InputGroupAddon></InputGroup><Select value={status} onValueChange={value => { setStatus(value); setPage(1); }}><SelectTrigger aria-label="文档状态筛选" className="w-26 lg:w-28"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="all">全部状态</SelectItem><SelectItem value="ready">可检索</SelectItem><SelectItem value="processing">处理中</SelectItem><SelectItem value="failed">处理失败</SelectItem></SelectGroup></SelectContent></Select></>}
            {tab === "documents" && canManage && <Button onClick={() => setUploadOpen(true)}><UploadIcon data-icon="inline-start" />上传文档</Button>}
          </div>
        </WorkspaceToolbar>
        <TabsContent value="documents" className="m-0 flex min-h-0 flex-1 flex-col">
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border">
            <div role="region" aria-label="文档列表滚动区域" tabIndex={0} className="min-h-0 flex-1 overflow-auto overscroll-contain outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring [&_[data-slot=table-container]]:overflow-visible">
            <Table><TableHeader className="sticky top-0 z-10 bg-background"><TableRow className="hover:bg-transparent"><TableHead className="w-[35%] pl-4">文档名称</TableHead><TableHead>处理状态</TableHead><TableHead>分块</TableHead><TableHead className="hidden lg:table-cell">分块策略</TableHead><TableHead className="hidden xl:table-cell">更新时间</TableHead><TableHead className="w-12"><span className="sr-only">操作</span></TableHead></TableRow></TableHeader>
              <TableBody>{visibleDocuments.map(document => <TableRow key={document.id}>
                <TableCell className="py-3 pl-4"><div className="flex items-center gap-3"><div className="flex size-9 shrink-0 items-center justify-center rounded-lg border bg-background">{document.format === "pdf" ? <FileTextIcon className="size-4 text-muted-foreground" strokeWidth={1.5} /> : <FileTypeIcon className="size-4 text-muted-foreground" strokeWidth={1.5} />}</div><div className="min-w-0"><Link href={`/knowledge/${document.id}`} className="line-clamp-1 text-sm font-medium hover:underline">{document.filename}</Link><p className="mt-1 text-xs text-muted-foreground">{document.format.toUpperCase()}<span className="mx-1.5">·</span>{formatBytes(document.bytes)}{document.format === "pdf" && document.pages > 0 && <><span className="mx-1.5">·</span>{document.pages} 页</>}</p></div></div></TableCell>
                <TableCell><div className="flex items-center gap-1.5"><DocumentStatusBadge status={document.status} />{document.status === "failed" && <Button variant="ghost" size="icon-xs" aria-label={`查看 ${document.filename} 的失败原因`} onClick={() => setFailed(failed === document.id ? undefined : document.id)}><CircleAlertIcon /></Button>}</div>{failed === document.id && <p className="mt-2 max-w-52 text-xs leading-5 text-destructive">{document.error}</p>}</TableCell>
                <TableCell className="tabular-nums text-muted-foreground">{document.activeRevision ? document.chunkCount : "—"}</TableCell><TableCell className="hidden text-muted-foreground lg:table-cell">{strategyLabels[document.strategy]}</TableCell><TableCell className="hidden text-xs text-muted-foreground xl:table-cell">{document.updatedAt}</TableCell>
                <TableCell className="pr-4"><DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon" aria-label={`${document.filename} 的操作`}><MoreHorizontalIcon /></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuGroup><DropdownMenuItem asChild disabled={!document.activeRevision}><Link href={`/knowledge/${document.id}`}><ArrowUpRightIcon />查看分块</Link></DropdownMenuItem><DropdownMenuItem disabled={!canManage || processingStatuses.has(document.status)} onClick={() => setReprocess(document)}><RefreshCwIcon />重新处理</DropdownMenuItem></DropdownMenuGroup><DropdownMenuSeparator /><DropdownMenuGroup><DropdownMenuItem variant="destructive" disabled={!canManage} onClick={() => setRemove(document)}><Trash2Icon />删除文档</DropdownMenuItem></DropdownMenuGroup></DropdownMenuContent></DropdownMenu></TableCell>
              </TableRow>)}</TableBody></Table>
            {loading && <div role="status" aria-label="正在加载文档" className="flex flex-col gap-5 p-5">{[1, 2, 3].map(item => <Skeleton key={item} className="h-12 w-full" />)}</div>}
            {!loading && !connectionError && !filtered.length && <Empty className="py-20"><EmptyHeader><EmptyMedia variant="icon"><BookOpenIcon /></EmptyMedia><EmptyTitle>{documents.length ? "没有找到匹配的文档" : "添加第一份业务文档"}</EmptyTitle><EmptyDescription>{documents.length ? "试试其他关键词或处理状态。" : "上传 PDF 或 Markdown，建立可追溯的业务知识。"}</EmptyDescription></EmptyHeader>{!documents.length && canManage && <Button onClick={() => setUploadOpen(true)}>上传文档</Button>}</Empty>}
            </div>
            <footer className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t bg-background px-4 py-3">
              <p className="text-xs text-muted-foreground">共 {filtered.length} 份文档</p>
              <div className="flex items-center gap-4"><div className="flex items-center gap-2"><span className="hidden text-xs text-muted-foreground sm:inline">每页</span><Select value={String(pageSize)} onValueChange={value => { setPageSize(Number(value)); setPage(1); }}><SelectTrigger aria-label="每页文档数量" className="w-18"><SelectValue /></SelectTrigger><SelectContent><SelectGroup>{[5, 10, 20, 50].map(size => <SelectItem key={size} value={String(size)}>{size}</SelectItem>)}</SelectGroup></SelectContent></Select></div><div className="flex items-center gap-2"><Button variant="outline" size="icon" aria-label="上一页文档" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}><ChevronLeftIcon /></Button><span aria-live="polite" className="min-w-14 text-center text-xs tabular-nums text-muted-foreground">{currentPage} / {pageCount}</span><Button variant="outline" size="icon" aria-label="下一页文档" disabled={currentPage >= pageCount} onClick={() => setPage(currentPage + 1)}><ChevronRightIcon /></Button></div></div>
            </footer>
          </div>
        </TabsContent>
        <TabsContent value="testing" className="m-0 flex min-h-0 flex-1 flex-col overflow-hidden"><RetrievalTestPanel /></TabsContent>
      </Tabs>
    {uploadOpen && <UploadDialog open onOpenChange={setUploadOpen} />}
    {remove && <RemoveDocumentDialog document={remove} onClose={() => setRemove(undefined)} />}
    {reprocess && <ReprocessDialog document={reprocess} onClose={() => setReprocess(undefined)} />}
  </WorkspacePage>;
}
