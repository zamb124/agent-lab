from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

import pytest

from core.ai.adapters.catalog_base import AIProviderAdapterError
from core.ai.free_pool import (
    PlatformFreeModelRecord,
    compute_platform_free_record_scores,
    fetch_platform_free_model_records,
    parse_platform_free_models,
    refresh_platform_free_models_cache,
    rescore_cached_platform_free_models,
    serialize_platform_free_models,
)
from core.ai.models import AIModelRecord
from core.ai.providers import AICapability
from core.ai.scoring import PlatformModelScoreOverlay
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.config.models import (
    BothubProviderConfig,
    CerebrasProviderConfig,
    GitHubModelsProviderConfig,
    GoogleLLMProviderConfig,
    GroqProviderConfig,
    HuggingFaceProviderConfig,
    MistralProviderConfig,
    NvidiaProviderConfig,
    OpenRouterProviderConfig,
    SambaNovaProviderConfig,
    ZAIProviderConfig,
)


class _JsonGetServer:
    def __init__(self, *, status: int, payload: Mapping[str, Any] | None = None) -> None:
        self.status = status
        self.payload = dict(payload) if payload is not None else None
        self._server: asyncio.AbstractServer | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("server is not started")
        host, port = self._server.sockets[0].getsockname()[:2]
        return f"http://{host}:{port}"

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)

    async def close(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            _ = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=1.0)
            body = b"{}" if self.payload is None else json.dumps(self.payload).encode("utf-8")
            writer.write(
                (
                    f"HTTP/1.1 {self.status} Error\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                ).encode("ascii")
                + body
            )
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, BrokenPipeError):
            return
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, BrokenPipeError):
                pass


def _free_record(*, unique_id: str) -> PlatformFreeModelRecord:
    return PlatformFreeModelRecord(
        provider="groq",
        id=f"keep-{unique_id}",
        score=12.0,
        context_length=8192,
        supported_parameters=("tools",),
        input_modalities=("text",),
        output_modalities=("text",),
        free_reason="account_free_tier",
    )


def _llm_update_without_free_pool_keys(**provider_overrides: object) -> dict[str, object]:
    update: dict[str, object] = {
        "openrouter": OpenRouterProviderConfig(api_key=None),
        "bothub": BothubProviderConfig(api_key=None),
        "groq": GroqProviderConfig(api_key=None),
        "cerebras": CerebrasProviderConfig(api_key=None),
        "google": GoogleLLMProviderConfig(api_key=None),
        "github": GitHubModelsProviderConfig(api_key=None),
        "huggingface": HuggingFaceProviderConfig(api_key=None),
        "nvidia": NvidiaProviderConfig(api_key=None),
        "mistral": MistralProviderConfig(api_key=None),
        "zai": ZAIProviderConfig(api_key=None),
        "sambanova": SambaNovaProviderConfig(api_key=None),
    }
    update.update(provider_overrides)
    return update


def _settings_without_free_pool_keys():
    live = get_settings()
    return live.model_copy(
        update={"llm": live.llm.model_copy(update=_llm_update_without_free_pool_keys())}
    )


@pytest.fixture
def platform_free_cache_key(unique_id: str, monkeypatch: pytest.MonkeyPatch) -> str:
    key = f"llm:platform:free_models:test:{unique_id}"
    monkeypatch.setattr("core.ai.free_pool.PLATFORM_FREE_MODELS_CACHE_KEY", key)
    monkeypatch.setattr("core.clients.llm.platform_pool.PLATFORM_FREE_MODELS_CACHE_KEY", key)
    monkeypatch.setattr("core.clients.llm.platform_pool._platform_free_pool_redis", None)
    return key


@pytest.mark.asyncio
async def test_refresh_empty_records_keeps_existing_redis(
    platform_free_cache_key: str,
    unique_id: str,
) -> None:
    redis_client = RedisClient(get_settings().database.redis_url)
    snapshot = serialize_platform_free_models([_free_record(unique_id=unique_id)])
    wrote = await redis_client.set(platform_free_cache_key, snapshot, ttl=120)
    assert wrote is True
    with pytest.raises(RuntimeError, match="empty records"):
        await refresh_platform_free_models_cache(
            redis_client,
            _settings_without_free_pool_keys(),
        )
    stored = await redis_client.get(platform_free_cache_key)
    assert stored == snapshot
    parsed = parse_platform_free_models(stored)
    assert parsed[0].id == f"keep-{unique_id}"


@pytest.mark.asyncio
async def test_refresh_aa_http_500_does_not_change_redis(
    platform_free_cache_key: str,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _JsonGetServer(status=500, payload={"error": "aa fail"})
    await server.start()
    redis_client = RedisClient(get_settings().database.redis_url)
    snapshot = serialize_platform_free_models([_free_record(unique_id=unique_id)])
    wrote = await redis_client.set(platform_free_cache_key, snapshot, ttl=120)
    assert wrote is True
    live = get_settings()
    settings = live.model_copy(
        update={
            "llm": live.llm.model_copy(
                update={
                    "openrouter": OpenRouterProviderConfig(
                        api_key="sk-test",
                        site_url="https://platform.example",
                        site_name="Platform Test",
                    )
                }
            )
        }
    )
    monkeypatch.setattr(
        "core.ai.adapters.openrouter._OPENROUTER_BENCHMARKS_URL",
        f"{server.url}/benchmarks",
    )
    try:
        with pytest.raises(AIProviderAdapterError):
            await refresh_platform_free_models_cache(
                redis_client,
                settings,
            )
        stored = await redis_client.get(platform_free_cache_key)
        assert stored == snapshot
    finally:
        await server.close()


def test_rescore_pool_record_without_catalog_raises() -> None:
    record = PlatformFreeModelRecord(
        provider="groq",
        id="missing-from-catalog",
        score=1.0,
        context_length=None,
        supported_parameters=(),
        input_modalities=("text",),
        output_modalities=("text",),
        free_reason="account_free_tier",
    )
    with pytest.raises(ValueError, match="is missing from the catalog"):
        compute_platform_free_record_scores(
            [record],
            catalog_records=[],
            overlays=None,
        )


@pytest.mark.asyncio
async def test_rescore_empty_records_does_not_write_redis(
    platform_free_cache_key: str,
    unique_id: str,
) -> None:
    redis_client = RedisClient(get_settings().database.redis_url)
    snapshot = serialize_platform_free_models([_free_record(unique_id=unique_id)])
    wrote = await redis_client.set(platform_free_cache_key, snapshot, ttl=120)
    assert wrote is True
    groq_model = AIModelRecord(
        provider="groq",
        model_id=f"disabled-{unique_id}",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
    )
    _ = await AIModelRecord.set(groq_model)
    existing = await AIModelRecord.list_by_provider_capability("groq", AICapability.LLM_CHAT)
    live = get_settings()
    settings = live.model_copy(
        update={
            "llm": live.llm.model_copy(
                update=_llm_update_without_free_pool_keys(
                    groq=GroqProviderConfig(
                        api_key="sk-test",
                        smoke_model="llama-3.1-8b-instant",
                    ),
                )
            )
        }
    )
    overlays = {
        (row.provider, row.model_id): PlatformModelScoreOverlay(
            enabled=False,
            editorial_prior=0.0,
            note=None,
        )
        for row in existing
    }
    try:
        with pytest.raises(RuntimeError, match="empty records"):
            await rescore_cached_platform_free_models(
                redis_client,
                settings,
                overlays=overlays,
            )
        stored = await redis_client.get(platform_free_cache_key)
        assert stored == snapshot
    finally:
        stored_row = await AIModelRecord.by_provider_and_model_id("groq", groq_model.model_id)
        if stored_row is not None:
            _ = await stored_row.delete()


@pytest.mark.asyncio
async def test_fetch_skips_unconfigured_provider_and_keeps_configured(
    unique_id: str,
) -> None:
    groq_model = AIModelRecord(
        provider="groq",
        model_id=f"live-{unique_id}",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
    )
    openrouter_model = AIModelRecord(
        provider="openrouter",
        model_id=f"ignored-{unique_id}:free",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
        is_free=True,
        free_reason="zero_price_catalog",
    )
    _ = await AIModelRecord.set(groq_model)
    _ = await AIModelRecord.set(openrouter_model)
    live = get_settings()
    settings = live.model_copy(
        update={
            "llm": live.llm.model_copy(
                update=_llm_update_without_free_pool_keys(
                    groq=GroqProviderConfig(
                        api_key="sk-test",
                        smoke_model="llama-3.1-8b-instant",
                    ),
                )
            )
        }
    )
    try:
        records = await fetch_platform_free_model_records(settings)
        ids = [(row.provider, row.id) for row in records]
        assert ("groq", groq_model.model_id) in ids
        assert ("openrouter", openrouter_model.model_id) not in ids
    finally:
        for provider, model_id in (
            ("groq", groq_model.model_id),
            ("openrouter", openrouter_model.model_id),
        ):
            stored_row = await AIModelRecord.by_provider_and_model_id(provider, model_id)
            if stored_row is not None:
                _ = await stored_row.delete()
