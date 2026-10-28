"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { KnowledgeDocument } from "@/lib/services/contracts";
import { useWorkspace } from "@/lib/services/provider";
import { ChunkConfigurationFields, validConfiguration } from "./chunk-configuration";

export function ReprocessDialog({ document, onClose }: { document: KnowledgeDocument; onClose: () => void }) {
  const [configuration, setConfiguration] = useState({ strategy: document.strategy, targetLength: document.targetLength, maxLength: document.maxLength, minLength: document.minLength });
  const [saving, setSaving] = useState(false);
  const { repository } = useWorkspace();
  async function submit() {
    if (!validConfiguration(configuration)) return;
    setSaving(true);
    try {
      await repository.reprocess(document.id, configuration);
      toast.success("已加入重新处理队列"); onClose();
    } catch (error) { toast.error(error instanceof Error ? error.message : "处理失败"); }
    finally { setSaving(false); }
  }
  return <Dialog open onOpenChange={open => !open && !saving && onClose()}><DialogContent className="sm:max-w-[500px]">
    <DialogHeader><DialogTitle>重新处理文档</DialogTitle><DialogDescription>{document.filename}</DialogDescription></DialogHeader>
    <div className="py-3"><ChunkConfigurationFields value={configuration} onChange={setConfiguration} prefix="reprocess" /></div>
    <p className="text-xs leading-5 text-muted-foreground">新版本入库成功后替换当前分块；处理期间旧版本仍可检索，分块启停状态会在新版本中重置。</p>
    <DialogFooter><Button variant="outline" onClick={onClose} disabled={saving}>取消</Button><Button onClick={() => void submit()} disabled={saving || !validConfiguration(configuration)}>{saving ? "提交中…" : "确认处理"}</Button></DialogFooter>
  </DialogContent></Dialog>;
}

export function RemoveDocumentDialog({ document, onClose, onRemoved }: { document: KnowledgeDocument; onClose: () => void; onRemoved?: () => void }) {
  const { repository } = useWorkspace();
  const [saving, setSaving] = useState(false);
  async function submit() {
    setSaving(true);
    try { await repository.removeDocument(document.id); toast.success("文档已删除"); onClose(); onRemoved?.(); }
    catch (error) { toast.error(error instanceof Error ? error.message : "删除失败"); }
    finally { setSaving(false); }
  }
  return <AlertDialog open onOpenChange={open => !open && !saving && onClose()}><AlertDialogContent>
    <AlertDialogHeader><AlertDialogTitle>删除这份文档？</AlertDialogTitle><AlertDialogDescription>删除后，“{document.filename}”及其分块不再参与检索。</AlertDialogDescription></AlertDialogHeader>
    <AlertDialogFooter><AlertDialogCancel onClick={onClose} disabled={saving}>取消</AlertDialogCancel><AlertDialogAction disabled={saving} onClick={event => { event.preventDefault(); void submit(); }}>{saving ? "删除中…" : "删除文档"}</AlertDialogAction></AlertDialogFooter>
  </AlertDialogContent></AlertDialog>;
}
