"use client";

import { CheckIcon, CircleAlertIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import type { ReviewPresentation } from "./presentation-types";
import { EvidenceSourceButton } from "./evidence-source";
import { QueryDetailsButton } from "./query-details";
import type { UiTone } from "@/lib/ui-tones";

export function EvidenceReviewCard({ payload }: { payload: ReviewPresentation }) {
  const tone: UiTone = payload.verdict === "存在差异" || payload.verdict === "存在执行偏差" ? "danger" : payload.verdict === "版本适用" ? "success" : payload.verdict === "不可直接比较" ? "info" : "warning";
  return <Card tone={tone} aria-label={payload.title} className="min-w-0">
    <CardHeader><CardTitle>{payload.title}</CardTitle><CardDescription>{payload.summary}</CardDescription><CardAction><Badge variant="outline" tone={tone}>{payload.verdict}</Badge></CardAction></CardHeader>
    <CardContent className="flex flex-col gap-4">
      {!!payload.facts.length && <dl className="grid gap-4 sm:grid-cols-2">{payload.facts.map(fact => <div key={fact.label} className="flex flex-col gap-1.5 rounded-lg bg-muted/50 p-4"><dt className="text-xs text-muted-foreground">{fact.label}</dt><dd className="text-2xl font-semibold tabular-nums">{fact.value}</dd><dd className="text-xs leading-6 text-muted-foreground">{fact.detail}</dd></div>)}</dl>}
      {!!payload.checks.length && <ul aria-label="核对依据" className="flex flex-col gap-2">{payload.checks.map(check => <li key={check} className="flex items-start gap-2 text-sm leading-6"><CheckIcon className="mt-1 size-4 shrink-0 text-muted-foreground" /><span>{check}</span></li>)}</ul>}
      {!!payload.limitations.length && <Alert tone={tone}><CircleAlertIcon /><AlertDescription><ul className="flex flex-col gap-2">{payload.limitations.map(limit => <li key={limit}>{limit}</li>)}</ul></AlertDescription></Alert>}
    </CardContent>
    <CardFooter className="flex-wrap justify-between gap-2"><div className="flex flex-wrap items-center gap-1"><Badge variant="outline">证据核对</Badge>{payload.sources.map(source => <EvidenceSourceButton key={source.id} source={source} />)}</div>{payload.result && <QueryDetailsButton result={payload.result} />}</CardFooter>
  </Card>;
}
