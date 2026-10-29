"""Provider-neutral free LLM pool built from the shared AI model catalog."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from core.ai.adapters.model_catalog import create_model_catalog_adapter_registry
from core.ai.adapters.openrouter import OpenRouterModelCatalogAdapter
from core.ai.models import AIModelRecord, ArtificialAnalysisIndices, LLMModelScore
from core.ai.providers import (
    ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS,
    HUMANITEC_LLM_AUTO_MODEL,
    LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER,
    AICapability,
    humanitec_llms_model_ref,
)
from core.ai.scoring import (
    PlatformModelScoreOverlay,
    attach_artificial_analysis,
    compute_platform_model_score,
    platform_model_score_overlays,
)
from core.clients.redis_client import RedisClient
from core.config.base import BaseSettings
from core.config.llm_openai_compat import (
    provider_is_configured_for_free_pool as llm_provider_is_configured_for_free_pool,
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

_OPENROUTER_ROUTER_MODEL_ID = "openrouter/free"
_PROVIDER_ROUTER_MODEL_KEYS = frozenset({("openrouter", _OPENROUTER_ROUTER_MODEL_ID)})
_FREE_REASON_PRIORITY = {
    "verified_zero_price": 2,
    "account_free_tier": 1,
}


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


def _json_str(value: JsonValue | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _json_int(value: JsonValue | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _free_reason_priority(free_reason: str) -> int:
    if free_reason not in _FREE_REASON_PRIORITY:
        raise ValueError(f"unknown free_reason {free_reason!r}")
    return _FREE_REASON_PRIORITY[free_reason]


def _record_sort_key(record: PlatformFreeModelRecord) -> tuple[float, int, int, int, int, int, str, str]:
    return (
        record.score,
        record.context_length or 0,
        int("tools" in record.supported_parameters),
        int(
            "structured_outputs" in record.supported_parameters
            or "json_schema" in record.supported_parameters
        ),
        _free_reason_priority(record.free_reason),
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


def _catalog_record_map(
    catalog_records: Iterable[AIModelRecord],
) -> dict[tuple[str, str], AIModelRecord]:
    return {
        (record.provider, record.model_id): record
        for record in catalog_records
    }


def catalog_record_map(
    catalog_records: Iterable[AIModelRecord],
) -> dict[tuple[str, str], AIModelRecord]:
    return _catalog_record_map(catalog_records)


def provider_is_configured_for_free_pool(settings: BaseSettings, provider: str) -> bool:
    return llm_provider_is_configured_for_free_pool(settings.llm, provider)


def compute_platform_free_record_scores(
    records: Iterable[PlatformFreeModelRecord],
    *,
    catalog_records: Iterable[AIModelRecord],
    overlays: Mapping[tuple[str, str], PlatformModelScoreOverlay] | None,
) -> list[PlatformFreeModelRecord]:
    catalog_by_key = _catalog_record_map(catalog_records)
    overlay_map = overlays or {}
    scored: list[PlatformFreeModelRecord] = []
    for record in records:
        overlay = overlay_map.get((record.provider, record.id))
        if overlay is not None and not overlay.enabled:
            continue
        catalog_record = catalog_by_key.get((record.provider, record.id))
        if catalog_record is None:
            raise ValueError(
                f"free-pool record {record.provider}:{record.id} is missing from the catalog"
            )
        computed = compute_platform_model_score(
            catalog_record,
            AICapability.LLM_CHAT,
            overlay=overlay,
        )
        scored.append(replace(record, score=float(computed.score)))
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
    policy = LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER.get(provider)
    if policy is None:
        raise ValueError(f"provider {provider!r} has no free-model discovery policy")
    return policy


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
        score=0.0,
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
        if not provider_is_configured_for_free_pool(settings, record.provider):
            return None
        return "account_free_tier"
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


async def fetch_artificial_analysis_indices(
    settings: BaseSettings,
) -> dict[str, ArtificialAnalysisIndices]:
    registry = create_model_catalog_adapter_registry(settings)
    if not registry.has("openrouter"):
        raise ValueError('openrouter adapter is missing from the registry')
    adapter = registry.get("openrouter")
    if not adapter.is_configured():
        return {}
    if not isinstance(adapter, OpenRouterModelCatalogAdapter):
        raise TypeError("openrouter registry entry must be OpenRouterModelCatalogAdapter")
    return await adapter.list_artificial_analysis()


async def persist_catalog_artificial_analysis(
    records: Sequence[AIModelRecord],
) -> None:
    for record in records:
        if record.artificial_analysis is None:
            continue
        _ = await AIModelRecord.set(record)


async def fetch_platform_free_model_records(
    settings: BaseSettings,
    *,
    overlays: Mapping[tuple[str, str], PlatformModelScoreOverlay] | None = None,
    artificial_analysis: Mapping[str, ArtificialAnalysisIndices] | None = None,
    persist_artificial_analysis: bool = False,
) -> list[PlatformFreeModelRecord]:
    pool_config = settings.llm.platform_free_pool
    all_records: list[PlatformFreeModelRecord] = []
    for provider_slug in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER:
        if not provider_is_configured_for_free_pool(settings, provider_slug):
            logger.info("platform_free_models.provider_unconfigured", provider=provider_slug)
            continue
        catalog_records = await AIModelRecord.list_unordered_by_provider_and_capability(
            provider_slug,
            AICapability.LLM_CHAT,
        )
        if artificial_analysis:
            catalog_records = attach_artificial_analysis(catalog_records, artificial_analysis)
            if persist_artificial_analysis:
                await persist_catalog_artificial_analysis(catalog_records)
        provider_records = platform_free_records_from_model_records(
            catalog_records,
            settings=settings,
        )
        provider_records = compute_platform_free_record_scores(
            provider_records,
            catalog_records=catalog_records,
            overlays=overlays,
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
        max_candidates=0,
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
    if raw_cache_payload is None:
        return []
    cache_payload = parse_json_object(raw_cache_payload, "platform.free_models.cache")
    version = cache_payload.get("version")
    if version != PLATFORM_FREE_MODELS_CACHE_VERSION:
        raise ValueError(
            f"platform free-models cache version {version!r} != {PLATFORM_FREE_MODELS_CACHE_VERSION}"
        )
    models_raw = cache_payload.get("models")
    if not isinstance(models_raw, list):
        raise ValueError("platform free-models cache: models must be an array")

    records: list[PlatformFreeModelRecord] = []
    for idx, raw_item in enumerate(models_raw):
        item = require_json_object(raw_item, f"platform.free_models.cache.models[{idx}]")
        provider = _json_str(item.get("provider"))
        model_id = _json_str(item.get("id"))
        if provider is None or model_id is None:
            raise ValueError(
                f"platform.free_models.cache.models[{idx}] requires provider and id"
            )
        score_value = item.get("score")
        if isinstance(score_value, bool) or not isinstance(score_value, (int, float)):
            raise ValueError(f"platform.free_models.cache.models[{idx}].score must be numeric")
        free_reason = _json_str(item.get("free_reason"))
        if free_reason is None:
            raise ValueError(f"platform.free_models.cache.models[{idx}].free_reason is required")
        records.append(
            PlatformFreeModelRecord(
                provider=provider,
                id=model_id,
                score=float(score_value),
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
                free_reason=free_reason,
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


async def _write_platform_free_models_cache(
    redis_client: RedisClient,
    settings: BaseSettings,
    records: Sequence[PlatformFreeModelRecord],
) -> None:
    if not records:
        raise RuntimeError(
            'platform free-models: empty records — Redis cache is not overwritten'
        )
    redis_ok = await redis_client.set(
        PLATFORM_FREE_MODELS_CACHE_KEY,
        serialize_platform_free_models(records),
        ttl=settings.llm.platform_free_pool.cache_ttl_seconds,
    )
    if not redis_ok:
        raise RuntimeError('failed to write platform free-models cache to Redis')


def _cache_result_payload(
    records: Sequence[PlatformFreeModelRecord],
    *,
    overlay_count: int,
) -> JsonObject:
    return {
        "count": len(records),
        "providers": sorted({record.provider for record in records}),
        "free_policies": {
            provider: platform_free_model_policy_for_provider(provider)
            for provider in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER
        },
        "models": [f"{record.provider}:{record.id}" for record in records],
        "overlay_count": overlay_count,
        "redis_ok": True,
    }


async def refresh_platform_free_models_cache(
    redis_client: RedisClient,
    settings: BaseSettings,
) -> JsonObject:
    overlays = platform_model_score_overlays(
        await LLMModelScore.list_unordered_for_capability(AICapability.LLM_CHAT),
    )
    artificial_analysis = await fetch_artificial_analysis_indices(settings)
    records = await fetch_platform_free_model_records(
        settings,
        overlays=overlays,
        artificial_analysis=artificial_analysis,
        persist_artificial_analysis=True,
    )
    overlay_count = len(overlays)
    await _write_platform_free_models_cache(redis_client, settings, records)
    logger.info(
        "platform_free_models.cache_refreshed",
        count=len(records),
        providers=sorted({record.provider for record in records}),
        overlay_count=overlay_count,
        ttl_seconds=settings.llm.platform_free_pool.cache_ttl_seconds,
    )
    return _cache_result_payload(records, overlay_count=overlay_count)


async def rescore_cached_platform_free_models(
    redis_client: RedisClient,
    settings: BaseSettings,
    *,
    overlays: Mapping[tuple[str, str], PlatformModelScoreOverlay] | None = None,
) -> JsonObject:
    resolved_overlays = (
        overlays
        if overlays is not None
        else platform_model_score_overlays(
            await LLMModelScore.list_unordered_for_capability(AICapability.LLM_CHAT),
        )
    )
    records = await fetch_platform_free_model_records(
        settings,
        overlays=resolved_overlays,
    )
    await _write_platform_free_models_cache(redis_client, settings, records)
    logger.info(
        "platform_free_models.cache_rescored",
        count=len(records),
        providers=sorted({record.provider for record in records}),
        overlay_count=len(resolved_overlays),
    )
    return _cache_result_payload(records, overlay_count=len(resolved_overlays))


__all__ = [
    "PLATFORM_FREE_MODEL_SOURCE",
    "PLATFORM_FREE_MODELS_CACHE_KEY",
    "PLATFORM_PAID_FALLBACK_SOURCE",
    "PlatformFreeModelRecord",
    "catalog_record_map",
    "compute_platform_free_record_scores",
    "fetch_artificial_analysis_indices",
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
