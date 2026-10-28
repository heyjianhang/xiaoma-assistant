"use client";

import { RotateCcwIcon } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { ChatPresentations } from "@/features/chat/chat-presentations";
import { EvidenceReviewCard } from "@/features/chat/evidence-review-card";
import type { ClarificationPresentation } from "@/features/chat/presentation-types";
import { ReviewEvidenceActions, ReviewEvidenceDialog } from "./review-evidence-dialog";
import { zeroDenominatorQuery, zeroDenominatorSources, type ReviewScenario } from "./review-scenarios";

const clarification: ClarificationPresentation = {
  type: "clarification", title: "先确认你想查看哪项指标", reason: "“售后异常率”尚无明确口径，可以选择已有指标或补充异常定义。",
  options: ["成功退款订单率", "延迟发货占比", "补充异常定义"].map((label, index) => ({ id: String(index), label, question: label })),
};

export function ReviewComponentPreview({ scenario }: { scenario: ReviewScenario }) {
  const [selected, setSelected] = useState<string>();
  const actions = <ReviewEvidenceActions sources={scenario.sources} query={scenario.query} />;
  return <section aria-label="解释结果组件" className="flex min-w-0 flex-col gap-3">
    {scenario.review && <EvidenceReviewCard payload={scenario.review} footer={actions} />}

    {scenario.id === "version" && <Card tone="success" className="min-w-0">
      <CardHeader><CardTitle>沿用旧版，实际到账按时</CardTitle><CardAction><Badge tone="success" variant="outline">版本适用</Badge></CardAction></CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ol className="flex flex-col gap-4">
          {[
            { time: scenario.query?.rows[0].applied_at, title: "提交申请", detail: "早于 9 月 1 日生效点，适用旧版 1.0。" },
            { time: scenario.query?.rows[0].accepted_at, title: "验收通过", detail: "到账阶段从此开始计时。" },
            { time: scenario.query?.rows[0].completed_at, title: "成功到账", detail: "实际 48 自然小时，等于旧版上限，视为按时。" },
          ].map((event, index) => <li key={event.title} className="flex gap-3"><Badge variant="outline">0{index + 1}</Badge><div className="flex flex-col gap-1"><h3 className="font-medium">{event.title} · {String(event.time)}</h3><p className="text-muted-foreground">{event.detail}</p></div></li>)}
        </ol>
        <p>所有时间均为北京时间。新旧时限不同属于版本适用问题，不能只看完成日期判“冲突”或“超时”。</p>
      </CardContent>
      <CardFooter>{actions}</CardFooter>
    </Card>}

    {scenario.id === "clarify" && <>
      <ChatPresentations slots={[{ id: "clarification-demo", title: clarification.title, status: "ready", payload: clarification, selectedOptionId: selected }]} busy={false} onSelect={(_, option) => setSelected(option)} />
      {selected && <div className="flex flex-wrap items-center gap-2"><p className="text-sm">本例已选择“{clarification.options.find(option => option.id === selected)?.label}”。</p><Button variant="ghost" size="sm" onClick={() => setSelected(undefined)}><RotateCcwIcon data-icon="inline-start" />重新选择</Button></div>}
      <p className="text-xs leading-5 text-muted-foreground">这里演示选择状态；正式对话会将选择作为下一条消息继续。</p>
      {actions}
    </>}

    {scenario.id === "small" && <div className="flex flex-wrap items-center gap-2 pt-1"><span className="text-sm">零分母时，0 / 0 保留为 NULL。</span><ReviewEvidenceDialog sources={zeroDenominatorSources} query={zeroDenominatorQuery} start="data" label="查看零分母样例" /></div>}
  </section>;
}
