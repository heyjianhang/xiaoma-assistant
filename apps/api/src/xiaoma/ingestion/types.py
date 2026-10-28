from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ChunkOptions(BaseModel):
    target_chars: int = Field(default=1000, ge=100, le=12000)
    max_chars: int = Field(default=1600, ge=100, le=20000)
    min_chars: int = Field(default=300, ge=0, le=12000)

    @model_validator(mode="after")
    def ordered(self):
        if not self.min_chars <= self.target_chars <= self.max_chars:
            raise ValueError("分块长度需满足 min ≤ target ≤ max")
        return self


class SourceBlock(BaseModel):
    id: str
    kind: Literal["heading", "text", "table", "equation", "code", "image"]
    markdown: str
    level: int = 0
    source_refs: list[dict[str, Any]] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    parser: str
    blocks: list[SourceBlock]
    pages: int = 0
    source_map_available: bool = False
    provider_task_id: str | None = None


class Chunk(BaseModel):
    sequence: int
    content: str
    block_ids: list[str]
    section_path: list[str]
    source_refs: list[dict[str, Any]]
    oversized_atom: bool
