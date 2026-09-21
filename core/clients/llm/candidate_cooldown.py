"""Redis cooldown for LLM candidates after a failure before the first token."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import cast

import httpx

from core.ai.llm_config import LLMCallConfig
from core.ai.provider_error import (
    RATE_LIMIT_HTTP_STATUS,
    AIProviderErrorRecord,
    classify_ai_provider_error,
)
from core.clients.llm.candidates import candidate_key
from core.clients.redis_client import RedisClient, RedisOperationError
from core.config import get_settings

_COOLDOWN_KEY_PREFIX = "llm:candidate_cooldown:"

_cooldown_redis: RedisClient | None = None


@dataclass(frozen=True)
class CandidateCooldownState:
    ttl_seconds: int
    record: AIProviderErrorRecord


def cooldown_redis_key(candidate: LLMCallConfig) -> str:
    return f"{_COOLDOWN_KEY_PREFIX}{candidate_key(candidate)}"


def _redis() -> RedisClient:
    global _cooldown_redis
    if _cooldown_redis is None:
        _cooldown_redis = RedisClient(get_settings().database.redis_url)
    return _cooldown_redis


def retry_after_ttl_seconds(response: httpx.Response) -> int | None:
    raw = cast(str | None, response.headers.get("retry-after"))
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        raise ValueError("Retry-After header is empty")
    if stripped.isdigit():
        return max(1, int(stripped))
    parsed = parsedate_to_datetime(stripped)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    remaining = (parsed - datetime.now(timezone.utc)).total_seconds()
    return max(1, int(math.ceil(remaining)))


def cooldown_ttl_from_error(error: BaseException | None, default_seconds: float) -> int | None:
    if isinstance(error, httpx.HTTPStatusError) and error.response.status_code == RATE_LIMIT_HTTP_STATUS:
        retry_after = retry_after_ttl_seconds(error.response)
        if retry_after is not None:
            return retry_after
    if default_seconds <= 0:
        return None
    return max(1, int(math.ceil(default_seconds)))


def parse_candidate_cooldown_payload(raw: str) -> AIProviderErrorRecord:
    return AIProviderErrorRecord.model_validate_json(raw)


def cooldown_ttl_is_active(ttl_seconds: int) -> bool:
    return ttl_seconds > 0 or ttl_seconds == -1


async def candidate_cooldown_ttl_map(candidates: Sequence[LLMCallConfig]) -> dict[str, int]:
    if not candidates:
        return {}
    redis = _redis()
    keys = [cooldown_redis_key(candidate) for candidate in candidates]
    ttls = await redis.ttl_batch(keys)
    return {
        candidate_key(candidate): ttl
        for candidate, ttl in zip(candidates, ttls, strict=True)
    }


async def candidate_cooldown_state_map(
    candidates: Sequence[LLMCallConfig],
) -> dict[str, CandidateCooldownState]:
    if not candidates:
        return {}
    redis = _redis()
    keys = [cooldown_redis_key(candidate) for candidate in candidates]
    ttls = await redis.ttl_batch(keys)
    values = await redis.get_batch(keys)
    states: dict[str, CandidateCooldownState] = {}
    for candidate, ttl_seconds, raw in zip(candidates, ttls, values, strict=True):
        if not cooldown_ttl_is_active(ttl_seconds):
            continue
        if raw is None:
            continue
        states[candidate_key(candidate)] = CandidateCooldownState(
            ttl_seconds=ttl_seconds,
            record=parse_candidate_cooldown_payload(raw),
        )
    return states


async def set_candidate_cooldown(
    candidate: LLMCallConfig,
    ttl_seconds: int,
    *,
    error: BaseException | None = None,
) -> None:
    if ttl_seconds <= 0:
        raise ValueError("candidate cooldown ttl must be a positive number of seconds")
    provider = candidate.provider
    if provider is None or not provider.strip():
        raise ValueError("candidate cooldown: provider is required")
    record = classify_ai_provider_error(provider, error, api_key=candidate.api_key)
    redis = _redis()
    key = cooldown_redis_key(candidate)
    wrote = await redis.set(key, record.model_dump_json(), ttl=ttl_seconds)
    if not wrote:
        raise RedisOperationError(f"failed to write LLM candidate cooldown {key}")


__all__ = [
    "AIProviderErrorRecord",
    "CandidateCooldownState",
    "candidate_cooldown_state_map",
    "candidate_cooldown_ttl_map",
    "cooldown_redis_key",
    "cooldown_ttl_from_error",
    "cooldown_ttl_is_active",
    "parse_candidate_cooldown_payload",
    "retry_after_ttl_seconds",
    "set_candidate_cooldown",
]
