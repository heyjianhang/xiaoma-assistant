"use client";

import { useActivityView } from "@/lib/access/activity";
import { Badge } from "@/components/ui/badge";
import { Card, CardAction, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { MarkdownPreview } from "@/components/markdown-preview";
import { documentTitles, promptSetup, type PromptCase } from "./prompt-cases";

export function PromptCaseDetails({ prompt }: { prompt: PromptCase }) {
  useActivityView("test_case_view", { target_id: prompt.id });
  return <div className="flex min-w-0 flex-col gap-4 p-0.5">
    <div className="flex flex-wrap gap-2">
      <Badge variant="secondary">{prompt.group}</Badge>
      <Badge variant="outline">参考路径：{prompt.expected_route}</Badge>
      {prompt.components.map(component => <Badge key={component} variant="outline">{component}</Badge>)}
    </div>
    <Card size="sm" aria-label="测试问题">
      <CardHeader className="border-b"><CardTitle role="heading" aria-level={3}>测试问题</CardTitle></CardHeader>
      <CardContent><p className="text-sm leading-6">{prompt.question}</p></CardContent>
    </Card>
    <Card tone="info" aria-label="预期答案" className="min-w-0">
      <CardHeader className="border-b"><CardTitle role="heading" aria-level={3}>预期答案</CardTitle></CardHeader>
      <CardContent className="min-w-0"><MarkdownPreview content={prompt.expected_answer} className="text-sm leading-7" /></CardContent>
    </Card>
    <Card aria-label="验收要点">
      <CardHeader className="border-b"><CardTitle role="heading" aria-level={3}>验收要点</CardTitle><CardAction><Badge variant="secondary">{prompt.checks.length} 项</Badge></CardAction></CardHeader>
      <CardContent><ol className="flex list-decimal flex-col gap-2 pl-5 text-sm leading-6">{prompt.checks.map(check => <li key={check}>{check}</li>)}</ol></CardContent>
    </Card>
    <Card size="sm" aria-label="测试准备">
      <CardHeader className="border-b"><CardTitle role="heading" aria-level={3}>测试准备</CardTitle></CardHeader>
      <CardContent className="grid gap-5 sm:grid-cols-2">
        <section aria-label="前置资料" className="flex min-w-0 flex-col gap-2">
          <h4 className="text-xs font-medium text-muted-foreground">前置资料</h4>
          {prompt.required_documents.length ? <ul className="flex flex-col gap-3 text-sm">{prompt.required_documents.map(filename => <li key={filename} className="flex flex-col gap-1"><span>{documentTitles[filename] ?? filename}</span><span className="break-all text-xs text-muted-foreground">{filename}</span></li>)}</ul> : <p className="text-sm leading-6">固定演示业务数据库，无需额外文档。</p>}
        </section>
        <section aria-label="参考依据" className="flex min-w-0 flex-col gap-2">
          <h4 className="text-xs font-medium text-muted-foreground">参考依据</h4>
          <ul className="flex list-disc flex-col gap-1 pl-4 text-sm leading-6">{prompt.reference.map(reference => <li key={reference}>{reference}</li>)}</ul>
        </section>
      </CardContent>
      <CardFooter className="flex-col items-start gap-2">
        <h4 className="text-xs font-medium text-muted-foreground">测试条件</h4>
        <ul className="flex list-disc flex-col gap-1 pl-4 text-xs leading-6 text-muted-foreground">{promptSetup.map(condition => <li key={condition}>{condition}</li>)}</ul>
      </CardFooter>
    </Card>
  </div>;
}
