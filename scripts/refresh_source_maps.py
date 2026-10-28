"""Enrich existing active PDF chunks using saved MinerU archives; no provider calls."""

import asyncio
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from xiaoma.ingestion.mineru import parse_archive
from xiaoma.settings import Settings


async def main():
    settings = Settings()
    schema = settings.knowledge_schema
    engine = create_async_engine(settings.database_url.get_secret_value())
    updated = []
    try:
        async with engine.begin() as conn:
            documents = (
                (
                    await conn.execute(
                        text(f'''
                SELECT id, active_index_id FROM "{schema}".documents
                WHERE deleted_at IS NULL AND format='pdf' AND status='ready'
                  AND active_index_id IS NOT NULL FOR UPDATE
            ''')
                    )
                )
                .mappings()
                .all()
            )
            for doc in documents:
                directory = settings.storage_root / str(doc["id"]) / str(doc["active_index_id"])
                archive = directory / "mineru.zip"
                if not archive.exists():
                    continue
                parsed = parse_archive(archive.read_bytes(), "saved-archive")
                refs = {
                    ref["block_index"]: ref
                    for block in parsed.blocks
                    for ref in block.source_refs
                    if "block_index" in ref
                }
                chunks = (
                    (
                        await conn.execute(
                            text(f'''
                    SELECT id, metadata FROM "{schema}".chunks WHERE index_id=:index
                '''),
                            {"index": doc["active_index_id"]},
                        )
                    )
                    .mappings()
                    .all()
                )
                for chunk in chunks:
                    enriched = [
                        refs.get(ref.get("block_index"), ref)
                        for ref in chunk["metadata"].get("source_refs", [])
                    ]
                    payload = {"id": chunk["id"], "refs": json.dumps(enriched)}
                    await conn.execute(
                        text(f'''
                        UPDATE "{schema}".chunks SET metadata=jsonb_set(metadata,
                          '{{source_refs}}', CAST(:refs AS jsonb)) WHERE id=:id
                    '''),
                        payload,
                    )
                    await conn.execute(
                        text(f'''
                        UPDATE "{schema}".vectors SET langchain_metadata=jsonb_set(
                          CAST(langchain_metadata AS jsonb),'{{source_refs}}',CAST(:refs AS jsonb))
                        WHERE langchain_id=:id
                    '''),
                        payload,
                    )
                await conn.execute(
                    text(f'''
                    UPDATE "{schema}".documents SET source_map_available=:available
                    WHERE id=:id
                '''),
                    {"id": doc["id"], "available": parsed.source_map_available},
                )
                # Keep provider task attribution from the original artifact.
                artifact = directory / "parsed.json"
                if artifact.exists():
                    old = json.loads(artifact.read_text())
                    parsed.provider_task_id = old.get("provider_task_id")
                artifact.write_text(parsed.model_dump_json(indent=2))
                updated.append(
                    {
                        "document_id": str(doc["id"]),
                        "chunks": len(chunks),
                        "source_map_available": parsed.source_map_available,
                    }
                )
        print(json.dumps(updated, ensure_ascii=False))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
