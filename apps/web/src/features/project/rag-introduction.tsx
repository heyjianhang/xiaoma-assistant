"use client";

import { ArrowRightIcon } from "lucide-react";
import { Fragment, useRef } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ChunkPlayground } from "./chunk-playground";
import { ChunkRules, DocumentStage, ParseStage, StageHeading } from "./rag-document-stages";
import { AnswerStage, IndexStage, RetrieveStage } from "./rag-index-stages";

const stages = [
  { id: "parse", label: "文档解析" },
  { id: "chunk", label: "结构切块" },
  { id: "document", label: "Document" },
  { id: "index", label: "向量入库" },
  { id: "retrieve", label: "检索重排" },
  { id: "answer", label: "引用回答" },
];
const panel = "m-0 flex flex-col gap-6 data-[state=inactive]:hidden";

export function RagIntroduction() {
  const contentRef = useRef<HTMLDivElement>(null);
  return <article aria-label="RAG 实现" className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden text-sm leading-7">
    <Tabs defaultValue="chunk" onValueChange={() => contentRef.current?.scrollTo({ top: 0 })} className="min-h-0 min-w-0 flex-1 gap-5 overflow-hidden">
      <div className="min-w-0 shrink-0 overflow-x-auto px-0.5 pb-2">
        <TabsList aria-label="RAG 处理链路" variant="line" className="h-auto justify-start gap-2 p-0">
          {stages.map((stage, index) => <Fragment key={stage.id}>
            {index > 0 && <ArrowRightIcon aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />}
            <TabsTrigger value={stage.id} className="h-10 px-3">{stage.label}</TabsTrigger>
          </Fragment>)}
        </TabsList>
      </div>
      <div ref={contentRef} role="region" aria-label="RAG 说明" tabIndex={0} className="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain px-0.5 pb-6">
        <div className="flex flex-col gap-6">
          <TabsContent value="parse" className={panel}><ParseStage /></TabsContent>
          <TabsContent forceMount value="chunk" className={panel}>
            <StageHeading title="以完整结构为单位切块" tags={["structure-v1"]}>先将表格与附注、公式与释义归为原子块，再按标题和长度组合。调整参数，观察分块边界如何变化。</StageHeading>
            <ChunkPlayground />
            <ChunkRules />
          </TabsContent>
          <TabsContent value="document" className={panel}><DocumentStage /></TabsContent>
          <TabsContent value="index" className={panel}><IndexStage /></TabsContent>
          <TabsContent value="retrieve" className={panel}><RetrieveStage /></TabsContent>
          <TabsContent value="answer" className={panel}><AnswerStage /></TabsContent>
        </div>
      </div>
    </Tabs>
  </article>;
}
