"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ChevronDownIcon, ChevronUpIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MarkdownPreview } from "@/components/markdown-preview";

export function ExpandableMarkdown({ content, maxHeight = 220 }: { content: string; maxHeight?: number }) {
  const [expanded, setExpanded] = useState(false);
  const [overflow, setOverflow] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    const node = contentRef.current;
    if (!node) return;
    const measure = () => setOverflow(node.scrollHeight > maxHeight + 4);
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    measure();
    return () => observer.disconnect();
  }, [content, maxHeight]);
  return <div className="min-w-0">
    <div id={id} className="relative overflow-hidden" style={{ maxHeight: expanded ? undefined : maxHeight }}>
      <div ref={contentRef}><MarkdownPreview content={content} /></div>
      {overflow && !expanded && <div aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-background to-transparent" />}
    </div>
    {overflow && <Button variant="ghost" size="sm" className="mt-2" aria-expanded={expanded} aria-controls={id} onClick={event => { event.stopPropagation(); setExpanded(value => !value); }}>{expanded ? "收起" : "展开全文"}{expanded ? <ChevronUpIcon data-icon="inline-end" /> : <ChevronDownIcon data-icon="inline-end" />}</Button>}
  </div>;
}
