"""MinerU precision API v4 file upload and structured result adapter."""

import asyncio
import io
import json
import math
import time
import zipfile
from pathlib import PurePosixPath

import httpx

from xiaoma.errors import IngestionError
from xiaoma.settings import Settings

from .markdown import attach_notes
from .mineru_tables import merged_table_continuations
from .types import ParsedDocument, SourceBlock


def strings(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if item)
    return str(value or "")


def normalize_content(
    items: list[dict], task_id: str, continuations: dict[int, int] | None = None
) -> ParsedDocument:
    blocks, tables = [], {}
    continuations = continuations or {}
    pages = 0
    for number, item in enumerate(items):
        kind = item.get("type", "text")
        if kind in {"header", "footer", "page_header", "page_footer", "page_number"}:
            continue
        page = item.get("page_idx")
        if isinstance(page, int) and page >= 0:
            pages = max(pages, page + 1)
        ref = {"kind": "mineru_content", "block_index": number, "page_index": page}
        if "bbox" in item:
            ref["bbox_raw"] = item["bbox"]
            # Content List V1 uses top-left coordinates normalized to [0, 1000].
            # This is distinct from layout.json's PDF-point coordinates.
            bbox = item["bbox"]
            valid = (
                isinstance(bbox, list)
                and len(bbox) == 4
                and all(
                    isinstance(v, (int, float))
                    and not isinstance(v, bool)
                    and math.isfinite(v)
                    and 0 <= v <= 1000
                    for v in bbox
                )
                and bbox[0] < bbox[2]
                and bbox[1] < bbox[3]
                and isinstance(page, int)
                and page >= 0
            )
            if valid:
                ref["bbox"] = bbox
                ref["coordinate_space"] = "normalized_1000"
            else:
                ref["coordinate_space"] = "unavailable"
        if number in continuations and kind == "table":
            parent = tables.get(continuations[number])
            if parent is not None:
                parent.source_refs.append({**ref, "merged_table_parent": parent.id})
                continue
        level = 0
        if kind == "table":
            body = strings(item.get("table_body"))
            if not body.strip():
                raise IngestionError("mineru_table_missing", "MinerU 表格缺少结构化正文")
            text = "\n\n".join(
                filter(
                    None,
                    [
                        strings(item.get("table_caption")),
                        body,
                        strings(item.get("table_footnote")),
                    ],
                )
            )
        elif kind in {"equation", "interline_equation"}:
            kind = "equation"
            text = strings(item.get("text")).strip()
            if text and not text.startswith("$$"):
                text = "$$\n" + text + "\n$$"
        elif kind == "image":
            # Image caption remains searchable; archive retains image files for later preview.
            text = strings(item.get("image_caption"))
        elif kind in {"text", "title", "doc_title", "code"}:
            text = strings(item.get("text"))
            level = int(item.get("text_level") or (1 if kind in {"title", "doc_title"} else 0))
            kind = "heading" if level else ("code" if kind == "code" else "text")
            if kind == "heading":
                text = "#" * min(level, 6) + " " + text
        else:
            raise IngestionError("mineru_schema_unsupported", "MinerU 内容类型尚未支持")
        if text.strip():
            blocks.append(
                SourceBlock(
                    id=f"mineru:{number}",
                    kind=kind,
                    markdown=text,
                    level=level,
                    source_refs=[ref],
                )
            )
            if kind == "table":
                tables[number] = blocks[-1]
    return ParsedDocument(
        parser="mineru-v4-content-list-v1",
        blocks=attach_notes(blocks),
        pages=pages,
        source_map_available=any(
            ref.get("coordinate_space") == "normalized_1000"
            for block in blocks
            for ref in block.source_refs
        ),
        provider_task_id=task_id,
    )


def parse_archive(data: bytes, task_id: str) -> ParsedDocument:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > 5000 or sum(item.file_size for item in members) > 256 * 1024**2:
                raise IngestionError("mineru_archive_large", "解析产物超过安全大小限制")
            candidates = [
                item
                for item in members
                if (
                    PurePosixPath(item.filename).name == "content_list.json"
                    or item.filename.endswith("_content_list.json")
                )
            ]
            if len(candidates) != 1:
                raise IngestionError("mineru_structure_missing", "解析产物缺少唯一的结构化内容列表")
            item = candidates[0]
            if item.file_size > 32 * 1024**2:
                raise IngestionError("mineru_archive_large", "结构化内容超过大小限制")
            content = json.loads(archive.read(item))
            if not isinstance(content, list) or not all(isinstance(row, dict) for row in content):
                raise IngestionError("mineru_schema_unsupported", "MinerU 结构化内容格式不兼容")
            continuations = {}
            if any(row.get("type") == "table" and not row.get("table_body") for row in content):
                layouts = [m for m in members if PurePosixPath(m.filename).name == "layout.json"]
                if len(layouts) == 1 and layouts[0].file_size <= 32 * 1024**2:
                    layout = json.loads(archive.read(layouts[0]))
                    if isinstance(layout, dict):
                        continuations = merged_table_continuations(content, layout)
            return normalize_content(content, task_id, continuations)
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError, RuntimeError) as exc:
        raise IngestionError("mineru_archive_invalid", "MinerU 返回的解析压缩包无效") from exc


class MinerUParser:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def parse(self, content: bytes, document_id: str) -> tuple[ParsedDocument, bytes]:
        key = self.settings.mineru_api_key.get_secret_value()
        if not key:
            raise IngestionError("mineru_not_configured", "请先在 .env 配置 MINERU_API_KEY")
        headers = {"Authorization": f"Bearer {key}"}
        base = self.settings.mineru_base_url.rstrip("/")
        async with asyncio.timeout(self.settings.mineru_timeout):
            async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
                response = await client.post(
                    f"{base}/api/v4/file-urls/batch",
                    headers=headers,
                    json={
                        "files": [{"name": "document.pdf", "data_id": document_id}],
                        "model_version": self.settings.mineru_model_version,
                        "enable_formula": True,
                        "enable_table": True,
                        "language": "ch",
                    },
                )
                data = self._data(response)
                task = data["batch_id"]
                url = data["file_urls"][0]
                self._safe_download_url(url)
                upload = await client.put(url, content=content)
                upload.raise_for_status()
                deadline = time.monotonic() + self.settings.mineru_timeout
                while time.monotonic() < deadline:
                    result = self._data(
                        await client.get(
                            f"{base}/api/v4/extract-results/batch/{task}",
                            headers=headers,
                        )
                    )
                    rows = result.get("extract_result", [])
                    row = next((r for r in rows if r.get("data_id") == document_id), None)
                    if row is None and len(rows) == 1:
                        row = rows[0]
                    if row and row.get("state") == "failed":
                        raise IngestionError("mineru_failed", "MinerU 解析失败，请检查文档后重试")
                    if row and row.get("state") == "done":
                        archive_url = row["full_zip_url"]
                        self._safe_download_url(archive_url)
                        data = bytearray()
                        async with client.stream("GET", archive_url) as download:
                            download.raise_for_status()
                            async for part in download.aiter_bytes():
                                data.extend(part)
                                if len(data) > 128 * 1024**2:
                                    raise IngestionError("mineru_archive_large", "解析压缩包过大")
                        return parse_archive(bytes(data), task), bytes(data)
                    await asyncio.sleep(self.settings.mineru_poll_interval)
        raise IngestionError("mineru_timeout", "MinerU 解析超时")

    @staticmethod
    def _safe_download_url(url):
        parsed = httpx.URL(url)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise IngestionError("mineru_url_invalid", "MinerU 产物地址无效")

    @staticmethod
    def _data(response):
        response.raise_for_status()
        body = response.json()
        if body.get("code") != 0 or not isinstance(body.get("data"), dict):
            raise IngestionError("mineru_api_error", "MinerU 接口拒绝请求，请检查服务配置与配额")
        return body["data"]
