"""Runtime-каталог моделей provider_litserve без перезапуска процесса."""

from __future__ import annotations

from threading import RLock
from typing import Literal, TypedDict

from apps.provider_litserve.model_registry import (
    build_embedding_api_pairs,
    build_rerank_api_pairs,
    build_stt_api_pairs,
    build_tts_api_pairs,
    build_vad_api_pairs,
    list_ready_active_models,
)
from core.config.models import ProviderLitserveInfraConfig

ModelKind = Literal["embedding", "rerank", "stt", "tts", "vad"]

_KINDS: tuple[ModelKind, ...] = ("embedding", "rerank", "stt", "tts", "vad")

_catalog_lock = RLock()
_catalog: dict[ModelKind, dict[str, str]] = {kind: {} for kind in _KINDS}
_catalog_initialized = False


class RuntimeCatalogItem(TypedDict):
    kind: str
    api_model_id: str
    hf_model_id: str


def reset_runtime_catalog_for_tests() -> None:
    """Очищает runtime-каталог и сбрасывает флаг инициализации.

    Только для тестовой инфраструктуры (autouse-фикстура в
    ``tests/provider_litserve/conftest.py``). В рантайме провайдера не
    вызывается. Альтернатива моков/manкипатчей: позволяет тестам гарантировать
    чистый старт без подмены приватных переменных модуля.
    """
    global _catalog_initialized
    with _catalog_lock:
        for kind in _KINDS:
            _catalog[kind] = {}
        _catalog_initialized = False


def replace_runtime_catalog(models: list[RuntimeCatalogItem]) -> dict[str, int]:
    global _catalog_initialized
    updated: dict[ModelKind, dict[str, str]] = {kind: {} for kind in _KINDS}
    for item in models:
        kind = str(item.get("kind", "")).strip()
        hf_model_id = str(item.get("hf_model_id", "")).strip()
        api_model_id = str(item.get("api_model_id", "")).strip()
        if kind not in _KINDS:
            continue
        if not hf_model_id or not api_model_id:
            continue
        updated[kind][api_model_id] = hf_model_id
    with _catalog_lock:
        for kind in _KINDS:
            _catalog[kind] = updated[kind]
        _catalog_initialized = True
    return {kind: len(updated[kind]) for kind in _KINDS}


def reload_runtime_catalog_from_sqlite(cfg: ProviderLitserveInfraConfig) -> dict[str, int]:
    models = list_ready_active_models(cfg)
    payload: list[RuntimeCatalogItem] = [
        {
            "kind": model.kind,
            "api_model_id": model.api_model_id,
            "hf_model_id": model.hf_model_id,
        }
        for model in models
    ]
    return replace_runtime_catalog(payload)


def runtime_catalog_snapshot(kind: ModelKind) -> dict[str, str]:
    with _catalog_lock:
        return dict(_catalog[kind])


def _hf_from_api_map(map_: dict[str, str], api_model_id: str) -> str | None:
    if api_model_id in map_:
        return map_[api_model_id]
    lower = api_model_id.lower()
    for k, v in map_.items():
        if k.lower() == lower:
            return v
    return None


def _default_api_to_hf(kind: ModelKind, cfg: ProviderLitserveInfraConfig) -> dict[str, str]:
    match kind:
        case "embedding":
            return build_embedding_api_pairs(cfg)
        case "rerank":
            return build_rerank_api_pairs(cfg)
        case "stt":
            return build_stt_api_pairs(cfg)
        case "tts":
            return build_tts_api_pairs(cfg)
        case "vad":
            return build_vad_api_pairs(cfg)


def allowed_api_model_ids(kind: ModelKind, cfg: ProviderLitserveInfraConfig) -> frozenset[str]:
    runtime_map = runtime_catalog_snapshot(kind)
    default_map = _default_api_to_hf(kind, cfg)
    with _catalog_lock:
        initialized = _catalog_initialized
    if initialized and kind not in ("embedding", "rerank"):
        return frozenset(runtime_map.keys())
    return frozenset({*default_map.keys(), *runtime_map.keys()})


def resolve_hf_model_id(kind: ModelKind, api_model_id: str, cfg: ProviderLitserveInfraConfig) -> str | None:
    normalized = api_model_id.strip()
    if not normalized:
        return None
    runtime_map = runtime_catalog_snapshot(kind)
    hf = _hf_from_api_map(runtime_map, normalized)
    if hf is not None:
        return hf
    with _catalog_lock:
        initialized = _catalog_initialized
    if initialized and kind not in ("embedding", "rerank"):
        return None
    default_map = _default_api_to_hf(kind, cfg)
    return _hf_from_api_map(default_map, normalized)


def runtime_api_model_ids(kind: ModelKind, cfg: ProviderLitserveInfraConfig) -> list[str]:
    runtime_map = runtime_catalog_snapshot(kind)
    default_map = _default_api_to_hf(kind, cfg)
    with _catalog_lock:
        initialized = _catalog_initialized
    if initialized and kind not in ("embedding", "rerank"):
        return sorted(runtime_map.keys())
    merged = dict(default_map)
    merged.update(runtime_map)
    return sorted(merged.keys())
