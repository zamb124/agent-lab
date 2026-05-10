"""
AI providers CRUD: capability override и custom OpenAI-compatible провайдеры компании.

Хранилище — ``Company.metadata['ai_providers']`` (см. ``core.company_ai.schema``).
Секреты шифруются Fernet (``core.company_ai.crypto``).

Endpoints:

- ``GET    /frontend/api/settings/ai-providers``                — снимок: capabilities + custom + catalog.
- ``PUT    /frontend/api/settings/ai-providers/{capability}``   — задать/обновить capability override.
- ``DELETE /frontend/api/settings/ai-providers/{capability}``   — снять override capability.
- ``POST   /frontend/api/settings/ai-providers/custom``         — создать custom-провайдера.
- ``PATCH  /frontend/api/settings/ai-providers/custom/{id}``    — обновить custom-провайдера.
- ``DELETE /frontend/api/settings/ai-providers/custom/{id}``    — удалить custom-провайдера.
- ``GET    /frontend/api/settings/ai-providers/resolved``       — диагностика: эффективные значения.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import (
    AIProvidersCapabilityUpdate,
    CustomProviderCreate,
    CustomProviderUpdate,
)
from core.company_ai import (
    AICapability,
    CompanyAIProviders,
    CompanyCustomOpenAICompatibleProvider,
    CompanyEmbeddingOverride,
    CompanyLLMOverride,
    CompanyRerankOverride,
    CompanyVoiceOverride,
    METADATA_KEY,
    PLATFORM_LLM_PROVIDERS,
    encrypt_secret,
    mask_encrypted_secret,
    platform_default_model,
    platform_default_provider_for_capability,
    resolve_embedding_for_company,
    resolve_llm_for_capability,
    resolve_rerank_for_company,
    resolve_voice_for_company,
)
from core.context import set_context, clear_context
from core.models.context_models import Context
from core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/settings/ai-providers", tags=["settings", "ai-providers"])


_LLM_CAPABILITIES: tuple[AICapability, ...] = (
    AICapability.LLM_CHAT,
    AICapability.LLM_SUMMARIZE,
    AICapability.LLM_FORMAT_MARKDOWN,
    AICapability.LLM_CODEGEN,
    AICapability.LLM_VISION,
    AICapability.IMAGE_GEN,
)
_VOICE_CAPABILITIES: tuple[AICapability, ...] = (
    AICapability.VOICE_STT,
    AICapability.VOICE_TTS,
    AICapability.VOICE_VAD,
)


def _require_admin(request: Request) -> None:
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    if not hasattr(request.state, "company") or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    company = request.state.company
    user = request.state.user
    roles = company.members.get(user.user_id, [])
    if "owner" not in roles and "admin" not in roles:
        raise HTTPException(status_code=403, detail="Недостаточно прав")


def _load_aip(request: Request) -> CompanyAIProviders:
    company = request.state.company
    try:
        return CompanyAIProviders.from_metadata(company.metadata or {})
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=500, detail=f"company.metadata.ai_providers повреждён: {exc}")


async def _save_aip(request: Request, container, aip: CompanyAIProviders) -> None:
    company = request.state.company
    metadata = dict(company.metadata or {})
    serialized = aip.to_metadata_dict()
    if serialized:
        metadata[METADATA_KEY] = serialized
    else:
        metadata.pop(METADATA_KEY, None)
    company.metadata = metadata
    await container.company_repository.set(company)


def _capability_from_path(capability: str) -> AICapability:
    try:
        return AICapability(capability)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Неизвестная capability: {capability!r}") from exc


def _custom_provider_to_public(p: CompanyCustomOpenAICompatibleProvider) -> dict[str, Any]:
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
) -> dict[str, Any]:
    return {
        "capability": capability.value,
        "kind": "llm",
        "configured": ov is not None,
        "provider": ov.provider if ov else None,
        "model": ov.model if ov else None,
        "base_url": ov.base_url if ov else None,
        "folder_id": ov.folder_id if ov else None,
        "extra_request_headers": (ov.extra_request_headers or {}) if ov else {},
        "key_masked": mask_encrypted_secret(ov.api_key_encrypted) if ov and ov.api_key_encrypted else None,
        "platform_default_provider": platform_default_provider_for_capability(capability),
        "platform_default_model": platform_default_model(
            capability,
            ov.provider if (ov and ov.provider in PLATFORM_LLM_PROVIDERS) else None,
        ),
    }


def _embedding_override_to_public(ov: CompanyEmbeddingOverride | None) -> dict[str, Any]:
    return {
        "capability": AICapability.EMBEDDING.value,
        "kind": "embedding",
        "configured": ov is not None,
        "provider": ov.provider if ov else None,
        "base_url": ov.base_url if ov else None,
        "extra_request_headers": (ov.extra_request_headers or {}) if ov else {},
        "key_masked": mask_encrypted_secret(ov.api_key_encrypted) if ov and ov.api_key_encrypted else None,
        "platform_default_provider": platform_default_provider_for_capability(AICapability.EMBEDDING),
    }


def _rerank_override_to_public(ov: CompanyRerankOverride | None) -> dict[str, Any]:
    return {
        "capability": AICapability.RERANK.value,
        "kind": "rerank",
        "configured": ov is not None,
        "policy": ov.policy if ov else "inherit",
        "platform_default_provider": platform_default_provider_for_capability(AICapability.RERANK),
    }


def _voice_override_to_public(
    capability: AICapability, ov: CompanyVoiceOverride | None
) -> dict[str, Any]:
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


def _provider_catalog(aip: CompanyAIProviders) -> dict[str, Any]:
    """Каталог провайдеров для UI селектора (per capability)."""
    catalog: dict[str, list[dict[str, Any]]] = {}
    for cap in _LLM_CAPABILITIES:
        items: list[dict[str, Any]] = [
            {"value": p, "label": p, "kind": "platform"} for p in PLATFORM_LLM_PROVIDERS
        ]
        for cp in aip.custom_providers:
            if cap.value in cp.capabilities:
                items.append(
                    {
                        "value": f"custom:{cp.id}",
                        "label": cp.label,
                        "kind": "custom",
                        "custom_id": cp.id,
                    }
                )
        catalog[cap.value] = items

    embedding_items: list[dict[str, Any]] = [
        {"value": "openrouter", "label": "openrouter", "kind": "platform"},
        {"value": "provider_litserve", "label": "provider_litserve", "kind": "platform"},
    ]
    for cp in aip.custom_providers:
        if "embedding" in cp.capabilities:
            embedding_items.append(
                {
                    "value": f"custom:{cp.id}",
                    "label": cp.label,
                    "kind": "custom",
                    "custom_id": cp.id,
                }
            )
    catalog[AICapability.EMBEDDING.value] = embedding_items

    rerank_items: list[dict[str, Any]] = [
        {"value": "inherit", "label": "inherit", "kind": "policy"},
        {"value": "none", "label": "none", "kind": "policy"},
        {"value": "provider_litserve", "label": "provider_litserve", "kind": "platform"},
    ]
    for cp in aip.custom_providers:
        if "rerank" in cp.capabilities and cp.rerank_path:
            rerank_items.append(
                {
                    "value": f"custom:{cp.id}",
                    "label": cp.label,
                    "kind": "custom",
                    "custom_id": cp.id,
                }
            )
    catalog[AICapability.RERANK.value] = rerank_items

    return catalog


def _build_llm_override(capability: AICapability, payload: AIProvidersCapabilityUpdate) -> CompanyLLMOverride:
    encrypted = encrypt_secret(payload.api_key) if payload.api_key else None
    return CompanyLLMOverride(
        provider=payload.provider.strip(),
        api_key_encrypted=encrypted,
        base_url=payload.base_url,
        folder_id=payload.folder_id,
        extra_request_headers=payload.extra_request_headers,
        model=payload.model,
    )


def _build_embedding_override(payload: AIProvidersCapabilityUpdate) -> CompanyEmbeddingOverride:
    encrypted = encrypt_secret(payload.api_key) if payload.api_key else None
    return CompanyEmbeddingOverride(
        provider=payload.provider.strip(),
        api_key_encrypted=encrypted,
        base_url=payload.base_url,
        extra_request_headers=payload.extra_request_headers,
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


def _public_capabilities(aip: CompanyAIProviders) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for cap in _LLM_CAPABILITIES:
        items.append(_llm_override_to_public(cap, aip.get_capability_override(cap)))
    items.append(_embedding_override_to_public(aip.embedding))
    items.append(_rerank_override_to_public(aip.rerank))
    for cap in _VOICE_CAPABILITIES:
        items.append(_voice_override_to_public(cap, aip.get_capability_override(cap)))
    return items


@router.get("")
async def get_ai_providers(request: Request, container: ContainerDep):
    _require_admin(request)
    aip = _load_aip(request)
    return {
        "capabilities": _public_capabilities(aip),
        "custom_providers": [_custom_provider_to_public(p) for p in aip.custom_providers],
        "catalog": _provider_catalog(aip),
    }


@router.put("/{capability}")
async def put_capability(
    capability: str,
    payload: AIProvidersCapabilityUpdate,
    request: Request,
    container: ContainerDep,
):
    _require_admin(request)
    cap = _capability_from_path(capability)
    aip = _load_aip(request)

    try:
        if cap in _LLM_CAPABILITIES:
            new_override: Any = _build_llm_override(cap, payload)
        elif cap == AICapability.EMBEDDING:
            new_override = _build_embedding_override(payload)
        elif cap == AICapability.RERANK:
            new_override = _build_rerank_override(payload)
        elif cap in _VOICE_CAPABILITIES:
            new_override = _build_voice_override(payload)
        else:
            raise HTTPException(status_code=400, detail=f"Capability {capability} не поддерживается")
        new_aip = aip.model_copy(update={cap.value: new_override})
        new_aip = CompanyAIProviders.model_validate(new_aip.model_dump())
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _save_aip(request, container, new_aip)
    logger.info(
        "ai_providers PUT capability=%s company=%s provider=%s",
        capability,
        request.state.company.company_id,
        payload.provider,
    )
    return {"success": True}


@router.delete("/{capability}")
async def delete_capability(
    capability: str,
    request: Request,
    container: ContainerDep,
):
    _require_admin(request)
    cap = _capability_from_path(capability)
    aip = _load_aip(request)
    new_aip = aip.model_copy(update={cap.value: None})
    new_aip = CompanyAIProviders.model_validate(new_aip.model_dump())
    await _save_aip(request, container, new_aip)
    logger.info(
        "ai_providers DELETE capability=%s company=%s",
        capability,
        request.state.company.company_id,
    )
    return {"success": True}


@router.post("/custom")
async def create_custom_provider(
    payload: CustomProviderCreate,
    request: Request,
    container: ContainerDep,
):
    _require_admin(request)
    aip = _load_aip(request)

    if any(p.id == payload.id for p in aip.custom_providers):
        raise HTTPException(status_code=400, detail=f"custom provider {payload.id!r} уже существует")

    try:
        new_provider = CompanyCustomOpenAICompatibleProvider(
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
        new_list = list(aip.custom_providers) + [new_provider]
        new_aip = aip.model_copy(update={"custom_providers": new_list})
        new_aip = CompanyAIProviders.model_validate(new_aip.model_dump())
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _save_aip(request, container, new_aip)
    return {"success": True, "id": new_provider.id}


@router.patch("/custom/{provider_id}")
async def update_custom_provider(
    provider_id: str,
    payload: CustomProviderUpdate,
    request: Request,
    container: ContainerDep,
):
    _require_admin(request)
    aip = _load_aip(request)

    try:
        existing = aip.find_custom(provider_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"custom provider {provider_id!r} не найден")

    update_kwargs: dict[str, Any] = {}
    if payload.label is not None:
        update_kwargs["label"] = payload.label
    if payload.base_url is not None:
        update_kwargs["base_url"] = payload.base_url
    if payload.api_key is not None and payload.api_key.strip():
        update_kwargs["api_key_encrypted"] = encrypt_secret(payload.api_key)
    if payload.extra_request_headers is not None:
        update_kwargs["extra_request_headers"] = payload.extra_request_headers or None
    if payload.extra_request_body is not None:
        update_kwargs["extra_request_body"] = payload.extra_request_body or None
    if payload.rerank_path is not None:
        update_kwargs["rerank_path"] = payload.rerank_path or None
    if payload.capabilities is not None:
        update_kwargs["capabilities"] = payload.capabilities
    if payload.model_by_capability is not None:
        update_kwargs["model_by_capability"] = payload.model_by_capability

    try:
        new_provider = existing.model_copy(update=update_kwargs)
        new_provider = CompanyCustomOpenAICompatibleProvider.model_validate(new_provider.model_dump())
        new_list = [new_provider if p.id == provider_id else p for p in aip.custom_providers]
        new_aip = aip.model_copy(update={"custom_providers": new_list})
        new_aip = CompanyAIProviders.model_validate(new_aip.model_dump())
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _save_aip(request, container, new_aip)
    return {"success": True}


@router.delete("/custom/{provider_id}")
async def delete_custom_provider(
    provider_id: str,
    request: Request,
    container: ContainerDep,
):
    _require_admin(request)
    aip = _load_aip(request)

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

    new_list = [p for p in aip.custom_providers if p.id != provider_id]
    new_aip = aip.model_copy(update={"custom_providers": new_list})
    new_aip = CompanyAIProviders.model_validate(new_aip.model_dump())
    await _save_aip(request, container, new_aip)
    return {"success": True}


@router.get("/resolved")
async def get_resolved(request: Request, container: ContainerDep):
    """Диагностика: что резолвится для текущей компании по всем capabilities."""
    _require_admin(request)
    company = request.state.company
    user = request.state.user
    ctx = Context(user=user, active_company=company, channel="settings_resolved")
    set_context(ctx)
    try:
        items: list[dict[str, Any]] = []
        for cap in _LLM_CAPABILITIES:
            r = resolve_llm_for_capability(cap)
            if r is None:
                items.append(
                    {
                        "capability": cap.value,
                        "resolved": False,
                        "reason": "no_company_override_using_platform_defaults",
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
                    }
                )
        re = resolve_embedding_for_company()
        items.append(
            {
                "capability": AICapability.EMBEDDING.value,
                "resolved": re is not None,
                "provider": re.provider if re else None,
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
