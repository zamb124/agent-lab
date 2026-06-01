"""
AI providers CRUD: capability override и custom OpenAI-compatible провайдеры компании.

Хранилище — ``Company.metadata['ai_providers']`` (см. ``core.company_ai.schema``).
Секреты шифруются Fernet (``core.company_ai.crypto``).

Endpoints:

- ``GET    /frontend/api/settings/ai-providers``                — снимок: capabilities + custom + catalog.
- ``PUT    /frontend/api/settings/ai-providers/llm-context``    — company default контекстного слоя.
- ``DELETE /frontend/api/settings/ai-providers/llm-context``    — снять company default контекстного слоя.
- ``PUT    /frontend/api/settings/ai-providers/{capability}``   — задать/обновить capability override.
- ``DELETE /frontend/api/settings/ai-providers/{capability}``   — снять override capability.
- ``POST   /frontend/api/settings/ai-providers/custom``         — создать custom-провайдера.
- ``PATCH  /frontend/api/settings/ai-providers/custom/{id}``    — обновить custom-провайдера.
- ``DELETE /frontend/api/settings/ai-providers/custom/{id}``    — удалить custom-провайдера.
- ``GET    /frontend/api/settings/ai-providers/resolved``       — диагностика: эффективные значения.
"""

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import (
    AIProvidersCapabilityUpdate,
    CustomProviderCreate,
    CustomProviderUpdate,
)
from core.ai_provider_catalog import (
    LLM_CAPABILITIES,
    VOICE_CAPABILITIES,
    AICapability,
    platform_provider_specs_for_capability,
    validate_platform_provider_for_capability,
)
from core.clients.llm.model_routing import (
    HUMANITEC_LLM_PROVIDER,
    OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
)
from core.clients.llm.platform_free_models import read_humanitec_llms_model_options
from core.company_ai import (
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
    resolve_embedding_for_company,
    resolve_llm_for_capability,
    resolve_rerank_for_company,
    resolve_voice_for_company,
)
from core.config import get_settings
from core.context import clear_context, require_context, set_context
from core.llm_context import LLMContextPatch
from core.llm_context.resolver import resolve_llm_context_policy
from core.logging import get_logger
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.types import JsonObject, require_json_object

if TYPE_CHECKING:
    from apps.frontend.container import FrontendContainer

logger = get_logger(__name__)
router = APIRouter(prefix="/api/settings/ai-providers", tags=["settings", "ai-providers"])


_LLM_CAPABILITIES: tuple[AICapability, ...] = LLM_CAPABILITIES
_VOICE_CAPABILITIES: tuple[AICapability, ...] = VOICE_CAPABILITIES


def _require_admin() -> tuple[User, Company]:
    context = require_context()
    company = context.active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    user = context.user
    roles = _current_company_roles(user, company)
    if "owner" not in roles and "admin" not in roles and user.user_id != company.owner_user_id:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return user, company


def _current_company_roles(user: User, company: Company) -> set[str]:
    """Roles for the active company, accepting both sides of the platform membership mirror."""
    company_id = company.company_id

    roles: set[str] = set(company.members.get(user.user_id, []) or [])
    roles.update(user.companies.get(company_id, []) or [])

    if company_id == "system" and "admin" in user.groups:
        roles.add("admin")

    return roles


def _load_aip(company: Company) -> CompanyAIProviders:
    try:
        return CompanyAIProviders.from_metadata(company.metadata)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=500, detail=f"company.metadata.ai_providers повреждён: {exc}")


async def _save_aip(
    company: Company,
    container: "FrontendContainer",
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


def _capability_from_path(capability: str) -> AICapability:
    try:
        return AICapability(capability)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Неизвестная capability: {capability!r}") from exc


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
        "policy": ov.policy if ov else "inherit",
        "platform_default_provider": platform_default_provider_for_capability(AICapability.RERANK),
    }


def _voice_override_to_public(
    capability: AICapability, ov: CompanyVoiceOverride | None
) -> JsonObject:
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
        "platform_default_provider": platform_default_provider_for_capability(capability),
    }


def _llm_override_for_capability(
    aip: CompanyAIProviders,
    capability: AICapability,
) -> CompanyLLMOverride | None:
    override = aip.get_capability_override(capability)
    if override is None or isinstance(override, CompanyLLMOverride):
        return override
    raise TypeError(f"{capability.value} ожидает CompanyLLMOverride")


def _voice_override_for_capability(
    aip: CompanyAIProviders,
    capability: AICapability,
) -> CompanyVoiceOverride | None:
    override = aip.get_capability_override(capability)
    if override is None or isinstance(override, CompanyVoiceOverride):
        return override
    raise TypeError(f"{capability.value} ожидает CompanyVoiceOverride")


def _provider_catalog(
    aip: CompanyAIProviders,
    *,
    humanitec_llms_models: list[JsonObject],
    provider_models: dict[str, list[JsonObject]],
    embedding_models: dict[str, list[JsonObject]],
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
        for spec in platform_provider_specs_for_capability(
            cap,
            include_policies=cap == AICapability.RERANK,
        ):
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
                    "label": spec.label,
                    "kind": spec.kind,
                    **(
                        {
                            "models": humanitec_llms_models,
                            "tooltip_key": (
                                "settings_page.ai_providers.humanitec_llms_provider_tooltip"
                            ),
                        }
                        if p == HUMANITEC_LLM_PROVIDER
                        else (
                            {"models": provider_models[p]}
                            if cap in _LLM_CAPABILITIES and p in provider_models and provider_models[p]
                            else (
                                {"models": embedding_models[p]}
                                if cap == AICapability.EMBEDDING
                                and p in embedding_models
                                and embedding_models[p]
                                else {}
                            )
                        )
                    ),
                }
            )
        for cp in aip.custom_providers:
            if cap.value in cp.capabilities and (
                cap != AICapability.RERANK or cp.rerank_path
            ):
                items.append(
                    {
                        "value": f"custom:{cp.id}",
                        "label": cp.label,
                        "kind": "custom",
                        "custom_id": cp.id,
                    }
                )
        catalog[cap.value] = items

    return catalog


async def _provider_model_options(container: "FrontendContainer") -> dict[str, list[JsonObject]]:
    options: dict[str, list[JsonObject]] = {}
    for provider in OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER:
        rows = await container.flows_llm_model_repository.list_by_provider_capability(
            provider,
            AICapability.LLM_CHAT,
        )
        model_ids = sorted({row.model_id.strip() for row in rows if row.model_id.strip()})
        if not model_ids:
            continue
        options[provider] = [
            {
                "value": model_id,
                "label": model_id,
                "kind": "provider_model",
            }
            for model_id in model_ids
        ]
    return options


async def _embedding_model_options(container: "FrontendContainer") -> dict[str, list[JsonObject]]:
    settings = get_settings()
    storage_dimension = settings.rag.embedding.api.dimension
    options: dict[str, list[JsonObject]] = {}
    for spec in platform_provider_specs_for_capability(AICapability.EMBEDDING):
        provider_options: list[JsonObject] = []
        rows = await container.flows_llm_model_repository.list_by_provider_capability(
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


def _build_llm_override(capability: AICapability, payload: AIProvidersCapabilityUpdate) -> CompanyLLMOverride:
    provider = payload.provider.strip()
    if provider != HUMANITEC_LLM_PROVIDER and not provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        if payload.model is None or not payload.model.strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    f"capability {capability.value}: model обязателен для provider={provider!r}; "
                    + "auto доступен только через Humanitec LLMs"
                ),
            )
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
    container: "FrontendContainer",
) -> CompanyEmbeddingOverride:
    provider = payload.provider.strip()
    if not provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        _ = validate_platform_provider_for_capability(provider, AICapability.EMBEDDING)
    model = (payload.model or "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="capability embedding: model обязателен")

    storage_dimension = get_settings().rag.embedding.api.dimension
    if provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        if payload.dimension is None:
            raise HTTPException(
                status_code=400,
                detail="capability embedding: dimension обязателен для custom provider",
            )
        dimension = payload.dimension
        mrl_output_dimension = payload.mrl_output_dimension
    else:
        catalog_model = await container.flows_llm_model_repository.get_provider_model(
            provider,
            model,
        )
        if catalog_model is None or AICapability.EMBEDDING not in catalog_model.capabilities:
            raise HTTPException(
                status_code=400,
                detail=f"capability embedding: модель {provider}:{model} отсутствует в provider model catalog",
            )
        catalog_storage_dimension = catalog_model.storage_dimension
        if catalog_storage_dimension != storage_dimension:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"capability embedding: модель {provider}:{model} не подтверждена "
                    + f"для storage dimension={storage_dimension}"
                ),
            )
        if catalog_storage_dimension is None:
            raise HTTPException(
                status_code=400,
                detail=f"capability embedding: модель {provider}:{model} не имеет verified storage dimension",
            )
        dimension = catalog_storage_dimension
        mrl_output_dimension = catalog_model.mrl_output_dimension
        if payload.dimension is not None and payload.dimension != dimension:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"capability embedding: dimension={payload.dimension} не совпадает "
                    + f"с catalog dimension={dimension} для {provider}:{model}"
                ),
            )
        if (
            payload.mrl_output_dimension is not None
            and payload.mrl_output_dimension != mrl_output_dimension
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "capability embedding: mrl_output_dimension не совпадает "
                    + f"с catalog value={mrl_output_dimension} для {provider}:{model}"
                ),
            )

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


def _build_rerank_override(payload: AIProvidersCapabilityUpdate) -> CompanyRerankOverride:
    return CompanyRerankOverride(policy=payload.provider.strip())


def _build_voice_override(payload: AIProvidersCapabilityUpdate) -> CompanyVoiceOverride:
    encrypted = encrypt_secret(payload.api_key) if payload.api_key else None
    return CompanyVoiceOverride(
        provider=payload.provider.strip(),
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


@router.get("")
async def get_ai_providers(container: ContainerDep) -> JsonObject:
    _, company = _require_admin()
    aip = _load_aip(company)
    humanitec_llms_models = await read_humanitec_llms_model_options(container.redis_client)
    provider_models = await _provider_model_options(container)
    embedding_models = await _embedding_model_options(container)
    return {
        "capabilities": _public_capabilities(aip),
        "custom_providers": [_custom_provider_to_public(p) for p in aip.custom_providers],
        "catalog": _provider_catalog(
            aip,
            humanitec_llms_models=humanitec_llms_models,
            provider_models=provider_models,
            embedding_models=embedding_models,
        ),
        "llm_context": _public_llm_context(aip),
    }


@router.put("/llm-context")
async def put_llm_context(
    payload: LLMContextPatch,
    container: ContainerDep,
) -> JsonObject:
    _, company = _require_admin()
    aip = _load_aip(company)
    try:
        patch = LLMContextPatch.model_validate(
            require_json_object(
                payload.model_dump(mode="json", exclude_none=True),
                "LLMContextPatch",
            )
        )
        _ = resolve_llm_context_policy(config=get_settings().llm_context, company=patch)
        updated_aip = aip.model_copy(update={"llm_context": patch})
        updated_aip = _validated_ai_providers(updated_aip)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _save_aip(company, container, updated_aip)
    logger.info(
        "ai_providers PUT llm_context company=%s",
        company.company_id,
    )
    return {"success": True}


@router.delete("/llm-context")
async def delete_llm_context(container: ContainerDep) -> JsonObject:
    _, company = _require_admin()
    aip = _load_aip(company)
    updated_aip = aip.model_copy(update={"llm_context": None})
    updated_aip = _validated_ai_providers(updated_aip)
    await _save_aip(company, container, updated_aip)
    logger.info(
        "ai_providers DELETE llm_context company=%s",
        company.company_id,
    )
    return {"success": True}


@router.put("/{capability}")
async def put_capability(
    capability: str,
    payload: AIProvidersCapabilityUpdate,
    container: ContainerDep,
) -> JsonObject:
    _, company = _require_admin()
    cap = _capability_from_path(capability)
    aip = _load_aip(company)

    try:
        if cap in _LLM_CAPABILITIES:
            updated_override: (
                CompanyLLMOverride
                | CompanyEmbeddingOverride
                | CompanyRerankOverride
                | CompanyVoiceOverride
            ) = _build_llm_override(cap, payload)
        elif cap == AICapability.EMBEDDING:
            updated_override = await _build_embedding_override(payload, container)
        elif cap == AICapability.RERANK:
            updated_override = _build_rerank_override(payload)
        elif cap in _VOICE_CAPABILITIES:
            updated_override = _build_voice_override(payload)
        else:
            raise HTTPException(status_code=400, detail=f"Capability {capability} не поддерживается")
        updated_aip = aip.model_copy(update={cap.value: updated_override})
        updated_aip = _validated_ai_providers(updated_aip)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _save_aip(company, container, updated_aip)
    logger.info(
        "ai_providers PUT capability=%s company=%s provider=%s",
        capability,
        company.company_id,
        payload.provider,
    )
    return {"success": True}


@router.delete("/{capability}")
async def delete_capability(
    capability: str,
    container: ContainerDep,
) -> JsonObject:
    _, company = _require_admin()
    cap = _capability_from_path(capability)
    aip = _load_aip(company)
    updated_aip = aip.model_copy(update={cap.value: None})
    updated_aip = _validated_ai_providers(updated_aip)
    await _save_aip(company, container, updated_aip)
    logger.info(
        "ai_providers DELETE capability=%s company=%s",
        capability,
        company.company_id,
    )
    return {"success": True}


@router.post("/custom")
async def create_custom_provider(
    payload: CustomProviderCreate,
    container: ContainerDep,
) -> JsonObject:
    _, company = _require_admin()
    aip = _load_aip(company)

    if any(p.id == payload.id for p in aip.custom_providers):
        raise HTTPException(status_code=400, detail=f"custom provider {payload.id!r} уже существует")

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
        updated_providers = list(aip.custom_providers) + [built_provider]
        updated_aip = aip.model_copy(update={"custom_providers": updated_providers})
        updated_aip = _validated_ai_providers(updated_aip)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _save_aip(company, container, updated_aip)
    return {"success": True, "id": built_provider.id}


@router.patch("/custom/{provider_id}")
async def update_custom_provider(
    provider_id: str,
    payload: CustomProviderUpdate,
    container: ContainerDep,
) -> JsonObject:
    _, company = _require_admin()
    aip = _load_aip(company)

    try:
        existing = aip.find_custom(provider_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"custom provider {provider_id!r} не найден")

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
                payload.extra_request_body
                if payload.extra_request_body is not None
                else existing.extra_request_body
            ),
            rerank_path=(
                payload.rerank_path if payload.rerank_path is not None else existing.rerank_path
            ),
            capabilities=(
                payload.capabilities if payload.capabilities is not None else existing.capabilities
            ),
            model_by_capability=(
                payload.model_by_capability
                if payload.model_by_capability is not None
                else existing.model_by_capability
            ),
        )
        updated_providers = [built_provider if p.id == provider_id else p for p in aip.custom_providers]
        updated_aip = aip.model_copy(update={"custom_providers": updated_providers})
        updated_aip = _validated_ai_providers(updated_aip)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _save_aip(company, container, updated_aip)
    return {"success": True}


@router.delete("/custom/{provider_id}")
async def delete_custom_provider(
    provider_id: str,
    container: ContainerDep,
) -> JsonObject:
    _, company = _require_admin()
    aip = _load_aip(company)

    if not any(p.id == provider_id for p in aip.custom_providers):
        raise HTTPException(status_code=404, detail=f"custom provider {provider_id!r} не найден")

    ref = f"custom:{provider_id}"
    used_in: list[str] = []
    for cap in _LLM_CAPABILITIES:
        ov = aip.get_capability_override(cap)
        if isinstance(ov, CompanyLLMOverride) and ov.provider == ref:
            used_in.append(cap.value)
    if aip.embedding is not None and aip.embedding.provider == ref:
        used_in.append(AICapability.EMBEDDING.value)
    if aip.rerank is not None and aip.rerank.policy == ref:
        used_in.append(AICapability.RERANK.value)
    for cap in (AICapability.VOICE_STT, AICapability.VOICE_TTS):
        ov = aip.get_capability_override(cap)
        if isinstance(ov, CompanyVoiceOverride) and ov.provider == ref:
            used_in.append(cap.value)
    if used_in:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "custom_provider_in_use",
                "capabilities": used_in,
                "message": "Снимите override этих capabilities перед удалением custom провайдера",
            },
        )

    updated_providers = [p for p in aip.custom_providers if p.id != provider_id]
    updated_aip = aip.model_copy(update={"custom_providers": updated_providers})
    updated_aip = _validated_ai_providers(updated_aip)
    await _save_aip(company, container, updated_aip)
    return {"success": True}


@router.get("/resolved")
async def get_resolved() -> JsonObject:
    """Диагностика: что резолвится для текущей компании по всем capabilities."""
    user, company = _require_admin()
    ctx = Context(user=user, active_company=company, channel="settings_resolved")
    set_context(ctx)
    try:
        items: list[JsonObject] = []
        for cap in _LLM_CAPABILITIES:
            r = resolve_llm_for_capability(cap, include_platform_default=True)
            if r is None:
                items.append(
                    {
                        "capability": cap.value,
                        "resolved": False,
                        "reason": "platform_default_not_configured",
                    }
                )
            else:
                items.append(
                    {
                        "capability": cap.value,
                        "resolved": True,
                        "provider": r.provider,
                        "model": r.model,
                        "base_url": r.base_url,
                        "cost_origin": r.cost_origin,
                        "custom_provider_id": r.custom_provider_id,
                        "billing_resource_name": r.billing_resource_name,
                        "fallback_models": [
                            require_json_object(
                                fb.model_dump(mode="json", exclude_none=True),
                                "resolved fallback model",
                            )
                            for fb in (r.fallback_models or ())
                        ],
                    }
                )
        re = resolve_embedding_for_company()
        items.append(
            {
                "capability": AICapability.EMBEDDING.value,
                "resolved": re is not None,
                "provider": re.provider if re else None,
                "model": re.model if re else None,
                "dimension": re.dimension if re else None,
                "mrl_output_dimension": re.mrl_output_dimension if re else None,
                "base_url": re.base_url if re else None,
                "cost_origin": re.cost_origin if re else "platform",
                "custom_provider_id": re.custom_provider_id if re else None,
            }
        )
        rr = resolve_rerank_for_company()
        items.append(
            {
                "capability": AICapability.RERANK.value,
                "resolved": rr is not None,
                "enabled": rr.enabled if rr else None,
                "url": rr.url if rr else None,
                "cost_origin": rr.cost_origin if rr else "platform",
                "custom_provider_id": rr.custom_provider_id if rr else None,
            }
        )
        for cap in _VOICE_CAPABILITIES:
            rv = resolve_voice_for_company(cap)
            items.append(
                {
                    "capability": cap.value,
                    "resolved": rv is not None,
                    "provider": rv.provider if rv else None,
                    "model": rv.model if rv else None,
                    "cost_origin": rv.cost_origin if rv else "platform",
                    "custom_provider_id": rv.custom_provider_id if rv else None,
                }
            )
        return {"items": items}
    finally:
        clear_context()
