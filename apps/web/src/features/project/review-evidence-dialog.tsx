"use client";

import { CodeIcon, FileTextIcon } from "lucide-react";
import { MarkdownPreview } from "@/components/markdown-preview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SampleTable } from "@/features/chat/query-details";
import type { QuerySample } from "@/features/chat/presentation-types";

export type DocumentExcerpt = { title: string; clause: string; excerpt: string; file: string };

export function ReviewEvidenceDialog({ sources, query, start = "documents", label }: {
  sources: DocumentExcerpt[]; query?: QuerySample; start?: "documents" | "data"; label?: string;
}) {
  return <Dialog>
    <DialogTrigger asChild><Button size="sm" variant="outline">{start === "documents" ? <FileTextIcon data-icon="inline-start" /> : <CodeIcon data-icon="inline-start" />}{label ?? (start === "documents" ? "文档依据" : "数据与 SQL")}</Button></DialogTrigger>
    <DialogContent className="flex h-[min(85svh,38rem)] min-w-0 flex-col overflow-hidden sm:max-w-4xl">
      <DialogHeader><DialogTitle>核对依据</DialogTitle><DialogDescription>固定合成文档节选{query ? "与独立只读查询实测快照" : ""}，用于说明核对过程。</DialogDescription></DialogHeader>
      <Tabs defaultValue={start} className="min-h-0 min-w-0 flex-1 gap-4">
        <TabsList aria-label="核对依据内容"><TabsTrigger value="documents">文档</TabsTrigger>{query && <><TabsTrigger value="data">数据</TabsTrigger><TabsTrigger value="sql">SQL</TabsTrigger><TabsTrigger value="schema">选表与字段</TabsTrigger></>}</TabsList>
        <TabsContent value="documents" className="m-0 min-h-0 flex-1 overflow-y-auto overscroll-contain">
          <div className="flex flex-col gap-5 pr-1">{sources.map((source, index) => <section key={`${source.file}:${source.clause}`} className="flex min-w-0 flex-col gap-3">
            {index > 0 && <Separator />}
            <header className="flex flex-col gap-1"><h3 className="font-semibold">{source.title}</h3><p className="text-xs text-muted-foreground">{source.clause}</p></header>
            <MarkdownPreview content={source.excerpt} className="text-sm leading-7 [&_h2]:text-base [&_h3]:text-base" />
          </section>)}</div>
        </TabsContent>
        {query && <>
          <TabsContent value="data" className="m-0 min-h-0 min-w-0 flex-1 overflow-auto overscroll-contain"><div className="flex flex-col gap-4"><p className="text-sm leading-6">{query.scope}</p><SampleTable result={query} /><Badge variant="outline">SQL 实测快照 · 保留 NULL 与原始统计粒度</Badge></div></TabsContent>
          <TabsContent value="sql" className="m-0 min-h-0 min-w-0 flex-1 overflow-auto overscroll-contain"><MarkdownPreview content={`\`\`\`sql\n${query.sql}\n\`\`\``} /></TabsContent>
          <TabsContent value="schema" className="m-0 min-h-0 min-w-0 flex-1 overflow-auto overscroll-contain"><div className="flex flex-col gap-4">
            {Object.entries(query.schema.tables).map(([table, fields]) => <section key={table} className="flex flex-col gap-2"><h3 className="font-mono font-medium">{table}</h3><div className="flex flex-wrap gap-1.5">{fields.map(field => <Badge variant="outline" key={field}>{field}</Badge>)}</div></section>)}
            <Separator /><p>{query.schema.grain}</p>{query.schema.joins.map(join => <p className="break-words font-mono text-xs leading-5" key={join}>{join}</p>)}
          </div></TabsContent>
        </>}
      </Tabs>
    </DialogContent>
  </Dialog>;
}

export function ReviewEvidenceActions({ sources, query }: { sources: DocumentExcerpt[]; query?: QuerySample }) {
  return <div className="flex flex-wrap items-center gap-2"><ReviewEvidenceDialog sources={sources} query={query} />{query && <ReviewEvidenceDialog sources={sources} query={query} start="data" />}</div>;
}
