"use client";

import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { Badge } from "@/components/ui/badge";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { DataPresentation } from "./presentation-types";
import { formatValue, SampleSql, SampleTable } from "./query-details";

export function DataViewCard({ payload }: { payload: DataPresentation }) {
  const { result, columns, view, xKey } = payload;
  const config = Object.fromEntries(columns.map((column, index) => [`series${index}`, { label: `${column.label}${column.format === "percent" ? "（%）" : column.format === "money" ? "（元）" : ""}`, color: index ? "var(--chart-2)" : "var(--brand, #3d7eff)" }])) satisfies ChartConfig;
  const allColumns = xKey ? [{ key: xKey, label: xKey }, ...columns] : columns;
  return <Card tone="info" aria-label={payload.title} className="min-w-0">
    <CardHeader><CardTitle>{payload.title}</CardTitle><CardDescription>{result.scope}</CardDescription><CardAction><Badge variant="outline">{(result.executed || result.provenance.startsWith("真实只读")) ? "只读查询" : "历史样例"}</Badge></CardAction></CardHeader>
    <CardContent className="min-w-0"><Tabs className="min-w-0" defaultValue={view === "table" || !result.rows.length ? "data" : "view"}>
      <TabsList aria-label={`${payload.title}显示方式`}>{view !== "table" && !!result.rows.length && <TabsTrigger value="view">{view === "metrics" ? "概览" : "图表"}</TabsTrigger>}<TabsTrigger value="data">数据</TabsTrigger><TabsTrigger value="sql">SQL</TabsTrigger></TabsList>
      <TabsContent value="view" className="pt-3">
        {view === "metrics" && <dl className="grid grid-cols-2 gap-5 xl:grid-cols-4">{columns.map(column => <div key={column.key} className="flex min-w-0 flex-col gap-2"><dt className="text-xs text-muted-foreground">{column.label}</dt><dd className="break-words text-xl font-semibold tabular-nums tracking-tight">{formatValue(result.rows[0]?.[column.key] ?? null, column.format)}</dd></div>)}</dl>}
        {view === "bar" && xKey && <ChartContainer config={config} className="h-64 w-full" aria-label={payload.title}><BarChart accessibilityLayer data={result.rows} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
          <CartesianGrid vertical={false} /><XAxis dataKey={xKey} tickLine={false} axisLine={false} tickMargin={10} interval={0} /><YAxis width={64} unit={columns[0].format === "money" ? "元" : columns[0].format === "percent" ? "%" : columns[0].format === "hours" ? "小时" : undefined} tickLine={false} axisLine={false} /><ChartTooltip content={<ChartTooltipContent />} />{columns.map((column, index) => <Bar key={column.key} name={column.label} dataKey={column.key} fill={`var(--color-series${index})`} radius={[4, 4, 0, 0]} isAnimationActive={false} />)}
        </BarChart></ChartContainer>}
        {view === "line" && xKey && <ChartContainer config={config} className="h-72 w-full" aria-label={payload.title}><LineChart accessibilityLayer data={result.rows} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
          <CartesianGrid vertical={false} /><XAxis dataKey={xKey} minTickGap={28} tickLine={false} axisLine={false} />
          <YAxis tickLine={false} axisLine={false} width={64} />
          <ChartTooltip content={<ChartTooltipContent />} /><ChartLegend content={<ChartLegendContent />} />
          {columns.map((column, index) => <Line key={column.key} name={column.label} dataKey={column.key} stroke={`var(--color-series${index})`} strokeWidth={2} dot={false} isAnimationActive={false} />)}
        </LineChart></ChartContainer>}

      </TabsContent>
      <TabsContent value="data" className="min-w-0 pt-2"><SampleTable result={result} columns={allColumns} /></TabsContent>
      <TabsContent value="sql" className="min-w-0 pt-2"><SampleSql result={result} /></TabsContent>
    </Tabs></CardContent>
    <CardFooter className="flex-col items-start gap-1"><p className="text-xs leading-6 text-muted-foreground">{payload.note}</p><p className="text-xs text-muted-foreground">{result.rows.length} 行{(result.executed || result.provenance.startsWith("真实只读")) ? ` · ${result.elapsed_ms ?? 0} ms` : " · 历史样例"}</p></CardFooter>
  </Card>;
}
