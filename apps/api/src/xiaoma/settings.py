from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[4]


def identifier(value: str) -> str:
    import re

    if not re.fullmatch(r"[a-z][a-z0-9_]{0,45}", value):
        raise ValueError("Schema 名必须为小写 SQL 标识符")
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: SecretStr
    admin_password_hash: SecretStr = SecretStr("")
    web_origin: str = "http://127.0.0.1:3002"
    auth_cookie_secure: bool = False
    session_hours: int = Field(default=24, ge=1, le=168)
    chat_model_ids: str = "qwen3.8-flash,glm-5.3,deepseek-v4.1-flash"
    chat_max_steps: int = Field(default=512, ge=4, le=2048)
    chat_timeout_seconds: int = Field(default=900, ge=10, le=3600)
    chat_model_call_limit: int = Field(default=64, ge=2, le=256)
    chat_tool_call_limit: int = Field(default=128, ge=4, le=512)
    chat_max_output_tokens: int = Field(default=0, ge=0, le=1048576)
    chat_model_timeout_seconds: int = Field(default=180, ge=5, le=600)
    chat_temperature: float | None = Field(default=None, ge=0, le=2)
    chat_model_max_retries: int = Field(default=2, ge=0, le=3)
    chat_tool_max_retries: int = Field(default=2, ge=0, le=3)
    chat_repeated_tool_failure_limit: int = Field(default=3, ge=2, le=8)
    chat_retry_initial_delay: float = Field(default=1, ge=0, le=5)
    chat_summary_trigger_fraction: float = Field(default=0.75, ge=0.2, le=0.9)
    chat_summary_keep_fraction: float = Field(default=0.25, ge=0.01, le=0.5)
    chat_context_fallback_tokens: int = Field(default=128000, ge=4096, le=4000000)
    chat_context_window_tokens: int = Field(default=0, ge=0, le=4000000)
    chat_summary_max_output_tokens: int = Field(default=16384, ge=1024, le=65536)
    # Optional absolute overrides; zero follows model window fractions.
    chat_summary_trigger_tokens: int = Field(default=0, ge=0, le=4000000)
    chat_summary_keep_tokens: int = Field(default=0, ge=0, le=2000000)
    business_database_url: SecretStr = SecretStr("")
    business_schema: Annotated[str, AfterValidator(identifier)] = "business_v1"
    knowledge_schema: Annotated[str, AfterValidator(identifier)] = "knowledge"
    storage_root: Path = ROOT / "var/documents"
    model_base_url: str = ""
    model_api_key: SecretStr = SecretStr("")
    embedding_model: str = "qwen3.7-text-embedding"
    embedding_dimensions: int = Field(default=1024, ge=1, le=16000)
    embedding_send_dimensions: bool = True
    embedding_batch_size: int = Field(default=10, ge=1, le=20)
    rerank_enabled: bool = True
    rerank_model: str = "qwen3.7-text-rerank"
    retrieval_candidates: int = Field(default=20, ge=1, le=100)
    mineru_base_url: str = "https://mineru.net"
    mineru_api_key: SecretStr = SecretStr("")
    mineru_model_version: str = "vlm"
    mineru_poll_interval: float = Field(default=3, ge=0.01)
    mineru_timeout: float = Field(default=900, ge=1)
    chunk_target_chars: int = Field(default=1000, ge=100)
    chunk_max_chars: int = Field(default=1600, ge=100)
    chunk_min_chars: int = Field(default=300, ge=0)
    upload_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    worker_poll_interval: float = Field(default=1, ge=0.01)
    job_lease_seconds: int = Field(default=120, ge=10)
    background_workers_enabled: bool = True
    chat_worker_concurrency: int = Field(default=4, ge=1, le=32)
    chat_owner_concurrency: int = Field(default=2, ge=1, le=8)
    chat_owner_pending_limit: int = Field(default=10, ge=1, le=50)
    ingestion_worker_concurrency: int = Field(default=2, ge=1, le=8)
    run_event_poll_interval: float = Field(default=0.1, ge=0.01, le=2)

    @property
    def rerank_endpoint(self) -> str:
        """DashScope's native rerank route shares the configured model gateway."""
        base = self.model_base_url.rstrip("/")
        if not base.endswith("/compatible-mode/v1"):
            return ""
        return base.removesuffix("/compatible-mode/v1") + (
            "/api/v1/services/rerank/text-rerank/text-rerank"
        )

    @model_validator(mode="after")
    def validate_ranges(self):
        self.model_base_url = self.model_base_url.strip().rstrip("/")
        if not self.chunk_min_chars <= self.chunk_target_chars <= self.chunk_max_chars:
            raise ValueError("分块长度需满足 min ≤ target ≤ max")
        if self.chat_summary_keep_fraction >= self.chat_summary_trigger_fraction:
            raise ValueError("摘要保留比例必须小于触发比例")
        if (
            self.chat_summary_trigger_tokens
            and self.chat_summary_keep_tokens >= self.chat_summary_trigger_tokens
        ):
            raise ValueError("摘要保留预算必须小于摘要触发预算")
        if not self.storage_root.is_absolute():
            self.storage_root = (ROOT / self.storage_root).resolve()
        return self
