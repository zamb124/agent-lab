"""OpenRouter free model discovery and cache.

The discovery job stores an ordered list in Redis.  Runtime LLM routing only
reads this cache; if it is empty, the client still has a deterministic paid
fallback.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from core.config.base import BaseSettings
from core.http.client import ProxyStrategy, request_with_strategy
from core.logging import get_logger

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


def _float_zero(value: Any) -> bool:
    try:
        return float(value or 0) == 0
    except (TypeError, ValueError):
        return False


def _model_size_score(*texts: str) -> float:
    """Returns size in billions when the slug/name contains 80B, 120b, 1.2B, etc."""
    best = 0.0
    for text in texts:
        for match in _SIZE_RE.finditer(text or ""):
            value = float(match.group(1))
            unit = match.group(2).lower()
            billions = value if unit == "b" else value / 1000.0
            best = max(best, billions)
    return best


def is_free_text_model(item: dict[str, Any]) -> bool:
    pricing = item.get("pricing") or {}
    arch = item.get("architecture") or {}
    input_modalities = set(arch.get("input_modalities") or ())
    output_modalities = set(arch.get("output_modalities") or ())
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
    items: Iterable[dict[str, Any]],
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
        arch = item.get("architecture") or {}
        supported = tuple(sorted(str(v) for v in (item.get("supported_parameters") or [])))
        input_modalities = tuple(sorted(str(v) for v in (arch.get("input_modalities") or [])))
        output_modalities = tuple(sorted(str(v) for v in (arch.get("output_modalities") or [])))
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
        key=lambda r: (
            r.score,
            r.context_length or 0,
            int("response_format" in r.supported_parameters or "structured_outputs" in r.supported_parameters),
            r.created or 0,
            r.id,
        ),
        reverse=True,
    )
    if max_candidates > 0:
        records = records[:max_candidates]
    if include_router_as_last and router is not None and all(r.id != router.id for r in records):
        records.append(router)
    return records


def serialize_openrouter_free_models(records: Sequence[OpenRouterFreeModelRecord]) -> str:
    return json.dumps(
        {
            "version": OPENROUTER_FREE_MODELS_CACHE_VERSION,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "provider": "openrouter",
            "models": [asdict(record) for record in records],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def parse_openrouter_free_models(raw: str | None) -> list[OpenRouterFreeModelRecord]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("openrouter.free_models.cache_invalid_json")
        return []
    if not isinstance(payload, dict) or payload.get("version") != OPENROUTER_FREE_MODELS_CACHE_VERSION:
        return []
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    result: list[OpenRouterFreeModelRecord] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        result.append(
            OpenRouterFreeModelRecord(
                id=model_id,
                score=float(item.get("score") or 0),
                context_length=item.get("context_length") if isinstance(item.get("context_length"), int) else None,
                supported_parameters=tuple(str(v) for v in (item.get("supported_parameters") or [])),
                input_modalities=tuple(str(v) for v in (item.get("input_modalities") or [])),
                output_modalities=tuple(str(v) for v in (item.get("output_modalities") or [])),
                created=item.get("created") if isinstance(item.get("created"), int) else None,
            )
        )
    return result


async def fetch_openrouter_model_items(settings: BaseSettings) -> list[dict[str, Any]]:
    cfg = settings.llm.openrouter
    if cfg is None or not cfg.api_key:
        logger.warning("openrouter.free_models.no_api_key")
        return []
    url = f"{cfg.base_url.rstrip('/')}/models?output_modalities=text"
    response = await request_with_strategy(
        "GET",
        url,
        headers={
            "Authorization": f"Bearer {cfg.api_key}",
            "HTTP-Referer": cfg.site_url,
            "X-Title": cfg.site_name,
        },
        timeout=30.0,
        strategy=ProxyStrategy.DIRECT_FIRST,
        direct_attempts=3,
        proxy_attempts=3,
    )
    response.raise_for_status()
    data = response.json()
    items = data.get("data", [])
    return [item for item in items if isinstance(item, dict)]


async def refresh_openrouter_free_models_cache(redis_client: Any, settings: BaseSettings) -> dict[str, Any]:
    cfg = settings.llm.openrouter_free_pool
    items = await fetch_openrouter_model_items(settings)
    records = rank_openrouter_free_models(
        items,
        max_candidates=cfg.max_candidates,
        include_router_as_last=cfg.include_router_as_last_free_fallback,
    )
    payload = serialize_openrouter_free_models(records)
    ok = await redis_client.set(
        OPENROUTER_FREE_MODELS_CACHE_KEY,
        payload,
        ttl=cfg.cache_ttl_seconds,
    )
    logger.info(
        "openrouter.free_models.cache_refreshed",
        count=len(records),
        redis_ok=ok,
        ttl_seconds=cfg.cache_ttl_seconds,
    )
    return {
        "count": len(records),
        "models": [record.id for record in records],
        "redis_ok": bool(ok),
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
