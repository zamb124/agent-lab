"""Runtime availability of platform free-pool providers and models."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, timezone
from enum import StrEnum

from a2a.helpers.proto_helpers import new_text_message
from a2a.types import Role

from core.ai.llm_config import LLMCallConfig
from core.ai.provider_error import (
    AI_PROVIDER_IO_ERRORS,
    AIProviderErrorClass,
    classify_ai_provider_error,
)
from core.ai.providers import PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER
from core.clients.llm.candidate_cooldown import (
    CandidateCooldownState,
    candidate_cooldown_state_map,
)
from core.clients.llm.candidates import candidate_key
from core.clients.llm.client import LLMClient
from core.clients.llm.platform_pool import llm_call_configs_for_provider_model
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.config.base import BaseSettings
from core.config.llm_openai_compat import (
    provider_is_configured_for_free_pool,
    provider_smoke_model,
)
from core.logging import get_logger
from core.models import StrictBaseModel

logger = get_logger(__name__)

PROVIDER_HEALTH_REDIS_KEY = "llm:platform:provider_health:v1"
PROBE_TIMEOUT_SECONDS = 12.0
PROBE_SMOKE_MAX_TOKENS = 32

_health_redis: RedisClient | None = None


class LLMModelAvailability(StrEnum):
    AVAILABLE = "available"
    COOLDOWN = "cooldown"
    DISABLED = "disabled"
    NOT_CONFIGURED = "not_configured"


class LLMModelRuntimeStatus(StrictBaseModel):
    provider: str
    model_id: str
    availability: LLMModelAvailability
    cooldown_seconds: int | None = None
    error_class: AIProviderErrorClass | None = None
    error_text: str | None = None
    http_status: int | None = None


class LLMProviderProbeSnapshot(StrictBaseModel):
    provider: str
    probed_at: datetime
    ok: bool
    error_class: AIProviderErrorClass | None = None
    error_text: str | None = None
    http_status: int | None = None
    smoke_model: str | None = None


class LLMProviderHealthDocument(StrictBaseModel):
    providers: list[LLMProviderProbeSnapshot]


class LLMProviderRuntimeStatus(StrictBaseModel):
    provider: str
    configured: bool
    availability: LLMModelAvailability
    model_count: int
    blocked_model_count: int
    cooldown_seconds: int | None = None
    error_class: AIProviderErrorClass | None = None
    error_text: str | None = None
    http_status: int | None = None
    last_probe: LLMProviderProbeSnapshot | None = None


def _health_redis_client() -> RedisClient:
    global _health_redis
    if _health_redis is None:
        _health_redis = RedisClient(get_settings().database.redis_url)
    return _health_redis


def _require_resolved_candidate(candidate: LLMCallConfig) -> tuple[str, str, str]:
    provider = candidate.provider
    model = candidate.model
    api_key = candidate.api_key
    if provider is None or not provider.strip():
        raise ValueError("probe: provider is required")
    if model is None or not model.strip():
        raise ValueError("probe: model is required")
    if api_key is None or not api_key.strip():
        raise ValueError("probe: api_key is required")
    if candidate.base_url is None or not candidate.base_url.strip():
        raise ValueError("probe: base_url is required")
    return provider, model, api_key


def _worst_cooldown(states: Sequence[CandidateCooldownState]) -> CandidateCooldownState:
    def rank(state: CandidateCooldownState) -> tuple[int, datetime]:
        ttl_rank = 1_000_000_000 if state.ttl_seconds == -1 else state.ttl_seconds
        return (ttl_rank, state.record.set_at)

    return max(states, key=rank)


def _status_from_cooldown(
    *,
    provider: str,
    model_id: str,
    enabled: bool,
    cooldown: CandidateCooldownState | None,
) -> LLMModelRuntimeStatus:
    if not enabled:
        availability = LLMModelAvailability.DISABLED
    elif cooldown is None:
        availability = LLMModelAvailability.AVAILABLE
    else:
        availability = LLMModelAvailability.COOLDOWN
    if cooldown is None:
        return LLMModelRuntimeStatus(
            provider=provider,
            model_id=model_id,
            availability=availability,
        )
    cooldown_seconds = None if cooldown.ttl_seconds == -1 else cooldown.ttl_seconds
    return LLMModelRuntimeStatus(
        provider=provider,
        model_id=model_id,
        availability=availability,
        cooldown_seconds=cooldown_seconds,
        error_class=cooldown.record.error_class,
        error_text=cooldown.record.error_text,
        http_status=cooldown.record.http_status,
    )


def _model_cooldown(
    resolved: Sequence[LLMCallConfig],
    cooldown_states: dict[str, CandidateCooldownState],
) -> CandidateCooldownState | None:
    if not resolved:
        return None
    active: list[CandidateCooldownState] = []
    for candidate in resolved:
        state = cooldown_states.get(candidate_key(candidate))
        if state is None:
            return None
        active.append(state)
    return _worst_cooldown(active)


def _worst_model_cooldown(blocked: Sequence[LLMModelRuntimeStatus]) -> LLMModelRuntimeStatus:
    def rank(status: LLMModelRuntimeStatus) -> int:
        if status.cooldown_seconds is None:
            return 1_000_000_000
        return status.cooldown_seconds

    return max(blocked, key=rank)


async def load_provider_health_snapshots() -> dict[str, LLMProviderProbeSnapshot]:
    redis = _health_redis_client()
    values = await redis.get_batch([PROVIDER_HEALTH_REDIS_KEY])
    raw = values[0]
    if raw is None:
        return {}
    document = LLMProviderHealthDocument.model_validate_json(raw)
    return {item.provider: item for item in document.providers}


async def save_provider_health_snapshots(snapshots: Sequence[LLMProviderProbeSnapshot]) -> None:
    redis = _health_redis_client()
    document = LLMProviderHealthDocument(providers=list(snapshots))
    await redis.set_persist(PROVIDER_HEALTH_REDIS_KEY, document.model_dump_json())


async def collect_free_pool_runtime_status(
    models: Sequence[tuple[str, str, bool]],
    *,
    settings: BaseSettings,
) -> tuple[dict[tuple[str, str], LLMModelRuntimeStatus], list[LLMProviderRuntimeStatus]]:
    candidates: list[LLMCallConfig] = []
    model_candidates: dict[tuple[str, str], list[LLMCallConfig]] = {}
    for provider, model_id, _enabled in models:
        key = (provider, model_id)
        if key in model_candidates:
            continue
        resolved = llm_call_configs_for_provider_model(
            provider=provider,
            model_id=model_id,
            settings=settings,
        )
        model_candidates[key] = resolved
        candidates.extend(resolved)

    cooldown_states = await candidate_cooldown_state_map(candidates)
    snapshots = await load_provider_health_snapshots()

    model_status: dict[tuple[str, str], LLMModelRuntimeStatus] = {}
    for provider, model_id, enabled in models:
        key = (provider, model_id)
        model_status[key] = _status_from_cooldown(
            provider=provider,
            model_id=model_id,
            enabled=enabled,
            cooldown=_model_cooldown(model_candidates[key], cooldown_states),
        )

    providers: list[LLMProviderRuntimeStatus] = []
    for provider in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER:
        configured = provider_is_configured_for_free_pool(settings.llm, provider)
        provider_models = [
            model_status[(item_provider, item_model)]
            for item_provider, item_model, _enabled in models
            if item_provider == provider
        ]
        enabled_models = [
            model_status[(item_provider, item_model)]
            for item_provider, item_model, enabled in models
            if item_provider == provider and enabled
        ]
        blocked = [
            status
            for status in enabled_models
            if status.availability == LLMModelAvailability.COOLDOWN
        ]
        snapshot = snapshots.get(provider)
        if not configured:
            availability = LLMModelAvailability.NOT_CONFIGURED
            cooldown_seconds = None
            error_class = None
            error_text = None
            http_status = None
        elif blocked and len(blocked) == len(enabled_models):
            worst = _worst_model_cooldown(blocked)
            availability = LLMModelAvailability.COOLDOWN
            cooldown_seconds = worst.cooldown_seconds
            error_class = worst.error_class
            error_text = worst.error_text
            http_status = worst.http_status
        else:
            availability = LLMModelAvailability.AVAILABLE
            cooldown_seconds = None
            error_class = None
            error_text = None
            http_status = None
        providers.append(
            LLMProviderRuntimeStatus(
                provider=provider,
                configured=configured,
                availability=availability,
                model_count=len(provider_models),
                blocked_model_count=len(blocked),
                cooldown_seconds=cooldown_seconds,
                error_class=error_class,
                error_text=error_text,
                http_status=http_status,
                last_probe=snapshot,
            )
        )
    return model_status, providers


async def probe_platform_free_provider(
    provider: str,
    settings: BaseSettings,
) -> LLMProviderProbeSnapshot:
    probed_at = datetime.now(timezone.utc)
    if not provider_is_configured_for_free_pool(settings.llm, provider):
        raise ValueError(f"probe: provider {provider!r} is not configured for free-pool")
    smoke_model = provider_smoke_model(settings.llm, provider)
    candidates = llm_call_configs_for_provider_model(
        provider=provider,
        model_id=smoke_model,
        settings=settings,
    )
    if not candidates:
        raise ValueError(f"probe: no api_key for provider={provider!r}")
    candidate = candidates[0]
    resolved_provider, resolved_model, resolved_api_key = _require_resolved_candidate(candidate)
    if candidate.base_url is None:
        raise ValueError(f"probe: base_url is required for {provider}")
    pool = settings.llm.platform_free_pool
    client = LLMClient(
        model=resolved_model,
        api_key=resolved_api_key,
        base_url=candidate.base_url,
        llm_provider=resolved_provider,
        candidates=[candidate],
        timeout=PROBE_TIMEOUT_SECONDS,
        first_token_timeout=PROBE_TIMEOUT_SECONDS,
        candidate_cooldown_seconds=pool.candidate_cooldown_seconds,
        max_tokens=PROBE_SMOKE_MAX_TOKENS,
    )
    try:
        _ = await asyncio.wait_for(
            client.chat(
                [new_text_message("ping", role=Role.ROLE_USER)],
                max_tokens=PROBE_SMOKE_MAX_TOKENS,
            ),
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except AI_PROVIDER_IO_ERRORS as exc:
        record = classify_ai_provider_error(provider, exc, api_key=resolved_api_key)
        logger.warning(
            "llm.provider_probe_failed",
            provider=provider,
            smoke_model=smoke_model,
            error_class=record.error_class,
            http_status=record.http_status,
        )
        return LLMProviderProbeSnapshot(
            provider=provider,
            probed_at=probed_at,
            ok=False,
            error_class=record.error_class,
            error_text=record.error_text,
            http_status=record.http_status,
            smoke_model=smoke_model,
        )
    logger.info("llm.provider_probe_ok", provider=provider, smoke_model=smoke_model)
    return LLMProviderProbeSnapshot(
        provider=provider,
        probed_at=probed_at,
        ok=True,
        smoke_model=smoke_model,
    )


async def probe_platform_free_providers(*, settings: BaseSettings) -> list[LLMProviderProbeSnapshot]:
    configured = [
        provider
        for provider in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER
        if provider_is_configured_for_free_pool(settings.llm, provider)
    ]
    if not configured:
        await save_provider_health_snapshots(())
        return []
    snapshots = list(
        await asyncio.gather(
            *[probe_platform_free_provider(provider, settings) for provider in configured]
        )
    )
    await save_provider_health_snapshots(snapshots)
    return snapshots


__all__ = [
    "LLMModelAvailability",
    "LLMModelRuntimeStatus",
    "LLMProviderHealthDocument",
    "LLMProviderProbeSnapshot",
    "LLMProviderRuntimeStatus",
    "PROBE_SMOKE_MAX_TOKENS",
    "PROBE_TIMEOUT_SECONDS",
    "PROVIDER_HEALTH_REDIS_KEY",
    "collect_free_pool_runtime_status",
    "load_provider_health_snapshots",
    "probe_platform_free_provider",
    "probe_platform_free_providers",
    "save_provider_health_snapshots",
]
