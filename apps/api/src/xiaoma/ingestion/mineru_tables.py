"""Verify MinerU's merged-table continuation placeholders against layout evidence."""

import math
import re
from collections import Counter
from html.parser import HTMLParser


class TableRows(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.rows, self.row, self.cell = [], None, None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append(re.sub(r"\s+", "", "".join(self.cell)))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(tuple(self.row))
            self.row = None


def matching_table(blocks, bbox, page_size):
    if (
        not isinstance(bbox, list)
        or len(bbox) != 4
        or not isinstance(page_size, list)
        or len(page_size) != 2
        or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in bbox + page_size
        )
        or min(page_size) <= 0
        or not (0 <= bbox[0] < bbox[2] <= 1000 and 0 <= bbox[1] < bbox[3] <= 1000)
    ):
        return None
    found = []
    for block in blocks:
        box = block.get("bbox", [])
        if block.get("type") != "table" or not isinstance(box, list) or len(box) != 4:
            continue
        if all(
            isinstance(v, (int, float))
            and math.isfinite(v)
            and abs(v / page_size[i % 2] * 1000 - bbox[i]) <= 3
            for i, v in enumerate(box)
        ):
            found.append(block)
    return found[0] if len(found) == 1 else None


def merged_table_continuations(items, layout):
    """Accept only deleted layout bodies whose original rows exist in the merged parent.

    Ordinary empty tables still fail. No table text is synthesized or recovered from
    companion Markdown; the Content List's full merged HTML remains authoritative.
    """
    pages = {
        p["page_idx"]: p
        for p in layout.get("pdf_info", [])
        if isinstance(p, dict) and isinstance(p.get("page_idx"), int)
    }
    result, parent, parent_rows, last_page = {}, None, [], None
    for index, item in enumerate(items):
        if item.get("type") != "table":
            continue
        body = item.get("table_body")
        page = item.get("page_idx")
        if isinstance(body, str) and body.strip():
            parent, parent_rows, last_page = index, TableRows(body).rows, page
            continue
        # MinerU clears these when moving a continuation into the preceding table.
        if (
            parent is None
            or not isinstance(page, int)
            or not isinstance(last_page, int)
            or page != last_page + 1
            or item.get("img_path")
            or any(str(v).strip() for v in item.get("table_caption", []))
            or any(str(v).strip() for v in item.get("table_footnote", []))
        ):
            continue
        info = pages.get(page, {})
        raw = matching_table(
            info.get("preproc_blocks", []), item.get("bbox"), info.get("page_size")
        )
        merged = matching_table(
            info.get("para_blocks", []), item.get("bbox"), info.get("page_size")
        )
        if not raw or not merged:
            continue
        bodies = [b for b in merged.get("blocks", []) if b.get("type") == "table_body"]
        if len(bodies) != 1 or bodies[0].get("lines_deleted") is not True or bodies[0].get("lines"):
            continue
        html = [
            span["html"]
            for b in raw.get("blocks", [])
            if b.get("type") == "table_body"
            for line in b.get("lines", [])
            for span in line.get("spans", [])
            if span.get("type") == "table" and isinstance(span.get("html"), str)
        ]
        rows = TableRows(html[0]).rows if len(html) == 1 else []
        if (
            len(rows) < 2
            or len(parent_rows) <= len(rows)
            or rows[0] != parent_rows[0]
            or not Counter(rows[1:]) <= Counter(parent_rows[1:])
        ):
            continue
        result[index] = parent
        last_page = page
    return result
