import { ArrowRightIcon, CalendarDaysIcon, DatabaseIcon, FileStackIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { StageHeading } from "./rag-document-stages";

const scale = [
  { label: "业务与参考表", value: "10", detail: "9 张业务表 + 演示时间表" },
  { label: "订单", value: "5,000", detail: "600 位客户 · 6 个地区" },
  { label: "订单明细", value: "15,027", detail: "30 款商品 · 5 个品类" },
  { label: "退款申请", value: "474", detail: "477 条退款分配明细" },
];
const documents = [
  { title: "制度与经营核对", items: "新旧退款制度、指标口径、运营月报、月度核对流程。" },
  { title: "履约与供应链", items: "供应商准入、订单履约、冷链证据、商品主数据。" },
  { title: "凭证与交接", items: "历史退款凭证档案，以及仅 Markdown 的客服交接说明。" },
];
const scenarios = [
  { title: "制度版本", example: "电子钱包：旧版 48 小时，新版 24 小时。", boundary: "按申请时间选版本，跨生效日完成也不回溯改判。" },
  { title: "事实冲突", example: "华东生鲜：月报 2%，同口径实查 8%。", boundary: "对齐时间、地区、品类与粒度，再并列保留双方依据。" },
  { title: "数据边界", example: "验收时间缺失、3 / 3 小样本、0 / 0 零分母。", boundary: "保留 NULL 与样本量，不补造时间，不把高比例当作品质结论。" },
  { title: "文档结构", example: "表格、跨页续表、计时公式与附注。", boundary: "检验解析、结构保留切块与原文定位，避免只命中半张表。" },
];

function DataPath({ items }: { items: string[] }) {
  return <div className="flex flex-wrap items-center gap-2">{items.map((item, index) => <span key={item} className="inline-flex items-center gap-2">
    {index > 0 && <ArrowRightIcon aria-hidden="true" className="size-3.5 text-muted-foreground" />}<Badge variant="outline">{item}</Badge>
  </span>)}</div>;
}

export function DatasetIntroduction() {
  return <article aria-label="数据集介绍" className="flex min-w-0 flex-col gap-6 text-sm leading-7">
    <StageHeading title="禾序食集 · 食品电商" tags={["中文合成数据"]}>围绕销售、履约、售后与月度经营核对构建。制度、报表和业务记录共享同一背景，不含真实企业或客户资料。</StageHeading>

    <section aria-label="数据规模" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {scale.map((item, index) => <Card size="sm" tone={index === 0 ? "info" : undefined} key={item.label}>
        <CardHeader><CardTitle>{item.label}</CardTitle></CardHeader>
        <CardContent className="flex flex-col gap-1"><p className="text-2xl font-semibold tracking-tight tabular-nums">{item.value}</p><p className="text-xs leading-6 text-muted-foreground">{item.detail}</p></CardContent>
      </Card>)}
    </section>

    <div className="grid items-stretch gap-5 lg:grid-cols-2">
      <Card className="min-w-0">
        <CardHeader><CardTitle className="flex items-center gap-2"><DatabaseIcon aria-hidden="true" className="size-4" />从订单追溯到退款</CardTitle><CardAction><Badge variant="outline">PostgreSQL</Badge></CardAction></CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-2"><p className="text-xs text-muted-foreground">销售链路</p><DataPath items={["客户", "订单", "订单明细"]} /></div>
          <div className="flex flex-col gap-2"><p className="text-xs text-muted-foreground">售后追溯</p><DataPath items={["退款申请", "退款分配明细", "原购买行"]} /></div>
          <p>退款沿 <code>refund_items.order_item_id</code> 回到购买明细，保留部分退款和一单多次退款；订单数、退款单数与退款金额分别统计。</p>
          <Separator />
          <div className="flex flex-wrap gap-2">{["商品", "品类", "供应商", "地区"].map(name => <Badge key={name} variant="secondary">{name}</Badge>)}</div>
          <p className="text-muted-foreground">地区取订单收货快照，品类取成交明细快照，避免主数据变化改写历史统计。</p>
        </CardContent>
      </Card>
      <Card className="min-w-0">
        <CardHeader><CardTitle className="flex items-center gap-2"><FileStackIcon aria-hidden="true" className="size-4" />与业务记录配套的文档</CardTitle><CardAction><Badge variant="outline">10 份 PDF</Badge></CardAction></CardHeader>
        <CardContent className="flex flex-col gap-4">
          <dl className="flex flex-col gap-4">{documents.map(group => <div key={group.title} className="flex flex-col gap-1"><dt className="font-medium">{group.title}</dt><dd className="text-muted-foreground">{group.items}</dd></div>)}</dl>
          <Separator />
          <p>10 份 PDF 均有 Markdown 源文，另有 1 份客服交接 Markdown。PDF 用于版面解析与区域高亮，Markdown 用于文本与行号定位。</p>
        </CardContent>
      </Card>
    </div>

    <section aria-labelledby="dataset-scenarios" className="flex flex-col gap-4">
      <h3 id="dataset-scenarios" className="text-base font-semibold">用同一套数据检验四类问题</h3>
      <div className="grid gap-x-7 gap-y-5 sm:grid-cols-2">{scenarios.map((scenario, index) => <div key={scenario.title} className="flex items-start gap-3">
        <Badge tone="info" variant="outline" className="mt-1">0{index + 1}</Badge><div className="flex flex-col gap-1"><h4 className="font-medium">{scenario.title}</h4><p>{scenario.example}</p><p className="text-muted-foreground">{scenario.boundary}</p></div>
      </div>)}</div>
    </section>

    <Separator />
    <section aria-label="统计约定" className="flex flex-wrap items-start gap-x-8 gap-y-4">
      <h3 className="flex items-center gap-2 font-medium"><CalendarDaysIcon aria-hidden="true" className="size-4" />统计约定</h3>
      <dl className="flex flex-1 flex-wrap gap-x-8 gap-y-3"><div><dt className="text-xs text-muted-foreground">主要验收期</dt><dd>2026 年 9 月</dd></div><div><dt className="text-xs text-muted-foreground">统一时区</dt><dd>Asia/Shanghai</dd></div><div><dt className="text-xs text-muted-foreground">相对日期</dt><dd>读取 <code>demo_context</code> 的参考时刻</dd></div></dl>
    </section>
  </article>;
}
