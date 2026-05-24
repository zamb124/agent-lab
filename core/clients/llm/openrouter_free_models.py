"""OpenRouter free model discovery and cache.

The discovery job stores an ordered list in Redis.  Runtime LLM routing only
reads this cache; if it is empty, the client still has a deterministic paid
fallback.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from core.clients.redis_client import RedisClient
from core.config.base import BaseSettings
from core.http.client import ProxyStrategy, request_with_strategy
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

OPENROUTER_FREE_MODELS_CACHE_KEY = "llm:openrouter:free_models:v1"
OPENROUTER_FREE_MODELS_CACHE_VERSION = 1

_SIZE_RE = re.compile(r"(?<![a-z0-9])(\d+(?:\.\d+)?)\s*([bm])\b", re.IGNORECASE)


@dataclass(frozen=True)
class OpenRouterFreeModelRecord:
    id: str
    score: float
    context_length: int | None
    supported_parameters: tuple[str, ...]
    input_modalities: tuple[str, ...]
    output_modalities: tuple[str, ...]
    created: int | None = None


def _float_zero(value: JsonValue | None) -> bool:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return False
    try:
        return float(value) == 0
    except (TypeError, ValueError):
        return False


def _model_size_score(*texts: str) -> float:
    """Returns size in billions when the slug/name contains 80B, 120b, 1.2B, etc."""
    best_size_billions = 0.0
    for text in texts:
        for match in _SIZE_RE.finditer(text or ""):
            value = float(match.group(1))
            unit = match.group(2).lower()
            billions = value if unit == "b" else value / 1000.0
            best_size_billions = max(best_size_billions, billions)
    return best_size_billions


def is_free_text_model(item: JsonObject) -> bool:
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
        and _float_zero(pricing.get("request"))
    )


def rank_openrouter_free_models(
    items: Iterable[JsonObject],
    *,
    max_candidates: int,
    include_router_as_last: bool,
) -> list[OpenRouterFreeModelRecord]:
    records: list[OpenRouterFreeModelRecord] = []
    router: OpenRouterFreeModelRecord | None = None

    for item in items:
        model_id = str(item.get("id") or "").strip()
        if not model_id or not is_free_text_model(item):
            continue
        architecture = require_json_object(
            item.get("architecture", {}),
            "openrouter.model.architecture",
        )
        supported = tuple(
            sorted(
                str(parameter)
                for parameter in require_json_array(
                    item.get("supported_parameters", []),
                    "openrouter.model.supported_parameters",
                )
            )
        )
        input_modalities = tuple(
            sorted(
                str(value)
                for value in require_json_array(
                    architecture.get("input_modalities", []),
                    "openrouter.model.architecture.input_modalities",
                )
            )
        )
        output_modalities = tuple(
            sorted(
                str(value)
                for value in require_json_array(
                    architecture.get("output_modalities", []),
                    "openrouter.model.architecture.output_modalities",
                )
            )
        )
        context_length = item.get("context_length")
        if not isinstance(context_length, int):
            context_length = None
        created = item.get("created")
        if not isinstance(created, int):
            created = None
        score = _model_size_score(model_id, str(item.get("name") or ""))
        record = OpenRouterFreeModelRecord(
            id=model_id,
            score=score,
            context_length=context_length,
            supported_parameters=supported,
            input_modalities=input_modalities,
            output_modalities=output_modalities,
            created=created,
        )
        if model_id == "openrouter/free":
            router = record
            continue
        records.append(record)

    records.sort(
        key=lambda record: (
            record.score,
            record.context_length or 0,
            int(
                "response_format" in record.supported_parameters
                or "structured_outputs" in record.supported_parameters
            ),
            record.created or 0,
            record.id,
        ),
        reverse=True,
    )
    if max_candidates > 0:
        records = records[:max_candidates]
    if (
        include_router_as_last
        and router is not None
        and all(record.id != router.id for record in records)
    ):
        records.append(router)
    return records


def serialize_openrouter_free_models(records: Sequence[OpenRouterFreeModelRecord]) -> str:
    models: JsonArray = [
        {
            "id": record.id,
            "score": record.score,
            "context_length": record.context_length,
            "supported_parameters": list(record.supported_parameters),
            "input_modalities": list(record.input_modalities),
            "output_modalities": list(record.output_modalities),
            "created": record.created,
        }
        for record in records
    ]
    return json.dumps(
        {
            "version": OPENROUTER_FREE_MODELS_CACHE_VERSION,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "provider": "openrouter",
            "models": models,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def parse_openrouter_free_models(raw_cache_payload: str | None) -> list[OpenRouterFreeModelRecord]:
    if not raw_cache_payload:
        return []
    try:
        cache_payload = parse_json_object(raw_cache_payload, "openrouter.free_models.cache")
    except ValueError:
        logger.warning("openrouter.free_models.cache_invalid_json")
        return []
    if (
        cache_payload.get("version") != OPENROUTER_FREE_MODELS_CACHE_VERSION
    ):
        return []
    models_raw = cache_payload.get("models")
    if not isinstance(models_raw, list):
        return []
    records: list[OpenRouterFreeModelRecord] = []
    for raw_item in models_raw:
        if not isinstance(raw_item, dict):
            continue
        item = require_json_object(raw_item, "openrouter.free_models.cache.models[]")
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        score_value = item.get("score")
        context_length = item.get("context_length")
        created = item.get("created")
        records.append(
            OpenRouterFreeModelRecord(
                id=model_id,
                score=(
                    float(score_value)
                    if isinstance(score_value, (int, float)) and not isinstance(score_value, bool)
                    else 0.0
                ),
                context_length=(
                    context_length
                    if isinstance(context_length, int) and not isinstance(context_length, bool)
                    else None
                ),
                supported_parameters=tuple(
                    str(parameter)
                    for parameter in require_json_array(
                        item.get("supported_parameters", []),
                        "openrouter.free_models.supported_parameters",
                    )
                ),
                input_modalities=tuple(
                    str(modality)
                    for modality in require_json_array(
                        item.get("input_modalities", []),
                        "openrouter.free_models.input_modalities",
                    )
                ),
                output_modalities=tuple(
                    str(modality)
                    for modality in require_json_array(
                        item.get("output_modalities", []),
                        "openrouter.free_models.output_modalities",
                    )
                ),
                created=created if isinstance(created, int) and not isinstance(created, bool) else None,
            )
        )
    return records


async def fetch_openrouter_model_items(settings: BaseSettings) -> list[JsonObject]:
    openrouter_config = settings.llm.openrouter
    if openrouter_config is None or not openrouter_config.api_key:
        logger.warning("openrouter.free_models.no_api_key")
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


async def refresh_openrouter_free_models_cache(
    redis_client: RedisClient,
    settings: BaseSettings,
) -> JsonObject:
    free_pool_config = settings.llm.openrouter_free_pool
    model_items = await fetch_openrouter_model_items(settings)
    records = rank_openrouter_free_models(
        model_items,
        max_candidates=free_pool_config.max_candidates,
        include_router_as_last=free_pool_config.include_router_as_last_free_fallback,
    )
    payload = serialize_openrouter_free_models(records)
    redis_ok = await redis_client.set(
        OPENROUTER_FREE_MODELS_CACHE_KEY,
        payload,
        ttl=free_pool_config.cache_ttl_seconds,
    )
    logger.info(
        "openrouter.free_models.cache_refreshed",
        count=len(records),
        redis_ok=redis_ok,
        ttl_seconds=free_pool_config.cache_ttl_seconds,
    )
    return {
        "count": len(records),
        "models": [record.id for record in records],
        "redis_ok": bool(redis_ok),
    }


__all__ = [
    "OPENROUTER_FREE_MODELS_CACHE_KEY",
    "OpenRouterFreeModelRecord",
    "fetch_openrouter_model_items",
    "is_free_text_model",
    "parse_openrouter_free_models",
    "rank_openrouter_free_models",
    "refresh_openrouter_free_models_cache",
    "serialize_openrouter_free_models",
]
