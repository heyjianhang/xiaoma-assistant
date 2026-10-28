"use client";

import { useMemo, type ComponentProps } from "react";
import { defaultRemarkPlugins } from "streamdown";
import type { PluggableList } from "unified";
import { MessageResponse } from "@/components/ai-elements/message";
import type { Citation } from "@/lib/services/contracts";
import { ChatCitation } from "./chat-citation";
import { findCitation, remarkCitationLinks } from "./citation-links";

const noCitations: Citation[] = [];

export function ChatAnswer({ content, citations = noCitations, generating }: { content: string; citations?: Citation[]; generating: boolean }) {
  const components = useMemo(() => ({
    a: ({ href, children, ...props }: ComponentProps<"a">) => {
      const source = findCitation(href, citations);
      return source ? <ChatCitation {...source} /> : <a href={href} {...props}>{children}</a>;
    },
  }), [citations]);
  // Streamdown caches processors by plugin name + options, so evidence must be
  // an explicit option rather than a closure shared by different answers.
  const remarkPlugins = useMemo<PluggableList>(() => [...Object.values(defaultRemarkPlugins), [remarkCitationLinks, citations]], [citations]);
  // Its text-oriented memo also needs a new instance when evidence arrives
  // after the text (e.g. loading history or streaming source metadata).
  return <MessageResponse key={JSON.stringify(citations)} isAnimating={generating} controls={false} components={components} remarkPlugins={remarkPlugins}>{content}</MessageResponse>;
}
