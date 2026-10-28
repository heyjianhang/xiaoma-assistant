import asyncio
import hashlib
import json
from datetime import UTC, datetime

from langchain_postgres import Column as VectorColumn
from langchain_postgres import PGEngine, PGVectorStore
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import create_async_engine

from .embeddings import ProviderEmbeddings
from .rerank import rerank_runnable
from .settings import Settings
from .task_queue import PgQueue


def utcnow():
    return datetime.now(UTC)


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.schema = settings.knowledge_schema
        self.engine = create_async_engine(
            settings.database_url.get_secret_value(),
            pool_pre_ping=True,
        )
        self.metadata = MetaData(schema=self.schema)
        self.documents = Table(
            "documents",
            self.metadata,
            Column("id", UUID(as_uuid=True), primary_key=True),
            Column("filename", String(255), nullable=False),
            Column("format", String(10), nullable=False),
            Column("sha256", String(64), nullable=False),
            Column("byte_size", BigInteger, nullable=False),
            Column("revision", Integer, nullable=False, default=1),
            Column("active_revision", Integer),
            Column("active_index_id", UUID(as_uuid=True)),
            Column("status", String(24), nullable=False),
            Column("chunk_options", JSONB, nullable=False),
            Column("pages", Integer, nullable=False, default=0),
            Column("source_map_available", Boolean, nullable=False, default=False),
            Column("created_at", DateTime(timezone=True), server_default=func.now()),
            Column("updated_at", DateTime(timezone=True), server_default=func.now()),
            Column("deleted_at", DateTime(timezone=True)),
        )
        self.jobs = Table(
            "ingestion_jobs",
            self.metadata,
            Column("id", UUID(as_uuid=True), primary_key=True),
            Column("document_id", UUID(as_uuid=True), ForeignKey(self.documents.c.id)),
            Column("revision", Integer, nullable=False),
            Column("index_id", UUID(as_uuid=True)),
            Column("status", String(24), nullable=False),
            Column("stage", String(24), nullable=False, default="queued"),
            Column("attempts", Integer, nullable=False, default=0),
            Column("lease_until", DateTime(timezone=True)),
            Column("error_code", String(64)),
            Column("error_message", Text),
            Column("created_at", DateTime(timezone=True), server_default=func.now()),
            Column("updated_at", DateTime(timezone=True), server_default=func.now()),
            UniqueConstraint("document_id", "revision"),
        )
        self.chunks = Table(
            "chunks",
            self.metadata,
            Column("id", UUID(as_uuid=True), primary_key=True),
            Column("document_id", UUID(as_uuid=True), ForeignKey(self.documents.c.id)),
            Column("revision", Integer, nullable=False),
            Column("index_id", UUID(as_uuid=True), nullable=False),
            Column("sequence", Integer, nullable=False),
            Column("content", Text, nullable=False),
            Column("metadata", JSONB, nullable=False),
            Column("enabled", Boolean, nullable=False, default=True),
            UniqueConstraint("index_id", "sequence"),
        )
        self.config = Table(
            "index_config",
            self.metadata,
            Column("key", String(32), primary_key=True),
            Column("value", JSONB, nullable=False),
        )
        self.store: PGVectorStore | None = None
        self.queue = PgQueue(self)

    @property
    def vector_table(self):
        # Schema is validated as a SQL identifier in Settings, never supplied by an HTTP caller.
        return f'"{self.schema}"."vectors"'

    async def initialize(self):
        fingerprint = {
            "model": self.settings.embedding_model,
            "base_url": self.settings.model_base_url.rstrip("/"),
            "dimensions": self.settings.embedding_dimensions,
        }
        lock = int.from_bytes(hashlib.sha256(self.schema.encode()).digest()[:8], "big", signed=True)
        # Serialize bootstrap, including LangChain's own table-creation transactions.
        async with self.engine.connect() as guard:
            await guard.execute(text("SELECT pg_advisory_lock(:lock)"), {"lock": lock})
            await guard.commit()
            try:
                async with self.engine.begin() as conn:
                    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                    await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"'))
                    await conn.run_sync(self.metadata.create_all)
                    current = (
                        await conn.execute(
                            select(self.config.c.value).where(
                                self.config.c.key == "embedding",
                            )
                        )
                    ).scalar_one_or_none()
                    if current is not None and current != fingerprint:
                        raise ValueError("Embedding 配置与现有索引不同；请新建 schema 后重新入库")
                    # Before a workspace is filled, no provider identity is pinned yet.
                    if current is None and self.settings.model_base_url:
                        await conn.execute(
                            self.config.insert().values(
                                key="embedding",
                                value=fingerprint,
                            )
                        )
                    exists = (
                        await conn.execute(
                            text("SELECT to_regclass(:name)"),
                            {"name": f"{self.schema}.vectors"},
                        )
                    ).scalar_one()
                # Agent Server may invoke graphs on a worker event loop. Keep asyncpg
                # connections and the provider HTTP client on their owning app loop.
                pg = PGEngine.from_engine(self.engine, loop=asyncio.get_running_loop())
                if exists is None:
                    await pg.ainit_vectorstore_table(
                        "vectors",
                        self.settings.embedding_dimensions,
                        schema_name=self.schema,
                        metadata_columns=[
                            VectorColumn("document_id", "TEXT", False),
                            VectorColumn("revision", "INTEGER", False),
                            VectorColumn("index_id", "TEXT", False),
                            VectorColumn("active", "BOOLEAN", False),
                            VectorColumn("enabled", "BOOLEAN", False),
                        ],
                    )
                else:
                    async with self.engine.connect() as conn:
                        vector_type = (
                            await conn.execute(
                                text(
                                    "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                                    "WHERE attrelid = to_regclass(:name) AND attname = 'embedding'"
                                ),
                                {"name": f"{self.schema}.vectors"},
                            )
                        ).scalar_one()
                    if vector_type != f"vector({self.settings.embedding_dimensions})":
                        raise ValueError("向量维度与已有表不同；请新建 schema 后重新入库")
                self.store = await PGVectorStore.create(
                    engine=pg,
                    embedding_service=ProviderEmbeddings(self.settings),
                    table_name="vectors",
                    schema_name=self.schema,
                    metadata_columns=["document_id", "revision", "index_id", "active", "enabled"],
                )
                await self.queue.initialize()
            finally:
                await guard.execute(text("SELECT pg_advisory_unlock(:lock)"), {"lock": lock})
                await guard.commit()

    async def close(self):
        await self.engine.dispose()

    async def vector_visibility(self, conn, document_id, index_id=None):
        await conn.execute(
            text(f"UPDATE {self.vector_table} SET active = false WHERE document_id = :id"),
            {"id": str(document_id)},
        )
        if index_id is not None:
            await conn.execute(
                text(f"UPDATE {self.vector_table} SET active = true WHERE index_id = :index"),
                {"index": str(index_id)},
            )

    async def search(self, query: str, k: int, document_id=None):
        filters = {"active": {"$eq": True}, "enabled": {"$eq": True}}
        if document_id:
            filters["document_id"] = {"$eq": str(document_id)}
        candidates = (
            max(k, self.settings.retrieval_candidates) if self.settings.rerank_enabled else k
        )
        retriever = self.store.as_retriever(search_kwargs={"k": candidates, "filter": filters})
        if self.settings.rerank_enabled:
            results = await retriever.ainvoke(query)
        else:
            scored = await self.store.asimilarity_search_with_score(query, k=k, filter=filters)
            results = []
            for doc, distance in scored:
                doc.metadata["vector_distance"] = float(distance)
                results.append(doc)
        if self.settings.rerank_enabled:
            results = await rerank_runnable(self.settings).ainvoke(
                {
                    "query": query,
                    "documents": results,
                    "top_k": k,
                }
            )
        # Return the same Document contract, without internal publication flags.
        return [json.loads(doc.model_dump_json()) for doc in results]
