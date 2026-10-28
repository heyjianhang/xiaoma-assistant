"""Gateway availability plus LangChain's public Model Profile capability contract."""

import asyncio
import json
import time
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from .compatible_model import GatewayChatOpenAI
from .resilience import output_limit

PROFILE_FIELDS = (
    "max_input_tokens",
    "max_output_tokens",
    "tool_calling",
    "structured_output",
    "image_inputs",
    "reasoning_output",
)


class ModelCatalog:
    def __init__(self, settings):
        self.settings = settings
        self.cache = []
        self.checked = 0
        self.public_profiles = None
        self.lock = asyncio.Lock()

    def model(self, name, profile=None):
        kwargs = {
            "base_url": self.settings.model_base_url,
            "api_key": self.settings.model_api_key.get_secret_value(),
            "timeout": self.settings.chat_model_timeout_seconds,
            "stream_chunk_timeout": self.settings.chat_model_timeout_seconds,
            # Retry once at the middleware layer; avoid multiplying SDK attempts.
            "max_retries": 0,
        }
        limit = output_limit(self.settings, profile or {})
        if limit:
            kwargs["max_tokens"] = limit
        if self.settings.chat_temperature is not None:
            kwargs["temperature"] = self.settings.chat_temperature
        if profile:
            kwargs["profile"] = profile
        return GatewayChatOpenAI(model=name, **kwargs)

    async def registry_profiles(self):
        if self.public_profiles is not None:
            return self.public_profiles
        self.public_profiles = {}
        # The configured mainland DashScope gateway is matched to its own registry
        # provider, never to a similarly named model served by another provider.
        host = urlparse(self.settings.model_base_url).hostname or ""
        if not host.endswith(".maas.aliyuncs.com") or ".cn-" not in host:
            return self.public_profiles
        cached = self.settings.storage_root.parent / "model-profiles.json"
        try:
            if cached.stat().st_size < 10 * 1024**2:
                stored = json.loads(cached.read_text())
                if isinstance(stored, dict) and isinstance(stored.get("models"), dict):
                    self.public_profiles = stored["models"]
                    if time.time() - stored.get("updated_at", 0) < 86400:
                        return self.public_profiles
        except (OSError, ValueError, TypeError):
            pass
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                async with client.stream("GET", "https://models.dev/api.json") as response:
                    response.raise_for_status()
                    content = bytearray()
                    async for part in response.aiter_bytes():
                        content.extend(part)
                        if len(content) > 10 * 1024**2:
                            return self.public_profiles
            self.public_profiles = json.loads(content).get("alibaba-cn", {}).get("models", {})
            try:
                cached.parent.mkdir(parents=True, exist_ok=True)
                temporary = cached.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps({"updated_at": time.time(), "models": self.public_profiles})
                )
                temporary.replace(cached)
            except OSError:
                pass  # Cache failures never block model requests.
        except Exception:
            pass  # Public metadata is optional; an outage must not disable chat.
        return self.public_profiles

    async def list(self, force=False):
        async with self.lock:
            return await self._list(force)

    async def _list(self, force=False):
        if self.cache and not force and time.monotonic() - self.checked < 300:
            return self.cache
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    self.settings.model_base_url + "/models",
                    headers={
                        "Authorization": "Bearer " + self.settings.model_api_key.get_secret_value()
                    },
                )
                response.raise_for_status()
                available = {row["id"] for row in response.json()["data"]}
        except Exception as exc:
            raise HTTPException(503, "无法读取模型网关目录，请检查服务配置") from exc
        allowed = [
            name.strip()
            for name in self.settings.chat_model_ids.split(",")
            if name.strip() in available
        ]
        items = []
        registry = await self.registry_profiles()
        for name in allowed:
            profile = dict(self.model(name).profile or {})
            source = "langchain" if profile else "unavailable"
            if not profile and name in registry:
                row = registry[name]
                limits = row.get("limit", {})
                for key, field in [
                    ("context", "max_input_tokens"),
                    ("output", "max_output_tokens"),
                ]:
                    value = limits.get(key)
                    if isinstance(value, int) and value > 0:
                        profile[field] = value
                if isinstance(row.get("tool_call"), bool):
                    profile["tool_calling"] = row["tool_call"]
                if isinstance(row.get("reasoning"), bool):
                    profile["reasoning_output"] = row["reasoning"]
                source = "models.dev:alibaba-cn" if profile else "unavailable"
            if profile.get("tool_calling") is False:
                continue
            items.append(
                {
                    "id": name,
                    "name": name,
                    "profile": {k: v for k, v in profile.items() if k in PROFILE_FIELDS},
                    "profile_source": source,
                }
            )
        if not items:
            raise HTTPException(503, "网关没有提供当前允许的聊天模型")
        self.cache = items
        self.checked = time.monotonic()
        return items

    async def resolve(self, name):
        items = await self.list()
        model = next((item for item in items if item["id"] == name), None) if name else items[0]
        if not model:
            raise HTTPException(422, "请选择服务提供的聊天模型")
        return self.model(model["id"], model["profile"]), model
