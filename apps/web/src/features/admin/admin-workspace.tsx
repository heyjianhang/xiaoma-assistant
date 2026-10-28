"use client";
import { useEffect, useState } from "react";
import { CopyIcon, PlusIcon, LoaderCircleIcon, RefreshCwIcon } from "lucide-react";
import { toast } from "sonner";
import { WorkspacePage, WorkspaceToolbar } from "@/components/workspace-page";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Table, TableHeader, TableHead, TableBody, TableCell, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ActivityPanel, activityTime, type Invite } from "./activity-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { useAccess } from "@/lib/access/provider";
import { accessApi, jsonRequest } from "@/lib/access/client";

const localTime = (date: Date) => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
function status(invite: Invite) { const now = Date.now(); return invite.revoked_at ? "已撤销" : now >= Date.parse(invite.expires_at) ? "已到期" : now < Date.parse(invite.valid_from) ? "未生效" : invite.bound ? "已绑定" : "待使用"; }
export function AdminWorkspace() {
  const { user } = useAccess();
  const [invites, setInvites] = useState<Invite[]>([]);
  const [tab, setTab] = useState("invitations");
  const [inspecting, setInspecting] = useState<Invite | null>(null);
  const [error, setError] = useState(""); const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false);
  const [inviteEdit, setInviteEdit] = useState<Invite | "new" | null>(null); const [name, setName] = useState("");
  const [start, setStart] = useState(""); const [end, setEnd] = useState(""); const [link, setLink] = useState("");
  const [action, setAction] = useState<{ invite: Invite; type: "revoke" | "reset-device" } | null>(null);
  async function load() {
    try { setError(""); const a = await accessApi<{ items: Invite[] }>("/admin/invitations"); setInvites(a.items); }
    catch (error) { setError(error instanceof Error ? error.message : "加载失败"); }
    finally { setLoading(false); }
  }
  useEffect(() => { if (user?.role === "admin") void Promise.resolve().then(load); }, [user?.role]);
  function edit(invite: Invite | "new") {
    setInviteEdit(invite); setError(""); setLink(""); setName(invite === "new" ? "" : invite.name);
    setStart(localTime(invite === "new" ? new Date(Date.now() - 60000) : new Date(invite.valid_from)));
    setEnd(localTime(invite === "new" ? new Date(Date.now() + 7 * 86400000) : new Date(invite.expires_at)));
  }
  async function saveInvite() {
    if (!inviteEdit) return; setBusy(true); setError("");
    try {
      const body = { name: name.trim(), valid_from: new Date(start).toISOString(), expires_at: new Date(end).toISOString() };
      const result = await accessApi<{ url?: string }>(inviteEdit === "new" ? "/admin/invitations" : `/admin/invitations/${inviteEdit.id}`, jsonRequest(inviteEdit === "new" ? "POST" : "PATCH", body));
      if (result.url) setLink(result.url); else { setInviteEdit(null); toast.success("邀请有效期已更新"); } await load();
    } catch (error) { setError(error instanceof Error ? error.message : "保存失败"); }
    finally { setBusy(false); }
  }
  async function applyAction() {
    if (!action) return; setBusy(true); setError("");
    try {
      const result = await accessApi<{ url?: string }>(`/admin/invitations/${action.invite.id}/${action.type}`, { method: "POST" });
      if (result.url) setLink(result.url); toast.success(action.type === "revoke" ? "邀请已撤销" : "设备绑定已重置，已生成新链接"); setAction(null); await load();
    } catch (error) { setError(error instanceof Error ? error.message : "操作失败"); }
    finally { setBusy(false); }
  }
  if (user?.role !== "admin") return <WorkspacePage title="管理后台"><Alert variant="destructive"><AlertDescription>此页面仅管理员可访问。</AlertDescription></Alert></WorkspacePage>;
  return <WorkspacePage title="管理后台"><Tabs value={tab} onValueChange={setTab} className="min-h-0 flex-1 gap-4 overflow-hidden"><WorkspaceToolbar><TabsList aria-label="后台管理内容"><TabsTrigger value="invitations">邀请管理</TabsTrigger><TabsTrigger value="activity">访问记录</TabsTrigger></TabsList><div className="flex items-center gap-2">{tab === "invitations" && <><Button variant="ghost" size="icon" aria-label="刷新邀请" onClick={() => void load()}><RefreshCwIcon /></Button><Button onClick={() => edit("new")}><PlusIcon data-icon="inline-start" />创建邀请</Button></>}</div></WorkspaceToolbar><TabsContent value="invitations" className="m-0 flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
    {error && !inviteEdit && <Alert variant="destructive"><AlertDescription>{error}<Button variant="outline" size="sm" onClick={() => void load()}>重试</Button></AlertDescription></Alert>}
    {loading ? <Skeleton className="h-64 w-full" /> : <div className="min-h-0 flex-1 overflow-auto rounded-xl border"><Table><TableHeader><TableRow><TableHead>访客</TableHead><TableHead>状态</TableHead><TableHead>首次激活</TableHead><TableHead>最近访问</TableHead><TableHead className="text-right">访问次数</TableHead><TableHead className="text-right">提问次数</TableHead><TableHead>有效期</TableHead><TableHead className="text-right">操作</TableHead></TableRow></TableHeader><TableBody>
      {invites.map(invite => <TableRow key={invite.id}><TableCell><Button variant="link" className="h-auto max-w-48 justify-start truncate p-0" onClick={() => setInspecting(invite)}>{invite.name}</Button></TableCell><TableCell><Badge variant="secondary">{status(invite)}</Badge></TableCell><TableCell className="text-xs tabular-nums">{activityTime(invite.first_activated_at)}</TableCell><TableCell className="text-xs tabular-nums">{activityTime(invite.last_visited_at)}</TableCell><TableCell className="text-right tabular-nums">{invite.visit_count}</TableCell><TableCell className="text-right tabular-nums">{invite.question_count}</TableCell><TableCell><div className="flex flex-col gap-1 text-xs tabular-nums text-muted-foreground"><span>{activityTime(invite.valid_from)}</span><span>至 {activityTime(invite.expires_at)}</span></div></TableCell><TableCell><div className="flex justify-end gap-1"><Button size="sm" variant="ghost" onClick={() => edit(invite)}>有效期</Button><Button size="sm" variant="ghost" disabled={!invite.bound || ["已撤销", "已到期"].includes(status(invite))} onClick={() => setAction({ invite, type: "reset-device" })}>重置设备</Button><Button size="sm" variant="ghost" disabled={!!invite.revoked_at} onClick={() => setAction({ invite, type: "revoke" })}>撤销</Button></div></TableCell></TableRow>)}
      {!invites.length && <TableRow><TableCell colSpan={8} className="py-16 text-center text-muted-foreground">还没有邀请</TableCell></TableRow>}
    </TableBody></Table></div>}
    </TabsContent><TabsContent value="activity" className="m-0 flex min-h-0 flex-1 flex-col overflow-hidden"><ActivityPanel invites={invites} /></TabsContent></Tabs>
    <Dialog open={!!inspecting} onOpenChange={open => !open && setInspecting(null)}><DialogContent className="flex h-[78dvh] flex-col overflow-hidden sm:max-w-5xl"><DialogHeader><DialogTitle>{inspecting?.name} · 访问记录</DialogTitle><DialogDescription className="sr-only">查看此邀请的访问与使用情况</DialogDescription></DialogHeader>{inspecting && <ActivityPanel key={inspecting.id} invites={invites} invitationId={inspecting.id} />}</DialogContent></Dialog>
    <Dialog open={inviteEdit !== null || !!link} onOpenChange={open => { if (!open && !busy) { setInviteEdit(null); setLink(""); setError(""); } }}><DialogContent><DialogHeader><DialogTitle>{link ? "邀请链接已生成" : inviteEdit === "new" ? "创建邀请" : "修改邀请有效期"}</DialogTitle><DialogDescription className={link ? undefined : "sr-only"}>{link ? "链接仅在此处完整显示。首次使用后绑定浏览器设备。" : "设置访客名称及有效期"}</DialogDescription></DialogHeader>{link ? <div className="flex flex-col gap-3"><Input readOnly value={link} aria-label="邀请链接" /><Button onClick={() => { void navigator.clipboard.writeText(link).then(() => toast.success("已复制邀请链接")); }}><CopyIcon data-icon="inline-start" />复制链接</Button></div> : <><FieldGroup><Field><FieldLabel htmlFor="invite-name">访客名称</FieldLabel><Input id="invite-name" value={name} onChange={event => setName(event.target.value)} maxLength={80} /></Field><Field><FieldLabel htmlFor="invite-start">生效时间</FieldLabel><Input id="invite-start" type="datetime-local" value={start} onChange={event => setStart(event.target.value)} /></Field><Field><FieldLabel htmlFor="invite-end">到期时间</FieldLabel><Input id="invite-end" type="datetime-local" value={end} onChange={event => setEnd(event.target.value)} /></Field></FieldGroup>{error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}<DialogFooter><Button variant="outline" disabled={busy} onClick={() => setInviteEdit(null)}>取消</Button><Button disabled={busy || !name.trim() || !start || !end} onClick={() => void saveInvite()}>{busy && <LoaderCircleIcon data-icon="inline-start" className="animate-spin" />}保存</Button></DialogFooter></>}</DialogContent></Dialog>
    <Dialog open={!!action} onOpenChange={open => !open && !busy && setAction(null)}><DialogContent><DialogHeader><DialogTitle>{action?.type === "revoke" ? "撤销邀请" : "重置设备绑定"}</DialogTitle><DialogDescription>{action?.type === "revoke" ? "当前访客会失去访问权限，正在运行的请求也会停止。" : "旧链接与设备登录将失效。新链接创建独立访客，旧聊天记录不会转给新设备。"}</DialogDescription></DialogHeader>{error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}<DialogFooter><Button variant="outline" disabled={busy} onClick={() => setAction(null)}>取消</Button><Button disabled={busy} onClick={() => void applyAction()}>确认</Button></DialogFooter></DialogContent></Dialog>

  </WorkspacePage>;
}
