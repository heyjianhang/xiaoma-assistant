"""Generate RAG playground examples using the production parser and chunker."""

import argparse
import hashlib
import json
from pathlib import Path

from xiaoma.ingestion.chunker import CHUNKER_VERSION, StructureChunker
from xiaoma.ingestion.markdown import parse_markdown
from xiaoma.ingestion.types import ChunkOptions
from xiaoma.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "apps/web/src/features/project/fixtures"
REFERENCE = ROOT / "apps/web/tests/fixtures/chunking-reference.json"


def build():
    source = (FIXTURES / "chunking-source.md").read_text()
    # Non-BMP characters catch JS UTF-16/Python character-count drift.
    examples = [
        ("refund", "退款制度节选", source),
        (
            "unicode",
            "Unicode boundary",
            "# 🐴\n\n" + "说明😀" * 40 + "\n\n## 公式\n\n$$\nx=1\n$$\n\n式中 x 为数量。",
        ),
    ]
    samples = []
    for name, title, content in examples:
        parsed = parse_markdown(content)
        cases = []
        for minimum in (0, 80, 180):
            for target in (180, 240, 500, 1000):
                for maximum in sorted({target, max(target, 360), max(target, 720)}):
                    options = ChunkOptions(
                        min_chars=minimum, target_chars=target, max_chars=maximum
                    )
                    chunks = StructureChunker(options).split(parsed.blocks)
                    cases.append(
                        {
                            "options": options.model_dump(),
                            "chunks": [
                                {
                                    "sequence": chunk.sequence,
                                    "block_ids": chunk.block_ids,
                                    "section_path": chunk.section_path,
                                    "source_refs": chunk.source_refs,
                                    "oversized_atom": chunk.oversized_atom,
                                    "characters": len(chunk.content),
                                    "sha256": hashlib.sha256(chunk.content.encode()).hexdigest(),
                                }
                                for chunk in chunks
                            ],
                        }
                    )
        samples.append(
            {
                "id": name,
                "title": title,
                "blocks": [b.model_dump() for b in parsed.blocks],
                "cases": cases,
            }
        )
    # Keep the full reference snapshots out of the browser bundle.
    sample = {key: value for key, value in samples[0].items() if key != "cases"}
    return {
        FIXTURES / "chunking-sample.json": {"chunker_version": CHUNKER_VERSION, **sample},
        REFERENCE: {"chunker_version": CHUNKER_VERSION, "samples": samples},
        FIXTURES / "rag-defaults.json": {
            key: Settings.model_fields[key].default
            for key in (
                "mineru_model_version",
                "embedding_model",
                "embedding_dimensions",
                "embedding_batch_size",
                "rerank_model",
                "retrieval_candidates",
                "chunk_min_chars",
                "chunk_target_chars",
                "chunk_max_chars",
            )
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, data in build().items():
        expected = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        if args.check:
            if not path.exists() or path.read_text() != expected:
                raise SystemExit(
                    f"Stale fixture: {path.relative_to(ROOT)}. "
                    "Run scripts/build_chunk_demo.py with the API environment."
                )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected)
            print(f"Updated {path.relative_to(ROOT)}")
    if args.check:
        print("RAG playground fixtures match the production parser and chunker.")


if __name__ == "__main__":
    main()
