"use client";

import { RotateCcwIcon } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { MarkdownPreview } from "@/components/markdown-preview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { characterCount, defaultOptions, splitStructure, validateOptions, type ChunkOptions } from "./chunk-demo";
import sample from "./fixtures/chunking-sample.json";

type Draft = Record<keyof ChunkOptions, string>;
const toDraft = (options: ChunkOptions): Draft => ({
  min_chars: String(options.min_chars), target_chars: String(options.target_chars), max_chars: String(options.max_chars),
});
const fields = [
  { key: "min_chars", label: "最小长度", min: 0, max: 12000 },
  { key: "target_chars", label: "目标长度", min: 100, max: 12000 },
  { key: "max_chars", label: "最大长度", min: 100, max: 20000 },
] as const;
const atomicLabels: Record<string, string> = { table: "表格与附注", equation: "公式与释义", code: "代码块" };

export function ChunkPlayground() {
  const [draft, setDraft] = useState<Draft>(() => toDraft(defaultOptions));
  const [options, setOptions] = useState(defaultOptions);
  const [selectedBlock, setSelectedBlock] = useState<string | null>(null);
  const sourceRef = useRef<HTMLDivElement>(null);
  const chunks = useMemo(() => splitStructure(sample.blocks, options), [options]);
  const parsed = Object.fromEntries(Object.entries(draft).map(([key, value]) => [key, value.trim() ? Number(value) : NaN])) as ChunkOptions;
  const error = validateOptions(parsed);
  const selected = chunks.find(chunk => selectedBlock && chunk.block_ids.includes(selectedBlock))?.sequence ?? 1;
  const sourceLabels = (ids: string[]) => [...new Set(sample.blocks.filter(block => ids.includes(block.id)).map(block => atomicLabels[block.kind]).filter(Boolean))];

  function update(key: keyof ChunkOptions, value: string) {
    const next = { ...draft, [key]: value };
    setDraft(next);
    const candidate = Object.fromEntries(Object.entries(next).map(([name, text]) => [name, text.trim() ? Number(text) : NaN])) as ChunkOptions;
    if (!validateOptions(candidate)) setOptions(candidate);
  }

  function selectChunk(sequence: number) {
    const chunk = chunks.find(item => item.sequence === sequence);
    if (!chunk) return;
    setSelectedBlock(chunk.block_ids[0]);
    const panel = sourceRef.current;
    const target = panel?.querySelector<HTMLElement>(`[data-chunk="${sequence}"]`);
    if (panel && target) {
      // Scroll only the document pane, without moving the page or its fixed tabs.
      panel.scrollTo({ top: target.getBoundingClientRect().top - panel.getBoundingClientRect().top + panel.scrollTop - 12, behavior: "smooth" });
    }
  }

  function reset() {
    setDraft(toDraft(defaultOptions));
    setOptions(defaultOptions);
    setSelectedBlock(null);
    sourceRef.current?.scrollTo({ top: 0 });
  }

  return <section aria-label="结构切块演示" className="grid min-w-0 overflow-hidden rounded-xl border lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
    <section aria-label="原文与切块边界" className="flex min-w-0 flex-col border-b lg:border-b-0 lg:border-r">
      <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b px-4">
        <h4 className="text-sm font-medium">原文与切块边界</h4>
        <Badge variant="outline">{sample.title}</Badge>
      </header>
      <div ref={sourceRef} role="region" aria-label="可滚动原文" tabIndex={0} className="h-[clamp(22rem,50dvh,32rem)] overflow-y-auto overscroll-contain scroll-smooth p-3 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring">
        {chunks.map(chunk => <section key={chunk.sequence} data-chunk={chunk.sequence} aria-label={`原文分块 ${chunk.sequence}`} className={cn("flex flex-col gap-4 rounded-lg border border-transparent p-4 transition-colors", selected === chunk.sequence && "border-border bg-accent/50")}>
          <div className="flex items-center justify-between gap-3">
            <Button variant="ghost" size="sm" aria-pressed={selected === chunk.sequence} onClick={() => setSelectedBlock(chunk.block_ids[0])}>分块 {String(chunk.sequence).padStart(2, "0")}</Button>
            <span className="text-xs tabular-nums text-muted-foreground">{characterCount(chunk.content)} 字符</span>
          </div>
          <MarkdownPreview content={chunk.content} className="text-sm leading-7 [&_h1]:text-lg [&_h2]:text-base [&_table]:min-w-[24rem]" />
        </section>)}
      </div>
    </section>

    <section aria-label="切块参数与结果" className="flex min-w-0 flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b px-4">
        <h4 className="text-sm font-medium">调整参数</h4>
        <Button variant="ghost" size="sm" onClick={reset}><RotateCcwIcon data-icon="inline-start" />重置</Button>
      </header>
      <div className="flex h-[clamp(22rem,50dvh,32rem)] min-h-0 flex-col">
        <div className="flex shrink-0 flex-col gap-3 p-4">
          <FieldGroup className="grid grid-cols-3 gap-3">
            {fields.map(field => <Field key={field.key} data-invalid={Boolean(error)}>
              <FieldLabel htmlFor={`chunk-${field.key}`}>{field.label}</FieldLabel>
              <Input id={`chunk-${field.key}`} type="number" min={field.min} max={field.max} step={1} value={draft[field.key]} aria-invalid={Boolean(error)} aria-describedby={error ? "chunk-error" : undefined} onChange={event => update(field.key, event.target.value)} />
            </Field>)}
          </FieldGroup>
          {error ? <FieldError id="chunk-error">{error} 当前保留上次有效结果。</FieldError>
            : null}
        </div>
        <div className="flex items-center justify-between gap-3 border-y bg-muted/40 px-4 py-3">
          <h4 className="text-sm font-medium">切分结果</h4>
          <span role="status" className="text-xs text-muted-foreground">{chunks.length} 个分块 · {sample.blocks.length} 个原子块</span>
        </div>
        <ol aria-label="切分结果" className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto overscroll-contain p-2">
          {chunks.map(chunk => <li key={chunk.sequence}>
            <Button variant="ghost" aria-label={`定位分块 ${chunk.sequence}`} aria-current={selected === chunk.sequence ? "true" : undefined} className="h-auto w-full justify-start whitespace-normal p-3 text-left aria-current:bg-accent" onClick={() => selectChunk(chunk.sequence)}>
              <span className="flex w-full min-w-0 flex-col gap-2">
                <span className="flex items-start justify-between gap-3">
                  <span className="flex min-w-0 items-start gap-2"><span className="tabular-nums text-muted-foreground">{String(chunk.sequence).padStart(2, "0")}</span><span>{chunk.section_path.at(-1) ?? "文档内容"}</span></span>
                  <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{characterCount(chunk.content)} 字符</span>
                </span>
                <span className="flex flex-wrap items-center gap-2">
                  {sourceLabels(chunk.block_ids).map(label => <Badge key={label} variant="outline">{label}</Badge>)}
                  {chunk.oversized_atom && <Badge tone="info" variant="outline">完整保留 · 允许超长</Badge>}
                  {!sourceLabels(chunk.block_ids).length && <span className="text-xs font-normal text-muted-foreground">{chunk.block_ids.length} 个标题 / 段落</span>}
                </span>
              </span>
            </Button>
          </li>)}
        </ol>
      </div>
    </section>
  </section>;
}
