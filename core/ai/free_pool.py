"""Provider-neutral free LLM pool built from the shared AI model catalog."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol

from core.ai.model_catalog_repository import AIModelCatalogRepository
from core.ai.models import AIModelRecord
from core.ai.providers import (
    ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS,
    HUMANITEC_LLM_AUTO_MODEL,
    LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER,
    AICapability,
    humanitec_llms_model_ref,
)
from core.clients.redis_client import RedisClient
from core.config.base import BaseSettings
from core.config.models import (
    GitHubModelsProviderConfig,
    GoogleLLMProviderConfig,
    GroqProviderConfig,
    HuggingFaceProviderConfig,
)
from core.logging import get_logger
from core.types import (
    JsonArray,
    JsonObject,
    JsonValue,
    parse_json_object,
    require_json_array,
    require_json_object,
)

logger = get_logger(__name__)

PLATFORM_FREE_MODELS_CACHE_KEY = "llm:platform:free_models:v1"
PLATFORM_FREE_MODELS_CACHE_VERSION = 1
PLATFORM_FREE_MODEL_SOURCE = "platform_free"
PLATFORM_PAID_FALLBACK_SOURCE = "platform_paid_fallback"

_SIZE_RE = re.compile(r"(?<![a-z0-9])(\d+(?:\.\d+)?)\s*([bm])\b", re.IGNORECASE)
_OPENROUTER_ROUTER_MODEL_ID = "openrouter/free"
_PROVIDER_ROUTER_MODEL_KEYS = frozenset({("openrouter", _OPENROUTER_ROUTER_MODEL_ID)})
_FREE_REASON_PRIORITY = {
    "verified_zero_price": 2,
    "account_free_tier": 1,
}

_AccountFreeTierProviderConfig = (
    GroqProviderConfig
    | GoogleLLMProviderConfig
    | GitHubModelsProviderConfig
    | HuggingFaceProviderConfig
)


@dataclass(frozen=True)
class PlatformFreeModelRecord:
    provider: str
    id: str
    score: float
    context_length: int | None
    supported_parameters: tuple[str, ...]
    input_modalities: tuple[str, ...]
    output_modalities: tuple[str, ...]
    created: int | None = None
    max_tokens: int | None = None
    free_reason: str = "verified_zero_price"


class PlatformModelScoreProvider(Protocol):
    async def list_enabled_score_map(
        self,
        capability: AICapability,
    ) -> Mapping[tuple[str, str], float]: ...


def _json_str(value: JsonValue | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _json_int(value: JsonValue | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _model_size_score(*texts: str) -> float:
    """Returns size in billions when a slug/name contains 80B, 120b, 1.2B, etc."""
    best_size_billions = 0.0
    for text in texts:
        for match in _SIZE_RE.finditer(text or ""):
            value = float(match.group(1))
            unit = match.group(2).lower()
            billions = value if unit == "b" else value / 1000.0
            best_size_billions = max(best_size_billions, billions)
    return best_size_billions


def _account_free_tier_provider_config(
    settings: BaseSettings,
    provider_slug: str,
) -> _AccountFreeTierProviderConfig | None:
    if provider_slug == "groq":
        return settings.llm.groq
    if provider_slug == "google":
        return settings.llm.google
    if provider_slug == "github":
        return settings.llm.github
    if provider_slug == "huggingface":
        return settings.llm.huggingface
    return None


def _record_sort_key(record: PlatformFreeModelRecord) -> tuple[float, int, int, int, int, int, str, str]:
    return (
        record.score,
        record.context_length or 0,
        int("tools" in record.supported_parameters),
        int(
            "response_format" in record.supported_parameters
            or "structured_outputs" in record.supported_parameters
        ),
        _FREE_REASON_PRIORITY.get(record.free_reason, 0),
        record.created or 0,
        record.provider,
        record.id,
    )


def sort_platform_free_records(
    records: Iterable[PlatformFreeModelRecord],
    *,
    max_candidates: int,
) -> list[PlatformFreeModelRecord]:
    sorted_records = sorted(records, key=_record_sort_key, reverse=True)
    if max_candidates > 0:
        return sorted_records[:max_candidates]
    return sorted_records


def apply_platform_model_score_overrides(
    records: Iterable[PlatformFreeModelRecord],
    score_overrides: Mapping[tuple[str, str], float] | None,
) -> list[PlatformFreeModelRecord]:
    if not score_overrides:
        return list(records)
    scored: list[PlatformFreeModelRecord] = []
    for record in records:
        override = score_overrides.get((record.provider, record.id))
        if override is None:
            scored.append(record)
            continue
        scored.append(replace(record, score=float(override)))
    return scored


def _sort_provider_records(
    records: Iterable[PlatformFreeModelRecord],
    *,
    max_candidates: int,
    include_provider_router_as_last: bool,
) -> list[PlatformFreeModelRecord]:
    records_list = list(records)
    if not include_provider_router_as_last:
        return sort_platform_free_records(records_list, max_candidates=max_candidates)

    pinned_last = [
        record
        for record in records_list
        if (record.provider, record.id) in _PROVIDER_ROUTER_MODEL_KEYS
    ]
    normal_records = [
        record
        for record in records_list
        if (record.provider, record.id) not in _PROVIDER_ROUTER_MODEL_KEYS
    ]
    sorted_records = sort_platform_free_records(
        normal_records,
        max_candidates=max_candidates,
    )
    for record in pinned_last:
        if all(record.provider != existing.provider or record.id != existing.id for existing in sorted_records):
            sorted_records.append(record)
    return sorted_records


def platform_free_model_policy_for_provider(provider: str) -> str:
    return LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER.get(
        provider,
        "unknown_provider",
    )


def _provider_is_configured_for_free_pool(settings: BaseSettings, provider: str) -> bool:
    if provider == "openrouter":
        cfg = settings.llm.openrouter
        return cfg is not None and bool(cfg.api_key)
    if provider == "bothub":
        cfg = settings.llm.bothub
        return cfg is not None and bool(cfg.api_key)
    if provider in ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS:
        cfg = _account_free_tier_provider_config(settings, provider)
        return (
            cfg is not None
            and isinstance(cfg.api_key, str)
            and bool(cfg.api_key.strip())
            and bool(cfg.smoke_model.strip())
        )
    return False


def _configured_account_free_tier_model(settings: BaseSettings, provider: str) -> str | None:
    cfg = _account_free_tier_provider_config(settings, provider)
    if cfg is None:
        return None
    model = cfg.smoke_model.strip()
    return model or None


def _text_chat_record(record: AIModelRecord) -> bool:
    if AICapability.LLM_CHAT not in record.capabilities:
        return False
    input_modalities = {value.lower() for value in record.input_modalities}
    output_modalities = {value.lower() for value in record.output_modalities}
    if input_modalities and "text" not in input_modalities:
        return False
    if output_modalities and "text" not in output_modalities:
        return False
    return True


def _raw_name(record: AIModelRecord) -> str:
    for key in ("name", "label", "display_name"):
        value = record.raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _record_max_tokens(record: AIModelRecord) -> int | None:
    raw_top_provider = record.raw.get("top_provider")
    if isinstance(raw_top_provider, dict):
        top_provider = raw_top_provider
        value = _json_int(top_provider.get("max_completion_tokens"))
        if value is not None:
            return value
    for key in ("maxTokens", "max_tokens", "max_completion_tokens", "outputTokenLimit"):
        value = _json_int(record.raw.get(key))
        if value is not None:
            return value
    return None


def platform_free_record_from_model_record(
    record: AIModelRecord,
    *,
    free_reason: str,
) -> PlatformFreeModelRecord:
    return PlatformFreeModelRecord(
        provider=record.provider,
        id=record.model_id,
        score=_model_size_score(record.model_id, _raw_name(record)),
        context_length=record.context_length,
        max_tokens=_record_max_tokens(record),
        supported_parameters=tuple(sorted(record.supported_parameters)),
        input_modalities=tuple(sorted(record.input_modalities)),
        output_modalities=tuple(sorted(record.output_modalities)),
        created=record.created,
        free_reason=free_reason,
    )


def _free_reason_for_catalog_record(
    record: AIModelRecord,
    *,
    settings: BaseSettings,
) -> str | None:
    if not _text_chat_record(record):
        return None
    if record.provider in ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS:
        configured_model = _configured_account_free_tier_model(settings, record.provider)
        if configured_model is not None and record.model_id == configured_model:
            return "account_free_tier"
        return None
    if record.is_free is True:
        if record.free_reason in (None, "zero_price_catalog"):
            return "verified_zero_price"
        return record.free_reason
    return None


def platform_free_records_from_model_records(
    records: Iterable[AIModelRecord],
    *,
    settings: BaseSettings,
) -> list[PlatformFreeModelRecord]:
    free_records: list[PlatformFreeModelRecord] = []
    for record in records:
        free_reason = _free_reason_for_catalog_record(record, settings=settings)
        if free_reason is None:
            continue
        free_records.append(
            platform_free_record_from_model_record(record, free_reason=free_reason)
        )
    return free_records


async def fetch_platform_free_model_records(
    settings: BaseSettings,
    model_catalog_repository: AIModelCatalogRepository,
    *,
    score_overrides: Mapping[tuple[str, str], float] | None = None,
) -> list[PlatformFreeModelRecord]:
    pool_config = settings.llm.platform_free_pool
    all_records: list[PlatformFreeModelRecord] = []
    for provider_slug in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER:
        if not _provider_is_configured_for_free_pool(settings, provider_slug):
            logger.info("platform_free_models.provider_unconfigured", provider=provider_slug)
            continue
        catalog_records = await model_catalog_repository.list_by_provider_capability(
            provider_slug,
            AICapability.LLM_CHAT,
        )
        provider_records = platform_free_records_from_model_records(
            catalog_records,
            settings=settings,
        )
        provider_records = apply_platform_model_score_overrides(
            provider_records,
            score_overrides,
        )
        provider_records = _sort_provider_records(
            provider_records,
            max_candidates=pool_config.max_candidates_per_provider,
            include_provider_router_as_last=pool_config.include_provider_router_as_last_free_fallback,
        )
        logger.info(
            "platform_free_models.provider_discovered",
            provider=provider_slug,
            count=len(provider_records),
        )
        all_records.extend(provider_records)
    return sort_platform_free_records(
        all_records,
        max_candidates=pool_config.max_candidates_total,
    )


def serialize_platform_free_models(records: Sequence[PlatformFreeModelRecord]) -> str:
    models: JsonArray = [
        {
            "provider": record.provider,
            "id": record.id,
            "score": record.score,
            "context_length": record.context_length,
            "max_tokens": record.max_tokens,
            "supported_parameters": list(record.supported_parameters),
            "input_modalities": list(record.input_modalities),
            "output_modalities": list(record.output_modalities),
            "created": record.created,
            "free_reason": record.free_reason,
        }
        for record in records
    ]
    return json.dumps(
        {
            "version": PLATFORM_FREE_MODELS_CACHE_VERSION,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "providers": sorted({record.provider for record in records}),
            "models": models,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def parse_platform_free_models(raw_cache_payload: str | None) -> list[PlatformFreeModelRecord]:
    if not raw_cache_payload:
        return []
    try:
        cache_payload = parse_json_object(raw_cache_payload, "platform.free_models.cache")
    except ValueError:
        logger.warning("platform_free_models.cache_invalid_json")
        return []
    if cache_payload.get("version") != PLATFORM_FREE_MODELS_CACHE_VERSION:
        return []
    models_raw = cache_payload.get("models")
    if not isinstance(models_raw, list):
        return []

    records: list[PlatformFreeModelRecord] = []
    for raw_item in models_raw:
        if not isinstance(raw_item, dict):
            continue
        item = require_json_object(raw_item, "platform.free_models.cache.models[]")
        provider = _json_str(item.get("provider"))
        model_id = _json_str(item.get("id"))
        if provider is None or model_id is None:
            continue
        score_value = item.get("score")
        records.append(
            PlatformFreeModelRecord(
                provider=provider,
                id=model_id,
                score=(
                    float(score_value)
                    if isinstance(score_value, (int, float)) and not isinstance(score_value, bool)
                    else 0.0
                ),
                context_length=_json_int(item.get("context_length")),
                max_tokens=_json_int(item.get("max_tokens")),
                supported_parameters=tuple(
                    str(parameter)
                    for parameter in require_json_array(
                        item.get("supported_parameters", []),
                        "platform.free_models.supported_parameters",
                    )
                ),
                input_modalities=tuple(
                    str(modality)
                    for modality in require_json_array(
                        item.get("input_modalities", []),
                        "platform.free_models.input_modalities",
                    )
                ),
                output_modalities=tuple(
                    str(modality)
                    for modality in require_json_array(
                        item.get("output_modalities", []),
                        "platform.free_models.output_modalities",
                    )
                ),
                created=_json_int(item.get("created")),
                free_reason=_json_str(item.get("free_reason")) or "verified_zero_price",
            )
        )
    return records


async def read_platform_free_model_records(
    redis_client: RedisClient,
) -> list[PlatformFreeModelRecord]:
    raw_cache_payload = await redis_client.get(PLATFORM_FREE_MODELS_CACHE_KEY)
    return parse_platform_free_models(raw_cache_payload)


def humanitec_llms_model_options_from_records(
    records: Iterable[PlatformFreeModelRecord],
) -> list[JsonObject]:
    items: list[JsonObject] = [
        {
            "value": HUMANITEC_LLM_AUTO_MODEL,
            "label": HUMANITEC_LLM_AUTO_MODEL,
            "kind": "auto",
        }
    ]
    seen: set[str] = {HUMANITEC_LLM_AUTO_MODEL}
    for record in sort_platform_free_records(list(records), max_candidates=0):
        value = humanitec_llms_model_ref(record.provider, record.id)
        if value in seen:
            continue
        seen.add(value)
        items.append(
            {
                "value": value,
                "label": f"{record.provider} / {record.id}",
                "kind": "free_model",
                "provider": record.provider,
                "model_id": record.id,
                "score": record.score,
                "context_length": record.context_length,
                "max_tokens": record.max_tokens,
                "supported_parameters": list(record.supported_parameters),
                "input_modalities": list(record.input_modalities),
                "output_modalities": list(record.output_modalities),
                "free_reason": record.free_reason,
            }
        )
    return items


async def read_humanitec_llms_model_options(
    redis_client: RedisClient,
) -> list[JsonObject]:
    return humanitec_llms_model_options_from_records(
        await read_platform_free_model_records(redis_client)
    )


async def refresh_platform_free_models_cache(
    redis_client: RedisClient,
    settings: BaseSettings,
    model_catalog_repository: AIModelCatalogRepository,
    *,
    model_score_provider: PlatformModelScoreProvider | None = None,
) -> JsonObject:
    score_overrides = (
        await model_score_provider.list_enabled_score_map(AICapability.LLM_CHAT)
        if model_score_provider is not None
        else None
    )
    records = await fetch_platform_free_model_records(
        settings,
        model_catalog_repository,
        score_overrides=score_overrides,
    )
    payload = serialize_platform_free_models(records)
    redis_ok = await redis_client.set(
        PLATFORM_FREE_MODELS_CACHE_KEY,
        payload,
        ttl=settings.llm.platform_free_pool.cache_ttl_seconds,
    )
    logger.info(
        "platform_free_models.cache_refreshed",
        count=len(records),
        providers=sorted({record.provider for record in records}),
        free_policies={
            provider: platform_free_model_policy_for_provider(provider)
            for provider in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER
        },
        score_overrides_count=len(score_overrides or {}),
        redis_ok=redis_ok,
        ttl_seconds=settings.llm.platform_free_pool.cache_ttl_seconds,
    )
    return {
        "count": len(records),
        "providers": sorted({record.provider for record in records}),
        "free_policies": {
            provider: platform_free_model_policy_for_provider(provider)
            for provider in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER
        },
        "models": [f"{record.provider}:{record.id}" for record in records],
        "score_overrides_count": len(score_overrides or {}),
        "redis_ok": bool(redis_ok),
    }


async def rescore_cached_platform_free_models(
    redis_client: RedisClient,
    settings: BaseSettings,
    *,
    model_score_provider: PlatformModelScoreProvider,
) -> JsonObject:
    raw_cache_payload = await redis_client.get(PLATFORM_FREE_MODELS_CACHE_KEY)
    records = parse_platform_free_models(raw_cache_payload)
    if not records:
        return {
            "cache_present": False,
            "count": 0,
            "providers": [],
            "score_overrides_count": 0,
            "redis_ok": True,
        }

    score_overrides = await model_score_provider.list_enabled_score_map(AICapability.LLM_CHAT)
    records = sort_platform_free_records(
        apply_platform_model_score_overrides(records, score_overrides),
        max_candidates=settings.llm.platform_free_pool.max_candidates_total,
    )
    redis_ok = await redis_client.set(
        PLATFORM_FREE_MODELS_CACHE_KEY,
        serialize_platform_free_models(records),
        ttl=settings.llm.platform_free_pool.cache_ttl_seconds,
    )
    logger.info(
        "platform_free_models.cache_rescored",
        count=len(records),
        providers=sorted({record.provider for record in records}),
        score_overrides_count=len(score_overrides),
        redis_ok=redis_ok,
    )
    return {
        "cache_present": True,
        "count": len(records),
        "providers": sorted({record.provider for record in records}),
        "score_overrides_count": len(score_overrides),
        "redis_ok": bool(redis_ok),
    }


__all__ = [
    "PLATFORM_FREE_MODEL_SOURCE",
    "PLATFORM_FREE_MODELS_CACHE_KEY",
    "PLATFORM_PAID_FALLBACK_SOURCE",
    "PlatformFreeModelRecord",
    "apply_platform_model_score_overrides",
    "fetch_platform_free_model_records",
    "parse_platform_free_models",
    "platform_free_model_policy_for_provider",
    "platform_free_record_from_model_record",
    "platform_free_records_from_model_records",
    "humanitec_llms_model_options_from_records",
    "read_humanitec_llms_model_options",
    "read_platform_free_model_records",
    "rescore_cached_platform_free_models",
    "refresh_platform_free_models_cache",
    "serialize_platform_free_models",
    "sort_platform_free_records",
]
