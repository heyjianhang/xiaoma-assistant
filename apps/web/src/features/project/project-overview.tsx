import { ArrowLeftRightIcon, BookOpenIcon, BotIcon, ChartNoAxesCombinedIcon, DatabaseIcon, FileStackIcon, MonitorIcon, ServerIcon, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function ArchitectureNode({ title, icon: Icon, children, accent = false }: { title: string; icon: LucideIcon; children: ReactNode; accent?: boolean }) {
  return <Card size="sm" tone={accent ? "info" : undefined} className="h-full min-w-0">
    <CardHeader><CardTitle className="flex items-center gap-2"><Icon aria-hidden="true" className="size-4 shrink-0" />{title}</CardTitle></CardHeader>
    <CardContent className="text-sm leading-6 text-muted-foreground">{children}</CardContent>
  </Card>;
}

export function ProjectOverview() {
  return <figure aria-label="小马助手整体架构" className="flex min-w-0 flex-col gap-4">
    <div className="grid items-center gap-3 sm:grid-cols-[1fr_auto_1fr]">
      <ArchitectureNode title="Web 客户端" icon={MonitorIcon}>Next.js · AI Elements · shadcn/ui</ArchitectureNode>
      <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground sm:flex-col"><ArrowLeftRightIcon aria-hidden="true" className="size-4" /><span>HTTP / SSE</span></div>
      <ArchitectureNode title="API 与后台任务" icon={ServerIcon}>FastAPI · PGMQ · Worker</ArchitectureNode>
    </div>

    <ArchitectureNode title="LangChain Agent" icon={BotIcon} accent>
      <div className="flex flex-wrap gap-2"><Badge variant="outline">create_agent</Badge><Badge variant="outline">Skill 按需加载</Badge><Badge variant="outline">TodoList</Badge><Badge variant="outline">上下文总结</Badge></div>
    </ArchitectureNode>

    <div className="grid gap-3 @2xl/workspace:grid-cols-3">
      <ArchitectureNode title="文档检索" icon={BookOpenIcon}>向量召回 → 重排 → 原文引用</ArchitectureNode>
      <ArchitectureNode title="Text2SQL" icon={DatabaseIcon}>Schema Linking → SQL → 只读执行</ArchitectureNode>
      <ArchitectureNode title="结构化结果" icon={ChartNoAxesCombinedIcon}>图表 / 指标卡 / 核对 / 澄清</ArchitectureNode>
    </div>

    <div className="grid gap-3 sm:grid-cols-[1.4fr_1fr]">
      <ArchitectureNode title="PostgreSQL" icon={DatabaseIcon}>
        <div className="flex flex-wrap gap-2"><Badge variant="secondary">pgvector 知识索引</Badge><Badge variant="secondary">只读业务表</Badge><Badge variant="secondary">身份 / 会话 / 事件</Badge></div>
      </ArchitectureNode>
      <ArchitectureNode title="文件存储" icon={FileStackIcon}>原文件 / 解析产物 / 来源坐标</ArchitectureNode>
    </div>

    <section aria-label="文档入库链路" className="flex flex-col gap-2 pt-2">
      <h2 className="text-sm font-medium">文档入库 · 独立后台 Worker</h2>
      <p className="text-sm leading-7 text-muted-foreground">上传 → PGMQ → MinerU / Markdown 解析 → 结构分块 → LangChain Document → Embedding → pgvector</p>
    </section>
  </figure>;
}
