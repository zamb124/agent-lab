"""
API-ключ и корень ``.../v1`` OpenAI-совместимого HTTP API для вызовов из RAG (эмбеддинги pgvector).

Источник — блок ``llm`` (активный ``llm.provider`` и соответствующий подблок).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from core.config.models import LLMConfig
from core.config.openai_v1_base_url import normalize_openai_v1_base_url

_LLM_KEY_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "YOUR_EMBEDDING_API_KEY",
        "YOUR_OPENROUTER_API_KEY",
        "YOUR_OPENAI_API_KEY",
        "YOUR_BOTHUB_API_KEY",
        "YOUR_YANDEX_API_KEY",
    }
)


def _norm_api_key(raw: Optional[str]) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s or s in _LLM_KEY_PLACEHOLDERS:
        return ""
    return s


def _active_llm_provider_block(llm: LLMConfig) -> Tuple[str, Any]:
    p = (llm.provider or "").strip().lower()
    if p == "openrouter":
        return p, llm.openrouter
    if p == "bothub":
        return p, llm.bothub
    if p == "openai":
        return p, llm.openai
    if p == "yandex":
        return p, llm.yandex
    raise ValueError(
        f"llm.provider={p!r} не поддержан для OpenAI-совместимого API; "
        "нужен openrouter, bothub, openai или yandex."
    )


def resolve_llm_api_key_for_openai_compatible_calls(llm: LLMConfig) -> str:
    """Ключ для ``POST .../embeddings`` при привязке эмбеддингов к активному ``llm``."""
    p, cfg = _active_llm_provider_block(llm)
    if cfg is None:
        raise ValueError(f"Конфиг провайдера не задан для llm.provider={p!r}")
    k = _norm_api_key(cfg.api_key)
    if not k:
        raise ValueError(f"Нужен непустой api_key для llm.provider={p!r} (эмбеддинги).")
    return k


def yandex_provider_http_headers(cfg: Any) -> Dict[str, str]:
    """Заголовки Yandex по подблоку ``llm.yandex`` (без требования ``llm.provider``)."""
    if cfg is None:
        raise ValueError("yandex config is None")
    k = _norm_api_key(getattr(cfg, "api_key", None))
    if not k:
        raise ValueError("Нужен непустой api_key в конфиге Yandex LLM")
    fid = getattr(cfg, "folder_id", None)
    if fid is None or not str(fid).strip():
        raise ValueError("Нужен непустой folder_id в конфиге Yandex LLM")
    return {
        "Authorization": f"Api-Key {k}",
        "x-folder-id": str(fid).strip(),
    }


def yandex_llm_openai_root_from_provider_cfg(cfg: Any) -> str:
    """Корень ``.../v1`` для Yandex из подблока ``llm.yandex``."""
    if cfg is None:
        raise ValueError("yandex config is None")
    raw = getattr(cfg, "base_url", None)
    raw = str(raw).strip() if raw is not None else ""
    if not raw:
        raw = "https://llm.api.cloud.yandex.net/v1"
    return normalize_openai_v1_base_url(raw)


def yandex_llm_http_headers(llm: LLMConfig) -> Dict[str, str]:
    """Заголовки ``Authorization: Api-Key`` и ``x-folder-id`` для Yandex OpenAI-compatible API."""
    p, cfg = _active_llm_provider_block(llm)
    if p != "yandex":
        raise ValueError(f"yandex_llm_http_headers: ожидался yandex, получено {p!r}")
    if cfg is None:
        raise ValueError("llm.yandex не задан")
    return yandex_provider_http_headers(cfg)


def resolve_llm_openai_v1_base_url(llm: LLMConfig) -> str:
    """Корень OpenAI-совместимого API (суффикс ``/v1``) для эмбеддингов."""
    p, cfg = _active_llm_provider_block(llm)
    if cfg is None:
        raise ValueError(f"Конфиг провайдера не задан для llm.provider={p!r}")
    if p == "openai":
        raw = cfg.base_url
        if raw is None or not str(raw).strip():
            return normalize_openai_v1_base_url("https://api.openai.com/v1")
        return normalize_openai_v1_base_url(str(raw).strip())
    if p == "yandex":
        return yandex_llm_openai_root_from_provider_cfg(cfg)
    return normalize_openai_v1_base_url(cfg.base_url)
