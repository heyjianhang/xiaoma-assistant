"use client";

import { useState } from "react";
import { useActivityView } from "@/lib/access/activity";
import { WorkspacePage, WorkspaceToolbar } from "@/components/workspace-page";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DatasetIntroduction } from "./dataset-introduction";
import { ProjectOverview } from "./project-overview";
import { MemoryIntroduction } from "./memory-introduction";
import { RagIntroduction } from "./rag-introduction";
import { Text2SqlIntroduction } from "./text2sql-introduction";
import { EvidenceIntroduction } from "./evidence-introduction";

export function ProjectWorkspace() {
  const [tab, setTab] = useState("overview");
  useActivityView("page_view", { path: "/project", tab });
  return <WorkspacePage title="项目介绍">
    <Tabs value={tab} onValueChange={setTab} className="min-h-0 flex-1 gap-4 overflow-hidden">
      <WorkspaceToolbar>
        <div className="min-w-0 overflow-x-auto"><TabsList aria-label="项目介绍内容">
          <TabsTrigger value="overview" className="px-3">整体架构</TabsTrigger>
          <TabsTrigger value="dataset" className="px-3">数据集介绍</TabsTrigger>
          <TabsTrigger value="memory" className="px-3">记忆与上下文</TabsTrigger>
          <TabsTrigger value="rag" className="px-3">RAG</TabsTrigger>
          <TabsTrigger value="text2sql" className="px-3">Text2SQL</TabsTrigger>
          <TabsTrigger value="evidence" className="px-3">证据核对</TabsTrigger>
        </TabsList></div>
      </WorkspaceToolbar>
      <TabsContent value="overview" className="m-0 min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-0.5 pb-6 pt-0.5"><ProjectOverview /></div>
      </TabsContent>
      <TabsContent value="dataset" className="m-0 min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-0.5 pb-6 pt-0.5"><DatasetIntroduction /></div>
      </TabsContent>
      <TabsContent value="memory" className="m-0 min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-0.5 pb-6 pt-0.5"><MemoryIntroduction /></div>
      </TabsContent>
      <TabsContent value="rag" className="m-0 min-h-0 flex-1 overflow-hidden">
        <div className="mx-auto flex h-full min-h-0 w-full max-w-6xl flex-col px-0.5 pt-0.5"><RagIntroduction /></div>
      </TabsContent>
      <TabsContent value="text2sql" className="m-0 min-h-0 flex-1 overflow-hidden">
        <div className="mx-auto flex h-full min-h-0 w-full max-w-6xl flex-col px-0.5 pt-0.5"><Text2SqlIntroduction /></div>
      </TabsContent>
      <TabsContent value="evidence" className="m-0 min-h-0 flex-1 overflow-hidden">
        <div className="mx-auto flex h-full min-h-0 w-full max-w-6xl flex-col px-0.5 pt-0.5"><EvidenceIntroduction /></div>
      </TabsContent>
    </Tabs>
  </WorkspacePage>;
}
