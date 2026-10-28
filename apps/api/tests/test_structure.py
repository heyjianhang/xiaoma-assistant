from uuid import uuid4

from langchain_core.documents import Document

from xiaoma.ingestion.chunker import StructureChunker, as_documents
from xiaoma.ingestion.markdown import parse_markdown
from xiaoma.ingestion.mineru import normalize_content
from xiaoma.ingestion.types import ChunkOptions


def test_markdown_atoms_notes_and_stable_document_ids():
    content = """# 退款时效

说明段落。

| 渠道 | 时效 |
| --- | --- |
| 银行卡 | 3 个工作日 |

注：到账时间以银行为准。

$$
R = A / B

X = 2
$$

式中 A 为退款订单数。

```python
print('hello')
```
"""
    parsed = parse_markdown(content)
    table = next(block for block in parsed.blocks if block.kind == "table")
    equation = next(block for block in parsed.blocks if block.kind == "equation")
    assert "银行为准" in table.markdown and len(table.source_refs) == 2
    assert "X = 2" in equation.markdown and "A 为退款" in equation.markdown
    chunks = StructureChunker(ChunkOptions(target_chars=100, max_chars=110, min_chars=0)).split(
        parsed.blocks,
    )
    combined = "\n".join(chunk.content for chunk in chunks)
    for atom in parsed.blocks:
        assert atom.markdown in combined
        assert sum(atom.id in chunk.block_ids for chunk in chunks) == 1
    args = dict(
        parsed=parsed, document_id=uuid4(), revision=1, index_id=uuid4(), filename="test.md"
    )
    first = as_documents(chunks, **args)
    second = as_documents(chunks, **args)
    assert all(isinstance(item, Document) for item in first)
    assert [item.id for item in first] == [item.id for item in second]
    assert first[0].metadata["source_refs"][0]["line_start"] == 1


def test_large_table_is_not_truncated_and_mineru_prefers_structured_body():
    table = "<table><tr><td>" + "完整表格" * 100 + "</td></tr></table>"
    parsed = normalize_content(
        [
            {"type": "text", "text": "退款", "text_level": 1, "page_idx": 0},
            {
                "type": "table",
                "table_body": table,
                "table_caption": ["表 1"],
                "table_footnote": ["注：工作日"],
                "img_path": "table.png",
                "page_idx": 1,
                "bbox": [10, 20, 800, 600],
            },
            {"type": "equation", "text": "R=A/B", "page_idx": 1},
            {"type": "text", "text": "式中：B 为订单总数。", "page_idx": 1},
        ],
        "task",
    )
    chunks = StructureChunker(ChunkOptions(target_chars=100, max_chars=120, min_chars=0)).split(
        parsed.blocks,
    )
    assert any(table in chunk.content and chunk.oversized_atom for chunk in chunks)
    assert "工作日" in parsed.blocks[1].markdown
    assert "B 为订单总数" in parsed.blocks[2].markdown
    assert parsed.pages == 2
    assert parsed.source_map_available
    assert parsed.blocks[1].source_refs[0]["bbox_raw"] == [10, 20, 800, 600]


def test_math_without_blank_lines_does_not_drop_surrounding_prose():
    source = "前面说明\n$$\nx=1\n$$\n后面说明\n"
    parsed = parse_markdown(source)
    joined = "\n".join(block.markdown for block in parsed.blocks)
    assert "前面说明" in joined and "后面说明" in joined and "x=1" in joined
