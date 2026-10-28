"use client";

import { useEffect, useState, type RefObject } from "react";
import { DownloadIcon, FileTextIcon, LoaderCircleIcon, UploadIcon, MoreHorizontalIcon, Trash2Icon, Undo2Icon } from "lucide-react";
import { toast } from "sonner";
import { accessApi, authFetch, jsonRequest } from "@/lib/access/client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { CodeBlock } from "@/components/ai-elements/code-block";
import { MarkdownPreview } from "@/components/markdown-preview";
import type { ChatSkill } from "@/features/chat/chat-skills";
import { SkillFileTree } from "./skill-file-tree";

interface Skill extends ChatSkill {
  body: string;
  enabled: boolean;
  builtin: boolean;
  deleted_at: string | null;
  manifest: { source: "builtin" | "uploaded"; sha256: string; frontmatter: Record<string, unknown>; files: { path: string; size: number; text: boolean }[] };
}

export function SkillManager({ uploadRef }: { uploadRef: RefObject<HTMLInputElement | null> }) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState<Skill | null>(null);
  const [path, setPath] = useState("SKILL.md");
  const [resource, setResource] = useState<string | null>(null);
  const [resourceError, setResourceError] = useState("");
  const [replacement, setReplacement] = useState<Skill | null>(null);
  const [showDeleted, setShowDeleted] = useState(false);
  const removed = skills.filter(skill => skill.deleted_at);
  const visibleSkills = skills.filter(skill => showDeleted ? !!skill.deleted_at : !skill.deleted_at);
  async function load() {
    try { const result = await accessApi<{ items: Skill[] }>("/admin/skills?include_deleted=true"); setSkills(result.items); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : "加载技能失败"); }
    finally { setLoading(false); }
  }
  useEffect(() => { void Promise.resolve().then(load); }, []);
  useEffect(() => {
    const input = uploadRef.current; const cancel = () => setReplacement(null);
    input?.addEventListener("cancel", cancel);
    return () => input?.removeEventListener("cancel", cancel);
  }, [uploadRef]);
  useEffect(() => {
    if (!detail) return;
    const controller = new AbortController();
    void accessApi<{ content: string }>(`/admin/skills/${detail.id}/resource?revision=${detail.revision}&path=${encodeURIComponent(path)}`, { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) { setResource(value.content); setResourceError(""); }
    }).catch(e => { if (!controller.signal.aborted) setResourceError(e instanceof Error ? e.message : "无法读取资源"); });
    return () => controller.abort();
  }, [detail, path]);
  async function upload(file: File) {
    if (!file.name.toLowerCase().endsWith(".zip") || file.size > 5 * 1024 * 1024) { toast.error("请选择不超过5MB的 Skill ZIP"); setReplacement(null); return; }
    setBusy(true);
    try {
      const data = new FormData(); data.append("file", file);
      if (replacement) { data.append("expected_revision", String(replacement.revision)); data.append("expected_id", replacement.id); }
      const result = await accessApi<{ id: string; revision: number }>("/admin/skills/upload", { method: "POST", body: data });
      toast.success(`/${result.id} 已安装，版本 ${result.revision}`); await load(); window.dispatchEvent(new Event("xiaoma-skills-updated"));
    } catch (e) { toast.error(e instanceof Error ? e.message : "安装失败"); }
    finally { setBusy(false); setReplacement(null); }
  }
  async function toggle(skill: Skill, enabled: boolean) {
    setBusy(true);
    try { await accessApi(`/admin/skills/${skill.id}/enabled`, jsonRequest("PATCH", { revision: skill.revision, enabled })); await load(); window.dispatchEvent(new Event("xiaoma-skills-updated")); }
    catch (e) { toast.error(e instanceof Error ? e.message : "更新失败"); }
    finally { setBusy(false); }
  }
  async function download(skill: Skill) {
    try {
      const response = await authFetch(`/api/v1/admin/skills/${skill.id}/package`);
      if (!response.ok) throw new Error("下载技能失败");
      const url = URL.createObjectURL(await response.blob()); const link = document.createElement("a");
      link.href = url; link.download = `${skill.id}.zip`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { toast.error(e instanceof Error ? e.message : "下载失败"); }
  }
  async function restoreSkill(skill: Skill) {
    setBusy(true);
    try { await accessApi(`/admin/skills/${skill.id}/restore`, jsonRequest("POST", { revision: skill.revision })); await load(); window.dispatchEvent(new Event("xiaoma-skills-updated")); toast.success("技能已恢复"); }
    catch (e) { toast.error(e instanceof Error ? e.message : "恢复失败"); }
    finally { setBusy(false); }
  }
  async function removeSkill(skill: Skill) {
    setBusy(true);
    try {
      const result = await accessApi<{ revision: number }>(`/admin/skills/${skill.id}?revision=${skill.revision}`, { method: "DELETE" });
      await load(); window.dispatchEvent(new Event("xiaoma-skills-updated"));
      toast.success("技能已删除", { action: { label: "撤销", onClick: () => { void restoreSkill({ ...skill, revision: result.revision }); } } });
    } catch (e) { toast.error(e instanceof Error ? e.message : "删除失败"); }
    finally { setBusy(false); }
  }
  return <>
    <input ref={uploadRef} type="file" accept=".zip" className="hidden" aria-label="上传 Skill ZIP" disabled={busy} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void upload(file); }} />
    {error && <Alert variant="destructive"><AlertDescription>{error}<Button variant="outline" size="sm" onClick={() => void load()}>重试</Button></AlertDescription></Alert>}
    {busy && <div className="flex items-center gap-2 p-3 text-sm" role="status"><LoaderCircleIcon className="size-4 animate-spin" />正在更新技能…</div>}
    {loading ? <Skeleton className="h-64" /> : <Table><TableHeader><TableRow><TableHead>技能</TableHead><TableHead>来源</TableHead><TableHead>文件</TableHead><TableHead>版本</TableHead><TableHead>启用</TableHead><TableHead className="text-right">操作</TableHead></TableRow></TableHeader><TableBody>{visibleSkills.map(skill => <TableRow key={skill.id}>
      <TableCell><div className="flex max-w-lg flex-col gap-1"><span className="font-medium">{skill.name} <span className="text-xs text-muted-foreground">/{skill.id}</span></span><span className="line-clamp-2 text-xs text-muted-foreground">{skill.description}</span></div></TableCell>
      <TableCell><Badge variant="outline">{(skill.builtin ?? skill.manifest.source === "builtin") ? "内置" : "已上传"}</Badge></TableCell><TableCell>{skill.manifest.files.length}</TableCell><TableCell>{skill.revision}</TableCell>
      <TableCell><Switch aria-label={`启用技能 ${skill.id}`} checked={skill.enabled} disabled={busy || !!skill.deleted_at} onCheckedChange={value => void toggle(skill, value)} /></TableCell>
      <TableCell><div className="flex justify-end gap-1">{skill.deleted_at ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => void restoreSkill(skill)}><Undo2Icon data-icon="inline-start" />恢复</Button> : <><Button size="sm" variant="ghost" onClick={() => { setDetail(skill); setPath("SKILL.md"); setResource(null); setResourceError(""); }}><FileTextIcon data-icon="inline-start" />查看</Button>
        <DropdownMenu><DropdownMenuTrigger asChild><Button size="icon-sm" variant="ghost" disabled={busy} aria-label={`技能操作：${skill.id}`}><MoreHorizontalIcon /></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuGroup><DropdownMenuItem onSelect={() => void download(skill)}><DownloadIcon />下载技能包</DropdownMenuItem><DropdownMenuItem onSelect={() => { setReplacement(skill); uploadRef.current?.click(); }}><UploadIcon />上传新版本</DropdownMenuItem></DropdownMenuGroup>{!(skill.builtin ?? skill.manifest.source === "builtin") && <><DropdownMenuSeparator /><DropdownMenuGroup><DropdownMenuItem variant="destructive" onSelect={() => void removeSkill(skill)}><Trash2Icon />删除技能</DropdownMenuItem></DropdownMenuGroup></>}</DropdownMenuContent></DropdownMenu>
      </>}</div></TableCell>
    </TableRow>)}{!visibleSkills.length && <TableRow><TableCell colSpan={6} className="py-12 text-center text-muted-foreground">{showDeleted ? "没有已删除技能" : "还没有技能"}</TableCell></TableRow>}</TableBody></Table>}
    {(!!removed.length || showDeleted) && <div className="flex justify-end border-t p-2"><Button size="sm" variant="ghost" onClick={() => setShowDeleted(value => !value)}>{showDeleted ? "返回技能列表" : `最近删除（${removed.length}）`}</Button></div>}
    <Dialog open={!!detail} onOpenChange={open => { if (!open) setDetail(null); }}><DialogContent className="flex h-[min(82svh,760px)] flex-col gap-0 overflow-hidden p-0 sm:max-w-5xl"><DialogHeader className="shrink-0 p-5"><DialogTitle>{detail?.name}</DialogTitle><DialogDescription>/{detail?.id} · 版本 {detail?.revision}</DialogDescription></DialogHeader>
      <div className="grid min-h-0 flex-1 grid-rows-[140px_minmax(0,1fr)] overflow-hidden border-t sm:grid-cols-[220px_minmax(0,1fr)] sm:grid-rows-1">
        <aside className="min-h-0 overflow-auto p-2 sm:border-r">{detail && <SkillFileTree key={`${detail.id}:${detail.revision}`} paths={detail.manifest.files.map(file => file.path)} selectedPath={path} onSelect={path => { setPath(path); setResource(null); setResourceError(""); }} />}</aside>
        <section className="flex min-h-0 min-w-0 flex-col" aria-label="文件内容"><div className="shrink-0 truncate border-y px-4 py-3 font-mono text-xs text-muted-foreground sm:border-t-0" title={path}>{path}</div><div className="min-h-0 flex-1 overflow-auto p-4">{resourceError ? <Alert><AlertDescription>{resourceError}</AlertDescription></Alert> : resource === null ? <Skeleton className="h-48" /> : path === "SKILL.md" ? <CodeBlock code={resource} language="markdown" /> : <MarkdownPreview content={resource} />}</div></section>
      </div>
    </DialogContent></Dialog>
  </>;
}
