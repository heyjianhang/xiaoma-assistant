import { ArrowRightIcon, BrainCircuitIcon, DatabaseIcon, FileStackIcon, FileTextIcon, FilterIcon, ListOrderedIcon, MessageSquareQuoteIcon, SearchIcon, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StageHeading } from "./rag-document-stages";
import defaults from "./fixtures/rag-defaults.json";

type FlowItem = { title: string; icon: LucideIcon; label: string; detail: string };
function Flow({ items, label }: { items: FlowItem[]; label: string }) {
  return <ol aria-label={label} className="grid min-w-0 gap-3 lg:grid-cols-3">
    {items.map((item, index) => <li key={item.title} className="flex min-w-0 items-stretch gap-3">
      <Card size="sm" tone={index === 1 ? "info" : undefined} className="min-w-0 flex-1">
        <CardHeader><CardTitle className="flex items-center gap-2"><item.icon aria-hidden="true" className="size-4 shrink-0" />{item.title}</CardTitle></CardHeader>
        <CardContent className="flex min-w-0 flex-col gap-2"><p className="break-words font-medium">{item.label}</p><p className="text-muted-foreground">{item.detail}</p></CardContent>
      </Card>
      {index < items.length - 1 && <ArrowRightIcon aria-hidden="true" className="hidden size-4 shrink-0 self-center text-muted-foreground lg:block" />}
    </li>)}
  </ol>;
}

function Detail({ title, children }: { title: string; children: ReactNode }) {
  return <section className="flex flex-col gap-2"><h3 className="text-base font-semibold">{title}</h3><div className="text-muted-foreground">{children}</div></section>;
}

const stores = [
  { title: "文档与任务", tables: "documents · ingestion_jobs", description: "记录原文件、版本、分块配置、后台处理进度与错误。" },
  { title: "分块正文", tables: "chunks", description: "保存已发布分块、来源位置和启用状态，支撑查看与原文定位。" },
  { title: "向量索引", tables: "vectors", description: "PGVectorStore 管理正文、向量与元数据，检索时过滤生效批次。" },
  { title: "向量空间", tables: "index_config", description: "校验 Embedding 模型、维度与网关指纹，防止不同向量空间混用。" },
];

export function IndexStage() {
  return <>
    <StageHeading title="Embedding 向量化，PostgreSQL 保存索引" tags={["pgvector", `${defaults.embedding_dimensions} 维`]}>
      MinerU 的解析结果经过结构切块与 Document 转换后，才进入 Embedding。模型、连接和密钥由服务端配置，前端只展示处理结果。
    </StageHeading>
    <Flow label="向量化链路" items={[
      { title: "完整分块", icon: FileTextIcon, label: "LangChain Document", detail: "正文用于生成向量；文档版本、章节、来源区域作为关联元数据保留。" },
      { title: "Embedding 默认模型", icon: BrainCircuitIcon, label: defaults.embedding_model, detail: `通过 OpenAIEmbeddings 调用百炼兼容网关，按 ${defaults.embedding_batch_size} 条批量处理，输出 ${defaults.embedding_dimensions} 维向量。` },
      { title: "向量存储", icon: DatabaseIcon, label: "PGVectorStore → pgvector", detail: "使用 aadd_documents 写入内容、向量和元数据，文档与问题使用同一个 Embedding 空间。" },
    ]} />
    <section aria-label="知识库存储结构" className="flex flex-col gap-3">
      <h3 className="text-base font-semibold">一份文档的数据存在哪里</h3>
      <div className="min-w-0 overflow-hidden rounded-lg border"><Table>
        <TableHeader><TableRow><TableHead>用途</TableHead><TableHead>PostgreSQL 表</TableHead><TableHead>保存内容</TableHead></TableRow></TableHeader>
        <TableBody>{stores.map(store => <TableRow key={store.title}><TableCell className="align-top font-medium">{store.title}</TableCell><TableCell className="align-top font-mono text-xs">{store.tables}</TableCell><TableCell className="min-w-52 whitespace-normal align-top">{store.description}</TableCell></TableRow>)}</TableBody>
      </Table></div>
      <p className="flex items-start gap-2 text-muted-foreground"><FileStackIcon aria-hidden="true" className="mt-1 size-4 shrink-0" />原 PDF、MinerU ZIP 与解析产物保存在文件存储，数据库记录关联；向量索引不承担原文件归档。</p>
    </section>
    <Separator />
    <Detail title="整批写入成功后才发布">
      <p>PGMQ Worker 在后台完成解析与入库。新向量先保持未激活；全部写入成功后，在同一事务中保存分块、关闭旧索引、启用新索引。中途失败时旧索引继续可查，半成品不会进入检索。</p>
    </Detail>
  </>;
}

export function RetrieveStage() {
  return <>
    <StageHeading title="向量找候选，重排选出更相关的证据" tags={[`${defaults.retrieval_candidates} → 5`]}>
      先用语义向量扩大候选范围，再把问题与每个候选交给重排模型。两个阶段保留同一份正文与来源，重排只改变顺序。
    </StageHeading>
    <Flow label="召回与重排链路" items={[
      { title: "问题向量化", icon: SearchIcon, label: defaults.embedding_model, detail: "用 embed_query 编码问题，与入库分块保持相同的模型和维度。" },
      { title: "候选召回", icon: DatabaseIcon, label: `Retriever · ${defaults.retrieval_candidates} 个候选`, detail: "通过 PGVectorStore.as_retriever 搜索，只查生效索引中已启用的分块。" },
      { title: "重排默认模型", icon: ListOrderedIcon, label: defaults.rerank_model, detail: "结合问题与候选正文重新评分，按相关性返回前 5 个完整分块。" },
    ]} />
    <div className="grid gap-5 lg:grid-cols-2">
      <Card size="sm">
        <CardHeader><CardTitle className="flex items-center gap-2"><FilterIcon aria-hidden="true" className="size-4" />候选数与返回数分别控制什么</CardTitle></CardHeader>
        <CardContent className="flex flex-col gap-3"><p><strong className="font-medium">候选 {defaults.retrieval_candidates} 条</strong>：给重排留下比较空间，减少初筛过早排除相关内容。</p><p><strong className="font-medium">返回最多 5 条</strong>：限制交给回答模型的证据规模；不足时按实际结果返回。</p></CardContent>
      </Card>
      <Card size="sm" tone="info">
        <CardHeader><CardTitle className="flex items-center gap-2"><FileTextIcon aria-hidden="true" className="size-4" />返回内容仍可追溯</CardTitle></CardHeader>
        <CardContent className="flex flex-col gap-3"><div className="flex flex-wrap gap-2"><Badge variant="outline">完整正文</Badge><Badge variant="outline">文档 / 版本</Badge><Badge variant="outline">块 ID / 来源区域</Badge></div><p>重排不会重新切块或改写条款，表格与附注的组合关系继续保留。</p></CardContent>
      </Card>
    </div>
    <Detail title="关闭重排时">
      <p>直接使用向量检索返回的前 5 条结果。开启重排时通过 LangChain RunnableLambda 调用重排服务；分数表示本次问题的相关性，不代表答案正确率。</p>
    </Detail>
  </>;
}


export function AnswerStage() {
  return <>
    <StageHeading title="检索证据进入回答，引用可以回到原文" tags={["search_knowledge", "PDF.js"]}>
      Agent 按问题调用知识库工具，结合文档版本和业务口径组织答案。前端选定的聊天模型负责生成，相关性分数不直接代替业务判断。
    </StageHeading>
    <div className="grid items-start gap-5 lg:grid-cols-2">
      <Card tone="info" className="min-w-0">
        <CardHeader><CardTitle className="flex items-center gap-2"><MessageSquareQuoteIcon aria-hidden="true" className="size-4" />回答中的引用呈现</CardTitle></CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p>新版制度下，电子钱包退款应在验收通过后 <strong className="font-semibold">24 自然小时</strong>内成功到账。这里衡量的是验收到到账阶段，不能把申请时间当作验收时间。<Badge variant="secondary" className="mx-1 align-baseline">1</Badge></p>
          <Separator />
          <div className="flex flex-col gap-2"><span className="font-medium">引用 1 · 售后退款制度（新版）</span><span className="text-muted-foreground">第 2 页 · 表 AS2-T2 · 支付渠道退款到账时效</span></div>
        </CardContent>
      </Card>
      <ol className="flex flex-col gap-5">
        <li className="flex gap-3"><Badge variant="outline" tone="info">01</Badge><div className="flex flex-col gap-1"><h3 className="font-medium">取得证据</h3><p className="text-muted-foreground">工具返回片段、文档版本、页码和证据 ID，模型用证据链接标注结论，不自行编造来源。</p></div></li>
        <li className="flex gap-3"><Badge variant="outline" tone="info">02</Badge><div className="flex flex-col gap-1"><h3 className="font-medium">预览片段</h3><p className="text-muted-foreground">链接渲染为引用角标；悬停显示完整 Markdown、表格与公式，点击打开原文。</p></div></li>
        <li className="flex gap-3"><Badge variant="outline" tone="info">03</Badge><div className="flex flex-col gap-1"><h3 className="font-medium">定位高亮</h3><p className="text-muted-foreground">PDF 将页码与归一化坐标映射到 PDF.js 视图，缩放后同步换算；Markdown 按行号定位。没有有效坐标时保留页级定位。</p></div></li>
      </ol>
    </div>
    <Separator />
    <Detail title="冲突与缺失怎样处理">
      <p>制度版本不同，先确认适用时间与范围；文档和查询结果不一致，保留双方依据再解释差异。只有单一来源、缺少关键字段或证据不足时，明确限制，不把检索命中当成事实已经核实。</p>
    </Detail>
  </>;
}
