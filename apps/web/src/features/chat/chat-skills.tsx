"use client";

import { useEffect, useState } from "react";
import { accessApi } from "@/lib/access/client";
import type { ChatToolAccess } from "@/lib/services/contracts";

export interface ChatSkill {
  id: string;
  name: string;
  description: string;
  required_tools: string[];
  revision: number;
  source: "builtin" | "uploaded";
}

export function skillAvailable(skill: ChatSkill, tools: ChatToolAccess) {
  return skill.required_tools.every(name => {
    if (name === "search_knowledge") return tools.knowledge;
    if (name === "present_evidence_review") return tools.knowledge && tools.data;
    if (["list_tables", "get_table_schema", "link_schema", "execute_readonly_sql", "render_chart"].includes(name)) return tools.data;
    return ["load_skill", "read_skill_resource", "write_todos", "ask_clarification"].includes(name);
  });
}

export function useChatSkills() {
  const [skills, setSkills] = useState<ChatSkill[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    const load = () => { void accessApi<{ items: ChatSkill[] }>("/agent/skills").then(value => {
      if (live) { setSkills(value.items); setError(""); }
    }).catch(() => { if (live) setError("技能目录加载失败，重新聚焦页面可重试"); }); };
    load();
    window.addEventListener("focus", load);
    window.addEventListener("xiaoma-skills-updated", load);
    return () => { live = false; window.removeEventListener("focus", load); window.removeEventListener("xiaoma-skills-updated", load); };
  }, []);
  return { skills, error };
}
