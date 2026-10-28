"use client";

import { ArrowUpRightIcon, CircleAlertIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { ChatPresentation, ClarificationPresentation, PresentationSlot } from "./presentation-types";
import { DataViewCard } from "./data-view-card";
import { EvidenceReviewCard } from "./evidence-review-card";

interface OutputContext { busy: boolean; selectedOptionId?: string; onSelect: (optionId: string) => void }
function ClarificationCard({ payload, busy, selectedOptionId, onSelect }: { payload: ClarificationPresentation } & OutputContext) {
  return <Card tone="info" aria-label={payload.title}><CardHeader><CardTitle>{payload.title}</CardTitle><CardDescription>{payload.reason}</CardDescription><CardAction><Badge variant="outline" tone={selectedOptionId ? "success" : "info"}>{selectedOptionId ? "已选择" : "待确认"}</Badge></CardAction></CardHeader><CardContent className="flex flex-wrap gap-2">{payload.options.map(option => <Button key={option.id} variant="outline" tone={selectedOptionId === option.id ? "success" : "info"} disabled={busy || !!selectedOptionId} aria-pressed={selectedOptionId === option.id} onClick={() => onSelect(option.id)}>{option.label}<ArrowUpRightIcon data-icon="inline-end" /></Button>)}</CardContent></Card>;
}
type Renderer = (payload: ChatPresentation, context: OutputContext) => React.ReactNode;
// Tool output types map to registered components. The model never supplies JSX.
const renderers: Record<ChatPresentation["type"], Renderer> = {
  data_view: payload => payload.type === "data_view" && <DataViewCard payload={payload} />,
  evidence_review: payload => payload.type === "evidence_review" && <EvidenceReviewCard payload={payload} />,
  clarification: (payload, context) => payload.type === "clarification" && <ClarificationCard payload={payload} {...context} />,
};
export function ChatPresentations({ slots, busy, onSelect }: { slots: PresentationSlot[]; busy: boolean; onSelect: (slotId: string, optionId: string) => void }) {
  return <div className="flex min-w-0 flex-col gap-4 p-0.5">{slots.map(slot => <div key={slot.id} data-presentation={slot.payload?.type ?? slot.status}>
    {slot.status === "loading" ? <Card aria-label={`${slot.title}生成中`}><CardHeader><CardTitle>{slot.title}</CardTitle><CardDescription>正在组织展示内容…</CardDescription></CardHeader><CardContent className="flex flex-col gap-3"><Skeleton className="h-8 w-1/3" /><Skeleton className="h-24 w-full" /></CardContent></Card>
      : slot.status === "error" ? <Alert variant="destructive" tone="danger"><CircleAlertIcon /><AlertTitle>{slot.title}</AlertTitle><AlertDescription>{slot.error}</AlertDescription></Alert>
        : slot.status === "stopped" ? <p className="text-xs text-muted-foreground">{slot.title} · 已停止，展示内容尚未完成</p>
          : slot.payload ? renderers[slot.payload.type](slot.payload, { busy, selectedOptionId: slot.selectedOptionId, onSelect: optionId => onSelect(slot.id, optionId) }) : null}
  </div>)}</div>;
}
