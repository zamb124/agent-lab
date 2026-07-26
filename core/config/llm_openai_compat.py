"""
API-ключ и корень ``.../v1`` OpenAI-совместимого HTTP API для вызовов из RAG (эмбеддинги pgvector).

Источник — блок ``llm`` (активный ``llm.provider`` и соответствующий подблок).
"""

from __future__ import annotations

from core.ai.providers import LLM_PROVIDER_DEFAULT_BASE_URLS
from core.config.models import (
    BothubProviderConfig,
    CailaProviderConfig,
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

_LLMProviderConfig = (
    OpenAIProviderConfig
    | OpenRouterProviderConfig
    | BothubProviderConfig
    | YandexLLMProviderConfig
    | GroqProviderConfig
    | GoogleLLMProviderConfig
    | GitHubModelsProviderConfig
    | HuggingFaceProviderConfig
    | DeepInfraProviderConfig
    | CailaProviderConfig
)

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
        "YOUR_CAILA_API_KEY",
    }
)


def _norm_api_key(raw: str | None) -> str:
    if raw is None:
        return ""
    s = raw.strip()
    if not s or s in _LLM_KEY_PLACEHOLDERS:
        return ""
    return s


def normalize_llm_api_key(raw: str | None) -> str:
    """Пустая строка, если ключ отсутствует или это conf-placeholder ``YOUR_*_API_KEY``."""
    return _norm_api_key(raw)


def _active_llm_provider_block(
    llm: LLMConfig,
) -> tuple[str, _LLMProviderConfig | None]:
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
    if p == "caila":
        return p, llm.caila
    raise ValueError(
        f"llm.provider={p!r} не поддержан для OpenAI-совместимого API."
    )


def llm_provider_block(
    llm: LLMConfig,
    provider: str,
) -> _LLMProviderConfig | None:
    """Provider sub-config by explicit slug, independent of active ``llm.provider``."""
    p = provider.strip().lower()
    if p == "openai":
        return llm.openai
    if p == "openrouter":
        return llm.openrouter
    if p == "bothub":
        return llm.bothub
    if p == "yandex":
        return llm.yandex
    if p == "groq":
        return llm.groq
    if p == "google":
        return llm.google
    if p == "github":
        return llm.github
    if p == "huggingface":
        return llm.huggingface
    if p == "deepinfra":
        return llm.deepinfra
    if p == "caila":
        return llm.caila
    raise ValueError(f"provider={p!r} не поддержан для OpenAI-совместимого API.")


def collect_provider_api_keys(cfg: _LLMProviderConfig) -> list[str]:
    """Все нормализованные API ключи из provider config блока (может быть пустым).

    Единая точка нормализации для всей платформы: ``api_key`` становится первым
    элементом, затем добавляются ``api_keys`` без дубликатов. Placeholder'ы и
    пустые строки фильтруются.
    """
    keys: list[str] = []
    main_key = _norm_api_key(cfg.api_key)
    if main_key:
        keys.append(main_key)
    if cfg.api_keys:
        for k in cfg.api_keys:
            nk = _norm_api_key(k)
            if nk and nk not in keys:
                keys.append(nk)
    return keys


def resolve_provider_api_keys(llm: LLMConfig, provider: str) -> list[str]:
    """Все активные API ключи провайдера (основной api_key + дополнительные api_keys)."""
    cfg = llm_provider_block(llm, provider)
    if cfg is None:
        raise ValueError(f"Конфиг провайдера не задан для provider={provider!r}")
    keys = collect_provider_api_keys(cfg)
    if not keys:
        raise ValueError(f"Нужен хотя бы один api_key для provider={provider!r}.")
    return keys


def resolve_llm_api_key_for_openai_compatible_calls(llm: LLMConfig) -> str:
    """Ключ для ``POST .../embeddings`` при привязке эмбеддингов к активному ``llm``."""
    p, cfg = _active_llm_provider_block(llm)
    if cfg is None:
        raise ValueError(f"Конфиг провайдера не задан для llm.provider={p!r}")
    keys = collect_provider_api_keys(cfg)
    if not keys:
        raise ValueError(f"Нужен непустой api_key для llm.provider={p!r} (эмбеддинги).")
    return keys[0]


def resolve_provider_api_key_for_openai_compatible_calls(llm: LLMConfig, provider: str) -> str:
    """API key for an explicit OpenAI-compatible provider slug."""
    return resolve_provider_api_keys(llm, provider)[0]


def yandex_provider_http_headers(cfg: YandexLLMProviderConfig) -> dict[str, str]:
    """Заголовки Yandex по подблоку ``llm.yandex`` (без требования ``llm.provider``)."""
    keys = collect_provider_api_keys(cfg)
    if not keys:
        raise ValueError("Нужен непустой api_key в конфиге Yandex LLM")
    fid = cfg.folder_id
    if fid is None or not fid.strip():
        raise ValueError("Нужен непустой folder_id в конфиге Yandex LLM")
    return {
        "Authorization": f"Api-Key {keys[0]}",
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
    return _provider_openai_v1_base_url(p, cfg)


def _provider_openai_v1_base_url(
    provider: str,
    cfg: _LLMProviderConfig | None,
) -> str:
    if cfg is None:
        default_base_url = LLM_PROVIDER_DEFAULT_BASE_URLS.get(provider)
        if default_base_url is not None and provider != "yandex":
            if provider in {"groq", "google", "github", "huggingface", "deepinfra"}:
                return default_base_url.rstrip("/")
            return normalize_openai_v1_base_url(default_base_url)
        raise ValueError(f"Конфиг провайдера не задан для provider={provider!r}")
    if provider == "openai":
        raw = cfg.base_url
        if raw is None or not raw.strip():
            return normalize_openai_v1_base_url("https://api.openai.com/v1")
        return normalize_openai_v1_base_url(raw.strip())
    if provider == "yandex":
        if not isinstance(cfg, YandexLLMProviderConfig):
            raise ValueError("llm.yandex не задан")
        return yandex_llm_openai_root_from_provider_cfg(cfg)
    raw = cfg.base_url
    if raw is None or not str(raw).strip():
        raise ValueError(f"Нужен непустой base_url для provider={provider!r}")
    if provider in {"groq", "google", "github", "huggingface", "deepinfra"}:
        return str(raw).strip().rstrip("/")
    return normalize_openai_v1_base_url(str(raw).strip())


def resolve_provider_openai_v1_base_url(llm: LLMConfig, provider: str) -> str:
    """OpenAI-compatible ``.../v1`` root for an explicit provider slug."""
    p = provider.strip().lower()
    return _provider_openai_v1_base_url(p, llm_provider_block(llm, p))
