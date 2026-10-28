import type { Metadata } from "next";
import { ProjectWorkspace } from "@/features/project/project-workspace";

export const metadata: Metadata = { title: "项目介绍 · 小马助手" };

export default function ProjectPage() {
  return <ProjectWorkspace />;
}
