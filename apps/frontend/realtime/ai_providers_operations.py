"""Команды AI-провайдеров компании: capability override, custom OpenAI-compatible провайдеры, LLM-контекст.

Хранилище — ``Company.metadata['ai_providers']`` (``core.ai.company_settings.schema``),
секреты шифруются Fernet (``core.ai.company_settings.crypto``). Бренд для подписей каталога
резолвится по `public_host` из payload (REST — Host запроса, WS — `window.location.host`).
"""

from __future__ import annotations

from pydantic import Field, ValidationError

from apps.frontend.container import FrontendContainer
from apps.frontend.models import (
    AIProvidersCapabilityUpdate,
    CustomProviderCreate,
    CustomProviderUpdate,
)
from core.ai.company_settings import (
    CUSTOM_PROVIDER_REF_PREFIX,
    METADATA_KEY,
    PLATFORM_LLM_PROVIDERS,
    CompanyAIProviders,
    CompanyCustomOpenAICompatibleProvider,
    CompanyEmbeddingOverride,
    CompanyLLMOverride,
    CompanyRerankOverride,
    CompanyVoiceOverride,
    encrypt_secret,
    mask_encrypted_secret,
    platform_default_model,
    platform_default_provider_for_capability,
)
from core.ai.free_pool import read_humanitec_llms_model_options
from core.ai.providers import (
    HUMANITEC_LLM_PROVIDER,
    LLM_CAPABILITIES,
    PROVIDER_LITSERVE,
    VOICE_CAPABILITIES,
    VOICE_PROVIDER_LITSERVE,
    AICapability,
    platform_provider_spec,
    platform_provider_specs_for_capability,
    validate_platform_provider_for_capability,
)
from core.ai.resolver import resolve_ai_model
from core.config import get_settings
from core.config.models import PlatformBrandConfig
from core.context import require_active_company, reset_context, set_context
from core.errors.boundary import PlatformNotFoundError
from core.llm_context import LLMContextPatch
from core.llm_context.resolver import resolve_llm_context_policy
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.models.voice_providers_catalog import build_voice_providers_catalog_dto
from core.platform_brand.resolver import (
    UnknownPlatformDomainError,
    resolve_brand,
    resolve_context_host,
)
from core.request_scope import require_company_admin
from core.types import JsonObject, require_json_object
from core.websocket import EmptyPayload, raise_invalid

logger = get_logger(__name__)


_LLM_CAPABILITIES: tuple[AICapability, ...] = LLM_CAPABILITIES
_VOICE_CAPABILITIES: tuple[AICapability, ...] = VOICE_CAPABILITIES


class AIProvidersSnapshotPayload(StrictBaseModel):
    public_host: str | None = Field(default=None, description="Host браузера для бренда подписей каталога")


class AIProvidersCapabilityPayload(AIProvidersCapabilityUpdate):
    capability: str = Field(min_length=1)


class AIProvidersCapabilityIdPayload(StrictBaseModel):
    capability: str = Field(min_length=1)


class CustomProviderUpdatePayload(CustomProviderUpdate):
    provider_id: str = Field(min_length=1)


class CustomProviderIdPayload(StrictBaseModel):
    provider_id: str = Field(min_length=1)


class AIProvidersMutationResult(StrictBaseModel):
    success: bool = True


class CustomProviderCreated(AIProvidersMutationResult):
    id: str


async def _require_admin_company(container: FrontendContainer) -> Company:
    _ = await require_company_admin(container.authz_service)
    return require_active_company()


def _load_aip(company: Company) -> CompanyAIProviders:
    try:
        return CompanyAIProviders.from_metadata(company.metadata)
    except (ValueError, ValidationError) as exc:
        raise RuntimeError(f"company.metadata.ai_providers is corrupt: {exc}") from exc


async def _save_aip(
    company: Company,
    container: FrontendContainer,
    aip: CompanyAIProviders,
) -> None:
    metadata = dict(company.metadata)
    serialized = aip.to_metadata_dict()
    if serialized:
        metadata[METADATA_KEY] = serialized
    else:
        _ = metadata.pop(METADATA_KEY, None)
    company.metadata = metadata
    _ = await container.company_repository.set(company)


def _capability_from_payload(capability: str) -> AICapability:
    try:
        return AICapability(capability)
    except ValueError:
        raise_invalid(ValueError(f"unknown capability: {capability!r}"))


def _custom_provider_to_public(p: CompanyCustomOpenAICompatibleProvider) -> JsonObject:
    return {
        "id": p.id,
        "label": p.label,
        "base_url": p.base_url,
        "extra_request_headers": p.extra_request_headers or {},
        "extra_request_body": p.extra_request_body or {},
        "rerank_path": p.rerank_path,
        "capabilities": list(p.capabilities),
        "model_by_capability": dict(p.model_by_capability),
        "key_masked": mask_encrypted_secret(p.api_key_encrypted),
    }


def _llm_override_to_public(
    capability: AICapability, ov: CompanyLLMOverride | None
) -> JsonObject:
    return {
        "capability": capability.value,
        "kind": "llm",
        "configured": ov is not None,
        "provider": ov.provider if ov else None,
        "model": ov.model if ov else None,
        "base_url": ov.base_url if ov else None,
        "folder_id": ov.folder_id if ov else None,
        "extra_request_headers": (ov.extra_request_headers or {}) if ov else {},
        "fallback_models": (
            [
                require_json_object(
                    fb.model_dump(mode="json", exclude_none=True),
                    "LLM fallback model",
                )
                for fb in (ov.fallback_models or [])
            ]
            if ov
            else []
        ),
        "key_masked": mask_encrypted_secret(ov.api_key_encrypted) if ov and ov.api_key_encrypted else None,
        "platform_default_provider": platform_default_provider_for_capability(capability),
        "platform_default_model": platform_default_model(
            capability,
            ov.provider if (ov and ov.provider in PLATFORM_LLM_PROVIDERS) else None,
        ),
    }


def _embedding_override_to_public(ov: CompanyEmbeddingOverride | None) -> JsonObject:
    return {
        "capability": AICapability.EMBEDDING.value,
        "kind": "embedding",
        "configured": ov is not None,
        "provider": ov.provider if ov else None,
        "model": ov.model if ov else None,
        "dimension": ov.dimension if ov else None,
        "mrl_output_dimension": ov.mrl_output_dimension if ov else None,
        "base_url": ov.base_url if ov else None,
        "extra_request_headers": (ov.extra_request_headers or {}) if ov else {},
        "key_masked": mask_encrypted_secret(ov.api_key_encrypted) if ov and ov.api_key_encrypted else None,
        "platform_default_provider": platform_default_provider_for_capability(AICapability.EMBEDDING),
        "platform_default_model": get_settings().rag.embedding.api.model,
    }


def _rerank_override_to_public(ov: CompanyRerankOverride | None) -> JsonObject:
    return {
        "capability": AICapability.RERANK.value,
        "kind": "rerank",
        "configured": ov is not None,
        "enabled": ov.enabled if ov else True,
        "provider": ov.provider if ov else None,
        "model": ov.model if ov else None,
        "base_url": ov.base_url if ov else None,
        "extra_request_headers": (ov.extra_request_headers or {}) if ov else {},
        "key_masked": mask_encrypted_secret(ov.api_key_encrypted) if ov and ov.api_key_encrypted else None,
        "platform_default_provider": platform_default_provider_for_capability(AICapability.RERANK),
    }


def _voice_override_to_public(
    capability: AICapability, ov: CompanyVoiceOverride | None
) -> JsonObject:
    platform_default_provider = platform_default_provider_for_capability(capability)
    if capability == AICapability.VOICE_VAD and platform_default_provider in {"silero_local", "mock"}:
        platform_default_provider = "litserve"
    return {
        "capability": capability.value,
        "kind": "voice",
        "configured": ov is not None,
        "provider": ov.provider if ov else None,
        "model": ov.model if ov else None,
        "voice": ov.voice if ov else None,
        "language": ov.language if ov else None,
        "sample_rate": ov.sample_rate if ov else None,
        "base_url": ov.base_url if ov else None,
        "extra_request_headers": (ov.extra_request_headers or {}) if ov else {},
        "key_masked": mask_encrypted_secret(ov.api_key_encrypted) if ov and ov.api_key_encrypted else None,
        "platform_default_provider": platform_default_provider,
    }


def _llm_override_for_capability(
    aip: CompanyAIProviders,
    capability: AICapability,
) -> CompanyLLMOverride | None:
    override = aip.get_capability_override(capability)
    if override is None or isinstance(override, CompanyLLMOverride):
        return override
    raise TypeError(f"{capability.value} expects CompanyLLMOverride")


def _voice_override_for_capability(
    aip: CompanyAIProviders,
    capability: AICapability,
) -> CompanyVoiceOverride | None:
    override = aip.get_capability_override(capability)
    if override is None or isinstance(override, CompanyVoiceOverride):
        return override
    raise TypeError(f"{capability.value} expects CompanyVoiceOverride")


def _resolve_brand_for_ai_providers(host: str | None) -> PlatformBrandConfig:
    if host is not None and str(host).strip():
        try:
            return resolve_brand(str(host).strip())
        except UnknownPlatformDomainError:
            pass
    settings = get_settings()
    return settings.platform_brands[settings.primary_platform_domain]


def _provider_display_label(
    provider: str,
    default_label: str,
    brand: PlatformBrandConfig,
) -> str:
    if provider == HUMANITEC_LLM_PROVIDER:
        return brand.llms_display_label
    if provider == PROVIDER_LITSERVE:
        return brand.models_product_name
    if provider == VOICE_PROVIDER_LITSERVE:
        return brand.voice_product_name
    return default_label


def _llms_display_label_for_context() -> str:
    return _resolve_brand_for_ai_providers(resolve_context_host()).llms_display_label


def _provider_catalog(
    aip: CompanyAIProviders,
    *,
    brand: PlatformBrandConfig,
    humanitec_llms_models: list[JsonObject],
    provider_models: dict[str, dict[str, list[JsonObject]]],
    embedding_models: dict[str, list[JsonObject]],
    voice_models: dict[str, dict[str, list[JsonObject]]],
) -> JsonObject:
    """Каталог провайдеров для UI селектора (per capability)."""
    catalog: JsonObject = {}
    for cap in (
        *_LLM_CAPABILITIES,
        AICapability.EMBEDDING,
        AICapability.RERANK,
        *_VOICE_CAPABILITIES,
    ):
        items: list[JsonObject] = []
        for spec in platform_provider_specs_for_capability(cap):
            p = spec.provider
            if (
                cap == AICapability.EMBEDDING
                and spec.kind == "platform"
                and p not in embedding_models
            ):
                continue
            items.append(
                {
                    "value": p,
                    "label": _provider_display_label(p, spec.label, brand),
                    "kind": spec.kind,
                    "byok_allowed": spec.byok_allowed,
                    **(
                        {
                            "models": humanitec_llms_models,
                            "tooltip_key": (
                                "settings_page.ai_providers.humanitec_llms_provider_tooltip"
                            ),
                        }
                        if p == HUMANITEC_LLM_PROVIDER
                        else (
                            {"models": provider_models[cap.value][p]}
                            if cap in (*_LLM_CAPABILITIES, AICapability.RERANK)
                            and cap.value in provider_models
                            and p in provider_models[cap.value]
                            and provider_models[cap.value][p]
                            else (
                                {"models": embedding_models[p]}
                                if cap == AICapability.EMBEDDING
                                and p in embedding_models
                                and embedding_models[p]
                                else (
                                    {"models": voice_models[cap.value][p]}
                                    if cap in _VOICE_CAPABILITIES
                                    and cap.value in voice_models
                                    and p in voice_models[cap.value]
                                    and voice_models[cap.value][p]
                                    else {}
                                )
                            )
                        )
                    ),
                }
            )
        for cp in aip.custom_providers:
            if cap.value in cp.capabilities and (
                cap != AICapability.RERANK or cp.rerank_path
            ):
                model_for_capability = cp.model_by_capability.get(cap.value)
                items.append(
                    {
                        "value": f"custom:{cp.id}",
                        "label": cp.label,
                        "kind": "custom",
                        "custom_id": cp.id,
                        **(
                            {
                                "models": [
                                    {
                                        "value": model_for_capability,
                                        "label": model_for_capability,
                                        "kind": "custom_model",
                                    }
                                ]
                            }
                            if model_for_capability
                            else {}
                        ),
                    }
                )
        catalog[cap.value] = items

    return catalog


async def _provider_model_options(container: FrontendContainer) -> dict[str, dict[str, list[JsonObject]]]:
    options: dict[str, dict[str, list[JsonObject]]] = {}
    for cap in (*_LLM_CAPABILITIES, AICapability.RERANK):
        capability_options: dict[str, list[JsonObject]] = {}
        for spec in platform_provider_specs_for_capability(cap):
            if spec.kind != "platform":
                continue
            rows = await container.ai_model_catalog_repository.list_by_provider_capability(
                spec.provider,
                cap,
            )
            model_ids = sorted({row.model_id.strip() for row in rows if row.model_id.strip()})
            if not model_ids:
                continue
            capability_options[spec.provider] = [
                {
                    "value": model_id,
                    "label": model_id,
                    "kind": "provider_model",
                }
                for model_id in model_ids
            ]
        options[cap.value] = capability_options
    return options


async def _embedding_model_options(container: FrontendContainer) -> dict[str, list[JsonObject]]:
    settings = get_settings()
    storage_dimension = settings.rag.embedding.api.dimension
    options: dict[str, list[JsonObject]] = {}
    for spec in platform_provider_specs_for_capability(AICapability.EMBEDDING):
        provider_options: list[JsonObject] = []
        rows = await container.ai_model_catalog_repository.list_by_provider_capability(
            spec.provider,
            AICapability.EMBEDDING,
        )
        for model in rows:
            if model.storage_dimension != storage_dimension:
                continue
            provider_options.append(
                {
                    "value": model.model_id,
                    "label": model.model_id,
                    "kind": "embedding_model",
                    "native_dimension": model.native_dimension,
                    "dimension": model.storage_dimension,
                    "mrl_output_dimension": model.mrl_output_dimension,
                    "metadata_status": model.metadata_status,
                    "source": "provider_catalog",
                }
            )
        if provider_options:
            options[spec.provider] = sorted(
                provider_options,
                key=lambda item: str(item["value"]),
            )
    return options


def _model_options(values: list[str], *, kind: str = "provider_model") -> list[JsonObject]:
    return [
        {
            "value": value,
            "label": value,
            "kind": kind,
        }
        for value in values
        if value.strip()
    ]


def _voice_model_options() -> dict[str, dict[str, list[JsonObject]]]:
    settings = get_settings()
    catalog = build_voice_providers_catalog_dto(settings.provider_litserve)
    vad_models = [entry.api_model_id for entry in settings.provider_litserve.infra.vad_models]
    return {
        AICapability.VOICE_STT.value: {
            "litserve": _model_options(catalog.stt_litserve_models, kind="voice_model"),
            "cloud_ru": _model_options(catalog.cloud_ru_stt_models, kind="voice_model"),
            "yandex": _model_options(catalog.yandex_speech_models, kind="voice_model"),
            "sber": _model_options(catalog.sber_speech_models, kind="voice_model"),
        },
        AICapability.VOICE_TTS.value: {
            "litserve": _model_options(catalog.tts_litserve_models, kind="voice_model"),
            "cloud_ru": _model_options(catalog.cloud_ru_tts_models, kind="voice_model"),
            "yandex": _model_options(catalog.yandex_speech_models, kind="voice_model"),
            "sber": _model_options(catalog.sber_speech_models, kind="voice_model"),
        },
        AICapability.VOICE_VAD.value: {
            "litserve": _model_options(vad_models, kind="voice_model"),
        },
    }


def _build_llm_override(capability: AICapability, payload: AIProvidersCapabilityUpdate) -> CompanyLLMOverride:
    if payload.provider is None:
        raise_invalid(ValueError(f"capability {capability.value}: provider is required"))
    provider = payload.provider.strip()
    if provider != HUMANITEC_LLM_PROVIDER and not provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        if payload.model is None or not payload.model.strip():
            raise_invalid(ValueError((
                    f"capability {capability.value}: model is required for provider={provider!r}; "
                    + f"auto is available only via {_llms_display_label_for_context()}"
                )))
    encrypted = encrypt_secret(payload.api_key) if payload.api_key else None
    return CompanyLLMOverride(
        provider=provider,
        api_key_encrypted=encrypted,
        base_url=payload.base_url,
        folder_id=payload.folder_id,
        extra_request_headers=payload.extra_request_headers,
        model=payload.model,
        fallback_models=payload.fallback_models,
    )


async def _build_embedding_override(
    payload: AIProvidersCapabilityUpdate,
    container: FrontendContainer,
) -> CompanyEmbeddingOverride:
    if payload.provider is None:
        raise_invalid(ValueError("capability embedding: provider is required"))
    provider = payload.provider.strip()
    if not provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        _ = validate_platform_provider_for_capability(provider, AICapability.EMBEDDING)
    model = (payload.model or "").strip()
    if not model:
        raise_invalid(ValueError("capability embedding: model is required"))

    storage_dimension = get_settings().rag.embedding.api.dimension
    if provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        if payload.dimension is None:
            raise_invalid(ValueError("capability embedding: dimension is required for custom provider"))
        dimension = payload.dimension
        mrl_output_dimension = payload.mrl_output_dimension
    else:
        catalog_model = await container.ai_model_catalog_repository.get_provider_model(
            provider,
            model,
        )
        if catalog_model is None or AICapability.EMBEDDING not in catalog_model.capabilities:
            raise_invalid(ValueError(f"capability embedding: model {provider}:{model} is missing from provider model catalog"))
        catalog_storage_dimension = catalog_model.storage_dimension
        if catalog_storage_dimension != storage_dimension:
            raise_invalid(ValueError((
                    f"capability embedding: model {provider}:{model} is not verified "
                    + f"for storage dimension={storage_dimension}"
                )))
        if catalog_storage_dimension is None:
            raise_invalid(ValueError(f"capability embedding: model {provider}:{model} has no verified storage dimension"))
        dimension = catalog_storage_dimension
        mrl_output_dimension = catalog_model.mrl_output_dimension
        if payload.dimension is not None and payload.dimension != dimension:
            raise_invalid(ValueError((
                    f"capability embedding: dimension={payload.dimension} does not match "
                    + f"catalog dimension={dimension} for {provider}:{model}"
                )))
        if (
            payload.mrl_output_dimension is not None
            and payload.mrl_output_dimension != mrl_output_dimension
        ):
            raise_invalid(ValueError((
                    "capability embedding: mrl_output_dimension does not match "
                    + f"catalog value={mrl_output_dimension} for {provider}:{model}"
                )))

    encrypted = encrypt_secret(payload.api_key) if payload.api_key else None
    return CompanyEmbeddingOverride(
        provider=provider,
        api_key_encrypted=encrypted,
        base_url=payload.base_url,
        extra_request_headers=payload.extra_request_headers,
        model=model,
        dimension=dimension,
        mrl_output_dimension=mrl_output_dimension,
    )


async def _build_rerank_override(
    payload: AIProvidersCapabilityUpdate,
    container: FrontendContainer,
) -> CompanyRerankOverride:
    if payload.enabled is False:
        return CompanyRerankOverride(enabled=False)
    if payload.provider is None:
        raise_invalid(ValueError("capability rerank: provider is required"))
    provider = payload.provider.strip()
    model = (payload.model or "").strip()
    if not provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        _ = validate_platform_provider_for_capability(provider, AICapability.RERANK)
        if not model:
            raise_invalid(ValueError("capability rerank: model is required"))
        catalog_model = await container.ai_model_catalog_repository.get_provider_model(
            provider,
            model,
        )
        if catalog_model is None or AICapability.RERANK not in catalog_model.capabilities:
            raise_invalid(ValueError(f"capability rerank: model {provider}:{model} is missing from provider model catalog"))
    elif not model:
        raise_invalid(ValueError("capability rerank: model is required for custom provider"))

    encrypted = encrypt_secret(payload.api_key) if payload.api_key else None
    return CompanyRerankOverride(
        enabled=True,
        provider=provider,
        model=model,
        api_key_encrypted=encrypted,
        base_url=payload.base_url,
        extra_request_headers=payload.extra_request_headers,
    )


def _build_voice_override(
    capability: AICapability,
    payload: AIProvidersCapabilityUpdate,
) -> CompanyVoiceOverride:
    if payload.provider is None:
        raise_invalid(ValueError("capability voice: provider is required"))
    provider = validate_platform_provider_for_capability(payload.provider.strip(), capability)
    spec = platform_provider_spec(provider)
    if spec is None:
        raise_invalid(ValueError(f"capability voice: provider {provider!r} is unknown"))
    if not spec.byok_allowed and (
        payload.api_key
        or payload.base_url
        or payload.folder_id
        or payload.extra_request_headers
    ):
        raise_invalid(ValueError(f"capability {capability.value}: provider {provider!r} does not accept BYOK/base_url"))
    if payload.model:
        allowed_models: set[str] = set()
        for item in _voice_model_options().get(capability.value, {}).get(provider, []):
            value = item.get("value")
            if isinstance(value, str):
                allowed_models.add(value)
        if allowed_models and payload.model not in allowed_models:
            raise_invalid(ValueError((
                    f"capability {capability.value}: model must be one of: "
                    + ", ".join(sorted(allowed_models))
                )))
    encrypted = encrypt_secret(payload.api_key) if payload.api_key else None
    return CompanyVoiceOverride(
        provider=provider,
        api_key_encrypted=encrypted,
        base_url=payload.base_url,
        folder_id=payload.folder_id,
        extra_request_headers=payload.extra_request_headers,
        model=payload.model,
        voice=payload.voice,
        language=payload.language,
        sample_rate=payload.sample_rate,
    )


def _public_capabilities(aip: CompanyAIProviders) -> list[JsonObject]:
    items: list[JsonObject] = []
    for cap in _LLM_CAPABILITIES:
        items.append(_llm_override_to_public(cap, _llm_override_for_capability(aip, cap)))
    items.append(_embedding_override_to_public(aip.embedding))
    items.append(_rerank_override_to_public(aip.rerank))
    for cap in _VOICE_CAPABILITIES:
        items.append(_voice_override_to_public(cap, _voice_override_for_capability(aip, cap)))
    return items


def _public_llm_context(aip: CompanyAIProviders) -> JsonObject:
    settings = get_settings().llm_context
    resolved = resolve_llm_context_policy(config=settings, company=aip.llm_context)
    resolved_public = require_json_object(
        resolved.model_dump(mode="json"),
        "resolved LLM context policy",
    )
    resolved_public["profile"] = (
        aip.llm_context.profile
        if aip.llm_context is not None and aip.llm_context.profile is not None
        else settings.default_profile
    )
    return {
        "configured": aip.llm_context is not None,
        "config": (
            require_json_object(
                aip.llm_context.model_dump(mode="json", exclude_none=True),
                "company LLM context",
            )
            if aip.llm_context is not None
            else {}
        ),
        "resolved": resolved_public,
        "default_profile": settings.default_profile,
        "profiles": list(settings.profiles.keys()),
        "budgets": list(settings.budgets.keys()),
    }


def _validated_ai_providers(aip: CompanyAIProviders) -> CompanyAIProviders:
    return CompanyAIProviders.model_validate(
        require_json_object(aip.model_dump(mode="json"), "CompanyAIProviders")
    )


async def op_ai_providers_snapshot(
    payload: AIProvidersSnapshotPayload, *, user: User, container: FrontendContainer
) -> JsonObject:
    """Снимок: capabilities + custom-провайдеры + каталог селектора + LLM-контекст."""
    _ = user
    company = await _require_admin_company(container)
    aip = _load_aip(company)
    brand = _resolve_brand_for_ai_providers(payload.public_host)
    humanitec_llms_models = await read_humanitec_llms_model_options(container.redis_client)
    return {
        "capabilities": _public_capabilities(aip),
        "custom_providers": [_custom_provider_to_public(p) for p in aip.custom_providers],
        "catalog": _provider_catalog(
            aip,
            brand=brand,
            humanitec_llms_models=humanitec_llms_models,
            provider_models=await _provider_model_options(container),
            embedding_models=await _embedding_model_options(container),
            voice_models=_voice_model_options(),
        ),
        "llm_context": _public_llm_context(aip),
    }


async def op_ai_providers_llm_context_update(
    payload: LLMContextPatch, *, user: User, container: FrontendContainer
) -> AIProvidersMutationResult:
    _ = user
    company = await _require_admin_company(container)
    aip = _load_aip(company)
    try:
        patch = LLMContextPatch.model_validate(
            require_json_object(payload.model_dump(mode="json", exclude_none=True), "LLMContextPatch")
        )
        _ = resolve_llm_context_policy(config=get_settings().llm_context, company=patch)
        updated_aip = _validated_ai_providers(aip.model_copy(update={"llm_context": patch}))
    except (ValueError, ValidationError) as exc:
        raise_invalid(exc)
    await _save_aip(company, container, updated_aip)
    logger.info("ai_providers.llm_context_updated", company_id=company.company_id)
    return AIProvidersMutationResult()


async def op_ai_providers_llm_context_remove(
    payload: EmptyPayload, *, user: User, container: FrontendContainer
) -> AIProvidersMutationResult:
    _ = payload, user
    company = await _require_admin_company(container)
    aip = _load_aip(company)
    updated_aip = _validated_ai_providers(aip.model_copy(update={"llm_context": None}))
    await _save_aip(company, container, updated_aip)
    logger.info("ai_providers.llm_context_removed", company_id=company.company_id)
    return AIProvidersMutationResult()


async def op_ai_providers_capability_update(
    payload: AIProvidersCapabilityPayload, *, user: User, container: FrontendContainer
) -> AIProvidersMutationResult:
    _ = user
    company = await _require_admin_company(container)
    cap = _capability_from_payload(payload.capability)
    aip = _load_aip(company)
    try:
        if cap in _LLM_CAPABILITIES:
            updated_override: (
                CompanyLLMOverride | CompanyEmbeddingOverride | CompanyRerankOverride | CompanyVoiceOverride
            ) = _build_llm_override(cap, payload)
        elif cap == AICapability.EMBEDDING:
            updated_override = await _build_embedding_override(payload, container)
        elif cap == AICapability.RERANK:
            updated_override = await _build_rerank_override(payload, container)
        elif cap in _VOICE_CAPABILITIES:
            updated_override = _build_voice_override(cap, payload)
        else:
            raise_invalid(ValueError(f"capability {payload.capability} is not supported"))
        updated_aip = _validated_ai_providers(aip.model_copy(update={cap.value: updated_override}))
    except (ValueError, ValidationError) as exc:
        raise_invalid(exc)
    await _save_aip(company, container, updated_aip)
    logger.info(
        "ai_providers.capability_updated",
        capability=payload.capability,
        company_id=company.company_id,
        provider=payload.provider,
    )
    return AIProvidersMutationResult()


async def op_ai_providers_capability_remove(
    payload: AIProvidersCapabilityIdPayload, *, user: User, container: FrontendContainer
) -> AIProvidersMutationResult:
    _ = user
    company = await _require_admin_company(container)
    cap = _capability_from_payload(payload.capability)
    aip = _load_aip(company)
    updated_aip = _validated_ai_providers(aip.model_copy(update={cap.value: None}))
    await _save_aip(company, container, updated_aip)
    logger.info("ai_providers.capability_removed", capability=payload.capability, company_id=company.company_id)
    return AIProvidersMutationResult()


async def op_ai_providers_custom_create(
    payload: CustomProviderCreate, *, user: User, container: FrontendContainer
) -> CustomProviderCreated:
    _ = user
    company = await _require_admin_company(container)
    aip = _load_aip(company)
    if any(p.id == payload.id for p in aip.custom_providers):
        raise_invalid(ValueError(f"custom provider {payload.id!r} already exists"))
    try:
        built_provider = CompanyCustomOpenAICompatibleProvider(
            id=payload.id,
            label=payload.label,
            base_url=payload.base_url,
            api_key_encrypted=encrypt_secret(payload.api_key),
            extra_request_headers=payload.extra_request_headers,
            extra_request_body=payload.extra_request_body,
            rerank_path=payload.rerank_path,
            capabilities=payload.capabilities,
            model_by_capability=payload.model_by_capability,
        )
        updated_aip = _validated_ai_providers(
            aip.model_copy(update={"custom_providers": [*aip.custom_providers, built_provider]})
        )
    except (ValueError, ValidationError) as exc:
        raise_invalid(exc)
    await _save_aip(company, container, updated_aip)
    return CustomProviderCreated(id=built_provider.id)


async def op_ai_providers_custom_update(
    payload: CustomProviderUpdatePayload, *, user: User, container: FrontendContainer
) -> AIProvidersMutationResult:
    _ = user
    company = await _require_admin_company(container)
    aip = _load_aip(company)
    try:
        existing = aip.find_custom(payload.provider_id)
    except KeyError as exc:
        raise PlatformNotFoundError(f"custom provider {payload.provider_id!r} not found", error_code='not_found') from exc
    try:
        api_key_encrypted = existing.api_key_encrypted
        if payload.api_key is not None and payload.api_key.strip():
            api_key_encrypted = encrypt_secret(payload.api_key)
        built_provider = CompanyCustomOpenAICompatibleProvider(
            id=existing.id,
            label=payload.label if payload.label is not None else existing.label,
            base_url=payload.base_url if payload.base_url is not None else existing.base_url,
            api_key_encrypted=api_key_encrypted,
            extra_request_headers=(
                payload.extra_request_headers
                if payload.extra_request_headers is not None
                else existing.extra_request_headers
            ),
            extra_request_body=(
                payload.extra_request_body if payload.extra_request_body is not None else existing.extra_request_body
            ),
            rerank_path=payload.rerank_path if payload.rerank_path is not None else existing.rerank_path,
            capabilities=payload.capabilities if payload.capabilities is not None else existing.capabilities,
            model_by_capability=(
                payload.model_by_capability
                if payload.model_by_capability is not None
                else existing.model_by_capability
            ),
        )
        updated_providers = [built_provider if p.id == payload.provider_id else p for p in aip.custom_providers]
        updated_aip = _validated_ai_providers(aip.model_copy(update={"custom_providers": updated_providers}))
    except (ValueError, ValidationError) as exc:
        raise_invalid(exc)
    await _save_aip(company, container, updated_aip)
    return AIProvidersMutationResult()


async def op_ai_providers_custom_remove(
    payload: CustomProviderIdPayload, *, user: User, container: FrontendContainer
) -> AIProvidersMutationResult:
    _ = user
    company = await _require_admin_company(container)
    aip = _load_aip(company)
    if not any(p.id == payload.provider_id for p in aip.custom_providers):
        raise PlatformNotFoundError(f"custom provider {payload.provider_id!r} not found", error_code='not_found')
    ref = f"custom:{payload.provider_id}"
    used_in: list[str] = []
    for cap in _LLM_CAPABILITIES:
        ov = aip.get_capability_override(cap)
        if isinstance(ov, CompanyLLMOverride) and ov.provider == ref:
            used_in.append(cap.value)
    if aip.embedding is not None and aip.embedding.provider == ref:
        used_in.append(AICapability.EMBEDDING.value)
    if aip.rerank is not None and aip.rerank.provider == ref:
        used_in.append(AICapability.RERANK.value)
    for cap in (AICapability.VOICE_STT, AICapability.VOICE_TTS):
        ov = aip.get_capability_override(cap)
        if isinstance(ov, CompanyVoiceOverride) and ov.provider == ref:
            used_in.append(cap.value)
    if used_in:
        raise_invalid(
            ValueError(
                "custom_provider_in_use: remove capability overrides before deleting the custom provider: "
                + ", ".join(used_in)
            )
        )
    updated_providers = [p for p in aip.custom_providers if p.id != payload.provider_id]
    updated_aip = _validated_ai_providers(aip.model_copy(update={"custom_providers": updated_providers}))
    await _save_aip(company, container, updated_aip)
    return AIProvidersMutationResult()


async def op_ai_providers_resolved(
    payload: EmptyPayload, *, user: User, container: FrontendContainer
) -> JsonObject:
    """Диагностика: что резолвится для текущей компании по всем capabilities."""
    _ = payload
    company = await _require_admin_company(container)
    context_token = set_context(Context(user=user, active_company=company, channel="settings_resolved"))
    try:
        items: list[JsonObject] = []
        for cap in _LLM_CAPABILITIES:
            resolved_llm = resolve_ai_model(cap, include_platform_default=True)
            if resolved_llm is None:
                items.append(
                    {"capability": cap.value, "resolved": False, "reason": "platform_default_not_configured"}
                )
                continue
            items.append(
                {
                    "capability": cap.value,
                    "resolved": True,
                    "provider": resolved_llm.provider,
                    "model": resolved_llm.model,
                    "base_url": resolved_llm.base_url,
                    "cost_origin": resolved_llm.cost_origin,
                    "custom_provider_id": resolved_llm.metadata.get("custom_provider_id"),
                    "fallback_models": list(resolved_llm.fallback_models),
                }
            )
        resolved_embedding = resolve_ai_model(AICapability.EMBEDDING, include_platform_default=True)
        items.append(
            {
                "capability": AICapability.EMBEDDING.value,
                "resolved": resolved_embedding is not None,
                "provider": resolved_embedding.provider if resolved_embedding else None,
                "model": resolved_embedding.model if resolved_embedding else None,
                "dimension": resolved_embedding.dimension if resolved_embedding else None,
                "mrl_output_dimension": resolved_embedding.mrl_output_dimension if resolved_embedding else None,
                "base_url": resolved_embedding.base_url if resolved_embedding else None,
                "cost_origin": resolved_embedding.cost_origin if resolved_embedding else "platform",
                "custom_provider_id": (
                    resolved_embedding.metadata.get("custom_provider_id") if resolved_embedding else None
                ),
            }
        )
        resolved_rerank = resolve_ai_model(AICapability.RERANK, include_platform_default=False)
        items.append(
            {
                "capability": AICapability.RERANK.value,
                "resolved": resolved_rerank is not None,
                "enabled": resolved_rerank.metadata.get("enabled") if resolved_rerank else None,
                "provider": resolved_rerank.provider if resolved_rerank else None,
                "model": resolved_rerank.model if resolved_rerank else None,
                "url": resolved_rerank.endpoint_url if resolved_rerank else None,
                "cost_origin": resolved_rerank.cost_origin if resolved_rerank else "platform",
                "custom_provider_id": resolved_rerank.metadata.get("custom_provider_id") if resolved_rerank else None,
            }
        )
        for cap in _VOICE_CAPABILITIES:
            resolved_voice = resolve_ai_model(cap, include_platform_default=False)
            items.append(
                {
                    "capability": cap.value,
                    "resolved": resolved_voice is not None,
                    "provider": resolved_voice.provider if resolved_voice else None,
                    "model": resolved_voice.model if resolved_voice else None,
                    "cost_origin": resolved_voice.cost_origin if resolved_voice else "platform",
                    "custom_provider_id": resolved_voice.metadata.get("custom_provider_id") if resolved_voice else None,
                }
            )
        return {"items": items}
    finally:
        reset_context(context_token)
