import re

from markdown_it import MarkdownIt

from .types import ParsedDocument, SourceBlock

NOTE = re.compile(r"^(注[：:\d一二三四五六七八九、. ]|注：|注:|备注|说明[：:]|式中|其中)")


def attach_notes(blocks: list[SourceBlock]) -> list[SourceBlock]:
    result: list[SourceBlock] = []
    for block in blocks:
        if (
            result
            and result[-1].kind in {"table", "equation"}
            and block.kind == "text"
            and NOTE.match(block.markdown.strip())
        ):
            result[-1].markdown += "\n\n" + block.markdown
            result[-1].source_refs.extend(block.source_refs)
        else:
            result.append(block.model_copy(deep=True))
    return result


def parse_markdown(content: str) -> ParsedDocument:
    lines = content.splitlines(keepends=True)
    math_spans: list[tuple[int, int]] = []
    start = None
    in_fence = False
    for number, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
        if in_fence:
            continue
        if stripped.startswith("$$"):
            if start is None and stripped != "$$" and stripped.endswith("$$"):
                math_spans.append((number, number + 1))
            elif start is None:
                start = number
            else:
                math_spans.append((start, number + 1))
                start = None
    if start is not None:
        math_spans.append((start, len(lines)))
    blocks: list[tuple[int, int, str, int]] = [
        (left, right, "equation", 0) for left, right in math_spans
    ]
    tokens = MarkdownIt("commonmark", {"html": True}).enable("table").parse(content)
    for token in tokens:
        if token.level != 0 or token.map is None or token.nesting == -1:
            continue
        left, right = token.map
        kind = "text"
        level = 0
        if token.type == "heading_open":
            kind, level = "heading", int(token.tag[1])
        elif token.type == "table_open" or (
            token.type == "html_block" and re.search(r"<table\b", token.content, re.I)
        ):
            kind = "table"
        elif token.type in {"fence", "code_block"}:
            kind = "code"
        # A Markdown paragraph may straddle display math without blank lines.
        # Preserve the prose on both sides instead of dropping the entire token.
        segments = [(left, right)]
        for begin, end in math_spans:
            segments = [
                part
                for a, b in segments
                for part in (
                    [(a, b)]
                    if b <= begin or a >= end
                    else [
                        (a, min(b, begin)),
                        (max(a, end), b),
                    ]
                )
                if part[0] < part[1]
            ]
        blocks.extend((a, b, kind, level) for a, b in segments)
    unique = {(left, right): (kind, level) for left, right, kind, level in blocks}
    source = [
        SourceBlock(
            id=f"md:{left}:{right}",
            kind=kind,
            level=level,
            markdown="".join(lines[left:right]).strip(),
            source_refs=[{"kind": "markdown_lines", "line_start": left + 1, "line_end": right}],
        )
        for (left, right), (kind, level) in sorted(unique.items())
    ]
    return ParsedDocument(
        parser="markdown-it-v1",
        blocks=attach_notes(source),
        source_map_available=True,
    )
