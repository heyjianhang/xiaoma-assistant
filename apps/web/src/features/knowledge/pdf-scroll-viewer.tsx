"use client";

import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import { ExpandIcon, FileWarningIcon, LoaderCircleIcon, MinusIcon, PlusIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { authFetch } from "@/lib/access/client";
import { cn } from "@/lib/utils";
import type { SourceViewerProps } from "./source-viewer";

export function PdfScrollViewer({ document, selectedBlockIds, navigationRequest, highlight, onBlockSelect }: SourceViewerProps) {
  const [pdf, setPdf] = useState<PDFDocumentProxy>();
  const [error, setError] = useState("");
  const [zoom, setZoom] = useState(1);
  const [availableWidth, setAvailableWidth] = useState(600);
  const [currentPage, setCurrentPage] = useState(1);
  const containerRef = useRef<HTMLDivElement>(null);
  const visiblePageRef = useRef(1);
  const navigationRef = useRef("");
  const zoomAnchorRef = useRef<{ page: number; ratio: number } | null>(null);
  const pageWidth = Math.round(Math.min(availableWidth, 760) * zoom);
  const navigationKey = `${selectedBlockIds.join(",")}:${navigationRequest}`;

  useEffect(() => {
    let active = true;
    let task: PDFDocumentLoadingTask | undefined;
    let blobUrl: string | undefined;
    const abort = new AbortController();
    if (!document.sourceUrl) return;
    void Promise.all([import("pdfjs-dist"), authFetch(document.sourceUrl, { signal: abort.signal }).then(async response => { if (!response.ok) throw new Error("无权读取原文或文档已失效"); return response.blob(); })]).then(([library, blob]) => {
      if (!active) return;
      library.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.min.mjs";
      blobUrl = URL.createObjectURL(blob);
      task = library.getDocument({
        url: blobUrl, cMapUrl: "/pdfjs/cmaps/", cMapPacked: true,
        standardFontDataUrl: "/pdfjs/standard_fonts/", wasmUrl: "/pdfjs/wasm/", useSystemFonts: true,
      });
      return task.promise.then(result => { if (active) setPdf(result); });
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "PDF 加载失败"); });
    return () => { active = false; abort.abort(); if (task) void task.destroy(); if (blobUrl) URL.revokeObjectURL(blobUrl); };
  }, [document.sourceUrl]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(entries => {
      if (entries[0].contentRect.width > 0) setAvailableWidth(Math.max(240, Math.floor(entries[0].contentRect.width - 48)));
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!pdf || !container) return;
    const visibleHeights = new Map<number, number>();
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        const number = Number((entry.target as HTMLElement).dataset.pdfPage);
        if (entry.isIntersecting) visibleHeights.set(number, entry.intersectionRect.height);
        else visibleHeights.delete(number);
      }
      const largest = [...visibleHeights].sort((left, right) => right[1] - left[1])[0];
      if (largest) { visiblePageRef.current = largest[0]; setCurrentPage(largest[0]); }
    }, { root: container, threshold: [0, .1, .25, .5, .75, 1] });
    container.querySelectorAll("[data-pdf-page]").forEach(element => observer.observe(element));
    return () => observer.disconnect();
  }, [pdf]);

  function changeZoom(value: number) {
    if (value === zoom) return;
    const container = containerRef.current;
    const frame = container?.querySelector<HTMLElement>(`[data-pdf-page="${visiblePageRef.current}"]`);
    if (container && frame) {
      const frameTop = frame.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop;
      zoomAnchorRef.current = { page: visiblePageRef.current, ratio: (container.scrollTop + container.clientHeight / 2 - frameTop) / frame.clientHeight };
    }
    setZoom(value);
  }

  useLayoutEffect(() => {
    const anchor = zoomAnchorRef.current;
    const container = containerRef.current;
    const frame = anchor && container?.querySelector<HTMLElement>(`[data-pdf-page="${anchor.page}"]`);
    if (!anchor || !container || !frame) return;
    const frameTop = frame.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop;
    container.scrollTop = frameTop + anchor.ratio * frame.clientHeight - container.clientHeight / 2;
    zoomAnchorRef.current = null;
  }, [pageWidth]);

  function locateTarget(key: string, target: HTMLElement) {
    const container = containerRef.current;
    if (!container || !container.clientHeight || navigationRef.current === key) return;
    navigationRef.current = key;
    const top = container.scrollTop + target.getBoundingClientRect().top - container.getBoundingClientRect().top;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    container.scrollTo({
      top: Math.max(0, top - 24),
      behavior: navigationRequest > 0 && !reducedMotion ? "smooth" : "auto",
    });
  }

  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="viewer-toolbar">
      <span className="text-xs tabular-nums text-muted-foreground" aria-live="polite">第 {currentPage} / {pdf?.numPages ?? document.pages} 页</span>
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="icon-sm" aria-label="缩小原文" disabled={zoom <= .5} onClick={() => changeZoom(Math.max(.5, zoom - .25))}><MinusIcon /></Button>
        <span className="min-w-11 text-center text-xs tabular-nums">{Math.round(zoom * 100)}%</span>
        <Button variant="ghost" size="icon-sm" aria-label="放大原文" disabled={zoom >= 2} onClick={() => changeZoom(Math.min(2, zoom + .25))}><PlusIcon /></Button>
        <Button variant="ghost" size="icon-sm" aria-label="适应宽度" onClick={() => changeZoom(1)}><ExpandIcon /></Button>
      </div>
    </div>
    <div ref={containerRef} role="region" aria-label="PDF 原文滚动区域" tabIndex={0} className="relative min-h-0 flex-1 overflow-auto overscroll-contain bg-muted/60 p-6 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
      {error ? <Empty><EmptyHeader><EmptyMedia variant="icon"><FileWarningIcon /></EmptyMedia><EmptyTitle>无法预览这份 PDF</EmptyTitle><EmptyDescription>{error}</EmptyDescription></EmptyHeader></Empty> : !pdf ? <div className="flex min-h-64 items-center justify-center gap-2 text-sm text-muted-foreground" role="status"><LoaderCircleIcon className="size-4 animate-spin" />正在加载原文…</div> : <div className="flex w-max min-w-full flex-col items-center gap-6">
        {Array.from({ length: pdf.numPages }, (_, index) => <PdfPage
          key={index + 1} pdf={pdf} pageNumber={index + 1} width={pageWidth} containerRef={containerRef}
          document={document} selectedBlockIds={selectedBlockIds} highlight={highlight}
          navigationKey={navigationKey} onTargetReady={locateTarget} onBlockSelect={onBlockSelect}
        />)}
      </div>}
    </div>
    {!document.sourceMapAvailable && <Alert className="rounded-none border-x-0 border-b-0"><AlertDescription>当前支持定位到页，区域高亮尚未启用。</AlertDescription></Alert>}
  </div>;
}

interface PdfPageProps extends Pick<SourceViewerProps, "document" | "selectedBlockIds" | "highlight" | "onBlockSelect"> {
  pdf: PDFDocumentProxy;
  pageNumber: number;
  width: number;
  containerRef: RefObject<HTMLDivElement | null>;
  navigationKey: string;
  onTargetReady: (key: string, target: HTMLElement) => void;
}

function PdfPage({ pdf, pageNumber, width, containerRef, document, selectedBlockIds, highlight, navigationKey, onTargetReady, onBlockSelect }: PdfPageProps) {
  const frameRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const targetRef = useRef<HTMLButtonElement>(null);
  const [nearViewport, setNearViewport] = useState(pageNumber === 1);
  const [aspectRatio, setAspectRatio] = useState(595.28 / 841.89);
  const [renderedKey, setRenderedKey] = useState("");
  const [error, setError] = useState("");
  const targetBlock = document.blocks.find(block => block.page === pageNumber && block.id === selectedBlockIds[0]);
  const shouldRender = nearViewport || !!targetBlock;
  const renderKey = `${pageNumber}:${width}`;

  useEffect(() => {
    const frame = frameRef.current;
    const container = containerRef.current;
    if (!frame || !container) return;
    const observer = new IntersectionObserver(entries => setNearViewport(entries[0].isIntersecting), { root: container, rootMargin: "600px 0px" });
    observer.observe(frame);
    return () => observer.disconnect();
  }, [containerRef]);

  useEffect(() => {
    if (!shouldRender || !canvasRef.current) return;
    let active = true;
    let task: RenderTask | undefined;
    void pdf.getPage(pageNumber).then(async page => {
      if (!active || !canvasRef.current) return;
      const original = page.getViewport({ scale: 1 });
      const viewport = page.getViewport({ scale: width / original.width });
      const canvas = canvasRef.current;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      setAspectRatio(original.width / original.height);
      setError("");
      canvas.width = Math.floor(viewport.width * ratio);
      canvas.height = Math.floor(viewport.height * ratio);
      task = page.render({ canvas, viewport, transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0] });
      await task.promise;
      if (active) setRenderedKey(renderKey);
    }).catch(reason => {
      if (active && reason?.name !== "RenderingCancelledException") setError(reason instanceof Error ? reason.message : "页面渲染失败");
    });
    return () => { active = false; task?.cancel(); };
  }, [pdf, pageNumber, width, shouldRender, renderKey]);

  useEffect(() => {
    const target = document.sourceMapAvailable && targetRef.current ? targetRef.current : frameRef.current;
    if (targetBlock && renderedKey === renderKey && target) onTargetReady(navigationKey, target);
  }, [targetBlock, renderedKey, renderKey, navigationKey, onTargetReady, nearViewport, document.sourceMapAvailable]);

  return <div ref={frameRef} role="group" aria-label={`PDF 第 ${pageNumber} 页`} data-pdf-page={pageNumber} className="relative shrink-0 bg-white shadow-sm" style={{ width, aspectRatio }}>
    {error ? <div role="alert" className="flex h-full items-center justify-center p-6 text-sm text-destructive">第 {pageNumber} 页：{error}</div> : shouldRender && <canvas key={renderKey} ref={canvasRef} className="size-full" aria-label={`${document.filename} 第 ${pageNumber} 页`} />}
    {shouldRender && renderedKey === renderKey && document.sourceMapAvailable && document.blocks.filter(block => block.page === pageNumber && block.box[2] > block.box[0] && block.box[3] > block.box[1]).map(block => {
      const selected = highlight && selectedBlockIds.includes(block.id);
      return <button type="button" key={block.id} ref={block.id === selectedBlockIds[0] ? targetRef : undefined}
        className={cn("source-box absolute rounded-sm transition-colors", selected && "source-box-selected")}
        style={{ left: `${block.box[0] / 10}%`, top: `${block.box[1] / 10}%`, width: `${(block.box[2] - block.box[0]) / 10}%`, height: `${(block.box[3] - block.box[1]) / 10}%` }}
        aria-label={`原文区域：${block.title}`} aria-pressed={selected} onClick={() => onBlockSelect(block.id)} />;
    })}
  </div>;
}
