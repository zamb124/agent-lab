"""
API-ключ и корень ``.../v1`` OpenAI-совместимого HTTP API для вызовов из RAG (эмбеддинги pgvector).

Источник — блок ``llm`` (активный ``llm.provider`` и соответствующий подблок).
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

from core.config.models import LLMConfig
from core.config.openai_v1_base_url import normalize_openai_v1_base_url

_LLM_KEY_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "YOUR_EMBEDDING_API_KEY",
        "YOUR_OPENROUTER_API_KEY",
        "YOUR_OPENAI_API_KEY",
        "YOUR_BOTHUB_API_KEY",
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
    raise ValueError(
        f"llm.provider={p!r} не поддержан для OpenAI-совместимого API; "
        "нужен openrouter, bothub или openai."
    )


def resolve_llm_api_key_for_openai_compatible_calls(llm: LLMConfig) -> str:
    """Ключ для ``POST .../embeddings`` при ``rag.embedding.provider`` = ``openrouter``."""
    p, cfg = _active_llm_provider_block(llm)
    k = _norm_api_key(cfg.api_key)
    if not k:
        raise ValueError(f"Нужен непустой api_key для llm.provider={p!r} (эмбеддинги).")
    return k


def resolve_llm_openai_v1_base_url(llm: LLMConfig) -> str:
    """Корень OpenAI-совместимого API (суффикс ``/v1``) для эмбеддингов."""
    p, cfg = _active_llm_provider_block(llm)
    if p == "openai":
        raw = cfg.base_url
        if raw is None or not str(raw).strip():
            return normalize_openai_v1_base_url("https://api.openai.com/v1")
        return normalize_openai_v1_base_url(str(raw).strip())
    return normalize_openai_v1_base_url(cfg.base_url)
