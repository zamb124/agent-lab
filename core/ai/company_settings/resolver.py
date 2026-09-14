"""
Internal company AI settings resolution for ``core.ai``.

Capability selection is public only through ``core.ai.resolver.resolve_ai_model``.
This module reads persisted company AI settings and expands secrets/custom
providers into transport parameters for the canonical resolver.

Источник правды — ``Company.metadata['ai_providers']`` (см. ``schema.py``). Если override
отсутствует, вызывающий код может запросить platform default через ``platform_defaults``.

cost_origin:

- ``company`` — компания платит сама (BYOK поверх платформенного provider, либо custom:<id>).
- ``platform`` — расход идёт через платформенные ключи и облагается биллингом как обычно.

Все функции — read-only; запись и шифрование секретов делает API слой.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, computed_field

from core.ai.company_settings.crypto import decrypt_secret
from core.ai.company_settings.platform_defaults import (
    platform_default_model,
    platform_default_provider_for_capability,
)
from core.ai.company_settings.schema import (
    CUSTOM_PROVIDER_REF_PREFIX,
    CUSTOM_PROVIDER_SLUG,
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
    AICapability,
    CompanyAIProviders,
    CompanyCustomOpenAICompatibleProvider,
    CompanyLLMOverride,
    CompanyRerankOverride,
    CompanyVoiceOverride,
)
from core.ai.llm_config import LLMCallConfig
from core.context import get_context
from core.logging import get_logger
from core.models.billing_models import BillingCostOrigin
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)


CostOrigin = BillingCostOrigin
COST_ORIGIN_PLATFORM: CostOrigin = "platform"
COST_ORIGIN_COMPANY: CostOrigin = "company"


class _FrozenModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class CompanyResolvedLLM(_FrozenModel):
    """Финальные параметры LLM route + биллинг-метаданные."""

    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    folder_id: str | None = None
    extra_request_headers: dict[str, str] | None = None
    extra_request_body: JsonObject | None = None
    fallback_models: tuple[LLMCallConfig, ...] | None = None
    cost_origin: CostOrigin = COST_ORIGIN_PLATFORM
    custom_provider_id: str | None = None

    @computed_field  # type: ignore[misc]
    @property
    def billing_resource_name(self) -> str:
        if self.cost_origin == COST_ORIGIN_COMPANY:
            return "llm:byok"
        return f"llm:{self.model}"


class CompanyResolvedEmbedding(_FrozenModel):
    """Финальные параметры embedding HTTP-клиента."""

    provider: str
    model: str
    base_url: str
    api_key: str | None = None
    extra_request_headers: dict[str, str] | None = None
    cost_origin: CostOrigin = COST_ORIGIN_PLATFORM
    custom_provider_id: str | None = None
    dimension: int | None = None
    mrl_output_dimension: int | None = None

    @computed_field  # type: ignore[misc]
    @property
    def billing_resource_name(self) -> str:
        if self.cost_origin == COST_ORIGIN_COMPANY:
            return "embedding:byok"
        return f"embedding:{self.model}"


class CompanyResolvedRerank(_FrozenModel):
    """Политика реранка после применения company override."""

    enabled: bool
    provider: str | None = None
    model: str | None = None
    url: str | None = None
    api_key: str | None = None
    extra_request_headers: dict[str, str] | None = None
    cost_origin: CostOrigin = COST_ORIGIN_PLATFORM
    billing_resource_id: str = "rerank"
    custom_provider_id: str | None = None

    @computed_field  # type: ignore[misc]
    @property
    def billing_resource_name(self) -> str:
        if self.cost_origin == COST_ORIGIN_COMPANY:
            return "rerank:byok"
        return f"rerank:{self.billing_resource_id}"


class CompanyResolvedVoice(_FrozenModel):
    """Резолв провайдера речи (STT/TTS/VAD)."""

    provider: str
    model: str | None = None
    voice: str | None = None
    language: str | None = None
    sample_rate: int | None = None
    api_key: str | None = None
    base_url: str | None = None
    folder_id: str | None = None
    extra_request_headers: dict[str, str] | None = None
    cost_origin: CostOrigin = COST_ORIGIN_PLATFORM
    custom_provider_id: str | None = None


def load_company_ai_providers() -> CompanyAIProviders:
    """Читает ``ai_providers`` из активной компании контекста; пусто если контекст не задан."""
    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        return CompanyAIProviders()
    metadata = require_json_object(ctx.active_company.metadata, "company.metadata")
    return CompanyAIProviders.from_metadata(metadata)


def _resolve_custom_provider(
    aip: CompanyAIProviders, ref: str
) -> CompanyCustomOpenAICompatibleProvider:
    if not ref.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        raise ValueError(f"_resolve_custom_provider: ref должен начинаться с custom:, получено {ref!r}")
    cid = ref[len(CUSTOM_PROVIDER_REF_PREFIX) :]
    return aip.find_custom(cid)


def _decrypt_or_none(token: str | None) -> str | None:
    if token is None or not str(token).strip():
        return None
    return decrypt_secret(token)


def _resolve_llm_fallback_models(
    aip: CompanyAIProviders,
    capability: AICapability,
    *,
    primary: CompanyResolvedLLM,
    fallback_models: list[LLMCallConfig] | None,
) -> tuple[LLMCallConfig, ...] | None:
    """Разворачивает company-level fallback policy в конкретные LLMCallConfig.

    Не читает конфиг ноды/ресурса: fallback chain для компании существует только
    в ``Company.metadata['ai_providers']``. Для BYOK fallback используется
    ``custom:<id>``; секреты внутри самих fallback_models схемой запрещены.
    """
    if not fallback_models:
        return None
    resolved_items: list[LLMCallConfig] = []
    for idx, fallback in enumerate(fallback_models):
        if fallback.provider is None:
            raise ValueError(f"capability {capability.value}: fallback_models[{idx}].provider обязателен")
        if (
            primary.cost_origin == COST_ORIGIN_COMPANY
            and not fallback.provider.startswith(CUSTOM_PROVIDER_REF_PREFIX)
        ):
            raise ValueError(
                f"capability {capability.value}: fallback_models[{idx}] задаёт платформенный "
                + f"provider={fallback.provider!r} после BYOK/custom primary. Это смешивает "
                + "company-cost и platform-cost в одном failover; используйте custom:<id>."
            )
        if fallback.provider and fallback.provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
            custom = _resolve_custom_provider(aip, fallback.provider)
            if capability.value not in custom.capabilities:
                raise ValueError(
                    f"capability={capability.value}: custom_provider {custom.id!r} "
                    + f"не поддерживает её (capabilities={custom.capabilities})"
                )
            resolved_model = fallback.model or custom.model_by_capability.get(capability.value)
            if not resolved_model or not str(resolved_model).strip():
                raise ValueError(
                    f"capability {capability.value}: для custom_provider {custom.id!r} "
                    + "не задана fallback model"
                )
            fallback_body: JsonObject = dict(custom.extra_request_body or {})
            fallback_body.update(fallback.extra_request_body or {})
            resolved_items.append(
                fallback.model_copy(
                    update={
                        "provider": CUSTOM_PROVIDER_SLUG,
                        "model": str(resolved_model).strip(),
                        "api_key": decrypt_secret(custom.api_key_encrypted),
                        "base_url": custom.base_url,
                        "folder_id": fallback.folder_id,
                        "extra_request_headers": dict(custom.extra_request_headers or {}) or None,
                        "extra_request_body": fallback_body or None,
                    }
                )
            )
            continue

        resolved_items.append(fallback)

    return tuple(resolved_items)


def _with_company_fallbacks(
    aip: CompanyAIProviders,
    capability: AICapability,
    *,
    resolved: CompanyResolvedLLM,
    override: CompanyLLMOverride,
) -> CompanyResolvedLLM:
    fallback_models = _resolve_llm_fallback_models(
        aip,
        capability,
        primary=resolved,
        fallback_models=override.fallback_models,
    )
    return resolved.model_copy(update={"fallback_models": fallback_models})


def resolve_company_llm(
    capability: AICapability,
    *,
    fallback_provider: str | None = None,
    fallback_model: str | None = None,
    include_platform_default: bool = False,
) -> CompanyResolvedLLM | None:
    """
    Резолв LLM-капасити: company override, затем опциональный platform default.
    """
    if capability not in {
        AICapability.LLM_CHAT,
        AICapability.LLM_SUMMARIZE,
        AICapability.LLM_FORMAT_MARKDOWN,
        AICapability.LLM_CODEGEN,
        AICapability.LLM_VISION,
        AICapability.IMAGE_GEN,
    }:
        raise ValueError(f"resolve_company_llm: capability {capability} не LLM-типа")

    aip = load_company_ai_providers()
    override = aip.get_capability_override(capability)
    if override is None:
        if fallback_provider and fallback_model:
            return CompanyResolvedLLM(
                provider=fallback_provider,
                model=fallback_model,
                cost_origin=COST_ORIGIN_PLATFORM,
            )
        if include_platform_default:
            default_provider = platform_default_provider_for_capability(capability)
            default_model = platform_default_model(capability, default_provider)
            if default_model is None or not str(default_model).strip():
                raise ValueError(
                    f"capability {capability.value}: platform default model не настроен "
                    + f"для provider {default_provider!r}"
                )
            return CompanyResolvedLLM(
                provider=default_provider,
                model=str(default_model).strip(),
                cost_origin=COST_ORIGIN_PLATFORM,
                custom_provider_id=None,
            )
        return None

    if not isinstance(override, CompanyLLMOverride):
        raise TypeError(
            f"capability {capability} ожидает CompanyLLMOverride, получено {type(override).__name__}"
        )

    if override.provider == HUMANITEC_LLM_PROVIDER:
        model = (
            override.model
            or platform_default_model(capability, override.provider)
            or HUMANITEC_LLM_AUTO_MODEL
        )
        resolved = CompanyResolvedLLM(
            provider=HUMANITEC_LLM_PROVIDER,
            model=str(model).strip(),
            cost_origin=COST_ORIGIN_PLATFORM,
            custom_provider_id=None,
        )
        return _with_company_fallbacks(
            aip,
            capability,
            resolved=resolved,
            override=override,
        )

    if override.provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        custom = _resolve_custom_provider(aip, override.provider)
        model = (
            override.model
            or custom.model_by_capability.get(capability.value)
            or fallback_model
        )
        if not model or not str(model).strip():
            raise ValueError(
                f"capability {capability.value}: для custom_provider {custom.id!r} не задана "
                + f"модель (model_by_capability[{capability.value}] или override.model)"
            )
        resolved = CompanyResolvedLLM(
            provider=CUSTOM_PROVIDER_SLUG,
            model=str(model).strip(),
            api_key=decrypt_secret(custom.api_key_encrypted),
            base_url=custom.base_url,
            extra_request_headers=dict(custom.extra_request_headers or {}) or None,
            extra_request_body=dict(custom.extra_request_body or {}) or None,
            cost_origin=COST_ORIGIN_COMPANY,
            custom_provider_id=custom.id,
        )
        return _with_company_fallbacks(
            aip,
            capability,
            resolved=resolved,
            override=override,
        )

    api_key = _decrypt_or_none(override.api_key_encrypted)
    has_byok = bool(api_key) or bool(override.base_url)
    cost_origin = COST_ORIGIN_COMPANY if has_byok else COST_ORIGIN_PLATFORM

    model = override.model or platform_default_model(capability, override.provider) or fallback_model
    if not model or not str(model).strip():
        raise ValueError(
            f"capability {capability.value}: не удалось определить model "
            + f"для provider {override.provider!r} (нет в platform_defaults и override.model пуст)"
        )

    resolved = CompanyResolvedLLM(
        provider=override.provider,
        model=str(model).strip(),
        api_key=api_key,
        base_url=override.base_url,
        folder_id=override.folder_id,
        extra_request_headers=dict(override.extra_request_headers or {}) or None,
        cost_origin=cost_origin,
        custom_provider_id=None,
    )
    return _with_company_fallbacks(
        aip,
        capability,
        resolved=resolved,
        override=override,
    )


def resolve_company_custom_llm_provider_ref(
    provider_ref: str,
    *,
    capability: AICapability = AICapability.LLM_CHAT,
    model: str | None = None,
) -> CompanyResolvedLLM:
    """
    Разворачивает прямой ``custom:<id>`` ref в параметры LLM route.

    Используется там, где пользователь явно выбрал custom provider в конфиге ноды,
    LLM-ресурса или sandbox capability. Это отличается от
    ``resolve_company_llm(...)``: здесь не требуется capability override, нужна
    только запись в ``custom_providers`` и поддержка указанной capability.
    """
    if capability not in {
        AICapability.LLM_CHAT,
        AICapability.LLM_SUMMARIZE,
        AICapability.LLM_FORMAT_MARKDOWN,
        AICapability.LLM_CODEGEN,
        AICapability.LLM_VISION,
        AICapability.IMAGE_GEN,
    }:
        raise ValueError(f"resolve_company_custom_llm_provider_ref: capability {capability} не LLM-типа")
    aip = load_company_ai_providers()
    custom = _resolve_custom_provider(aip, provider_ref)
    if capability.value not in custom.capabilities:
        raise ValueError(
            f"capability={capability.value}: custom_provider {custom.id!r} не поддерживает её "
            + f"(capabilities={custom.capabilities})"
        )
    resolved_model = model or custom.model_by_capability.get(capability.value)
    if not resolved_model or not str(resolved_model).strip():
        raise ValueError(
            f"capability {capability.value}: для custom_provider {custom.id!r} не задана "
            + f"модель (model_by_capability[{capability.value}] или явный model)"
        )
    return CompanyResolvedLLM(
        provider=CUSTOM_PROVIDER_SLUG,
        model=str(resolved_model).strip(),
        api_key=decrypt_secret(custom.api_key_encrypted),
        base_url=custom.base_url,
        extra_request_headers=dict(custom.extra_request_headers or {}) or None,
        extra_request_body=dict(custom.extra_request_body or {}) or None,
        cost_origin=COST_ORIGIN_COMPANY,
        custom_provider_id=custom.id,
    )


def resolve_company_embedding() -> CompanyResolvedEmbedding | None:
    """Резолв embedding override (provider + опц. ключ + URL); None если override не задан."""
    aip = load_company_ai_providers()
    if aip.embedding is None:
        return None
    ov = aip.embedding

    if ov.provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        custom = _resolve_custom_provider(aip, ov.provider)
        model = ov.model or custom.model_by_capability.get(AICapability.EMBEDDING.value)
        if not model:
            raise ValueError(
                f"capability=embedding: custom_provider {custom.id!r} не задал model_by_capability['embedding']"
            )
        return CompanyResolvedEmbedding(
            provider=CUSTOM_PROVIDER_SLUG,
            model=str(model).strip(),
            base_url=custom.base_url,
            api_key=decrypt_secret(custom.api_key_encrypted),
            extra_request_headers=dict(custom.extra_request_headers or {}) or None,
            cost_origin=COST_ORIGIN_COMPANY,
            custom_provider_id=custom.id,
            dimension=ov.dimension,
            mrl_output_dimension=ov.mrl_output_dimension,
        )

    api_key = _decrypt_or_none(ov.api_key_encrypted)
    has_byok = bool(api_key) or bool(ov.base_url)
    cost_origin = COST_ORIGIN_COMPANY if has_byok else COST_ORIGIN_PLATFORM

    return CompanyResolvedEmbedding(
        provider=ov.provider,
        model=ov.model,
        base_url=ov.base_url or "",
        api_key=api_key,
        extra_request_headers=dict(ov.extra_request_headers or {}) or None,
        cost_origin=cost_origin,
        custom_provider_id=None,
        dimension=ov.dimension,
        mrl_output_dimension=ov.mrl_output_dimension,
    )


def resolve_company_rerank() -> CompanyResolvedRerank | None:
    """
    Резолв rerank override.

    Возвращает None если ``CompanyRerankOverride`` не задан (использовать глобальные настройки),
    либо ``CompanyResolvedRerank(enabled=False)`` для явного отключения, либо параметры HTTP-клиента.
    """
    aip = load_company_ai_providers()
    ov: CompanyRerankOverride | None = aip.rerank
    if ov is None:
        return None

    if not ov.enabled:
        return CompanyResolvedRerank(
            enabled=False,
            provider=None,
            model=None,
            url=None,
            api_key=None,
            extra_request_headers=None,
            cost_origin=COST_ORIGIN_PLATFORM,
        )
    provider = ov.provider
    if provider is None:
        raise ValueError("rerank.provider обязателен при enabled=true")
    if provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        custom = _resolve_custom_provider(aip, provider)
        if not custom.rerank_path:
            raise ValueError(
                f"rerank: custom_provider {custom.id!r} не задал rerank_path"
            )
        model = ov.model or custom.model_by_capability.get(AICapability.RERANK.value)
        if not model or not str(model).strip():
            raise ValueError(
                f"capability=rerank: custom_provider {custom.id!r} не задал model"
            )
        url = custom.base_url.rstrip("/") + custom.rerank_path
        return CompanyResolvedRerank(
            enabled=True,
            provider=CUSTOM_PROVIDER_SLUG,
            model=str(model).strip(),
            url=url,
            api_key=decrypt_secret(custom.api_key_encrypted),
            extra_request_headers=dict(custom.extra_request_headers or {}) or None,
            cost_origin=COST_ORIGIN_COMPANY,
            billing_resource_id=str(model).strip(),
            custom_provider_id=custom.id,
        )
    api_key = _decrypt_or_none(ov.api_key_encrypted)
    has_byok = bool(api_key) or bool(ov.base_url)
    cost_origin = COST_ORIGIN_COMPANY if has_byok else COST_ORIGIN_PLATFORM
    model = ov.model
    if not model or not str(model).strip():
        raise ValueError(f"rerank: model обязателен для provider={provider!r}")
    return CompanyResolvedRerank(
        enabled=True,
        provider=provider,
        model=str(model).strip(),
        url=ov.base_url,
        api_key=api_key,
        extra_request_headers=dict(ov.extra_request_headers or {}) or None,
        cost_origin=cost_origin,
        billing_resource_id=str(model).strip(),
        custom_provider_id=None,
    )


def resolve_company_voice(capability: AICapability) -> CompanyResolvedVoice | None:
    """Резолв voice override (stt/tts/vad). None если override не задан."""
    if capability not in (AICapability.VOICE_STT, AICapability.VOICE_TTS, AICapability.VOICE_VAD):
        raise ValueError(f"resolve_company_voice: capability {capability} не voice")
    aip = load_company_ai_providers()
    ov_raw = aip.get_capability_override(capability)
    if ov_raw is None:
        return None
    if not isinstance(ov_raw, CompanyVoiceOverride):
        raise TypeError(f"resolve_company_voice: override {capability.value} должен быть CompanyVoiceOverride")
    ov = ov_raw
    if ov.provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        if capability == AICapability.VOICE_VAD:
            raise ValueError("voice_vad: custom провайдеры не поддерживаются")
        custom = _resolve_custom_provider(aip, ov.provider)
        model = ov.model or custom.model_by_capability.get(capability.value)
        return CompanyResolvedVoice(
            provider=CUSTOM_PROVIDER_SLUG,
            model=str(model).strip() if model else None,
            voice=ov.voice,
            language=ov.language,
            sample_rate=ov.sample_rate,
            api_key=decrypt_secret(custom.api_key_encrypted),
            base_url=custom.base_url,
            folder_id=ov.folder_id,
            extra_request_headers=dict(custom.extra_request_headers or {}) or None,
            cost_origin=COST_ORIGIN_COMPANY,
            custom_provider_id=custom.id,
        )

    api_key = _decrypt_or_none(ov.api_key_encrypted)
    has_byok = bool(api_key) or bool(ov.base_url)
    cost_origin = COST_ORIGIN_COMPANY if has_byok else COST_ORIGIN_PLATFORM
    return CompanyResolvedVoice(
        provider=ov.provider,
        model=ov.model,
        voice=ov.voice,
        language=ov.language,
        sample_rate=ov.sample_rate,
        api_key=api_key,
        base_url=ov.base_url,
        folder_id=ov.folder_id,
        extra_request_headers=dict(ov.extra_request_headers or {}) or None,
        cost_origin=cost_origin,
    )


__all__ = [
    "COST_ORIGIN_COMPANY",
    "COST_ORIGIN_PLATFORM",
    "CostOrigin",
    "CompanyResolvedEmbedding",
    "CompanyResolvedLLM",
    "CompanyResolvedRerank",
    "CompanyResolvedVoice",
    "load_company_ai_providers",
    "resolve_company_embedding",
    "resolve_company_custom_llm_provider_ref",
    "resolve_company_llm",
    "resolve_company_rerank",
    "resolve_company_voice",
]
