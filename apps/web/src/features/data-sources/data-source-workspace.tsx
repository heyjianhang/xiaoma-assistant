"use client";
import { authFetch } from "@/lib/access/client";

import { useEffect, useState } from "react";
import { ChevronLeftIcon, ChevronRightIcon, DatabaseIcon, EyeIcon, KeyRoundIcon, SearchIcon, Table2Icon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WorkspacePage, WorkspaceToolbar } from "@/components/workspace-page";
import { formatBusinessValue, type BusinessTablePreview, type BusinessColumn, type BusinessRow, type BusinessValue } from "@/lib/services/business-types";
import { cn } from "@/lib/utils";

function CellValue({ column, value }: { column: BusinessColumn; value: BusinessValue }) {
  if (value === null || value === undefined) return <span title="NULL" className="text-muted-foreground">—</span>;
  const formatted = formatBusinessValue(column, value);
  if (column.name.endsWith("_status")) return <Badge variant={value === "fulfilled" || value === "completed" || value === "approved" ? "secondary" : "outline"} title={String(value)}>{formatted}</Badge>;
  return <span title={String(value)} className={cn(column.type.startsWith("numeric") && "tabular-nums", column.type === "integer" && "font-mono text-xs")}>{formatted}</span>;
}

export function DataSourceWorkspace() {
  const [selected, setSelected] = useState("orders");
  const [view, setView] = useState("data");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [record, setRecord] = useState<BusinessRow | null>(null);
  const [businessTables, setBusinessTables] = useState<BusinessTablePreview[]>([]);
  const [visibleRows, setVisibleRows] = useState<BusinessRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [loadedRequest, setLoadedRequest] = useState("");
  const [catalogError, setCatalogError] = useState("");
  const [rowsError, setRowsError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    async function load() {
      setLoadingCatalog(true); setCatalogError("");
      try {
        const response = await authFetch("/api/v1/business/tables", { signal: abort.signal, cache: "no-store" });
        const body = await response.json();
        if (!response.ok) throw new Error(body.message ?? "无法读取业务表");
        if (!abort.signal.aborted) setBusinessTables(body.items);
      } catch (error) {
        if (!abort.signal.aborted) setCatalogError(error instanceof Error ? error.message : "无法连接业务数据库");
      } finally { if (!abort.signal.aborted) setLoadingCatalog(false); }
    }
    void load(); return () => abort.abort();
  }, [reload]);
  const table = businessTables.find(table => table.name === selected) ?? businessTables[0];
  const tableName = table?.name;
  const requestKey = JSON.stringify([tableName, query, page, pageSize, reload]);
  const loadingRows = loadedRequest !== requestKey;
  useEffect(() => {
    if (!tableName) return;
    const abort = new AbortController();
    const timer = setTimeout(async () => {
      setRowsError("");
      try {
        const params = new URLSearchParams({ q: query, limit: String(pageSize), offset: String((page - 1) * pageSize) });
        const response = await authFetch(`/api/v1/business/tables/${tableName}/rows?${params}`, { signal: abort.signal, cache: "no-store" });
        const body = await response.json();
        if (!response.ok) throw new Error(body.message ?? "读取数据失败");
        if (!abort.signal.aborted) { setVisibleRows(body.items); setTotal(body.total); }
      } catch (error) {
        if (!abort.signal.aborted) { setRowsError(error instanceof Error ? error.message : "读取数据失败"); setVisibleRows([]); }
      } finally { if (!abort.signal.aborted) setLoadedRequest(requestKey); }
    }, 180);
  return () => { clearTimeout(timer); abort.abort(); };
  }, [tableName, query, page, pageSize, reload, requestKey]);
  const previewColumns = table?.previewColumns.map(name => table.columns.find(column => column.name === name)).filter((column): column is BusinessColumn => !!column) ?? [];
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = page;

  function changeTable(name: string) {
    setSelected(name);
    setQuery("");
    setPage(1);
    setRecord(null);
  }

  if (loadingCatalog) return <WorkspacePage title="数据源"><Skeleton className="h-12 w-full" /><Skeleton className="h-96 w-full" /></WorkspacePage>;
  if (catalogError || !table) return <WorkspacePage title="数据源"><Alert variant="destructive"><AlertDescription>{catalogError || "业务库暂无数据"}<Button variant="outline" size="sm" onClick={() => setReload(value => value + 1)}>重试</Button></AlertDescription></Alert></WorkspacePage>;


  return (
    <WorkspacePage title="数据源">
      <div className="flex min-h-0 flex-1 flex-col gap-4">
        <WorkspaceToolbar>
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <DatabaseIcon className="size-4 shrink-0 text-muted-foreground" />
            <span className="text-sm font-medium">食品电商业务库</span>
            <Badge variant="outline"><KeyRoundIcon />只读</Badge>

          </div>
          <span className="text-xs text-muted-foreground">PostgreSQL · {businessTables.length} 张关联表</span>
        </WorkspaceToolbar>

        <div className="grid min-h-0 flex-1 gap-4 @2xl/workspace:grid-cols-[200px_minmax(0,1fr)]">
          <nav aria-label="业务表" className="hidden min-h-0 flex-col gap-1 overflow-y-auto rounded-xl border p-2 @2xl/workspace:flex">
            {businessTables.map(item => (
              <Button key={item.name} variant={selected === item.name ? "secondary" : "ghost"} aria-pressed={selected === item.name} className="h-auto justify-start px-3 py-3" onClick={() => changeTable(item.name)}>
                <Table2Icon data-icon="inline-start" />
                <span className="flex min-w-0 flex-col items-start gap-1">
                  <span className="max-w-full truncate">{item.title}<span className="ml-2 text-xs font-normal text-muted-foreground">{item.name}</span></span>
                  <span className="text-xs font-normal text-muted-foreground">{item.rowCount.toLocaleString("zh-CN")} 行</span>
                </span>
              </Button>
            ))}
          </nav>

          <Tabs value={view} onValueChange={setView} className="min-h-0 gap-0 overflow-hidden rounded-xl border">
            <header className="flex shrink-0 flex-col gap-3 border-b p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0"><h2 className="text-sm font-medium">{table.title}<span className="ml-2 font-mono text-xs font-normal text-muted-foreground">{table.name}</span></h2></div>
                <Select value={selected} onValueChange={changeTable}>
                  <SelectTrigger aria-label="选择业务表" className="w-44 @2xl/workspace:hidden"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectGroup>{businessTables.map(item => <SelectItem key={item.name} value={item.name}>{item.title} · {item.name}</SelectItem>)}</SelectGroup></SelectContent>
                </Select>
              </div>
              <p title={table.description} className="line-clamp-1 text-xs text-muted-foreground">{table.description}</p>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <TabsList aria-label="数据源视图"><TabsTrigger value="data" className="px-3">数据预览</TabsTrigger><TabsTrigger value="schema" className="px-3">表结构</TabsTrigger></TabsList>
                {view === "data" && <InputGroup className="w-full sm:w-44"><InputGroupInput aria-label="搜索业务数据" placeholder="搜索全部数据" value={query} onChange={event => { setQuery(event.target.value); setPage(1); }} /><InputGroupAddon><SearchIcon /></InputGroupAddon></InputGroup>}
              </div>
            </header>

            <TabsContent value="data" className="m-0 flex min-h-0 flex-1 flex-col">
              <div role="region" aria-label="业务数据预览" tabIndex={0} className="min-h-0 flex-1 overflow-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring [&_[data-slot=table-container]]:overflow-visible">
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-background"><TableRow className="hover:bg-transparent">
                    {previewColumns.map((column, index) => <TableHead key={column.name} className={cn("py-3", index === 0 && "pl-4", column.type.startsWith("numeric") && "text-right")}><div className="flex flex-col gap-0.5"><span>{column.label}</span><span className="font-mono text-[10px] font-normal text-muted-foreground">{column.name}</span></div></TableHead>)}
                    <TableHead className="w-10 pr-4"><span className="sr-only">查看记录</span></TableHead>
                  </TableRow></TableHeader>
                  <TableBody>{!loadingRows && visibleRows.map(row => <TableRow key={String(row[table.primaryKey])}>
                    {previewColumns.map((column, index) => <TableCell key={column.name} className={cn("py-3 text-xs", index === 0 && "pl-4", column.type.startsWith("numeric") && "text-right")}><CellValue column={column} value={row[column.name]} /></TableCell>)}
                    <TableCell className="pr-4"><Button variant="ghost" size="icon-xs" aria-label={`查看${table.title}记录 ${row[table.primaryKey]}`} onClick={() => setRecord(row)}><EyeIcon /></Button></TableCell>
                  </TableRow>)}</TableBody>
                </Table>
                {loadingRows && <div role="status" className="p-4"><Skeleton className="h-40 w-full" /></div>}
                {rowsError && <Alert variant="destructive"><AlertDescription>{rowsError}<Button variant="outline" size="sm" onClick={() => setReload(value => value + 1)}>重试</Button></AlertDescription></Alert>}
                {!loadingRows && !rowsError && !total && <Empty className="min-h-64"><EmptyHeader><EmptyMedia variant="icon"><SearchIcon /></EmptyMedia><EmptyTitle>没有匹配的数据</EmptyTitle><EmptyDescription>请调整搜索条件。</EmptyDescription></EmptyHeader></Empty>}
              </div>
              <footer className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t px-4 py-3">
                <p className="text-xs text-muted-foreground">{query.trim() ? `匹配 ${total.toLocaleString("zh-CN")} 行` : `共 ${total.toLocaleString("zh-CN")} 行`}</p>
                <div className="flex items-center gap-3">
                  <Select value={String(pageSize)} onValueChange={value => { setPageSize(Number(value)); setPage(1); }}><SelectTrigger aria-label="每页数据数量" className="w-18"><SelectValue /></SelectTrigger><SelectContent><SelectGroup>{[10, 20, 30].map(size => <SelectItem key={size} value={String(size)}>{size}</SelectItem>)}</SelectGroup></SelectContent></Select>
                  <div className="flex items-center gap-2"><Button variant="outline" size="icon" aria-label="上一页数据" disabled={loadingRows || currentPage <= 1} onClick={() => setPage(currentPage - 1)}><ChevronLeftIcon /></Button><span aria-live="polite" className="min-w-12 text-center text-xs tabular-nums text-muted-foreground">{currentPage} / {pageCount}</span><Button variant="outline" size="icon" aria-label="下一页数据" disabled={loadingRows || currentPage >= pageCount} onClick={() => setPage(currentPage + 1)}><ChevronRightIcon /></Button></div>
                </div>
              </footer>
            </TabsContent>

            <TabsContent value="schema" className="m-0 flex min-h-0 flex-1 flex-col">
              <div role="region" aria-label="字段列表" tabIndex={0} className="min-h-0 flex-1 overflow-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring [&_[data-slot=table-container]]:overflow-visible">
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-background"><TableRow className="hover:bg-transparent"><TableHead className="pl-4">字段</TableHead><TableHead>类型</TableHead><TableHead>业务含义</TableHead></TableRow></TableHeader>
                  <TableBody>{table.columns.map(column => <TableRow key={column.name}><TableCell className="py-3 pl-4"><div className="flex flex-col gap-1"><span className="font-mono text-xs">{column.name}</span><span className="flex items-center gap-1.5 text-xs text-muted-foreground">{column.label}{column.constraints.includes("PRIMARY KEY") ? <Badge variant="outline">主键</Badge> : column.constraints.includes("REFERENCES") ? <Badge variant="outline">外键</Badge> : null}</span></div></TableCell><TableCell className="font-mono text-xs text-muted-foreground">{column.type}</TableCell><TableCell className="min-w-48 whitespace-normal text-sm leading-6">{column.description}</TableCell></TableRow>)}</TableBody>
                </Table>
              </div>
              <footer className="shrink-0 border-t px-4 py-3 text-xs text-muted-foreground">共 {table.columns.length} 个字段 · 表结构来自 PostgreSQL</footer>
            </TabsContent>
          </Tabs>
        </div>
      </div>

      <Dialog open={record !== null} onOpenChange={open => { if (!open) setRecord(null); }}>
        <DialogContent className="flex max-h-[85svh] flex-col overflow-hidden sm:max-w-2xl">
          <DialogHeader><DialogTitle>{table.title} · 记录 {record?.[table.primaryKey]}</DialogTitle><DialogDescription>查看这条记录的全部字段。</DialogDescription></DialogHeader>
          <div className="min-h-0 overflow-auto rounded-lg border">
            <Table><TableHeader><TableRow><TableHead className="pl-4">字段</TableHead><TableHead>值</TableHead></TableRow></TableHeader><TableBody>{record && table.columns.map(column => <TableRow key={column.name}><TableCell className="py-3 pl-4"><div className="flex flex-col gap-1"><span>{column.label}</span><span className="font-mono text-xs text-muted-foreground">{column.name}</span></div></TableCell><TableCell className="whitespace-normal break-words"><CellValue column={column} value={record[column.name]} /></TableCell></TableRow>)}</TableBody></Table>
          </div>
          <DialogFooter><DialogClose asChild><Button variant="outline">关闭</Button></DialogClose></DialogFooter>
        </DialogContent>
      </Dialog>
    </WorkspacePage>
  );
}
