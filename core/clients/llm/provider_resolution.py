"""Provider and runtime config resolution for LLM attempts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from core.clients.llm.config import LLMCallConfig
from core.clients.llm.model_routing import HUMANITEC_LLM_PROVIDER, LLM_ROUTING_PROVIDER_SLUGS
from core.config.base import BaseSettings
from core.config.llm_openai_compat import yandex_llm_openai_root_from_provider_cfg
from core.config.openai_v1_base_url import normalize_openai_v1_base_url
from core.types import JsonObject
from core.variables import VariableResolutionError, VarResolver

if TYPE_CHECKING:
    from core.state import ExecutionState

_YANDEX_MODEL_URI_PREFIXES = ("gpt://", "emb://")


def _yandex_openai_root(settings: BaseSettings) -> str:
    yandex_config = settings.llm.yandex
    if yandex_config is None:
        return normalize_openai_v1_base_url("https://llm.api.cloud.yandex.net/v1")
    return yandex_llm_openai_root_from_provider_cfg(yandex_config)


def _yandex_auth_headers(*, api_key: str, folder_id: str) -> dict[str, str]:
    resolved_folder_id = folder_id.strip()
    if not resolved_folder_id:
        raise ValueError("Yandex LLM: folder_id пуст")
    resolved_api_key = api_key.strip()
    if not resolved_api_key:
        raise ValueError("Yandex LLM: api_key пуст")
    return {
        "Authorization": f"Api-Key {resolved_api_key}",
        "x-folder-id": resolved_folder_id,
    }


def normalize_yandex_resource_model_uri(model: str, folder_id: str) -> str:
    """Заменяет сегмент каталога в gpt:// и emb:// на folder_id."""
    resolved_folder_id = folder_id.strip()
    if not resolved_folder_id:
        return model
    for prefix in _YANDEX_MODEL_URI_PREFIXES:
        if not model.startswith(prefix):
            continue
        rest = model[len(prefix) :]
        if "/" not in rest:
            return model
        existing_folder_id, model_path = rest.split("/", 1)
        if existing_folder_id == resolved_folder_id:
            return model
        return f"{prefix}{resolved_folder_id}/{model_path}"
    return model


def _resolve_var(value: str | None, state: ExecutionState | None) -> str | None:
    """Резолвит @var:path из state.variables по strict-контракту."""
    if not value:
        return None
    if not value.startswith("@var:"):
        return value
    if state is None:
        raise VariableResolutionError(f"Cannot resolve '{value}' without ExecutionState")
    resolved_value = VarResolver.resolve_ref(value, state.variables or {})
    if not isinstance(resolved_value, str):
        raise VariableResolutionError(f"Variable '{value}' for LLM config must resolve to string")
    if not resolved_value:
        raise VariableResolutionError(f"Variable '{value}' resolved to empty string")
    return resolved_value


def _resolve_headers_vars(
    headers: dict[str, str] | None,
    state: ExecutionState | None,
) -> dict[str, str] | None:
    if not headers:
        return None
    resolved_headers: dict[str, str] = {}
    for key, header_value in headers.items():
        resolved_header_value = _resolve_var(header_value, state)
        if resolved_header_value is None:
            continue
        resolved_headers[key] = resolved_header_value
    return resolved_headers


def _detect_provider(base_url: str | None) -> str | None:
    """Определяет провайдера по base_url."""
    if not base_url:
        return None
    if (
        "provider_litserve" in base_url
        or "localhost:8014" in base_url
        or "127.0.0.1:8014" in base_url
    ):
        return "provider_litserve"
    if "openrouter.ai" in base_url:
        return "openrouter"
    if "bothub.chat" in base_url:
        return "bothub"
    if "api.openai.com" in base_url:
        return "openai"
    if "llm.api.cloud.yandex.net" in base_url:
        return "yandex"
    return None


def _is_humanitec_llm_provider(provider: str | None) -> bool:
    return str(provider or "").strip() == HUMANITEC_LLM_PROVIDER


def _ensure_known_provider(provider: str) -> None:
    if provider not in LLM_ROUTING_PROVIDER_SLUGS:
        raise ValueError(f"Неизвестный LLM провайдер: {provider}")


def _get_default_base_url(provider: str, settings: BaseSettings) -> str:
    """Возвращает base_url по умолчанию для провайдера."""
    if provider == "openrouter":
        return (
            settings.llm.openrouter.base_url or "https://openrouter.ai/api/v1"
            if settings.llm.openrouter
            else "https://openrouter.ai/api/v1"
        )
    if provider == "bothub":
        return (
            settings.llm.bothub.base_url or "https://bothub.chat/api/v2/openai/v1"
            if settings.llm.bothub
            else "https://bothub.chat/api/v2/openai/v1"
        )
    if provider == "openai":
        return (
            settings.llm.openai.base_url or "https://api.openai.com/v1"
            if settings.llm.openai
            else "https://api.openai.com/v1"
        )
    if provider == "yandex":
        return _yandex_openai_root(settings)
    if provider == "provider_litserve":
        return settings.provider_litserve.resolve_openai_v1_base_url()
    if provider == "custom_openai_compatible":
        raise ValueError("custom_openai_compatible LLM требует явный base_url")
    raise ValueError(f"Неизвестный LLM провайдер: {provider}")


def _resolve_default_base_url(
    *,
    provider: str,
    explicit_base_url: str | None,
    config_base_url_is_set: bool,
    inherit_transport: bool,
    inherit_transport_from: LLMCallConfig | None,
    settings: BaseSettings,
) -> str | None:
    if config_base_url_is_set:
        return explicit_base_url
    if inherit_transport and inherit_transport_from is not None:
        return inherit_transport_from.base_url
    if provider == "custom_openai_compatible":
        return None
    return _get_default_base_url(provider, settings)


def _resolve_llm_call_config(
    config: LLMCallConfig,
    *,
    settings: BaseSettings,
    state: ExecutionState | None = None,
    inherit_transport_from: LLMCallConfig | None = None,
    source: str | None = None,
) -> LLMCallConfig:
    """Resolve one LLM config into a concrete runtime attempt."""
    if not config.model or not str(config.model).strip():
        raise ValueError("LLM model обязателен")

    explicit_api_key = _resolve_var(config.api_key, state)
    explicit_base_url = _resolve_var(config.base_url, state)
    explicit_folder_id = _resolve_var(config.folder_id, state)
    inherit_transport = (
        inherit_transport_from is not None
        and config.provider is None
        and config.api_key is None
        and config.base_url is None
        and config.folder_id is None
    )
    resolved_provider = (
        config.provider
        or (inherit_transport_from.provider if inherit_transport and inherit_transport_from else None)
        or _detect_provider(explicit_base_url)
        or settings.llm.provider
    )
    if not resolved_provider:
        raise ValueError("LLM provider обязателен")
    _ensure_known_provider(resolved_provider)

    resolved_api_key = (
        explicit_api_key
        if config.api_key is not None
        else (inherit_transport_from.api_key if inherit_transport and inherit_transport_from else None)
    )
    resolved_base_url = _resolve_default_base_url(
        provider=resolved_provider,
        explicit_base_url=explicit_base_url,
        config_base_url_is_set=config.base_url is not None,
        inherit_transport=inherit_transport,
        inherit_transport_from=inherit_transport_from,
        settings=settings,
    )
    folder_id = (
        explicit_folder_id
        if config.folder_id is not None
        else (inherit_transport_from.folder_id if inherit_transport and inherit_transport_from else None)
    )
    default_headers: dict[str, str] = {}
    candidate_model = str(config.model).strip()
    resolved_source = source or config.source
    configured_model = settings.llm.models.get(candidate_model)
    resolved_context_length = (
        config.context_length
        if config.context_length is not None
        else (configured_model.context_length if configured_model else None)
    )

    if resolved_api_key:
        if resolved_provider == "custom_openai_compatible" and not resolved_base_url:
            raise ValueError(
                "custom_openai_compatible: base_url обязателен (URL OpenAI-совместимого endpoint компании)"
            )
        if resolved_provider == "openrouter" and settings.llm.openrouter:
            default_headers = {
                "HTTP-Referer": settings.llm.openrouter.site_url,
                "X-Title": settings.llm.openrouter.site_name,
            }
        if resolved_provider == "yandex":
            yandex_config = settings.llm.yandex
            platform_folder_id = (
                str(yandex_config.folder_id).strip()
                if yandex_config and yandex_config.folder_id and str(yandex_config.folder_id).strip()
                else ""
            )
            override_folder_id = str(folder_id).strip() if folder_id and str(folder_id).strip() else ""
            folder_id = override_folder_id or platform_folder_id
            if not folder_id:
                raise ValueError(
                    "Yandex LLM: задайте folder_id в переопределении ноды/ресурса "
                    + "или llm.yandex.folder_id"
                )
            default_headers = _yandex_auth_headers(
                api_key=resolved_api_key,
                folder_id=folder_id,
            )
            candidate_model = normalize_yandex_resource_model_uri(candidate_model, folder_id)
            if resolved_base_url is None:
                resolved_base_url = _yandex_openai_root(settings)
            resolved_base_url = normalize_openai_v1_base_url(str(resolved_base_url).strip())
        return config.model_copy(
            update={
                "provider": resolved_provider,
                "model": candidate_model,
                "api_key": resolved_api_key,
                "base_url": resolved_base_url,
                "folder_id": folder_id,
                "default_headers": default_headers,
                "source": resolved_source,
                "context_length": resolved_context_length,
                "extra_request_body": (
                    dict(config.extra_request_body) if config.extra_request_body else None
                ),
                "extra_request_headers": _resolve_headers_vars(
                    config.extra_request_headers,
                    state,
                ),
            }
        )

    provider_config = None
    if resolved_provider == "openrouter":
        provider_config = settings.llm.openrouter
        if not provider_config or not provider_config.api_key:
            raise ValueError("OpenRouter API key не настроен")
        default_headers = {
            "HTTP-Referer": provider_config.site_url,
            "X-Title": provider_config.site_name,
        }
    elif resolved_provider == "bothub":
        provider_config = settings.llm.bothub
        if not provider_config or not provider_config.api_key:
            raise ValueError("Bothub API key не настроен")
    elif resolved_provider == "openai":
        provider_config = settings.llm.openai
        if not provider_config or not provider_config.api_key:
            raise ValueError("OpenAI API key не настроен")
    elif resolved_provider == "yandex":
        provider_config = settings.llm.yandex
        if not provider_config or not provider_config.api_key:
            raise ValueError("Yandex LLM API key не настроен")
        if not provider_config.folder_id or not str(provider_config.folder_id).strip():
            raise ValueError("Yandex LLM folder_id не настроен")
        folder_id = str(provider_config.folder_id).strip()
        candidate_model = normalize_yandex_resource_model_uri(candidate_model, folder_id)
        default_headers = _yandex_auth_headers(api_key=str(provider_config.api_key), folder_id=folder_id)
    elif resolved_provider == "provider_litserve":
        resolved_api_key = "litserve-local"
    elif resolved_provider == "custom_openai_compatible":
        raise ValueError(
            "custom_openai_compatible LLM требует явный api_key и base_url; "
            + "вызывайте через core.company_ai.resolve_llm_for_capability(...)"
        )

    if provider_config is not None:
        resolved_api_key = str(provider_config.api_key).strip()
    return config.model_copy(
        update={
            "provider": resolved_provider,
            "model": candidate_model,
            "api_key": resolved_api_key,
            "base_url": resolved_base_url,
            "folder_id": folder_id,
            "default_headers": default_headers,
            "source": resolved_source,
            "context_length": resolved_context_length,
            "extra_request_body": (
                dict(config.extra_request_body) if config.extra_request_body else None
            ),
            "extra_request_headers": _resolve_headers_vars(
                config.extra_request_headers,
                state,
            ),
        }
    )


def _resolved_llm_configs(
    primary_config: LLMCallConfig,
    fallback_models: Sequence[LLMCallConfig | JsonObject] | None,
    *,
    settings: BaseSettings,
    state: ExecutionState | None,
) -> list[LLMCallConfig]:
    resolved_primary = _resolve_llm_call_config(
        primary_config,
        settings=settings,
        state=state,
        source=primary_config.source,
    )
    resolved_configs = [resolved_primary]
    for raw_fallback_config in fallback_models or []:
        fallback_config = (
            raw_fallback_config
            if isinstance(raw_fallback_config, LLMCallConfig)
            else LLMCallConfig.model_validate(raw_fallback_config)
        )
        resolved_configs.append(
            _resolve_llm_call_config(
                fallback_config,
                settings=settings,
                state=state,
                inherit_transport_from=resolved_primary,
                source="fallback",
            )
        )
    return resolved_configs


def _platform_default_pool_is_configured(settings: BaseSettings) -> bool:
    return (
        settings.llm.openrouter_free_pool.enabled
        and settings.llm.openrouter is not None
        and bool(settings.llm.openrouter.api_key)
    )


def _should_use_platform_default_pool(
    *,
    model: str | None,
    provider: str | None,
    api_key: str | None,
    base_url: str | None,
    folder_id: str | None,
    settings: BaseSettings,
) -> bool:
    has_explicit_transport = any(
        value is not None and str(value).strip()
        for value in (api_key, base_url, folder_id)
    )
    explicit_humanitec_llm = _is_humanitec_llm_provider(provider)
    implicit_default_route = (
        model is None
        and provider is None
        and settings.llm.default_strategy == "openrouter_free_pool"
    )
    return (
        not has_explicit_transport
        and _platform_default_pool_is_configured(settings)
        and (explicit_humanitec_llm or implicit_default_route)
    )


__all__ = [
    "_detect_provider",
    "_get_default_base_url",
    "_is_humanitec_llm_provider",
    "_platform_default_pool_is_configured",
    "_resolve_headers_vars",
    "_resolve_llm_call_config",
    "_resolve_var",
    "_resolved_llm_configs",
    "_should_use_platform_default_pool",
    "normalize_yandex_resource_model_uri",
]
