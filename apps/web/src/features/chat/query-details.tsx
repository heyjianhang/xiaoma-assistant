"use client";

import { trackActivity, useActivityView } from "@/lib/access/activity";
import { CodeIcon, CopyIcon } from "lucide-react";
import { toast } from "sonner";
import { CodeBlock } from "@/components/ai-elements/code-block";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { DataColumn, QuerySample, SampleRow } from "./presentation-types";

const fieldLabels: Record<string, DataColumn> = Object.fromEntries([
  ["paid_orders", "支付订单", "number"], ["refunded_orders", "退款订单", "number"], ["refund_sheets", "成功退款单", "number"],
  ["refunded_quantity", "退款件数", "number"], ["refund_amount", "退款金额", "money"], ["category_paid_amount", "品类实付金额", "money"],
  ["refund_rate_percent", "订单退款率", "percent"], ["order_id", "订单编号"], ["refund_no", "退款编号"], ["refund_status", "退款状态"],
  ["applied_at", "申请时间", "date"], ["accepted_at", "验收时间", "date"], ["completed_at", "完成时间", "date"], ["version", "制度版本"],
  ["payment_channel", "支付渠道"], ["limit_hours", "时限", "hours"], ["elapsed_hours", "实际耗时", "hours"], ["assessment", "核对结果"],
].map(([key, label, format]) => [key, { key, label, format: format as DataColumn["format"] }]));

export function formatValue(value: SampleRow[string], format?: DataColumn["format"]): string {
  if (value === null || value === undefined) return format === "percent" || format === "hours" ? "未定义" : "—";
  if (format === "money") return new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", minimumFractionDigits: 2 }).format(Number(value));
  if (format === "number") return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(Number(value));
  if (format === "percent") return `${value}%`;
  if (format === "hours") return `${value} 小时`;
  if (format === "date") return String(value).replace("T", " ");
  return String(value);
}
export function SampleTable({ result, columns }: { result: QuerySample; columns?: DataColumn[] }) {
  const fields: DataColumn[] = columns ?? Object.keys(result.rows[0] ?? {}).map(key => fieldLabels[key] ?? { key, label: key });
  if (!result.rows.length) return <Empty><EmptyHeader><EmptyTitle>没有符合条件的记录</EmptyTitle><EmptyDescription>保留筛选条件供核对，不生成补齐数字。</EmptyDescription></EmptyHeader></Empty>;
  return <div className="max-h-80 min-w-0 max-w-full overflow-auto"><Table aria-label="查询数据"><TableHeader><TableRow>{fields.map(column => <TableHead key={column.key}>{column.label}</TableHead>)}</TableRow></TableHeader><TableBody>{result.rows.map((row, index) => <TableRow key={index}>{fields.map(column => <TableCell key={column.key}>{formatValue(row[column.key], column.format)}</TableCell>)}</TableRow>)}</TableBody></Table></div>;
}
export function SampleSql({ result }: { result: QuerySample }) {
  const path = typeof window === "undefined" ? "/chat" : window.location.pathname;
  useActivityView("sql_view", { path, target_id: path === "/project" ? undefined : result.id });
  return <div className="flex min-w-0 flex-col gap-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><Badge variant="outline">{(result.executed || result.provenance.startsWith("真实只读")) ? "SQL 已实际执行 · 只读" : "参考 SQL"}</Badge><Button size="sm" variant="ghost" onClick={() => void navigator.clipboard.writeText(result.sql).then(() => toast.success("已复制 SQL")).catch(() => toast.error("当前浏览器不允许写入剪贴板"))}><CopyIcon data-icon="inline-start" />复制 SQL</Button></div>
    <div className="max-h-80 overflow-auto"><CodeBlock code={result.sql} language="sql" /></div>
  </div>;
}
export function QueryDetailsButton({ result }: { result: QuerySample }) {
  return <Dialog onOpenChange={open => { if (open) trackActivity("sql_view", { target_id: window.location.pathname === "/project" ? undefined : result.id }); }}><DialogTrigger asChild><Button size="sm" variant="outline"><CodeIcon data-icon="inline-start" />数据与 SQL</Button></DialogTrigger><DialogContent className="max-h-[85svh] min-w-0 overflow-hidden sm:max-w-3xl">
    <DialogHeader><DialogTitle>数据与 SQL</DialogTitle><DialogDescription>{result.scope}</DialogDescription></DialogHeader>
    <Tabs defaultValue="data" className="min-h-0 min-w-0"><TabsList><TabsTrigger value="data">数据</TabsTrigger><TabsTrigger value="sql">SQL</TabsTrigger><TabsTrigger value="schema">选表与字段</TabsTrigger></TabsList>
      <TabsContent value="data" className="min-h-0 min-w-0"><SampleTable result={result} /></TabsContent>
      <TabsContent value="sql" className="min-h-0 min-w-0"><SampleSql result={result} /></TabsContent>
      <TabsContent value="schema" className="min-h-0 min-w-0"><div className="flex max-h-80 min-w-0 flex-col gap-4 overflow-auto py-3">{Object.entries(result.schema.tables).map(([table, columns]) => <div key={table} className="flex flex-col gap-1"><p className="font-mono font-medium">{table}</p><p className="break-words font-mono text-xs leading-6 text-muted-foreground">{columns.join(" · ")}</p></div>)}<p className="text-sm">{result.schema.grain}</p>{result.schema.joins.map(join => <p key={join} className="break-words font-mono text-xs text-muted-foreground">{join}</p>)}</div></TabsContent>
    </Tabs><p title={result.provenance} className="break-words text-xs leading-5 text-muted-foreground">{(result.executed || result.provenance.startsWith("真实只读")) ? `真实只读查询 · ${result.elapsed_ms ?? 0} ms` : "历史结果快照"}</p>
  </DialogContent></Dialog>;
}
