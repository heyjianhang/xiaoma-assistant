import { ArrowDownIcon, HistoryIcon, LayersIcon, ListRestartIcon, LockKeyholeIcon, MessagesSquareIcon, RadioIcon, type LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { StageHeading } from "./rag-document-stages";

const states: { title: string; table: string; icon: LucideIcon; description: string }[] = [
  { title: "聊天记录", table: "chat_messages", icon: MessagesSquareIcon, description: "保存完整消息、引用、工具过程与结果组件，供用户回看。上下文总结不会删除原始聊天。" },
  { title: "模型上下文", table: "chat_contexts", icon: LayersIcon, description: "保存已整理的消息状态与覆盖位置。下一轮加载已有上下文，再补上该位置之后的消息。" },
  { title: "运行事件", table: "chat_run_events", icon: RadioIcon, description: "后台 Worker 持续保存输出事件。页面重连后按序号补读，切换会话不会取消执行。" },
];
const preserved = ["用户目标与确认", "任务状态", "时间与统计口径", "制度版本", "结论与证据", "冲突和缺失"];
const boundaries: { title: string; description: string; icon: LucideIcon }[] = [
  { title: "按身份与会话隔离", icon: LockKeyholeIcon, description: "同时校验 owner_id 与 conversation_id。新对话不继承其他会话，当前未启用跨会话偏好或经验记忆。" },
  { title: "历史结果仍需重新核验", icon: HistoryIcon, description: "摘要保留证据线索和未解决问题。旧结果不等于本轮已查询，工具仍会检查 context_id、result_id 和证据归属。" },
  { title: "失败与停止保留边界", icon: ListRestartIcon, description: "总结为空、截断或失败时保留原状态并报错；主动停止保留部分输出，下一轮按未完成任务处理。" },
  { title: "后台执行与重启恢复", icon: RadioIcon, description: "排队任务可在服务重启后继续；执行中断保留部分结果并标记状态，暂不支持从任意模型或工具步骤续跑。" },
];

export function MemoryIntroduction() {
  return <article aria-label="记忆与上下文介绍" className="flex min-w-0 flex-col gap-6 text-sm leading-7">
    <StageHeading title="会话记忆与长对话整理" tags={["LangChain", "PostgreSQL"]}>完整聊天、模型上下文和后台运行事件分别保存。用户可以回看历史，模型通过摘要与近期原文延续当前任务。</StageHeading>

    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,.8fr)]">
      <Card tone="info" className="min-w-0">
        <CardHeader><CardTitle className="flex items-center gap-2"><LayersIcon aria-hidden="true" className="size-4" />上下文如何压缩</CardTitle><p className="text-xs leading-6 text-muted-foreground">SummarizationMiddleware</p></CardHeader>
        <CardContent className="flex flex-col gap-5">
          <dl className="grid grid-cols-2 gap-5"><div><dt className="text-xs text-muted-foreground">默认总结触发点</dt><dd className="text-2xl font-semibold tracking-tight">约 75%<span className="ml-2 text-xs font-normal text-muted-foreground">窗口占用</span></dd></div><div><dt className="text-xs text-muted-foreground">默认近期原文预算</dt><dd className="text-2xl font-semibold tracking-tight">约 25%<span className="ml-2 text-xs font-normal text-muted-foreground">模型窗口</span></dd></div></dl>
          <Separator />
          <figure aria-label="上下文压缩前后示意" className="flex flex-col gap-3">
            <div className="flex flex-col gap-2"><p className="text-xs text-muted-foreground">压缩前 · 多轮消息逐步积累</p><div className="grid grid-cols-[2fr_1fr] gap-2"><Badge variant="secondary" className="h-10 w-full justify-center">早期消息</Badge><Badge variant="outline" className="h-10 w-full justify-center">近期原文</Badge></div></div>
            <ArrowDownIcon aria-hidden="true" className="size-4 self-center text-muted-foreground" />
            <div className="flex flex-col gap-2"><p className="text-xs text-muted-foreground">下一轮 · 会话消息的组成</p><div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] items-center gap-2"><Badge tone="info" variant="outline" className="h-9 w-full justify-center">历史摘要</Badge><span aria-hidden="true" className="text-muted-foreground">+</span><Badge variant="outline" className="h-9 w-full justify-center">近期原文</Badge><span aria-hidden="true" className="text-muted-foreground">+</span><Badge variant="outline" className="h-9 w-full justify-center">新增问题</Badge></div></div>
          </figure>
          <Separator />
          <div className="flex flex-col gap-3"><h3 className="font-medium">摘要保留什么</h3><div className="flex flex-wrap gap-2">{preserved.map(item => <Badge key={item} variant="secondary">{item}</Badge>)}</div><p className="text-muted-foreground">区分用户确认、工具事实与模型推测；内部总结不作为本轮回答输出。</p></div>
        </CardContent>
      </Card>
      <section aria-label="会话状态分层" className="grid gap-4">
        {states.map(state => <Card size="sm" key={state.title} className="min-w-0">
          <CardHeader><CardTitle className="flex items-center gap-2"><state.icon aria-hidden="true" className="size-4" />{state.title}</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-2"><p>{state.description}</p><code className="text-xs text-muted-foreground">{state.table}</code></CardContent>
        </Card>)}
      </section>
    </div>

    <section aria-labelledby="memory-boundaries" className="flex flex-col gap-4">
      <h3 id="memory-boundaries" className="text-base font-semibold">隔离、复核与恢复</h3>
      <div className="grid gap-x-7 gap-y-5 sm:grid-cols-2">{boundaries.map(item => <div key={item.title} className="flex items-start gap-3"><item.icon aria-hidden="true" className="mt-1 size-4 shrink-0 text-muted-foreground" /><div className="flex flex-col gap-1"><h4 className="font-medium">{item.title}</h4><p className="text-muted-foreground">{item.description}</p></div></div>)}</div>
    </section>
  </article>;
}
