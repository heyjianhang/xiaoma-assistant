import { ArrowRightIcon, FileTextIcon, LinkIcon, LockKeyholeIcon, ScanTextIcon } from "lucide-react";
import type { ReactNode } from "react";
import { MarkdownPreview } from "@/components/markdown-preview";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import pdf from "./fixtures/mineru-page-sample.json";
import defaults from "./fixtures/rag-defaults.json";

export function StageHeading({ title, children, tags }: { title: string; children: ReactNode; tags?: string[] }) {
  return <header className="flex max-w-4xl flex-col gap-3">
    <div className="flex flex-wrap items-center gap-3"><h2 className="text-xl font-semibold tracking-tight">{title}</h2>{tags?.map(tag => <Badge key={tag} variant="outline" tone="info">{tag}</Badge>)}</div>
    <p>{children}</p>
  </header>;
}

export function SourcePreview({ compact = false }: { compact?: boolean }) {
  const blocks = compact ? pdf.blocks.filter(block => block.kind === "table") : pdf.blocks;
  return <Card className="min-w-0">
    <CardHeader>
      <CardTitle className="flex items-center gap-2"><FileTextIcon aria-hidden="true" className="size-4" />{pdf.title}</CardTitle>
      <div className="flex flex-wrap items-center gap-2 pt-1"><Badge variant="secondary">第 {pdf.page} 页</Badge><Badge variant="outline">MinerU 真实解析节选</Badge></div>
    </CardHeader>
    <CardContent className="min-w-0">
      <div className="max-h-[26rem] overflow-y-auto overscroll-contain">
        <MarkdownPreview content={blocks.map(block => block.markdown).join("\n\n")} className="text-sm leading-7 [&_h2]:text-base [&_table]:min-w-[24rem]" />
      </div>
    </CardContent>
  </Card>;
}

export function ParseStage() {
  return <>
    <StageHeading title="从 PDF 版面提取可检索的结构" tags={["MinerU", defaults.mineru_model_version.toUpperCase()]}>
      PDF 使用 MinerU precision v4，开启中文、表格与公式识别；Markdown 使用 markdown-it 解析。两种入口统一为原子块，再进入切割器。
    </StageHeading>
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,.85fr)_minmax(0,1.15fr)]">
      <div className="flex min-w-0 flex-col gap-5">
        <Card size="sm" tone="info">
          <CardHeader><CardTitle className="flex items-center gap-2"><ScanTextIcon aria-hidden="true" className="size-4" />解析与归一化</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2"><Badge variant="outline">PDF 原文</Badge><ArrowRightIcon aria-hidden="true" className="size-4" /><Badge variant="outline">MinerU VLM</Badge><ArrowRightIcon aria-hidden="true" className="size-4" /><Badge variant="outline">结构块</Badge></div>
            <p>按阅读顺序提取标题、正文、表格、公式和图片说明，过滤页眉、页脚与页码。</p>
          </CardContent>
        </Card>
        <dl className="flex flex-col gap-4">
          <div className="flex flex-col gap-1"><dt className="font-medium">内容类型</dt><dd className="text-muted-foreground">保留标题层级与正文。表格保存为可渲染的 HTML，独立公式使用 LaTeX，避免压成一串文本。</dd></div>
          <div className="flex flex-col gap-1"><dt className="font-medium">附属说明</dt><dd className="text-muted-foreground">MinerU 表格标题、表体与脚注先合并；紧随其后的“注、说明、式中”等段落，再归入对应表格或公式。</dd></div>
          <div className="flex flex-col gap-1"><dt className="font-medium">来源位置</dt><dd className="text-muted-foreground">PDF 保留页码和区域坐标；Markdown 保留行号。合并内容时同时合并来源引用，供后续原文高亮。</dd></div>
        </dl>
      </div>
      <SourcePreview />
    </div>
  </>;
}

export function DocumentStage() {
  return <>
    <StageHeading title="正文与来源一起成为 Document" tags={["LangChain Document"]}>
      切好的内容直接写入 page_content，文档版本、章节和位置放入 metadata。检索返回原内容时，来源信息也随之返回。
    </StageHeading>
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,.9fr)]">
      <SourcePreview compact />
      <Card tone="info" className="min-w-0">
        <CardHeader><CardTitle className="flex items-center gap-2"><LinkIcon aria-hidden="true" className="size-4" />随分块保存的关联信息</CardTitle></CardHeader>
        <CardContent className="flex flex-col gap-4">
          <dl className="grid grid-cols-[72px_minmax(0,1fr)] gap-x-4 gap-y-3">
            <dt className="text-muted-foreground">来源</dt><dd>售后退款制度（新版）.pdf</dd>
            <dt className="text-muted-foreground">章节</dt><dd>3 材料验收与到账时限</dd>
            <dt className="text-muted-foreground">位置</dt><dd>第 2 页 · 表格和附注各自保留区域</dd>
            <dt className="text-muted-foreground">身份</dt><dd>文档 ID、分块 ID 和索引批次分别关联</dd>
            <dt className="text-muted-foreground">版本</dt><dd>处理版本 + 内容哈希 + 切割器版本</dd>
            <dt className="text-muted-foreground">状态</dt><dd>索引是否生效、分块是否启用</dd>
          </dl>
          <Separator />
          <p>一份 Document 对应一个完整分块。转换后不再经过普通字符切割器，表格与附注不会在入库前被二次拆开。</p>
        </CardContent>
      </Card>
    </div>
  </>;
}

const rules = [
  { title: "先确定不能拆的单元", text: "解析器先识别标题、段落、表格、公式和代码块；表格与其附注、公式与释义先归为一个原子块。后续切割器只接收这些完整单元。" },
  { title: "再按标题与长度组合", text: "按阅读顺序加入原子块。遇到新标题，已有内容达到目标长度的 75%（不低于最小长度）时另起一块；正文达到最小长度后，继续加入会超过最大长度时先结束当前块。" },
  { title: "完整性优先于长度", text: "表格、公式或代码加入后达到目标长度就收束当前块。单个原子块即使超过最大长度也整体保留，只标记超长，不从中间截断；末块可以短于最小长度。" },
];

export function ChunkRules() {
  return <section aria-label="结构完整性规则" className="flex flex-col gap-5">
    <h3 className="text-base font-semibold">为什么表格、公式与说明不会被切开</h3>
    <div className="grid gap-5 lg:grid-cols-3">
      {rules.map((rule, index) => <div key={rule.title} className="flex flex-col gap-2">
        <div className="flex items-center gap-2"><Badge variant="outline" tone="info">0{index + 1}</Badge><h4 className="font-medium">{rule.title}</h4></div>
        <p className="text-muted-foreground">{rule.text}</p>
      </div>)}
    </div>
    <Card size="sm">
      <CardHeader><CardTitle className="flex items-center gap-2"><LockKeyholeIcon aria-hidden="true" className="size-4" />保护发生在解析与组合两层</CardTitle></CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2"><Badge variant="secondary">表格正文</Badge><span>+</span><Badge variant="secondary">注 1 / 注 2</Badge><ArrowRightIcon aria-hidden="true" className="size-4" /><Badge tone="info" variant="outline">一个不可再分的原子块</Badge><ArrowRightIcon aria-hidden="true" className="size-4" /><span>整块参与组合</span></div>
        <p>长度约束决定“相邻单元是否合在一起”，不会对单元内部做固定字数截取。源块 ID 和来源区域全程保留，方便检查分块是否遗漏内容。</p>
      </CardContent>
    </Card>
    <p className="text-muted-foreground">这里保护的是已识别结构不被二次截断。解析遗漏、错误归属或尚未合并的跨页续表，需要在解析阶段处理，切割器不会自动修复。</p>
  </section>;
}
