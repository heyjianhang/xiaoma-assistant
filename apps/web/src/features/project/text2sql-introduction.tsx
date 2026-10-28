"use client";

import { ArrowRightIcon, BookOpenIcon, ShieldCheckIcon } from "lucide-react";
import { Fragment, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StageHeading } from "./rag-document-stages";
import { CatalogPreview, inspectedFields, linkedFields, LinkingPreview, ResultPreview, SchemaPreview, SqlPreview } from "./text2sql-previews";
import sample from "./fixtures/sql-walkthrough.json";

const stages = [
  { id: "catalog", label: "表目录" },
  { id: "schema", label: "候选表结构" },
  { id: "link", label: "Schema Linking" },
  { id: "execute", label: "SQL 生成与执行" },
  { id: "result", label: "摘要与图表" },
];
const tools = [
  { name: "list_tables", stage: "catalog", output: "表名与简短中文业务说明，建立业务目录。", boundary: "不返回字段、全量 DDL 或业务行。" },
  { name: "get_table_schema", stage: "schema", output: "候选表字段、类型、业务含义和主外键关系。", boundary: "每次读取 1–3 张候选表，可以继续补查。" },
  { name: "link_schema", stage: "link", output: "明确选表、选字段、关联和粒度，返回本轮 context_id。", boundary: "只接受已查看的表字段；上下文绑定当前运行。" },
  { name: "execute_readonly_sql", stage: "execute", output: "已执行 SQL、真实结果、截断标记与 result_id。", boundary: "校验已选表字段；独立只读连接，5 秒超时、最多展示 200 行。" },
  { name: "render_chart", stage: "result", output: "表格、指标卡、柱状图或折线图。", boundary: "引用本轮已执行的 result_id，不接收模型自造 rows。" },
];

export function Text2SqlIntroduction() {
  const [stage, setStage] = useState("link");
  const contentRef = useRef<HTMLDivElement>(null);

  function viewTool(id: string) {
    setStage(id);
    contentRef.current?.scrollTo({ top: 0 });
  }

  return <article aria-label="Text2SQL 实现" className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden text-sm leading-7">
    <Tabs value={stage} onValueChange={viewTool} className="min-h-0 min-w-0 flex-1 gap-5 overflow-hidden">
      <div className="min-w-0 shrink-0 overflow-x-auto px-0.5 pb-2">
        <TabsList variant="line" aria-label="Text2SQL 查询链路" className="h-auto justify-start gap-2 p-0">
          {stages.map((item, index) => <Fragment key={item.id}>
            {index > 0 && <ArrowRightIcon aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />}
            <TabsTrigger value={item.id} className="h-10 px-3">{item.label}</TabsTrigger>
          </Fragment>)}
        </TabsList>
      </div>

      <div ref={contentRef} role="region" aria-label="Text2SQL 说明" tabIndex={0} className="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain px-0.5 pb-6">
        <div className="flex flex-col gap-7">
          <TabsContent value="catalog" className="m-0">
            <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,.8fr)_minmax(0,1.2fr)]">
              <div className="flex flex-col gap-5">
                <StageHeading title="先了解有哪些业务表" tags={["list_tables"]}>初始提示词不放全量 DDL。AI 先读取精简目录，根据表的业务含义选择需要深入查看的候选。</StageHeading>
                <dl className="flex flex-col gap-4">
                  <div className="flex flex-col gap-1"><dt className="font-medium">这一步获得什么</dt><dd className="text-muted-foreground">{sample.catalog.length} 张表的名称和业务说明，还没有字段定义和业务数据。</dd></div>
                  <div className="flex flex-col gap-1"><dt className="font-medium">如何缩小范围</dt><dd className="text-muted-foreground">问题涉及退款金额与品类，优先查看退款单和明细，再沿关联寻找成交时的品类。</dd></div>
                  <div className="flex flex-col gap-1"><dt className="font-medium">为什么分层获取</dt><dd className="text-muted-foreground">目录用于发现业务范围，详细结构按需返回，避免让所有表字段占据模型上下文。</dd></div>
                </dl>
              </div>
              <CatalogPreview />
            </div>
          </TabsContent>

          <TabsContent value="schema" className="m-0">
            <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,.8fr)_minmax(0,1.2fr)]">
              <div className="flex flex-col gap-5">
                <StageHeading title="读完一批，再决定是否补查" tags={["get_table_schema"]}>每次最多查看 3 张候选表。字段说明和外键提供下一步线索，AI 可以继续调用工具补足结构。</StageHeading>
                <ol className="flex flex-col gap-4">
                  <li className="flex gap-3"><Badge tone="info" variant="outline">01</Badge><div className="flex flex-col gap-2"><h3 className="font-medium">第一批：退款与购买明细</h3><div className="flex flex-wrap gap-1.5"><Badge variant="secondary">refunds</Badge><Badge variant="secondary">refund_items</Badge><Badge variant="secondary">order_items</Badge></div><p className="text-muted-foreground">看到退款状态、分配金额与原购买行，并发现 category_id 是成交时的品类快照。</p></div></li>
                  <li className="flex gap-3"><Badge tone="info" variant="outline">02</Badge><div className="flex flex-col gap-2"><h3 className="font-medium">第二批：补查品类维表</h3><div><Badge variant="secondary">categories</Badge></div><p className="text-muted-foreground">沿 category_id 关系补查中文品类名称。本例共查看 4 张表、{inspectedFields} 个字段，尚未查询业务行。</p></div></li>
                </ol>
              </div>
              <SchemaPreview />
            </div>
          </TabsContent>

          <TabsContent value="link" className="m-0">
            <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,.8fr)_minmax(0,1.2fr)]">
              <div className="flex flex-col gap-5">
                <StageHeading title="把问题映射到表、字段与统计粒度" tags={["link_schema"]}>从已查看的 {inspectedFields} 个字段中选出本次查询需要的 {linkedFields} 个，显式记录关联路径、问题范围和统计粒度。</StageHeading>
                <dl className="flex flex-col gap-4">
                  <div className="flex flex-col gap-1"><dt className="font-medium">过滤范围</dt><dd className="text-muted-foreground">仅退款状态为 <code className="text-foreground">completed</code> 的记录，不限制日期。</dd></div>
                  <div className="flex flex-col gap-1"><dt className="font-medium">金额与品类</dt><dd className="text-muted-foreground">汇总 <code className="text-foreground">refund_items.amount</code>，经原购买行的 <code className="text-foreground">category_id</code> 关联品类名称。</dd></div>
                  <div className="flex flex-col gap-1"><dt className="font-medium">统计粒度</dt><dd className="text-muted-foreground">{sample.linked.grain}。不把退款头金额在明细关联后重复累计。</dd></div>
                </dl>
              </div>
              <LinkingPreview />
            </div>
          </TabsContent>

          <TabsContent value="execute" className="m-0">
            <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,.8fr)_minmax(0,1.2fr)]">
              <div className="flex flex-col gap-5">
                <StageHeading title="主 Agent 写 SQL，服务端校验后执行" tags={["SQLGlot", "PostgreSQL"]}>SQL 由当前 Agent 直接生成，交给 execute_readonly_sql；没有额外的 SQL 生成 Agent。</StageHeading>
                <dl className="flex flex-col gap-4">
                  <div className="flex flex-col gap-1"><dt className="font-medium">上下文检查</dt><dd className="text-muted-foreground">执行时提交有效 context_id，只允许引用本轮 Linking 选中的业务表与字段。</dd></div>
                  <div className="flex flex-col gap-1"><dt className="font-medium">语法树检查</dt><dd className="text-muted-foreground">SQLGlot 解析单条查询，校验别名、CTE 与字段引用，拒绝写入、锁、系统 Schema 和普通 SELECT *。</dd></div>
                  <div className="flex flex-col gap-1"><dt className="font-medium">只读执行</dt><dd className="text-muted-foreground">独立 SELECT-only 账号与只读事务，数据库超时 5 秒；最多展示 200 行，超出时明确标记截断。</dd></div>
                  <div className="flex flex-col gap-1"><dt className="font-medium">失败如何继续</dt><dd className="text-muted-foreground">语法或字段错误返回工具消息，让模型修正；只有执行成功后才能报告查询数值。</dd></div>
                </dl>
              </div>
              <SqlPreview />
            </div>
          </TabsContent>

          <TabsContent value="result" className="m-0">
            <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,.8fr)_minmax(0,1.2fr)]">
              <div className="flex flex-col gap-5">
                <StageHeading title="实际结果转成摘要与 ChatBI" tags={["result_id", "render_chart"]}>查询成功后，服务端保存结果并生成 result_id。模型选择展示类型和字段，图表的数值取自已执行结果。</StageHeading>
                <dl className="flex flex-col gap-4">
                  <div className="flex flex-col gap-1"><dt className="font-medium">自然语言结论</dt><dd className="text-muted-foreground">本例中，滋补礼盒的成功退款金额最高，为 <strong className="font-semibold text-foreground">5,456 元</strong>。金额高不等于退款率高，也不能直接推断品质问题。</dd></div>
                  <div className="flex flex-col gap-1"><dt className="font-medium">保留统计口径</dt><dd className="text-muted-foreground">统计所有日期的成功退款，按退款商品分配金额归入成交时品类；本例返回 5 行，未截断。</dd></div>
                  <div className="flex flex-col gap-1"><dt className="font-medium">结构化呈现</dt><dd className="text-muted-foreground">同一结果可展示为表格、指标卡、柱状图或折线图；渲染工具只接收结果引用与字段配置。</dd></div>
                  <div className="flex flex-col gap-1"><dt className="font-medium">需要交叉核对时</dt><dd className="text-muted-foreground">按需联动文档检索、证据核对或澄清工具，分别解释版本冲突、字段缺失与口径歧义。</dd></div>
                </dl>
              </div>
              <ResultPreview />
            </div>
          </TabsContent>

          <Separator />
          <section aria-labelledby="sql-tool-matrix" className="flex min-w-0 flex-col gap-3">
            <h2 id="sql-tool-matrix" className="text-base font-semibold">工具矩阵</h2>
            <div className="min-w-0 overflow-hidden rounded-lg border"><Table>
              <TableHeader><TableRow><TableHead>工具</TableHead><TableHead>AI 获得什么</TableHead><TableHead>调用边界</TableHead></TableRow></TableHeader>
              <TableBody>{tools.map(tool => <TableRow key={tool.name} data-state={stage === tool.stage ? "selected" : undefined}>
                <TableCell className="align-top"><Button variant="ghost" size="sm" onClick={() => viewTool(tool.stage)} aria-label={`查看 ${tool.name} 阶段说明`}><code>{tool.name}</code></Button></TableCell>
                <TableCell className="min-w-48 whitespace-normal align-top">{tool.output}</TableCell><TableCell className="min-w-56 whitespace-normal align-top">{tool.boundary}</TableCell>
              </TableRow>)}</TableBody>
            </Table></div>
          </section>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card size="sm">
              <CardHeader><CardTitle className="flex items-center gap-2"><BookOpenIcon aria-hidden="true" className="size-4" />Skill 给出查询 SOP</CardTitle></CardHeader>
              <CardContent className="flex flex-col gap-3"><p>按需加载 <code>/sql</code> 技能与核对清单，引导目录发现、候选结构、显式 Linking 和实际执行；约定时间口径、去重与聚合方式。</p><div className="flex flex-wrap gap-2"><Badge variant="outline">load_skill</Badge><Badge variant="outline">read_skill_resource</Badge></div></CardContent>
            </Card>
            <Card size="sm" tone="info">
              <CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheckIcon aria-hidden="true" className="size-4" />服务端强制执行边界</CardTitle></CardHeader>
              <CardContent className="flex flex-col gap-3"><p>工具开关控制本轮注册能力；已查看结构决定可链接字段；本轮 context_id 决定 SQL 可用范围；独立数据库账号落实只读权限。</p><div className="flex flex-wrap gap-2"><Badge variant="outline">运行归属</Badge><Badge variant="outline">AST 校验</Badge><Badge variant="outline">只读事务</Badge></div></CardContent>
            </Card>
          </div>
          <p className="text-muted-foreground">Schema 校验限制 SQL 使用的结构范围；关联方式和统计口径是否正确，仍需业务核对。已读取的上下文会保留，Linking 不会自动删除模型之前看过的字段。</p>
        </div>
      </div>
    </Tabs>
  </article>;
}
