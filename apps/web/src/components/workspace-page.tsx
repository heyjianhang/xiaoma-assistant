import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function WorkspacePage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="@container/workspace flex min-h-0 flex-1 flex-col gap-6 overflow-hidden p-4 pt-14 md:p-6 lg:p-8">
      <header className="shrink-0">
        <h1 className="text-2xl leading-8 font-semibold tracking-tight">{title}</h1>
      </header>
      {children}
    </section>
  );
}

export function WorkspaceToolbar({ children, className }: { children: ReactNode; className?: string }) {
  return <div data-slot="workspace-toolbar" className={cn("flex min-h-9 shrink-0 flex-wrap items-center justify-between gap-3", className)}>{children}</div>;
}
