"""
API-ключ и корень ``.../v1`` OpenAI-совместимого HTTP API для вызовов из RAG (эмбеддинги pgvector).

Источник — блок ``llm`` (активный ``llm.provider`` и соответствующий подблок).
"""

from __future__ import annotations

from core.ai.providers import (
    ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS,
    HUMANITEC_LLM_PROVIDER,
    LLM_PROVIDER_DEFAULT_BASE_URLS,
    OPENAI_COMPATIBLE_LLM_PROVIDER_SLUGS,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS,
)
from core.config.models import (
    BothubProviderConfig,
    CailaProviderConfig,
    CerebrasProviderConfig,
    DeepInfraProviderConfig,
    GitHubModelsProviderConfig,
    GoogleLLMProviderConfig,
    GroqProviderConfig,
    HuggingFaceProviderConfig,
    LLMConfig,
    MistralProviderConfig,
    NvidiaProviderConfig,
    OpenAIProviderConfig,
    OpenRouterProviderConfig,
    SambaNovaProviderConfig,
    YandexLLMProviderConfig,
    ZAIProviderConfig,
)
from core.config.openai_v1_base_url import normalize_openai_v1_base_url

_LLMProviderConfig = (
    OpenAIProviderConfig
    | OpenRouterProviderConfig
    | BothubProviderConfig
    | YandexLLMProviderConfig
    | GroqProviderConfig
    | CerebrasProviderConfig
    | GoogleLLMProviderConfig
    | GitHubModelsProviderConfig
    | HuggingFaceProviderConfig
    | NvidiaProviderConfig
    | MistralProviderConfig
    | ZAIProviderConfig
    | SambaNovaProviderConfig
    | DeepInfraProviderConfig
    | CailaProviderConfig
)

_ACCOUNT_FREE_TIER_PROVIDER_CONFIGS = (
    GroqProviderConfig,
    CerebrasProviderConfig,
    GoogleLLMProviderConfig,
    GitHubModelsProviderConfig,
    HuggingFaceProviderConfig,
    NvidiaProviderConfig,
    MistralProviderConfig,
    ZAIProviderConfig,
    SambaNovaProviderConfig,
)

_LLM_KEY_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "YOUR_EMBEDDING_API_KEY",
        "YOUR_OPENROUTER_API_KEY",
        "YOUR_OPENAI_API_KEY",
        "YOUR_BOTHUB_API_KEY",
        "YOUR_YANDEX_API_KEY",
        "YOUR_GROQ_API_KEY",
        "YOUR_CEREBRAS_API_KEY",
        "YOUR_GOOGLE_LLM_API_KEY",
        "YOUR_GITHUB_MODELS_API_KEY",
        "YOUR_HUGGINGFACE_API_KEY",
        "YOUR_NVIDIA_API_KEY",
        "YOUR_MISTRAL_API_KEY",
        "YOUR_ZAI_API_KEY",
        "YOUR_SAMBANOVA_API_KEY",
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


def openai_compat_http_root(raw: str) -> str:
    """Корень OpenAI-совместимого HTTP API: ``.../v1`` нормализуется, иначе как есть."""
    cleaned = raw.strip().rstrip("/")
    if not cleaned:
        raise ValueError("Нужен непустой base_url")
    if cleaned.endswith("/v1"):
        return normalize_openai_v1_base_url(cleaned)
    return cleaned


def _active_llm_provider_block(
    llm: LLMConfig,
) -> tuple[str, _LLMProviderConfig | None]:
    p = (llm.provider or "").strip().lower()
    if p == HUMANITEC_LLM_PROVIDER:
        raise ValueError(
            f"llm.provider={p!r} не поддержан для OpenAI-совместимого API."
        )
    return p, llm_provider_block(llm, p)


def llm_provider_block(
    llm: LLMConfig,
    provider: str,
) -> _LLMProviderConfig | None:
    """Provider sub-config by explicit slug, independent of active ``llm.provider``."""
    p = provider.strip().lower()
    if p not in OPENAI_COMPATIBLE_LLM_PROVIDER_SLUGS:
        raise ValueError(f"provider={p!r} не поддержан для OpenAI-совместимого API.")
    blocks: dict[str, _LLMProviderConfig | None] = {
        "openai": llm.openai,
        "openrouter": llm.openrouter,
        "bothub": llm.bothub,
        "yandex": llm.yandex,
        "groq": llm.groq,
        "cerebras": llm.cerebras,
        "google": llm.google,
        "github": llm.github,
        "huggingface": llm.huggingface,
        "nvidia": llm.nvidia,
        "mistral": llm.mistral,
        "zai": llm.zai,
        "sambanova": llm.sambanova,
        "deepinfra": llm.deepinfra,
        "caila": llm.caila,
    }
    if p not in blocks:
        raise ValueError(f"provider={p!r} нет поля в LLMConfig")
    return blocks[p]


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


def first_provider_api_key(cfg: _LLMProviderConfig) -> str:
    """Первый usable ключ блока. Нет ключей — ошибка, не пустая строка."""
    keys = collect_provider_api_keys(cfg)
    if not keys:
        raise ValueError("Нужен хотя бы один api_key в конфиге провайдера")
    return keys[0]


def provider_is_configured_for_free_pool(llm: LLMConfig, provider: str) -> bool:
    """Провайдер входит в free-pool и имеет ключи (api_key и/или api_keys).

    Для account-free-tier дополнительно нужен непустой ``smoke_model``.
    """
    p = provider.strip().lower()
    if p not in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS:
        return False
    cfg = llm_provider_block(llm, p)
    if cfg is None:
        return False
    if not collect_provider_api_keys(cfg):
        return False
    if p in ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS:
        if not isinstance(cfg, _ACCOUNT_FREE_TIER_PROVIDER_CONFIGS):
            raise ValueError(f"provider {p!r} должен иметь smoke_model")
        return bool(cfg.smoke_model.strip())
    return True


def provider_smoke_model(llm: LLMConfig, provider: str) -> str:
    """Непустой smoke_model провайдера. Нет строки — ошибка."""
    p = provider.strip().lower()
    cfg = llm_provider_block(llm, p)
    if cfg is None:
        raise ValueError(f"Конфиг провайдера не задан для provider={p!r}")
    smoke_model = cfg.smoke_model
    if not isinstance(smoke_model, str) or not smoke_model.strip():
        raise ValueError(f"llm.{p}.smoke_model обязателен")
    return smoke_model.strip()


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
            return openai_compat_http_root(default_base_url)
        raise ValueError(f"Конфиг провайдера не задан для provider={provider!r}")
    if provider == "openai":
        raw = cfg.base_url
        if raw is None or not raw.strip():
            return openai_compat_http_root("https://api.openai.com/v1")
        return openai_compat_http_root(raw.strip())
    if provider == "yandex":
        if not isinstance(cfg, YandexLLMProviderConfig):
            raise ValueError("llm.yandex не задан")
        return yandex_llm_openai_root_from_provider_cfg(cfg)
    raw = cfg.base_url
    if raw is None or not str(raw).strip():
        raise ValueError(f"Нужен непустой base_url для provider={provider!r}")
    return openai_compat_http_root(str(raw).strip())


def resolve_provider_openai_v1_base_url(llm: LLMConfig, provider: str) -> str:
    """OpenAI-compatible ``.../v1`` root for an explicit provider slug."""
    p = provider.strip().lower()
    return _provider_openai_v1_base_url(p, llm_provider_block(llm, p))
