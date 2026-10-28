from functools import cached_property

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from .errors import IngestionError
from .settings import Settings


class ProviderEmbeddings(Embeddings):
    """Lazy real provider; a missing key never falls back to fake embeddings."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @cached_property
    def client(self) -> OpenAIEmbeddings:
        return self.build_client(max_retries=2)

    @cached_property
    def query_client(self) -> OpenAIEmbeddings:
        # Agent ToolRetryMiddleware owns query retries; ingestion keeps its own.
        return self.build_client(max_retries=0)

    def build_client(self, max_retries: int) -> OpenAIEmbeddings:
        key = self.settings.model_api_key.get_secret_value()
        if not key or not self.settings.model_base_url:
            raise IngestionError(
                "embedding_not_configured",
                "请在 .env 配置 MODEL_BASE_URL 和 MODEL_API_KEY",
            )
        options = {}
        if self.settings.embedding_send_dimensions:
            options["dimensions"] = self.settings.embedding_dimensions
        return OpenAIEmbeddings(
            model=self.settings.embedding_model,
            api_key=key,
            base_url=self.settings.model_base_url,
            check_embedding_ctx_length=False,
            chunk_size=self.settings.embedding_batch_size,
            model_kwargs={"encoding_format": "float"},
            max_retries=max_retries,
            request_timeout=60,
            **options,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.client.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.query_client.embed_query(text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self.client.aembed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return await self.query_client.aembed_query(text)
