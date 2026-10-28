"use client";

import { useCallback, useEffect, useState } from "react";
import { ChevronLeftIcon, ChevronRightIcon, RefreshCwIcon } from "lucide-react";
import { accessApi } from "@/lib/access/client";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export interface Invite {
  id: string; name: string; valid_from: string; expires_at: string; revoked_at: string | null; bound: boolean;
  first_activated_at: string | null; last_visited_at: string | null; visit_count: number; question_count: number;
}
interface ActivityEvent {
  id: string; kind: string; label: string; name: string; user_id: string; created_at: string;
  details: { device?: string; status?: string; tool_names?: string[] };
}
interface ActivityPage { items: ActivityEvent[]; total: number }
const kinds: Record<string, string> = { all: "全部行为", invite_activated: "激活邀请", login: "登录", page_view: "查看页面", document_view: "查看原文", sql_view: "查看 SQL", test_case_view: "查看用例", question: "发送问题", answer: "回答结果" };
export const activityTime = (value: string | null) => value ? new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";

function usedTools(event: ActivityEvent) {
  if (event.kind !== "answer") return "";
  const names = event.details.tool_names ?? [];
  return [names.includes("search_knowledge") && "文档检索", names.includes("execute_readonly_sql") && "数据库查询", names.includes("render_chart") && "图表展示"].filter(Boolean).join("、");
}

export function ActivityPanel({ invites, invitationId }: { invites: Invite[]; invitationId?: string }) {
  const [guest, setGuest] = useState(invitationId ?? "all");
  const [kind, setKind] = useState("all");
  const [period, setPeriod] = useState("7");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<ActivityPage>({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const reload = useCallback(() => setRefresh(value => value + 1), []);
  useEffect(() => {
    let alive = true;
    const params = new URLSearchParams({ limit: "30", offset: String(offset) });
    if (guest !== "all") params.set("invite_id", guest);
    if (kind !== "all") params.set("kind", kind);
    if (period !== "all") params.set("start", new Date(Date.now() - Number(period) * 86400000).toISOString());
    void Promise.resolve().then(() => { if (alive) { setLoading(true); setError(""); } })
      .then(() => accessApi<ActivityPage>(`/admin/activity?${params}`))
      .then(value => { if (alive) setData(value); })
      .catch(error => { if (alive) setError(error instanceof Error ? error.message : "加载访问记录失败"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [guest, kind, period, offset, refresh]);
  return <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
    <div className="flex shrink-0 flex-wrap items-center gap-3">
      {!invitationId && <Select value={guest} onValueChange={value => { setGuest(value); setOffset(0); }}><SelectTrigger aria-label="筛选访客" className="max-w-52"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="all">全部访客</SelectItem>{invites.map(invite => <SelectItem key={invite.id} value={invite.id}>{invite.name}</SelectItem>)}</SelectGroup></SelectContent></Select>}
      <Select value={kind} onValueChange={value => { setKind(value); setOffset(0); }}><SelectTrigger aria-label="筛选行为"><SelectValue /></SelectTrigger><SelectContent><SelectGroup>{Object.entries(kinds).map(([id, title]) => <SelectItem key={id} value={id}>{title}</SelectItem>)}</SelectGroup></SelectContent></Select>
      <Select value={period} onValueChange={value => { setPeriod(value); setOffset(0); }}><SelectTrigger aria-label="筛选时间"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="7">最近 7 天</SelectItem><SelectItem value="30">最近 30 天</SelectItem><SelectItem value="all">全部时间</SelectItem></SelectGroup></SelectContent></Select>
      <Button variant="ghost" size="icon" className="ml-auto" aria-label="刷新访问记录" disabled={loading} onClick={reload}><RefreshCwIcon /></Button>
    </div>
    {error ? <Alert variant="destructive"><AlertDescription>{error}<Button variant="outline" size="sm" onClick={reload}>重试</Button></AlertDescription></Alert> : loading ? <Skeleton className="min-h-40 flex-1" /> : <div className="min-h-0 flex-1 overflow-auto rounded-xl border"><Table aria-label="访问行为记录"><TableHeader className="sticky top-0 bg-background"><TableRow><TableHead>时间</TableHead>{!invitationId && <TableHead>访客</TableHead>}<TableHead>行为</TableHead><TableHead>查看内容</TableHead><TableHead>浏览器 / 系统</TableHead></TableRow></TableHeader><TableBody>{data.items.map(event => <TableRow key={`${event.user_id}-${event.kind}-${event.id}`}><TableCell className="tabular-nums">{activityTime(event.created_at)}</TableCell>{!invitationId && <TableCell>{event.name}</TableCell>}<TableCell><Badge variant="secondary">{kinds[event.kind]}</Badge></TableCell><TableCell><div className="flex min-w-48 flex-col gap-1"><span className="max-w-lg truncate" title={event.label}>{event.label}</span>{usedTools(event) && <span className="text-xs text-muted-foreground">{usedTools(event)}</span>}</div></TableCell><TableCell className="text-muted-foreground">{event.details.device ?? "—"}</TableCell></TableRow>)}{!data.items.length && <TableRow><TableCell colSpan={invitationId ? 4 : 5} className="py-16 text-center text-muted-foreground">暂无访问记录</TableCell></TableRow>}</TableBody></Table></div>}
    <div className="flex shrink-0 items-center justify-between gap-3"><span className="text-xs text-muted-foreground">共 {data.total} 条</span><div className="flex items-center gap-3"><Button variant="outline" size="icon" aria-label="上一页" disabled={!offset || loading} onClick={() => setOffset(value => Math.max(0, value - 30))}><ChevronLeftIcon /></Button><span className="text-xs tabular-nums">{Math.floor(offset / 30) + 1} / {Math.max(1, Math.ceil(data.total / 30))}</span><Button variant="outline" size="icon" aria-label="下一页" disabled={offset + 30 >= data.total || loading} onClick={() => setOffset(value => value + 30)}><ChevronRightIcon /></Button></div></div>
  </div>;
}
