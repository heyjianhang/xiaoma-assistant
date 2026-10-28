"use client";

import { MessageResponse } from "@/components/ai-elements/message";
import { cn } from "@/lib/utils";

export function MarkdownPreview({ content, className }: { content: string; className?: string }) {
  return <div className={cn("min-w-0 [&_table]:min-w-[28rem]", className)}>
    <MessageResponse mode="static" isAnimating={false} parseIncompleteMarkdown={false} controls={false} codeBlockMaxHeight={280} tableMaxHeight={320}>{content}</MessageResponse>
  </div>;
}
