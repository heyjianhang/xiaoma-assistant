"use client";

import { useRef, useState } from "react";
import { FileTextIcon, LoaderCircleIcon, UploadIcon, XIcon } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { UploadBatchError } from "@/lib/services/upload-error";
import { useWorkspace } from "@/lib/services/provider";

export function knowledgeFilesError(incoming: File[]) {
  const invalid = incoming.find(file => !/\.(pdf|md|markdown)$/i.test(file.name) || file.size === 0 || file.size > 20 * 1024 * 1024);
  return invalid ? `“${invalid.name}”不符合要求，请选择不超过 20 MB 的非空 PDF 或 Markdown 文件。` : "";
}

export function UploadDialog({ open, onOpenChange, initialFiles = [] }: { open: boolean; onOpenChange: (open: boolean) => void; initialFiles?: File[] }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>(initialFiles);
  const [dragging, setDragging] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const { repository, chunkDefaults } = useWorkspace();
  function close(value: boolean) {
    if (saving) return;
    onOpenChange(value);
    if (!value) { setFiles([]); setError(""); }
  }
  function accept(incoming: File[]) {
    const error = knowledgeFilesError(incoming);
    if (error) { setError(error); return; }
    setError("");
    setFiles(previous => [...previous, ...incoming].filter((file, index, all) => all.findIndex(other => other.name === file.name && other.size === file.size) === index));
  }
  async function submit() {
    if (!files.length) return;
    setSaving(true); setError("");
    try {
      await repository.upload(files, chunkDefaults);
      setSaving(false); onOpenChange(false); setFiles([]);
      toast.success("已上传，正在后台处理");
    } catch (error) { if (error instanceof UploadBatchError) setFiles(error.failedFiles); setError(error instanceof Error ? error.message : "上传失败，请重试。"); setSaving(false); }
  }
  return <Dialog open={open} onOpenChange={close}><DialogContent className="sm:max-w-[560px]">
    <DialogHeader><DialogTitle>上传文档</DialogTitle><DialogDescription className="sr-only">选择多份文档上传处理</DialogDescription></DialogHeader>
    <div className="flex flex-col gap-4">
      <input ref={inputRef} type="file" className="sr-only" aria-label="选择上传文件" accept=".pdf,.md,.markdown" multiple onChange={event => { accept(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
      <button type="button" className="upload-zone flex min-h-44 flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-6 py-7 text-center" data-dragging={dragging} onClick={() => inputRef.current?.click()} onDragOver={event => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); accept(Array.from(event.dataTransfer.files)); }}>
        <UploadIcon className="size-6 text-muted-foreground" strokeWidth={1.6} /><span className="text-sm font-medium">点击选择，或将文件拖到这里</span><span className="text-xs text-muted-foreground">PDF、Markdown · 每个文件不超过 20 MB</span>
      </button>
      {(files.length > 0) && <div className="flex max-h-36 flex-col gap-2 overflow-y-auto">
        {files.map((file, index) => <div key={`${file.name}-${index}`} className="flex items-center gap-3 rounded-lg border px-3 py-2"><FileTextIcon className="size-4 shrink-0 text-muted-foreground" /><span className="min-w-0 flex-1 truncate text-sm">{file.name}</span><Button variant="ghost" size="icon-sm" aria-label={`移除 ${file.name}`} onClick={() => setFiles(files.filter((_, item) => item !== index))}><XIcon /></Button></div>)}
      </div>}
    </div>
    {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
    <DialogFooter><Button variant="outline" onClick={() => close(false)} disabled={saving}>取消</Button>
      <Button disabled={saving || !files.length} onClick={() => void submit()}>{saving ? <LoaderCircleIcon className="animate-spin" data-icon="inline-start" /> : <UploadIcon data-icon="inline-start" />}{saving ? "正在上传…" : `开始处理${files.length ? `（${files.length}）` : ""}`}</Button>
    </DialogFooter>
  </DialogContent></Dialog>;
}
