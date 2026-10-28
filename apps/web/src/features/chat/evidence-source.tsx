"use client";

import { ArrowUpRightIcon, FileTextIcon } from "lucide-react";
import { MarkdownPreview } from "@/components/markdown-preview";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import type { EvidenceSource } from "./presentation-types";

export function EvidenceSourceButton({ source }: { source: EvidenceSource }) {
  return <Dialog><DialogTrigger asChild><Button size="sm" variant="ghost" aria-label={`查看依据：${source.title} ${source.clause}`}><FileTextIcon data-icon="inline-start" />{source.clause}</Button></DialogTrigger><DialogContent className="sm:max-w-2xl">
    <DialogHeader><DialogTitle>{source.title}</DialogTitle><DialogDescription>条款 / 表号：{source.clause} · 虚构演示资料</DialogDescription></DialogHeader>
    <div className="max-h-[60svh] overflow-auto"><MarkdownPreview content={source.excerpt} /></div>
    <DialogFooter><Button variant="outline" asChild><a href={source.url} target="_blank" rel="noreferrer">打开 PDF 原文<ArrowUpRightIcon data-icon="inline-end" /></a></Button></DialogFooter>
  </DialogContent></Dialog>;
}
