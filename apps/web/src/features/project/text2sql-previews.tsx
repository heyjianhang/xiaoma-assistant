"use client";

import { ArrowRightIcon, DatabaseIcon, KeyRoundIcon, LinkIcon } from "lucide-react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { MarkdownPreview } from "@/components/markdown-preview";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import sample from "./fixtures/sql-walkthrough.json";

export const inspectedFields = sample.inspected.reduce((count, table) => count + table.columns.length, 0);
export const linkedFields = Object.values(sample.linked.tables).reduce((count, fields) => count + fields.length, 0);
const money = new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" });
const chartConfig = { refund_amount: { label: "成功退款金额（元）", color: "var(--brand)" } } satisfies ChartConfig;

export function CatalogPreview() {
  return <Card className="min-w-0">
    <CardHeader><CardTitle className="flex items-center justify-between gap-3"><span>业务目录</span><Badge variant="outline">{sample.catalog.length} 张表</Badge></CardTitle></CardHeader>
    <CardContent className="min-w-0">
      <div role="region" aria-label="表目录预览" tabIndex={0} className="max-h-80 overflow-y-auto overscroll-contain rounded-lg border">
        <Table><TableHeader><TableRow><TableHead>表名</TableHead><TableHead>业务说明</TableHead></TableRow></TableHeader><TableBody>
          {sample.catalog.map(table => <TableRow key={table.name}><TableCell className="align-top"><code>{table.name}</code></TableCell><TableCell className="min-w-56 whitespace-normal align-top">{table.description}</TableCell></TableRow>)}
        </TableBody></Table>
      </div>
    </CardContent>
  </Card>;
}

export function SchemaPreview() {
  return <Card className="min-w-0">
    <CardHeader><CardTitle className="flex flex-wrap items-center justify-between gap-3"><span>候选表结构</span><Badge variant="outline">4 张表 · {inspectedFields} 个字段</Badge></CardTitle></CardHeader>
    <CardContent className="min-w-0">
      <Tabs defaultValue="refunds" className="min-w-0 gap-4">
        <div className="min-w-0 overflow-x-auto"><TabsList aria-label="候选表结构">{sample.inspected.map(table => <TabsTrigger key={table.table} value={table.table}>{table.title}</TabsTrigger>)}</TabsList></div>
        {sample.inspected.map(table => <TabsContent key={table.table} value={table.table} className="m-0 min-w-0">
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2"><code className="font-medium">{table.table}</code><Badge variant="secondary"><KeyRoundIcon data-icon="inline-start" />{table.primary_key}</Badge></div>
            <div role="region" tabIndex={0} aria-label={`${table.title}字段`} className="max-h-64 overflow-y-auto overscroll-contain rounded-lg border">
              <Table><TableHeader><TableRow><TableHead>字段</TableHead><TableHead>类型</TableHead><TableHead>业务含义</TableHead></TableRow></TableHeader><TableBody>
                {table.columns.map(column => {
                  const reference = column.constraints.match(/REFERENCES\s+([a-z_][a-z0-9_]*)\(([^)]+)\)/i);
                  return <TableRow key={column.name}>
                    <TableCell className="align-top"><code>{column.name}</code></TableCell><TableCell className="align-top text-xs text-muted-foreground">{column.type}</TableCell>
                    <TableCell className="min-w-48 whitespace-normal align-top"><div className="flex flex-col gap-1"><span>{column.description}</span>{reference && <span className="flex items-center gap-1 text-xs text-muted-foreground"><ArrowRightIcon aria-hidden="true" className="size-3 shrink-0" /><code>{reference[1]}.{reference[2]}</code></span>}</div></TableCell>
                  </TableRow>;
                })}
              </TableBody></Table>
            </div>
          </div>
        </TabsContent>)}
      </Tabs>
    </CardContent>
  </Card>;
}

export function LinkingPreview() {
  return <Card tone="info" className="min-w-0">
    <CardHeader><CardTitle className="flex flex-wrap items-center justify-between gap-3"><span className="flex items-center gap-2"><LinkIcon aria-hidden="true" className="size-4" />本次 SQL 的使用范围</span><Badge variant="outline">4 张表 · {linkedFields} 个字段</Badge></CardTitle></CardHeader>
    <CardContent className="flex min-w-0 flex-col gap-4">
      <dl className="grid gap-x-5 gap-y-4 sm:grid-cols-2">
        {Object.entries(sample.linked.tables).map(([table, fields]) => <div key={table} className="flex min-w-0 flex-col gap-2"><dt className="font-mono font-medium">{table}</dt><dd className="flex flex-wrap gap-1.5">{fields.map(field => <Badge key={field} variant="outline">{field}</Badge>)}</dd></div>)}
      </dl>
      <Separator />
      <div className="flex flex-col gap-2"><h4 className="font-medium">关联路径</h4><ol className="flex flex-col gap-2">
        {sample.linked.joins.map(join => <li key={join} className="flex flex-wrap items-center gap-x-2 text-xs leading-5">{join.split(" = ").map((part, index) => index ? <span key={part} className="flex items-center gap-2"><ArrowRightIcon aria-hidden="true" className="size-3.5 shrink-0" /><code>{part}</code></span> : <code key={part}>{part}</code>)}</li>)}
      </ol></div>
      <Separator />
      <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-xs text-muted-foreground">生成本轮上下文，执行时必须携带</span><Badge variant="outline"><code>context_id</code></Badge></div>
    </CardContent>
  </Card>;
}

export function SqlPreview() {
  return <Card className="min-w-0">
    <CardHeader><CardTitle className="flex flex-wrap items-center justify-between gap-3"><span>通过校验的 SQL</span><Badge variant="outline">PostgreSQL · SELECT</Badge></CardTitle></CardHeader>
    <CardContent className="min-w-0"><MarkdownPreview content={`\`\`\`sql\n${sample.sql}\n\`\`\``} /></CardContent>
  </Card>;
}

export function ResultPreview() {
  return <Card className="min-w-0">
    <CardHeader><CardTitle className="flex flex-wrap items-center justify-between gap-3"><span className="flex items-center gap-2"><DatabaseIcon aria-hidden="true" className="size-4" />各品类成功退款金额</span><Badge variant="outline">只读实测快照</Badge></CardTitle></CardHeader>
    <CardContent className="flex min-w-0 flex-col gap-4">
      <Tabs defaultValue="chart" className="min-w-0 gap-3">
        <TabsList aria-label="示例查询结果显示方式"><TabsTrigger value="chart">图表</TabsTrigger><TabsTrigger value="data">数据</TabsTrigger></TabsList>
        <TabsContent value="chart" className="m-0 min-h-[17rem] min-w-0">
          <ChartContainer config={chartConfig} className="h-64 w-full" aria-label="各品类成功退款金额柱状图">
            <BarChart accessibilityLayer data={sample.result.rows} margin={{ left: 0, right: 12, top: 12, bottom: 4 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="category" tickLine={false} axisLine={false} tickMargin={8} interval={0} />
              <YAxis width={48} tickLine={false} axisLine={false} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar name="成功退款金额（元）" dataKey="refund_amount" fill="var(--color-refund_amount)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ChartContainer>
        </TabsContent>
        <TabsContent value="data" className="m-0 min-h-[17rem] min-w-0">
          <div className="min-w-0 rounded-lg border"><Table><TableHeader><TableRow><TableHead>品类</TableHead><TableHead className="text-right">成功退款金额</TableHead></TableRow></TableHeader><TableBody>
            {sample.result.rows.map(row => <TableRow key={row.category}><TableCell>{row.category}</TableCell><TableCell className="text-right tabular-nums">{money.format(row.refund_amount)}</TableCell></TableRow>)}
          </TableBody></Table></div>
        </TabsContent>
      </Tabs>
      <p className="text-xs leading-5 text-muted-foreground">{sample.provenance} · {sample.result.row_count} 行 · 不限制日期</p>
    </CardContent>
  </Card>;
}
