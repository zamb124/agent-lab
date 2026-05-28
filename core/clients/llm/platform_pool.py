"""Runtime resolver кандидатов для platform OpenRouter free-pool."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.clients.llm.config import LLMCallConfig
from core.clients.llm.openrouter_free_models import (
    OPENROUTER_FREE_MODELS_CACHE_KEY,
    OpenRouterFreeModelRecord,
    parse_openrouter_free_models,
)
from core.clients.llm.provider_resolution import _resolve_llm_call_config
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.config.base import BaseSettings

_openrouter_free_pool_redis: RedisClient | None = None


def _candidate_from_openrouter_free_record(
    record: OpenRouterFreeModelRecord,
    *,
    settings: BaseSettings,
) -> LLMCallConfig:
    return _resolve_llm_call_config(
        LLMCallConfig(
            provider="openrouter",
            model=record.id,
            source="openrouter_free",
            supported_parameters=frozenset(record.supported_parameters),
            input_modalities=frozenset(record.input_modalities),
            output_modalities=frozenset(record.output_modalities),
            context_length=record.context_length,
        ),
        settings=settings,
        source="openrouter_free",
    )


async def _read_openrouter_free_records() -> list[OpenRouterFreeModelRecord]:
    global _openrouter_free_pool_redis

    if _openrouter_free_pool_redis is None:
        settings = get_settings()
        _openrouter_free_pool_redis = RedisClient(settings.database.redis_url)
    raw_cache_payload = await _openrouter_free_pool_redis.get(OPENROUTER_FREE_MODELS_CACHE_KEY)
    return parse_openrouter_free_models(raw_cache_payload)


def _make_platform_default_candidate_resolver(
    settings: BaseSettings,
    *,
    include_paid_fallback: bool,
) -> Callable[[], Awaitable[list[LLMCallConfig]]]:
    async def _resolve() -> list[LLMCallConfig]:
        candidates: list[LLMCallConfig] = []
        records = await _read_openrouter_free_records()
        for record in records:
            candidates.append(_candidate_from_openrouter_free_record(record, settings=settings))
        paid_fallback_model = settings.llm.openrouter_free_pool.fallback_model.strip()
        if include_paid_fallback and paid_fallback_model:
            candidates.append(
                _resolve_llm_call_config(
                    LLMCallConfig(
                        provider="openrouter",
                        model=paid_fallback_model,
                        source="platform_paid_fallback",
                    ),
                    settings=settings,
                    source="platform_paid_fallback",
                )
            )
        return candidates

    return _resolve


__all__ = [
    "_make_platform_default_candidate_resolver",
]
