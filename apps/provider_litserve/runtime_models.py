"""Runtime-каталог моделей provider_litserve без перезапуска процесса."""

from __future__ import annotations

from threading import RLock
from typing import Any, Literal

from core.config.models import ProviderLitserveInfraConfig

from apps.provider_litserve.model_registry import list_ready_active_models

ModelKind = Literal["llm", "embedding", "rerank"]

_catalog_lock = RLock()
_catalog: dict[ModelKind, dict[str, str]] = {
    "llm": {},
    "embedding": {},
    "rerank": {},
}
_catalog_initialized = False


def replace_runtime_catalog(models: list[dict[str, str]]) -> dict[str, int]:
    global _catalog_initialized
    updated: dict[ModelKind, dict[str, str]] = {
        "llm": {},
        "embedding": {},
        "rerank": {},
    }
    for item in models:
        kind = str(item.get("kind", "")).strip()
        hf_model_id = str(item.get("hf_model_id", "")).strip()
        api_model_id = str(item.get("api_model_id", "")).strip()
        if kind not in {"llm", "embedding", "rerank"}:
            continue
        if not hf_model_id or not api_model_id:
            continue
        updated[kind][api_model_id] = hf_model_id
    with _catalog_lock:
        _catalog["llm"] = updated["llm"]
        _catalog["embedding"] = updated["embedding"]
        _catalog["rerank"] = updated["rerank"]
        _catalog_initialized = True
    return {
        "llm": len(updated["llm"]),
        "embedding": len(updated["embedding"]),
        "rerank": len(updated["rerank"]),
    }


def reload_runtime_catalog_from_sqlite(cfg: ProviderLitserveInfraConfig) -> dict[str, int]:
    models = list_ready_active_models(cfg)
    payload = [
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


def _default_api_to_hf(kind: ModelKind, cfg: ProviderLitserveInfraConfig) -> dict[str, str]:
    if kind == "llm":
        llm_ids = [model_id.strip() for model_id in cfg.llm_model_ids if model_id.strip()]
        if not llm_ids:
            llm_ids = [cfg.llm_model_id.strip()]
        return {model_id: model_id for model_id in llm_ids if model_id}
    if kind == "embedding":
        result: dict[str, str] = {}
        canonical_hf = cfg.embedding_model_id.strip()
        canonical_api = cfg.embedding_openai_model_id.strip()
        if canonical_api:
            result[canonical_api] = canonical_hf
        if canonical_hf:
            result[canonical_hf] = canonical_hf
        for model_id in cfg.embedding_model_ids:
            normalized = model_id.strip()
            if normalized:
                result[normalized] = normalized
        return result
    result = {}
    rerank_hf = cfg.model_id.strip()
    rerank_api = cfg.rerank_openai_model_id.strip()
    if rerank_api:
        result[rerank_api] = rerank_hf
    if rerank_hf:
        result[rerank_hf] = rerank_hf
    for model_id in cfg.rerank_model_ids:
        normalized = model_id.strip()
        if normalized:
            result[normalized] = normalized
    return result


def allowed_api_model_ids(kind: ModelKind, cfg: ProviderLitserveInfraConfig) -> frozenset[str]:
    runtime_map = runtime_catalog_snapshot(kind)
    with _catalog_lock:
        initialized = _catalog_initialized
    if initialized:
        return frozenset(runtime_map.keys())
    default_map = _default_api_to_hf(kind, cfg)
    return frozenset({*default_map.keys(), *runtime_map.keys()})


def resolve_hf_model_id(kind: ModelKind, api_model_id: str, cfg: ProviderLitserveInfraConfig) -> str | None:
    normalized = api_model_id.strip()
    if not normalized:
        return None
    runtime_map = runtime_catalog_snapshot(kind)
    if normalized in runtime_map:
        return runtime_map[normalized]
    with _catalog_lock:
        initialized = _catalog_initialized
    if initialized:
        return None
    default_map = _default_api_to_hf(kind, cfg)
    return default_map.get(normalized)


def runtime_api_model_ids(kind: ModelKind, cfg: ProviderLitserveInfraConfig) -> list[str]:
    runtime_map = runtime_catalog_snapshot(kind)
    with _catalog_lock:
        initialized = _catalog_initialized
    if initialized:
        return sorted(runtime_map.keys())
    merged = dict(_default_api_to_hf(kind, cfg))
    merged.update(runtime_map)
    return sorted(merged.keys())


def serialize_runtime_catalog() -> dict[str, Any]:
    with _catalog_lock:
        return {
            "models": [
                {"kind": kind, "api_model_id": api_model_id, "hf_model_id": hf_model_id}
                for kind in ("llm", "embedding", "rerank")
                for api_model_id, hf_model_id in _catalog[kind].items()
            ]
        }
