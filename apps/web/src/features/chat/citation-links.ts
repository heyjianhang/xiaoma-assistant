import type { Nodes, Parents, PhrasingContent, Root } from "mdast";
import type { Plugin } from "unified";
import type { Citation } from "@/lib/services/contracts";

export function citationHref(citation: Citation) {
  return `/knowledge/${encodeURIComponent(citation.documentId)}?chunk=${encodeURIComponent(citation.chunkId)}`;
}

export function findCitation(href: string | undefined, citations: readonly Citation[]) {
  if (!href?.startsWith("/knowledge/")) return;
  const url = new URL(href, "http://localhost");
  const index = citations.findIndex(citation =>
    url.pathname === `/knowledge/${encodeURIComponent(citation.documentId)}` &&
    url.searchParams.get("chunk") === citation.chunkId,
  );
  if (index >= 0) return { citation: citations[index], number: index + 1 };
}

const excluded = new Set(["link", "linkReference", "image", "imageReference", "code", "inlineCode", "math", "inlineMath", "html", "definition", "footnoteDefinition"]);

// Only turn references backed by this answer's evidence catalog into links.
// AST traversal keeps code, formulas and existing Markdown links intact.
export const remarkCitationLinks: Plugin<[readonly Citation[]], Root> = function remarkCitationLinks(citations) {
  return tree => {
    function walk(node: Nodes) {
      if (excluded.has(node.type) || !("children" in node)) return;
      const parent = node as Parents;
      for (let index = 0; index < parent.children.length; index++) {
        const child = parent.children[index];
        if (child.type !== "text") { walk(child); continue; }
        const replacements: PhrasingContent[] = [];
        let cursor = 0;
        for (const match of child.value.matchAll(/\[([1-9]\d*)\]/g)) {
          const citation = citations[Number(match[1]) - 1];
          if (!citation?.documentId || !citation.chunkId) continue;
          const start = match.index;
          if (start > cursor) replacements.push({ type: "text", value: child.value.slice(cursor, start) });
          replacements.push({ type: "link", url: citationHref(citation), children: [{ type: "text", value: match[1] }] });
          cursor = start + match[0].length;
        }
        if (!replacements.length) continue;
        if (cursor < child.value.length) replacements.push({ type: "text", value: child.value.slice(cursor) });
        parent.children.splice(index, 1, ...replacements);
        index += replacements.length - 1;
      }
    }
    walk(tree);
  };
};
