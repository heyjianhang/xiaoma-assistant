"use client";

import { FileCheckIcon, ScaleIcon } from "lucide-react";
import { useRef } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StageHeading } from "./rag-document-stages";
import { ReviewComponentPreview } from "./review-component-preview";
import { reviewScenarios } from "./review-scenarios";

const classifications = [
  { kind: "conflict", when: "同一口径下的事实数值仍然不同", output: "存在差异", action: "并列两份依据与差值，不自动认定原因。" },
  { kind: "execution_deviation", when: "实际执行超出适用制度要求", output: "存在执行偏差", action: "先匹配版本与计时条件，不把规范与事实的差别称为文档冲突。" },
  { kind: "missing_definition", when: "指标或计算口径没有明确规定", output: "待明确口径", action: "可以只凭文档定义核查后发起澄清，不先计算未知指标。" },
  { kind: "small_sample", when: "比例有事实依据，但样本不足", output: "样本不足", action: "保留分子分母，限制推广与因果结论。" },
];

export function EvidenceIntroduction() {
  const contentRef = useRef<HTMLDivElement>(null);
  return <article aria-label="证据核对与异常处理" className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden text-sm leading-7">
    <Tabs defaultValue="conflict" onValueChange={() => contentRef.current?.scrollTo({ top: 0 })} className="min-h-0 min-w-0 flex-1 gap-5 overflow-hidden">
      <div className="min-w-0 shrink-0 overflow-x-auto px-0.5 pb-2"><TabsList variant="line" aria-label="证据核对场景" className="h-auto justify-start gap-2 p-0">
        {reviewScenarios.map(scenario => <TabsTrigger key={scenario.id} value={scenario.id} className="h-10 px-3">{scenario.label}</TabsTrigger>)}
      </TabsList></div>
      <div ref={contentRef} role="region" aria-label="证据核对说明" tabIndex={0} className="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain px-0.5 pb-6">
        <div className="flex flex-col gap-7">
          {reviewScenarios.map(scenario => <TabsContent key={scenario.id} value={scenario.id} className="m-0 flex flex-col gap-5">
            <StageHeading title={scenario.title} tags={scenario.review ? [scenario.review.kind] : scenario.id === "clarify" ? ["ask_clarification"] : undefined}>{scenario.question}</StageHeading>
            <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,.95fr)_minmax(0,1.05fr)]">
              <div className="flex min-w-0 flex-col gap-5">
                <div className="grid gap-3 sm:grid-cols-2">
                  {scenario.evidence.map((item, index) => <Card size="sm" key={item.label} tone={index === 1 ? "info" : undefined} className="min-w-0">
                    <CardHeader><CardTitle>{item.label}</CardTitle></CardHeader>
                    <CardContent className="flex flex-col gap-2"><p className="break-words text-2xl font-semibold tracking-tight tabular-nums">{item.value}</p><p className="text-xs leading-6 text-muted-foreground">{item.detail}</p></CardContent>
                  </Card>)}
                </div>
                <section aria-label="本例核对口径" className="flex flex-col gap-3">
                  <h3 className="text-base font-semibold">本例核对口径</h3>
                  <dl className="grid gap-x-5 gap-y-3 sm:grid-cols-2">{scenario.scope.map(item => <div key={item.label} className="flex flex-col gap-1"><dt className="text-xs text-muted-foreground">{item.label}</dt><dd>{item.value}</dd></div>)}</dl>
                </section>
              </div>
              <ReviewComponentPreview scenario={scenario} />
            </div>
            <ol aria-label="本例判断过程" className="grid gap-4 lg:grid-cols-3">
              {scenario.steps.map((step, index) => <li key={step} className="flex items-start gap-2"><Badge variant="outline" tone="info" className="mt-1">0{index + 1}</Badge><p>{step}</p></li>)}
            </ol>
          </TabsContent>)}

          <Separator />
          <section aria-labelledby="evidence-classifications" className="flex min-w-0 flex-col gap-3">
            <h2 id="evidence-classifications" className="text-base font-semibold">不同情况，采用不同的解释方式</h2>
            <div className="min-w-0 overflow-hidden rounded-lg border"><Table>
              <TableHeader><TableRow><TableHead>核对类型</TableHead><TableHead>判断条件</TableHead><TableHead>组件状态</TableHead><TableHead>处理原则</TableHead></TableRow></TableHeader>
              <TableBody>{classifications.map(item => <TableRow key={item.kind}><TableCell className="align-top"><code className="text-xs">{item.kind}</code></TableCell><TableCell className="min-w-40 whitespace-normal align-top">{item.when}</TableCell><TableCell className="align-top">{item.output}</TableCell><TableCell className="min-w-52 whitespace-normal align-top">{item.action}</TableCell></TableRow>)}</TableBody>
            </Table></div>
            <p>缺少可比条件时，核对卡显示“不可直接比较”；需要等待用户定义时，由 <code>ask_clarification</code> 展示候选项。</p>
          </section>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card size="sm">
              <CardHeader><CardTitle className="flex items-center gap-2"><FileCheckIcon aria-hidden="true" className="size-4" />工具校验证据与结果的归属</CardTitle></CardHeader>
              <CardContent className="flex flex-col gap-3"><p><code>present_evidence_review</code> 要求引用本轮真实文档证据。除缺定义场景外，还必须引用本轮已执行的 SQL 结果。</p><p>工具返回结构化核对或澄清数据，前端映射到已注册 React 组件；模型不生成 JSX，也不另造查询行。</p></CardContent>
            </Card>
            <Card size="sm" tone="info">
              <CardHeader><CardTitle className="flex items-center gap-2"><ScaleIcon aria-hidden="true" className="size-4" />语义可比性仍由模型按 SOP 核对</CardTitle></CardHeader>
              <CardContent className="flex flex-col gap-3"><p><code>/evidence-review</code> 要求核对时间、地区、品类、粒度、分母、单位与制度版本，区分事实冲突、执行偏差和缺失。</p><p><code>comparable=true</code> 是模型的判断声明。证据 ID 校验通过，不代表服务端已证明业务结论正确。</p></CardContent>
            </Card>
          </div>
          <p className="text-xs leading-5 text-muted-foreground">案例使用固定合成文档节选与 SQL 实测快照，复用聊天中的核对卡和澄清组件；页面切换不会调用模型或提交新对话。</p>
        </div>
      </div>
    </Tabs>
  </article>;
}
