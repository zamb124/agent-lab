"""Provider-neutral discovery and cache for verified free LLM models."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol

from core.clients.redis_client import RedisClient
from core.config.base import BaseSettings
from core.config.models import (
    GitHubModelsProviderConfig,
    GoogleLLMProviderConfig,
    GroqProviderConfig,
    HuggingFaceProviderConfig,
)
from core.http.client import ProxyStrategy, request_with_strategy
from core.llm_model_routing import (
    ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS,
    HUMANITEC_LLM_AUTO_MODEL,
    LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER,
    humanitec_llms_model_ref,
)
from core.logging import get_logger
from core.types import (
    JsonArray,
    JsonObject,
    JsonValue,
    parse_json_object,
    parse_json_value,
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
_BOTHUB_MODELS_URL = "https://bothub.chat/api/v2/model/list?children=1"
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


class PlatformFreeModelAdapter(Protocol):
    provider_slug: str

    def is_configured(self, settings: BaseSettings) -> bool: ...

    async def fetch_model_items(self, settings: BaseSettings) -> list[JsonObject]: ...

    def records_from_items(
        self,
        items: Iterable[JsonObject],
        *,
        max_candidates: int,
        include_provider_router_as_last: bool,
    ) -> list[PlatformFreeModelRecord]: ...


class PlatformModelScoreProvider(Protocol):
    async def list_enabled_score_map(self) -> Mapping[tuple[str, str], float]: ...


def _float_zero(value: JsonValue | None) -> bool:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return False
    try:
        return float(value) == 0
    except (TypeError, ValueError):
        return False


def _float_zero_or_missing(value: JsonValue | None) -> bool:
    if value is None:
        return True
    return _float_zero(value)


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


def _sorted_str_tuple(values: JsonValue | None, field_name: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(value)
            for value in require_json_array(values or [], field_name)
            if isinstance(value, str) and value.strip()
        )
    )


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


def is_openrouter_verified_free_text_model(item: JsonObject) -> bool:
    pricing = require_json_object(item.get("pricing", {}), "openrouter.model.pricing")
    architecture = require_json_object(
        item.get("architecture", {}),
        "openrouter.model.architecture",
    )
    input_modalities = {
        modality
        for modality in require_json_array(
            architecture.get("input_modalities", []),
            "openrouter.model.architecture.input_modalities",
        )
        if isinstance(modality, str)
    }
    output_modalities = {
        modality
        for modality in require_json_array(
            architecture.get("output_modalities", []),
            "openrouter.model.architecture.output_modalities",
        )
        if isinstance(modality, str)
    }
    if "text" not in input_modalities or "text" not in output_modalities:
        return False
    if item.get("expiration_date") is not None:
        return False
    return (
        _float_zero(pricing.get("prompt"))
        and _float_zero(pricing.get("completion"))
        and _float_zero_or_missing(pricing.get("request"))
    )


def is_bothub_free_text_model(item: JsonObject) -> bool:
    features = {
        feature
        for feature in require_json_array(item.get("features", []), "bothub.model.features")
        if isinstance(feature, str)
    }
    if "TEXT_TO_TEXT" not in features:
        return False
    if item.get("disabled") is True or item.get("disabledApi") is True:
        return False
    if item.get("deletedAt") is not None:
        return False
    # Public responses expose plan-gated models with isAllowed=false. Authenticated
    # platform keys can still include those when the account is eligible.
    if item.get("allowedPlanType") is not None and item.get("isAllowed") is not True:
        return False
    pricing = require_json_object(item.get("pricing", {}), "bothub.model.pricing")
    return (
        _float_zero(pricing.get("input"))
        and _float_zero(pricing.get("output"))
        and _float_zero_or_missing(pricing.get("request"))
    )


class OpenRouterPlatformFreeModelAdapter:
    provider_slug: str = "openrouter"

    def is_configured(self, settings: BaseSettings) -> bool:
        cfg = settings.llm.openrouter
        return cfg is not None and bool(cfg.api_key)

    async def fetch_model_items(self, settings: BaseSettings) -> list[JsonObject]:
        openrouter_config = settings.llm.openrouter
        if openrouter_config is None or not openrouter_config.api_key:
            logger.warning("platform_free_models.openrouter.no_api_key")
            return []
        url = f"{openrouter_config.base_url.rstrip('/')}/models?output_modalities=text"
        http_response = await request_with_strategy(
            "GET",
            url,
            headers={
                "Authorization": f"Bearer {openrouter_config.api_key}",
                "HTTP-Referer": openrouter_config.site_url,
                "X-Title": openrouter_config.site_name,
            },
            timeout=30.0,
            strategy=ProxyStrategy.DIRECT_FIRST,
            direct_attempts=3,
            proxy_attempts=3,
        )
        _ = http_response.raise_for_status()
        response_payload = parse_json_object(http_response.content, "openrouter.models.response")
        model_items = require_json_array(response_payload.get("data", []), "openrouter.models.data")
        return [
            require_json_object(item, "openrouter.models.data[]")
            for item in model_items
            if isinstance(item, dict)
        ]

    def records_from_items(
        self,
        items: Iterable[JsonObject],
        *,
        max_candidates: int,
        include_provider_router_as_last: bool,
    ) -> list[PlatformFreeModelRecord]:
        records: list[PlatformFreeModelRecord] = []
        router: PlatformFreeModelRecord | None = None
        for item in items:
            model_id = _json_str(item.get("id"))
            if model_id is None or not is_openrouter_verified_free_text_model(item):
                continue
            architecture = require_json_object(
                item.get("architecture", {}),
                "openrouter.model.architecture",
            )
            raw_top_provider = item.get("top_provider")
            top_provider = (
                require_json_object(raw_top_provider, "openrouter.model.top_provider")
                if isinstance(raw_top_provider, dict)
                else {}
            )
            context_length = _json_int(item.get("context_length"))
            max_tokens = _json_int(top_provider.get("max_completion_tokens"))
            record = PlatformFreeModelRecord(
                provider=self.provider_slug,
                id=model_id,
                score=_model_size_score(model_id, str(item.get("name") or "")),
                context_length=context_length,
                max_tokens=max_tokens,
                supported_parameters=_sorted_str_tuple(
                    item.get("supported_parameters", []),
                    "openrouter.model.supported_parameters",
                ),
                input_modalities=_sorted_str_tuple(
                    architecture.get("input_modalities", []),
                    "openrouter.model.architecture.input_modalities",
                ),
                output_modalities=_sorted_str_tuple(
                    architecture.get("output_modalities", []),
                    "openrouter.model.architecture.output_modalities",
                ),
                created=_json_int(item.get("created")),
            )
            if model_id == _OPENROUTER_ROUTER_MODEL_ID:
                router = record
                continue
            records.append(record)

        records = sort_platform_free_records(records, max_candidates=max_candidates)
        if (
            include_provider_router_as_last
            and router is not None
            and all(record.id != router.id or record.provider != router.provider for record in records)
        ):
            records.append(router)
        return records


class BotHubFreeModelAdapter:
    provider_slug: str = "bothub"

    def is_configured(self, settings: BaseSettings) -> bool:
        cfg = settings.llm.bothub
        return cfg is not None and bool(cfg.api_key)

    async def fetch_model_items(self, settings: BaseSettings) -> list[JsonObject]:
        cfg = settings.llm.bothub
        if cfg is None or not cfg.api_key:
            logger.warning("platform_free_models.bothub.no_api_key")
            return []
        url = cfg.models_url or _BOTHUB_MODELS_URL
        response = await request_with_strategy(
            "GET",
            str(url),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg.api_key}",
            },
            timeout=30.0,
            strategy=ProxyStrategy.DIRECT_FIRST,
            direct_attempts=3,
            proxy_attempts=3,
        )
        _ = response.raise_for_status()
        payload = parse_json_value(response.content, "bothub.models.response")
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            payload_obj = require_json_object(payload, "bothub.models.response")
            items = require_json_array(payload_obj.get("data", []), "bothub.models.data")
        else:
            raise ValueError("bothub.models.response must be an object or array")
        return [
            require_json_object(item, "bothub.models.data[]")
            for item in items
            if isinstance(item, dict)
        ]

    def records_from_items(
        self,
        items: Iterable[JsonObject],
        *,
        max_candidates: int,
        include_provider_router_as_last: bool,
    ) -> list[PlatformFreeModelRecord]:
        del include_provider_router_as_last
        records: list[PlatformFreeModelRecord] = []
        for item in items:
            model_id = _json_str(item.get("id")) or _json_str(item.get("name"))
            if model_id is None or not is_bothub_free_text_model(item):
                continue
            features = {
                feature
                for feature in require_json_array(item.get("features", []), "bothub.model.features")
                if isinstance(feature, str)
            }
            supported_parameters: set[str] = set()
            if "TOOLS" in features:
                supported_parameters.update(("tools", "tool_choice"))
            if "EFFORT" in features:
                supported_parameters.add("reasoning")

            input_modalities = {"text"}
            if "IMAGE_TO_TEXT" in features:
                input_modalities.add("image")
            if "DOCUMENT_TO_TEXT" in features or "NATIVE_DOCUMENT_TO_TEXT" in features:
                input_modalities.add("file")

            records.append(
                PlatformFreeModelRecord(
                    provider=self.provider_slug,
                    id=model_id,
                    score=_model_size_score(model_id, str(item.get("label") or "")),
                    context_length=_json_int(item.get("contextLength")),
                    max_tokens=_json_int(item.get("maxTokens")),
                    supported_parameters=tuple(sorted(supported_parameters)),
                    input_modalities=tuple(sorted(input_modalities)),
                    output_modalities=("text",),
                    created=None,
                )
            )
        return sort_platform_free_records(records, max_candidates=max_candidates)


class ConfiguredAccountFreeTierModelAdapter:
    """Account-level free-tier candidate from an explicit provider smoke model.

    These providers do not expose a model-level zero price in catalog responses.
    We therefore publish only the configured smoke model as text-only and do not
    claim tools, structured output or vision support.
    """

    def __init__(self, provider_slug: str) -> None:
        self.provider_slug: str = provider_slug

    def is_configured(self, settings: BaseSettings) -> bool:
        cfg = _account_free_tier_provider_config(settings, self.provider_slug)
        if cfg is None:
            return False
        api_key = cfg.api_key
        smoke_model = cfg.smoke_model
        return (
            isinstance(api_key, str)
            and bool(api_key.strip())
            and bool(smoke_model.strip())
        )

    async def fetch_model_items(self, settings: BaseSettings) -> list[JsonObject]:
        cfg = _account_free_tier_provider_config(settings, self.provider_slug)
        if not self.is_configured(settings):
            logger.info(
                "platform_free_models.account_free_tier_unconfigured",
                provider=self.provider_slug,
            )
            return []
        if cfg is None:
            raise ValueError(f"{self.provider_slug} provider config не настроен")
        model_id = cfg.smoke_model.strip()
        return [{"id": model_id, "name": model_id}]

    def records_from_items(
        self,
        items: Iterable[JsonObject],
        *,
        max_candidates: int,
        include_provider_router_as_last: bool,
    ) -> list[PlatformFreeModelRecord]:
        del include_provider_router_as_last
        records: list[PlatformFreeModelRecord] = []
        seen: set[str] = set()
        for item in items:
            model_id = _json_str(item.get("id")) or _json_str(item.get("name"))
            if model_id is None or model_id in seen:
                continue
            seen.add(model_id)
            records.append(
                PlatformFreeModelRecord(
                    provider=self.provider_slug,
                    id=model_id,
                    score=_model_size_score(model_id, str(item.get("name") or "")),
                    context_length=None,
                    max_tokens=None,
                    supported_parameters=(),
                    input_modalities=("text",),
                    output_modalities=("text",),
                    created=None,
                    free_reason="account_free_tier",
                )
            )
        return sort_platform_free_records(records, max_candidates=max_candidates)


_ADAPTERS_BY_PROVIDER: dict[str, PlatformFreeModelAdapter] = {
    "openrouter": OpenRouterPlatformFreeModelAdapter(),
    "bothub": BotHubFreeModelAdapter(),
    **{
        provider: ConfiguredAccountFreeTierModelAdapter(provider)
        for provider in ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS
    },
}


def platform_free_model_policy_for_provider(provider: str) -> str:
    return LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER.get(
        provider,
        "unknown_provider",
    )


def platform_free_model_adapters_for_settings(
    settings: BaseSettings,
) -> list[PlatformFreeModelAdapter]:
    adapters: list[PlatformFreeModelAdapter] = []
    for provider_slug in settings.llm.platform_free_pool.providers:
        adapter = _ADAPTERS_BY_PROVIDER.get(provider_slug)
        if adapter is None:
            logger.info(
                "platform_free_models.provider_without_verified_free_catalog",
                provider=provider_slug,
                free_policy=platform_free_model_policy_for_provider(provider_slug),
            )
            continue
        if not adapter.is_configured(settings):
            logger.info("platform_free_models.provider_unconfigured", provider=provider_slug)
            continue
        adapters.append(adapter)
    return adapters


async def fetch_platform_free_model_records(
    settings: BaseSettings,
    *,
    score_overrides: Mapping[tuple[str, str], float] | None = None,
) -> list[PlatformFreeModelRecord]:
    pool_config = settings.llm.platform_free_pool
    all_records: list[PlatformFreeModelRecord] = []
    for adapter in platform_free_model_adapters_for_settings(settings):
        model_items = await adapter.fetch_model_items(settings)
        provider_records = adapter.records_from_items(
            model_items,
            max_candidates=0,
            include_provider_router_as_last=pool_config.include_provider_router_as_last_free_fallback,
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
            provider=adapter.provider_slug,
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
    *,
    model_score_provider: PlatformModelScoreProvider | None = None,
) -> JsonObject:
    score_overrides = (
        await model_score_provider.list_enabled_score_map()
        if model_score_provider is not None
        else None
    )
    records = await fetch_platform_free_model_records(settings, score_overrides=score_overrides)
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
            for provider in settings.llm.platform_free_pool.providers
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
            for provider in settings.llm.platform_free_pool.providers
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

    score_overrides = await model_score_provider.list_enabled_score_map()
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
    "BotHubFreeModelAdapter",
    "ConfiguredAccountFreeTierModelAdapter",
    "OpenRouterPlatformFreeModelAdapter",
    "PLATFORM_FREE_MODEL_SOURCE",
    "PLATFORM_FREE_MODELS_CACHE_KEY",
    "PLATFORM_PAID_FALLBACK_SOURCE",
    "PlatformFreeModelRecord",
    "apply_platform_model_score_overrides",
    "fetch_platform_free_model_records",
    "is_bothub_free_text_model",
    "is_openrouter_verified_free_text_model",
    "parse_platform_free_models",
    "platform_free_model_adapters_for_settings",
    "platform_free_model_policy_for_provider",
    "humanitec_llms_model_options_from_records",
    "read_humanitec_llms_model_options",
    "read_platform_free_model_records",
    "rescore_cached_platform_free_models",
    "refresh_platform_free_models_cache",
    "serialize_platform_free_models",
    "sort_platform_free_records",
]
