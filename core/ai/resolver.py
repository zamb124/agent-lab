"""Canonical company-aware AI capability resolver."""

from __future__ import annotations

from core.ai.adapters import create_model_catalog_adapter_registry
from core.ai.company_settings.resolver import (
    COST_ORIGIN_COMPANY,
    COST_ORIGIN_PLATFORM,
    CompanyResolvedEmbedding,
    CompanyResolvedLLM,
    CompanyResolvedRerank,
    CompanyResolvedVoice,
    CostOrigin,
    resolve_company_custom_llm_provider_ref,
    resolve_company_embedding,
    resolve_company_llm,
    resolve_company_rerank,
    resolve_company_voice,
)
from core.ai.company_settings.schema import CUSTOM_PROVIDER_SLUG
from core.ai.models import AICostOrigin, ResolvedAIModel
from core.ai.providers import LLM_CAPABILITIES, PROVIDER_LITSERVE, AICapability
from core.ai.requirements import AIRequestRequirements, AISelection
from core.config import get_settings
from core.config.llm_openai_compat import resolve_provider_api_key_for_openai_compatible_calls
from core.rag.embedding_runtime import resolve_rag_embedding_runtime
from core.types import JsonObject, require_json_object


def _cost_origin(value: CostOrigin) -> AICostOrigin:
    if value == COST_ORIGIN_COMPANY:
        return "company"
    return "platform"


def _fallback_payloads(resolved: CompanyResolvedLLM) -> tuple[JsonObject, ...]:
    if not resolved.fallback_models:
        return ()
    return tuple(
        require_json_object(
            fallback.model_dump(mode="json", exclude_none=True),
            "CompanyResolvedLLM.fallback_models[]",
        )
        for fallback in resolved.fallback_models
    )


def _from_resolved_llm(capability: AICapability, resolved: CompanyResolvedLLM) -> ResolvedAIModel:
    return ResolvedAIModel(
        capability=capability,
        provider=resolved.provider,
        model=resolved.model,
        base_url=resolved.base_url,
        api_key=resolved.api_key,
        folder_id=resolved.folder_id,
        headers=dict(resolved.extra_request_headers or {}),
        body=dict(resolved.extra_request_body or {}),
        cost_origin=_cost_origin(resolved.cost_origin),
        fallback_models=_fallback_payloads(resolved),
        metadata={"custom_provider_id": resolved.custom_provider_id},
    )


def _from_resolved_embedding(resolved: CompanyResolvedEmbedding) -> ResolvedAIModel:
    return ResolvedAIModel(
        capability=AICapability.EMBEDDING,
        provider=resolved.provider,
        model=resolved.model,
        base_url=resolved.base_url,
        api_key=resolved.api_key,
        headers=dict(resolved.extra_request_headers or {}),
        dimension=resolved.dimension,
        mrl_output_dimension=resolved.mrl_output_dimension,
        cost_origin=_cost_origin(resolved.cost_origin),
        metadata={"custom_provider_id": resolved.custom_provider_id},
    )


def _runtime_endpoint_url(
    provider: str,
    capability: AICapability,
    *,
    endpoint_override: str | None = None,
) -> str | None:
    if endpoint_override is not None and endpoint_override.strip():
        return endpoint_override.strip()
    settings = get_settings()
    registry = create_model_catalog_adapter_registry(settings)
    if not registry.has(provider):
        raise ValueError(f"provider {provider!r} не зарегистрирован в core.ai adapter registry")
    endpoint = registry.get(provider).runtime_endpoint(capability)
    if endpoint.endpoint_url is not None and endpoint.endpoint_url.strip():
        return endpoint.endpoint_url.strip()
    if capability == AICapability.RERANK and endpoint.base_url is not None and endpoint.base_url.strip():
        return f"{endpoint.base_url.strip().rstrip('/')}/rerank"
    return None


def _runtime_api_key(
    provider: str | None,
    *,
    explicit_api_key: str | None,
    cost_origin: CostOrigin,
) -> str | None:
    if explicit_api_key is not None and explicit_api_key.strip():
        return explicit_api_key
    if cost_origin == COST_ORIGIN_COMPANY:
        return None
    if provider is None or provider in {CUSTOM_PROVIDER_SLUG, PROVIDER_LITSERVE}:
        return None
    return resolve_provider_api_key_for_openai_compatible_calls(get_settings().llm, provider)


def _from_resolved_rerank(resolved: CompanyResolvedRerank) -> ResolvedAIModel:
    endpoint_url = resolved.url
    if resolved.enabled and resolved.provider is not None and resolved.provider != CUSTOM_PROVIDER_SLUG:
        endpoint_url = _runtime_endpoint_url(
            resolved.provider,
            AICapability.RERANK,
            endpoint_override=resolved.url,
        )
    api_key = _runtime_api_key(
        resolved.provider,
        explicit_api_key=resolved.api_key,
        cost_origin=resolved.cost_origin,
    )
    return ResolvedAIModel(
        capability=AICapability.RERANK,
        provider=resolved.provider,
        model=resolved.model,
        endpoint_url=endpoint_url,
        api_key=api_key,
        headers=dict(resolved.extra_request_headers or {}),
        cost_origin=_cost_origin(resolved.cost_origin),
        metadata={
            "enabled": resolved.enabled,
            "billing_resource_id": resolved.billing_resource_id,
            "custom_provider_id": resolved.custom_provider_id,
        },
    )


def _from_resolved_voice(capability: AICapability, resolved: CompanyResolvedVoice) -> ResolvedAIModel:
    return ResolvedAIModel(
        capability=capability,
        provider=resolved.provider,
        model=resolved.model,
        base_url=resolved.base_url,
        api_key=resolved.api_key,
        folder_id=resolved.folder_id,
        headers=dict(resolved.extra_request_headers or {}),
        cost_origin=_cost_origin(resolved.cost_origin),
        metadata={
            "voice": resolved.voice,
            "language": resolved.language,
            "sample_rate": resolved.sample_rate,
            "custom_provider_id": resolved.custom_provider_id,
        },
    )


def _resolve_platform_embedding_default() -> CompanyResolvedEmbedding:
    settings = get_settings()
    runtime = resolve_rag_embedding_runtime(
        settings.rag.embedding,
        settings.llm,
        settings.provider_litserve,
    )
    return CompanyResolvedEmbedding(
        provider=runtime.provider,
        model=runtime.model,
        base_url=runtime.base_url,
        extra_request_headers=runtime.extra_request_headers,
        cost_origin=COST_ORIGIN_PLATFORM,
        dimension=runtime.dimension,
        mrl_output_dimension=runtime.mrl_output_dimension,
    )


def _resolve_platform_rerank_default() -> CompanyResolvedRerank:
    settings = get_settings()
    rr = settings.rag.reranker
    model = (
        None
        if rr.provider == PROVIDER_LITSERVE and rr.billing_model_id == "rerank"
        else rr.billing_model_id
    )
    return CompanyResolvedRerank(
        enabled=rr.enabled,
        provider=rr.provider if rr.enabled else None,
        model=model if rr.enabled else None,
        url=rr.base_url if rr.enabled else None,
        api_key=None,
        extra_request_headers=None,
        cost_origin=COST_ORIGIN_PLATFORM,
        billing_resource_id=rr.billing_model_id,
        custom_provider_id=None,
    )


def _validate_resolved_requirements(
    resolved: ResolvedAIModel,
    requirements: AIRequestRequirements,
) -> None:
    if resolved.capability == AICapability.EMBEDDING and requirements.embedding_dimension is not None:
        if resolved.dimension != requirements.embedding_dimension:
            raise ValueError(
                "embedding dimension mismatch: "
                + f"required={requirements.embedding_dimension}, resolved={resolved.dimension}, "
                + f"provider={resolved.provider!r}, model={resolved.model!r}"
            )
    if requirements.free_only and resolved.model_record is not None and resolved.model_record.is_free is not True:
        raise ValueError(
            f"capability {resolved.capability.value}: resolved model "
            + f"{resolved.provider}:{resolved.model} is not free"
        )


def _resolve_explicit_llm_selection(
    capability: AICapability,
    selection: AISelection,
) -> ResolvedAIModel | None:
    if selection.provider is None:
        return None
    if selection.provider.startswith("custom:"):
        return _from_resolved_llm(
            capability,
            resolve_company_custom_llm_provider_ref(
                selection.provider,
                capability=capability,
                model=selection.model,
            ),
        )
    if selection.model is None:
        return None
    return ResolvedAIModel(
        capability=capability,
        provider=selection.provider,
        model=selection.model,
        cost_origin="platform",
        fallback_models=tuple(
            require_json_object(
                {"provider": provider, "model": model},
                "AISelection.fallback_models[]",
            )
            for provider, model in selection.fallback_models
        ),
    )


def resolve_ai_model(
    capability: AICapability,
    requirements: AIRequestRequirements | None = None,
    selection: AISelection | None = None,
    *,
    include_platform_default: bool = True,
) -> ResolvedAIModel | None:
    """Resolve any AI capability into the single runtime model contract."""
    req = requirements or AIRequestRequirements()
    if capability in LLM_CAPABILITIES:
        explicit = _resolve_explicit_llm_selection(capability, selection) if selection else None
        if explicit is not None:
            _validate_resolved_requirements(explicit, req)
            return explicit
        resolved_llm = resolve_company_llm(
            capability,
            include_platform_default=include_platform_default,
        )
        if resolved_llm is None:
            return None
        resolved_ai = _from_resolved_llm(capability, resolved_llm)
        _validate_resolved_requirements(resolved_ai, req)
        return resolved_ai

    if capability == AICapability.EMBEDDING:
        resolved_embedding = resolve_company_embedding()
        if resolved_embedding is None and include_platform_default:
            resolved_embedding = _resolve_platform_embedding_default()
        if resolved_embedding is None:
            return None
        resolved_ai = _from_resolved_embedding(resolved_embedding)
        _validate_resolved_requirements(resolved_ai, req)
        return resolved_ai

    if capability == AICapability.RERANK:
        resolved_rerank = resolve_company_rerank()
        if resolved_rerank is None and include_platform_default:
            resolved_rerank = _resolve_platform_rerank_default()
        if resolved_rerank is None:
            return None
        resolved_ai = _from_resolved_rerank(resolved_rerank)
        _validate_resolved_requirements(resolved_ai, req)
        return resolved_ai

    if capability in (AICapability.VOICE_STT, AICapability.VOICE_TTS, AICapability.VOICE_VAD):
        resolved_voice = resolve_company_voice(capability)
        if resolved_voice is None:
            return None
        resolved_ai = _from_resolved_voice(capability, resolved_voice)
        _validate_resolved_requirements(resolved_ai, req)
        return resolved_ai

    raise ValueError(f"resolve_ai_model: неизвестная capability {capability!r}")


__all__ = [
    "COST_ORIGIN_COMPANY",
    "COST_ORIGIN_PLATFORM",
    "AICapability",
    "CostOrigin",
    "ResolvedAIModel",
    "resolve_ai_model",
]
