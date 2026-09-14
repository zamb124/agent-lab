"""Runtime status free-pool провайдеров и smoke probe против локального сервера."""

from __future__ import annotations

import httpx
import pytest

from core.ai.provider_error import AIProviderErrorClass
from core.ai.providers import PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER
from core.clients.llm.candidate_cooldown import (
    candidate_cooldown_state_map,
    cooldown_redis_key,
    set_candidate_cooldown,
)
from core.clients.llm.candidates import candidate_key
from core.clients.llm.platform_pool import llm_call_configs_for_provider_model
from core.clients.llm.provider_runtime_status import (
    LLMModelAvailability,
    collect_free_pool_runtime_status,
    probe_platform_free_providers,
)
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.config.models import GroqProviderConfig, LLMConfig, PlatformFreePoolConfig
from tests.core.clients.test_llm_candidate_fallback_integration import (
    _OpenAICompatibleTestServer,
    _write_json_response,
    _write_sse_text,
)


def _groq_settings(*, api_key: str, base_url: str, smoke_model: str) -> LLMConfig:
    return LLMConfig(
        groq=GroqProviderConfig(
            api_key=api_key,
            base_url=base_url,
            smoke_model=smoke_model,
        ),
        platform_free_pool=PlatformFreePoolConfig(candidate_cooldown_seconds=30),
    )


def _http_status_error(status: int, body: str) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    response = httpx.Response(status, text=body, request=request)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


@pytest.mark.asyncio
async def test_collect_free_pool_runtime_status_cooldown_and_chips(unique_id: str) -> None:
    blocked_model = f"blocked-{unique_id}"
    live_model = f"live-{unique_id}"
    settings = get_settings().model_copy(
        update={
            "llm": _groq_settings(
                api_key=f"key-{unique_id}",
                base_url="https://api.groq.com/openai/v1",
                smoke_model="llama-3.1-8b-instant",
            )
        }
    )
    blocked_candidates = llm_call_configs_for_provider_model(
        provider="groq",
        model_id=blocked_model,
        settings=settings,
    )
    if not blocked_candidates:
        pytest.fail("groq test settings must resolve at least one api_key")
    redis = RedisClient(get_settings().database.redis_url)
    cooldown_keys = [cooldown_redis_key(candidate) for candidate in blocked_candidates]
    try:
        for candidate in blocked_candidates:
            await set_candidate_cooldown(
                candidate,
                50,
                error=_http_status_error(402, "Payment required"),
            )
        mixed_status, mixed_providers = await collect_free_pool_runtime_status(
            [
                ("groq", blocked_model, True),
                ("groq", live_model, True),
            ],
            settings=settings,
        )
        assert mixed_status[("groq", blocked_model)].availability == LLMModelAvailability.COOLDOWN
        assert mixed_status[("groq", blocked_model)].error_class == (
            AIProviderErrorClass.PAYMENT_REQUIRED
        )
        assert mixed_status[("groq", live_model)].availability == LLMModelAvailability.AVAILABLE
        groq_chip = next(row for row in mixed_providers if row.provider == "groq")
        assert groq_chip.configured is True
        assert groq_chip.availability == LLMModelAvailability.AVAILABLE
        assert groq_chip.model_count == 2
        assert groq_chip.blocked_model_count == 1
        assert [row.provider for row in mixed_providers] == list(
            PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER
        )
        openrouter_chip = next(row for row in mixed_providers if row.provider == "openrouter")
        assert openrouter_chip.configured is False
        assert openrouter_chip.availability == LLMModelAvailability.NOT_CONFIGURED

        all_blocked_status, all_blocked_providers = await collect_free_pool_runtime_status(
            [("groq", blocked_model, True)],
            settings=settings,
        )
        assert all_blocked_status[("groq", blocked_model)].availability == (
            LLMModelAvailability.COOLDOWN
        )
        groq_blocked = next(row for row in all_blocked_providers if row.provider == "groq")
        assert groq_blocked.availability == LLMModelAvailability.COOLDOWN
        assert groq_blocked.http_status == 402

        disabled_status, _providers = await collect_free_pool_runtime_status(
            [("groq", blocked_model, False)],
            settings=settings,
        )
        assert disabled_status[("groq", blocked_model)].availability == (
            LLMModelAvailability.DISABLED
        )
        assert disabled_status[("groq", blocked_model)].error_class == (
            AIProviderErrorClass.PAYMENT_REQUIRED
        )
    finally:
        if cooldown_keys:
            _ = await redis.delete(*cooldown_keys)


@pytest.mark.asyncio
async def test_probe_platform_free_providers_smoke_chat(
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smoke_model = f"smoke-ok-{unique_id}"
    server = _OpenAICompatibleTestServer(
        {smoke_model: lambda writer: _write_sse_text(writer, "pong")}
    )
    await server.start()
    health_key = f"llm:platform:provider_health:test:{unique_id}"
    monkeypatch.setattr(
        "core.clients.llm.provider_runtime_status.PROVIDER_HEALTH_REDIS_KEY",
        health_key,
    )
    settings = get_settings().model_copy(
        update={
            "llm": _groq_settings(
                api_key=f"key-{unique_id}",
                base_url=server.base_url,
                smoke_model=smoke_model,
            )
        }
    )
    redis = RedisClient(get_settings().database.redis_url)
    try:
        snapshots = await probe_platform_free_providers(settings=settings)
        assert len(snapshots) == 1
        assert snapshots[0].provider == "groq"
        assert snapshots[0].ok is True
        assert snapshots[0].error_class is None
        assert [request.model for request in server.requests] == [smoke_model]
        status_map, providers = await collect_free_pool_runtime_status(
            [("groq", smoke_model, True)],
            settings=settings,
        )
        assert status_map[("groq", smoke_model)].availability == LLMModelAvailability.AVAILABLE
        groq_chip = next(row for row in providers if row.provider == "groq")
        assert groq_chip.last_probe is not None
        assert groq_chip.last_probe.ok is True
        assert groq_chip.last_probe.probed_at is not None
    finally:
        _ = await redis.delete(health_key)
        await server.close()


@pytest.mark.asyncio
async def test_probe_platform_free_providers_writes_cooldown_on_402(
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smoke_model = f"smoke-402-{unique_id}"
    server = _OpenAICompatibleTestServer(
        {
            smoke_model: lambda writer: _write_json_response(
                writer,
                402,
                {"error": "Payment required"},
            )
        }
    )
    await server.start()
    health_key = f"llm:platform:provider_health:test:{unique_id}"
    monkeypatch.setattr(
        "core.clients.llm.provider_runtime_status.PROVIDER_HEALTH_REDIS_KEY",
        health_key,
    )
    settings = get_settings().model_copy(
        update={
            "llm": _groq_settings(
                api_key=f"key-{unique_id}",
                base_url=server.base_url,
                smoke_model=smoke_model,
            )
        }
    )
    candidates = llm_call_configs_for_provider_model(
        provider="groq",
        model_id=smoke_model,
        settings=settings,
    )
    redis = RedisClient(get_settings().database.redis_url)
    cooldown_keys = [cooldown_redis_key(candidate) for candidate in candidates]
    try:
        snapshots = await probe_platform_free_providers(settings=settings)
        assert len(snapshots) == 1
        assert snapshots[0].ok is False
        assert snapshots[0].error_class == AIProviderErrorClass.PAYMENT_REQUIRED
        states = await candidate_cooldown_state_map(candidates)
        assert candidate_key(candidates[0]) in states
        assert states[candidate_key(candidates[0])].record.error_class == (
            AIProviderErrorClass.PAYMENT_REQUIRED
        )
        _status_map, providers = await collect_free_pool_runtime_status(
            [("groq", smoke_model, True)],
            settings=settings,
        )
        groq_chip = next(row for row in providers if row.provider == "groq")
        assert groq_chip.last_probe is not None
        assert groq_chip.last_probe.ok is False
        assert groq_chip.availability == LLMModelAvailability.COOLDOWN
    finally:
        keys = [health_key, *cooldown_keys]
        _ = await redis.delete(*keys)
        await server.close()
