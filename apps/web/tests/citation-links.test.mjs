import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { Streamdown, defaultRemarkPlugins } from "streamdown";
import { citationHref, findCitation, remarkCitationLinks } from "../src/features/chat/citation-links.ts";

const sources = Array.from({ length: 4 }, (_, index) => ({
  documentId: `document-${index + 1}`, chunkId: `chunk-${index + 1}`, title: `来源 ${index + 1}`, clause: "退款时效",
}));

function parse(content, citations = sources) {
  const processor = unified().use(remarkParse).use(remarkGfm).use(remarkMath).use(remarkCitationLinks, citations);
  return processor.runSync(processor.parse(content));
}

function nodes(tree, type) {
  return [...(tree.type === type ? [tree] : []), ...(tree.children ?? []).flatMap(child => nodes(child, type))];
}

test("plain citations work in tables, lists and adjacent references from the actual answer format", () => {
  const tree = parse("| 版本 | 时效 |\n| --- | --- |\n| 旧版 | 待复核[2] |\n\n- 新版 24 小时。[1][3]\n- 跨生效日完成，仍按提交时版本。[4]");
  assert.equal(nodes(tree, "table").length, 1);
  assert.deepEqual(nodes(tree, "link").map(link => link.url), [sources[1], sources[0], sources[2], sources[3]].map(citationHref));
});

test("code, math, images, existing links and real footnotes retain their meaning", () => {
  const tree = parse('`values[1]`\n\n```sql\nSELECT values[2];\n```\n\n$A[3]$\n\n$$\nB[4]\n$$\n\n[existing [1]](https://example.com)\n\n![image [2]](https://example.com/a.png)\n\n[^1]\n\n[^1]: footnote [3]');
  assert.deepEqual(nodes(tree, "link").map(link => link.url), ["https://example.com"]);
  assert.equal(nodes(tree, "inlineCode")[0].value, "values[1]");
  assert.equal(nodes(tree, "inlineMath")[0].value, "A[3]");
  assert.equal(nodes(tree, "footnoteReference").length, 1);
});

test("unbacked or unfinished numbers stay as text rather than inventing citations", () => {
  assert.equal(nodes(parse("[0] [5] [99] [1.2] [1"), "link").length, 0);
  assert.equal(nodes(parse("[1]", []), "link").length, 0);
});

test("existing links resolve only to evidence belonging to this answer", () => {
  assert.deepEqual(findCitation(citationHref(sources[3]), sources), { citation: sources[3], number: 4 });
  assert.equal(findCitation(citationHref(sources[3]), [sources[0]]), undefined);
  assert.equal(findCitation("https://example.com/knowledge/document-1?chunk=chunk-1", sources), undefined);
  assert.equal(findCitation("javascript:alert(1)", sources), undefined);
  assert.equal(findCitation("/knowledge/document-1?chunk=another-chunk", sources), undefined);
});

test("late evidence binds unchanged answer text; source catalogs never leak between answers", () => {
  const content = "新版 24 小时。[1]";
  function render(citations) {
    return renderToStaticMarkup(createElement(Streamdown, {
      mode: "static", parseIncompleteMarkdown: false, controls: false,
      remarkPlugins: [...Object.values(defaultRemarkPlugins), [remarkCitationLinks, citations]],
      components: { a: ({ href, children }) => createElement("a", { href }, children) },
    }, content));
  }
  assert.ok(!render([]).includes("/knowledge/"));
  assert.ok(render([sources[0]]).includes(citationHref(sources[0])));
  assert.ok(render([sources[1]]).includes(citationHref(sources[1])));
  assert.ok(!render([sources[1]]).includes(citationHref(sources[0])));
  assert.ok(!render([]).includes("/knowledge/"));
});
