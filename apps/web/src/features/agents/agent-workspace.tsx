"use client";

import { useRef } from "react";
import { UploadIcon } from "lucide-react";
import { WorkspacePage, WorkspaceToolbar } from "@/components/workspace-page";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAccess } from "@/lib/access/provider";
import { SkillManager } from "./skill-manager";

export function AgentWorkspace() {
  const { user } = useAccess();
  const uploadRef = useRef<HTMLInputElement>(null);

  if (user?.role !== "admin") return <WorkspacePage title="Agent 配置"><Alert variant="destructive"><AlertDescription>此页面仅管理员可访问。</AlertDescription></Alert></WorkspacePage>;

  return <WorkspacePage title="Agent 配置">
    <Tabs defaultValue="skills" className="min-h-0 flex-1 gap-4 overflow-hidden">
      <WorkspaceToolbar>
        <TabsList aria-label="Agent 配置功能"><TabsTrigger value="skills" className="px-3">技能</TabsTrigger></TabsList>
        <Button onClick={() => uploadRef.current?.click()}><UploadIcon data-icon="inline-start" />上传 Skill ZIP</Button>
      </WorkspaceToolbar>
      <TabsContent value="skills" className="m-0 flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="min-h-0 flex-1 overflow-auto rounded-xl border"><SkillManager uploadRef={uploadRef} /></div>
      </TabsContent>
    </Tabs>
  </WorkspacePage>;
}
