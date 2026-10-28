/** Browser counterpart of ingestion/chunker.py, checked against Python snapshots. */
export type SourceAtom = {
  id: string;
  kind: string;
  markdown: string;
  level: number;
  source_refs: Record<string, unknown>[];
};

export type ChunkOptions = {
  min_chars: number;
  target_chars: number;
  max_chars: number;
};

export type DemoChunk = {
  sequence: number;
  content: string;
  block_ids: string[];
  section_path: string[];
  source_refs: Record<string, unknown>[];
  oversized_atom: boolean;
};

export const defaultOptions: ChunkOptions = { min_chars: 80, target_chars: 240, max_chars: 240 };

export const characterCount = (value: string) => Array.from(value).length;

export function validateOptions(options: ChunkOptions): string | null {
  if (!Object.values(options).every(Number.isInteger)) return "请填写完整的整数参数。";
  if (options.min_chars < 0 || options.min_chars > 12000) return "最小长度需在 0–12,000 字符之间。";
  if (options.target_chars < 100 || options.target_chars > 12000) return "目标长度需在 100–12,000 字符之间。";
  if (options.max_chars < 100 || options.max_chars > 20000) return "最大长度需在 100–20,000 字符之间。";
  if (options.min_chars > options.target_chars || options.target_chars > options.max_chars) {
    return "长度需满足：最小 ≤ 目标 ≤ 最大。";
  }
  return null;
}

export function splitStructure(blocks: SourceAtom[], options: ChunkOptions): DemoChunk[] {
  const error = validateOptions(options);
  if (error) throw new Error(error);
  const result: DemoChunk[] = [];
  let pending: SourceAtom[] = [];
  const headings: { level: number; text: string }[] = [];
  let section: string[] = [];
  const size = () => pending.reduce((sum, block) => sum + characterCount(block.markdown), 0)
    + Math.max(0, pending.length - 1) * 2;
  const flush = () => {
    if (!pending.length) return;
    const content = pending.map(block => block.markdown).join("\n\n").trim();
    if (content) {
      result.push({
        sequence: result.length + 1,
        content,
        block_ids: pending.map(block => block.id),
        section_path: [...section],
        source_refs: pending.flatMap(block => block.source_refs),
        oversized_atom: pending.some(block => characterCount(block.markdown) > options.max_chars),
      });
    }
    pending = [];
  };
  for (const block of blocks) {
    if (!block.markdown.trim()) continue;
    if (block.kind === "heading") {
      const boundary = Math.min(Math.max(options.min_chars, Math.floor(options.target_chars * 0.75)), options.target_chars);
      if (pending.length && size() >= boundary) flush();
      while (headings.length && headings[headings.length - 1].level >= block.level) headings.pop();
      headings.push({ level: block.level, text: block.markdown.replace(/^[# ]+/, "").trim() });
      if (!pending.length) section = headings.map(heading => heading.text);
    } else {
      const hasBody = pending.some(item => item.kind !== "heading");
      if (pending.length && hasBody && size() >= options.min_chars
        && size() + characterCount(block.markdown) + 2 > options.max_chars) flush();
      if (!pending.length) section = headings.map(heading => heading.text);
    }
    pending.push(block);
    if (["table", "equation", "code"].includes(block.kind) && size() >= options.target_chars) flush();
    else if (pending.length === 1 && characterCount(block.markdown) >= options.max_chars) flush();
  }
  flush();
  return result;
}
