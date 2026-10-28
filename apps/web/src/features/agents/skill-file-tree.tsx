"use client";

import { FileTree, FileTreeFile, FileTreeFolder } from "@/components/ai-elements/file-tree";

interface Node { name: string; path: string; children: Map<string, Node>; file: boolean }

function nodes(paths: string[]) {
  const root: Node = { name: "", path: "", children: new Map(), file: false };
  for (const path of paths) {
    let current = root;
    const parts = path.split("/");
    parts.forEach((name, index) => {
      const prefix = parts.slice(0, index + 1).join("/");
      if (!current.children.has(name)) current.children.set(name, { name, path: prefix, children: new Map(), file: index === parts.length - 1 });
      current = current.children.get(name)!;
    });
  }
  return root;
}

function Branch({ node }: { node: Node }) {
  return [...node.children.values()].sort((a, b) => Number(a.file) - Number(b.file) || a.name.localeCompare(b.name)).map(child => child.file
    ? <FileTreeFile key={child.path} path={child.path} name={child.name} />
    : <FileTreeFolder key={child.path} path={child.path} name={child.name}><Branch node={child} /></FileTreeFolder>);
}

export function SkillFileTree({ paths, selectedPath, onSelect }: { paths: string[]; selectedPath: string; onSelect: (path: string) => void }) {
  const folders = new Set(paths.flatMap(path => path.split("/").slice(0, -1).map((_, i) => path.split("/").slice(0, i + 1).join("/"))));
  return <FileTree aria-label="技能文件" className="min-h-full rounded-none border-0" defaultExpanded={folders} selectedPath={selectedPath} onSelect={path => { if (paths.includes(path)) onSelect(path); }}><Branch node={nodes(paths)} /></FileTree>;
}
