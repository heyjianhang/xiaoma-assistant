"use client";

import { useState } from "react";
import { ChevronUpIcon, CircleAlertIcon, ListTodoIcon } from "lucide-react";
import { Queue, QueueItem, QueueItemContent, QueueItemDescription, QueueItemIndicator, QueueList, QueueSection, QueueSectionContent, QueueSectionTrigger } from "@/components/ai-elements/queue";
import { Spinner } from "@/components/ui/spinner";
import type { ChatMessage, ChatTodo } from "@/lib/services/contracts";

export function ChatTaskBar({ message }: { message: ChatMessage }) {
  const [open, setOpen] = useState(false);
  const todos = message.todos ?? [];
  if (!todos.length) return null;

  const running = message.status === "running";
  const completed = todos.filter(todo => todo.status === "completed").length;
  const active = running ? todos.filter(todo => todo.status === "in_progress").length : 0;
  const pending = todos.filter(todo => todo.status === "pending" || (!running && todo.status === "in_progress")).length;
  const blocked = todos.filter(todo => todo.status === "blocked").length;
  const remaining = [active && `${active} 进行中`, pending && `${pending} 待处理`, blocked && `${blocked} 待补充`].filter(Boolean).join(" · ");
  const summary = message.status === "error" ? `处理失败 · ${completed}/${todos.length} 已完成`
    : message.status === "stopped" ? `已停止 · ${completed}/${todos.length} 已完成`
      : completed === todos.length ? `${completed} 已完成`
        : remaining || `${completed}/${todos.length} 已完成`;

  function statusLabel(todo: ChatTodo) {
    if (todo.status === "completed") return "已完成";
    if (todo.status === "blocked") return "待补充";
    return todo.status === "in_progress" && running ? "进行中" : "待处理";
  }

  return <Queue className="mx-1 bg-muted/40 p-0 shadow-none" role="region" aria-label="对话任务">
    <QueueSection open={open} onOpenChange={setOpen}>
      <QueueSectionTrigger className="gap-3 rounded-xl bg-transparent px-4 py-3 hover:bg-transparent" aria-label={`任务：${summary}`}>
        <span className="flex min-w-0 items-center gap-2.5">
          <ListTodoIcon className="size-4 shrink-0" />
          <span className="shrink-0 text-foreground">任务</span>
          <span className="truncate font-normal" aria-live="polite">{summary}</span>
        </span>
        <ChevronUpIcon className="size-4 shrink-0 transition-transform group-data-[state=open]:rotate-180" />
      </QueueSectionTrigger>
      <QueueSectionContent className="px-1 pb-3">
        <QueueList aria-label="本次任务清单">
          {todos.map(todo => <QueueItem key={todo.id} className="hover:bg-transparent" aria-label={`${todo.title}：${statusLabel(todo)}`}>
            <div className="flex items-start gap-3">
              {todo.status === "completed" ? <span className="mt-2 size-2 shrink-0 rounded-full bg-[var(--status-success)]" aria-hidden="true" />
                : todo.status === "in_progress" && running ? <Spinner className="mt-1.5 size-3 shrink-0" />
                  : todo.status === "blocked" ? <CircleAlertIcon className="mt-1.5 size-3.5 shrink-0 text-destructive" />
                    : <QueueItemIndicator className="mt-2 shrink-0" />}
              <QueueItemContent className="line-clamp-none leading-6">{todo.title}</QueueItemContent>
            </div>
            {todo.description && <QueueItemDescription>{todo.description}</QueueItemDescription>}
          </QueueItem>)}
        </QueueList>
      </QueueSectionContent>
    </QueueSection>
  </Queue>;
}
