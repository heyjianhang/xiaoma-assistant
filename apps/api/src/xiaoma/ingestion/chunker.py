"""Port of engi-one's atomic-block grouping rules, independent of Odoo.

Headings stay with their following body. A table, formula or code block is never
cut to satisfy a character target. Table notes are attached by the parser first.
"""

import hashlib
from uuid import UUID, uuid5

from langchain_core.documents import Document

from .types import Chunk, ChunkOptions, ParsedDocument, SourceBlock

CHUNKER_VERSION = "structure-v1"


class StructureChunker:
    def __init__(self, options: ChunkOptions):
        self.options = options

    def split(self, blocks: list[SourceBlock]) -> list[Chunk]:
        result: list[Chunk] = []
        pending: list[SourceBlock] = []
        headings: list[tuple[int, str]] = []
        section: list[str] = []

        def size() -> int:
            return sum(len(block.markdown) for block in pending) + max(0, len(pending) - 1) * 2

        def flush():
            nonlocal pending
            if not pending:
                return
            content = "\n\n".join(block.markdown for block in pending).strip()
            if content:
                result.append(
                    Chunk(
                        sequence=len(result) + 1,
                        content=content,
                        block_ids=[block.id for block in pending],
                        section_path=section.copy(),
                        source_refs=[ref for block in pending for ref in block.source_refs],
                        oversized_atom=any(
                            len(block.markdown) > self.options.max_chars for block in pending
                        ),
                    )
                )
            pending = []

        for block in blocks:
            if not block.markdown.strip():
                continue
            if block.kind == "heading":
                boundary = min(
                    max(self.options.min_chars, int(self.options.target_chars * 0.75)),
                    self.options.target_chars,
                )
                if pending and size() >= boundary:
                    flush()
                while headings and headings[-1][0] >= block.level:
                    headings.pop()
                headings.append((block.level, block.markdown.lstrip("# ").strip()))
                if not pending:
                    section = [text for _, text in headings]
            else:
                has_body = any(item.kind != "heading" for item in pending)
                if (
                    pending
                    and has_body
                    and size() >= self.options.min_chars
                    and size() + len(block.markdown) + 2 > self.options.max_chars
                ):
                    flush()
                if not pending:
                    section = [text for _, text in headings]
            pending.append(block)
            if block.kind in {"table", "equation", "code"} and size() >= self.options.target_chars:
                flush()
            elif len(pending) == 1 and len(block.markdown) >= self.options.max_chars:
                flush()
        flush()
        return result


def as_documents(
    chunks: list[Chunk],
    parsed: ParsedDocument,
    document_id: UUID,
    revision: int,
    index_id: UUID,
    filename: str,
) -> list[Document]:
    documents = []
    for chunk in chunks:
        digest = hashlib.sha256(chunk.content.encode()).hexdigest()
        chunk_id = str(uuid5(index_id, f"{chunk.sequence}:{digest}:{CHUNKER_VERSION}"))
        documents.append(
            Document(
                id=chunk_id,
                page_content=chunk.content,
                metadata={
                    "document_id": str(document_id),
                    "revision": revision,
                    "index_id": str(index_id),
                    "active": False,
                    "enabled": True,
                    "source": filename,
                    "title": chunk.section_path[0] if chunk.section_path else filename,
                    "sequence": chunk.sequence,
                    "section_path": chunk.section_path,
                    "block_ids": chunk.block_ids,
                    "source_refs": chunk.source_refs,
                    "content_hash": digest,
                    "oversized_atom": chunk.oversized_atom,
                    "parser": parsed.parser,
                    "chunker_version": CHUNKER_VERSION,
                },
            )
        )
    return documents
