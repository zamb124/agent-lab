"""
API-ключ и корень ``.../v1`` OpenAI-совместимого HTTP API для вызовов из RAG (эмбеддинги pgvector).

Источник — блок ``llm`` (активный ``llm.provider`` и соответствующий подблок).
"""

from __future__ import annotations

from core.config.models import (
    BothubProviderConfig,
    DeepInfraProviderConfig,
    GitHubModelsProviderConfig,
    GoogleLLMProviderConfig,
    GroqProviderConfig,
    HuggingFaceProviderConfig,
    LLMConfig,
    OpenAIProviderConfig,
    OpenRouterProviderConfig,
    YandexLLMProviderConfig,
)
from core.config.openai_v1_base_url import normalize_openai_v1_base_url

_LLM_KEY_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "YOUR_EMBEDDING_API_KEY",
        "YOUR_OPENROUTER_API_KEY",
        "YOUR_OPENAI_API_KEY",
        "YOUR_BOTHUB_API_KEY",
        "YOUR_YANDEX_API_KEY",
        "YOUR_GROQ_API_KEY",
        "YOUR_GOOGLE_LLM_API_KEY",
        "YOUR_GITHUB_MODELS_API_KEY",
        "YOUR_HUGGINGFACE_API_KEY",
        "YOUR_DEEPINFRA_API_KEY",
    }
)


def _norm_api_key(raw: str | None) -> str:
    if raw is None:
        return ""
    s = raw.strip()
    if not s or s in _LLM_KEY_PLACEHOLDERS:
        return ""
    return s


def _active_llm_provider_block(
    llm: LLMConfig,
) -> tuple[
    str,
    OpenAIProviderConfig
    | OpenRouterProviderConfig
    | BothubProviderConfig
    | YandexLLMProviderConfig
    | GroqProviderConfig
    | GoogleLLMProviderConfig
    | GitHubModelsProviderConfig
    | HuggingFaceProviderConfig
    | DeepInfraProviderConfig
    | None,
    ]:
    p = (llm.provider or "").strip().lower()
    if p == "openai":
        return p, llm.openai
    if p == "openrouter":
        return p, llm.openrouter
    if p == "bothub":
        return p, llm.bothub
    if p == "yandex":
        return p, llm.yandex
    if p == "groq":
        return p, llm.groq
    if p == "google":
        return p, llm.google
    if p == "github":
        return p, llm.github
    if p == "huggingface":
        return p, llm.huggingface
    if p == "deepinfra":
        return p, llm.deepinfra
    raise ValueError(
        f"llm.provider={p!r} не поддержан для OpenAI-совместимого API."
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


def yandex_provider_http_headers(cfg: YandexLLMProviderConfig) -> dict[str, str]:
    """Заголовки Yandex по подблоку ``llm.yandex`` (без требования ``llm.provider``)."""
    k = _norm_api_key(cfg.api_key)
    if not k:
        raise ValueError("Нужен непустой api_key в конфиге Yandex LLM")
    fid = cfg.folder_id
    if fid is None or not fid.strip():
        raise ValueError("Нужен непустой folder_id в конфиге Yandex LLM")
    return {
        "Authorization": f"Api-Key {k}",
        "x-folder-id": fid.strip(),
    }


def yandex_llm_openai_root_from_provider_cfg(cfg: YandexLLMProviderConfig) -> str:
    """Корень ``.../v1`` для Yandex из подблока ``llm.yandex``."""
    raw = cfg.base_url.strip()
    if not raw:
        raw = "https://llm.api.cloud.yandex.net/v1"
    return normalize_openai_v1_base_url(raw)


def yandex_llm_http_headers(llm: LLMConfig) -> dict[str, str]:
    """Заголовки ``Authorization: Api-Key`` и ``x-folder-id`` для Yandex OpenAI-compatible API."""
    p = (llm.provider or "").strip().lower()
    if p != "yandex":
        raise ValueError(f"yandex_llm_http_headers: ожидался yandex, получено {p!r}")
    cfg = llm.yandex
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
        if raw is None or not raw.strip():
            return normalize_openai_v1_base_url("https://api.openai.com/v1")
        return normalize_openai_v1_base_url(raw.strip())
    if p == "yandex":
        if not isinstance(cfg, YandexLLMProviderConfig):
            raise ValueError("llm.yandex не задан")
        return yandex_llm_openai_root_from_provider_cfg(cfg)
    raw = cfg.base_url
    if raw is None or not str(raw).strip():
        raise ValueError(f"Нужен непустой base_url для llm.provider={p!r}")
    if p in {"groq", "google", "github", "huggingface", "deepinfra"}:
        return str(raw).strip().rstrip("/")
    return normalize_openai_v1_base_url(str(raw).strip())
