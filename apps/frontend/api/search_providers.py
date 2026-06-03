"""Company Search provider settings CRUD."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.frontend.dependencies import ContainerDep
from apps.search.config import (
    SearchLinkupConfig,
    SearchSerperConfig,
    SearchTavilyConfig,
    SearchTinyFishConfig,
    get_search_settings,
)
from core.ai.company_settings import encrypt_secret, mask_encrypted_secret
from core.company_search import (
    COMPANY_SEARCH_METADATA_KEY,
    CompanyLinkupSearchProvider,
    CompanySearchProviderBase,
    CompanySearchProviders,
    CompanySerperSearchProvider,
    CompanyTavilySearchProvider,
    CompanyTinyFishSearchProvider,
    SearchCredentialSource,
    SearchProviderId,
)
from core.context import require_context
from core.models.identity_models import Company, User
from core.types import JsonObject

if TYPE_CHECKING:
    from apps.frontend.container import FrontendContainer

router = APIRouter(prefix="/api/settings/search-providers", tags=["settings", "search-providers"])

_PROVIDER_IDS: tuple[SearchProviderId, ...] = ("tinyfish", "linkup", "serper", "tavily")


class SearchProviderUpdateRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    enabled: bool = True
    credential_source: SearchCredentialSource = "platform"
    api_key: str | None = None
    base_url: str | None = Field(default=None, min_length=1)
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=60.0)
    depth: str | None = None
    search_depth: str | None = None
    topic: str | None = None
    include_answer: bool | None = None


class SearchProviderOrderRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider_order: list[SearchProviderId]


def _require_admin() -> tuple[User, Company]:
    context = require_context()
    company = context.active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    user = context.user
    roles: set[str] = set(company.members.get(user.user_id, []) or [])
    roles.update(user.companies.get(company.company_id, []) or [])
    if company.company_id == "system" and "admin" in user.groups:
        roles.add("admin")
    if "owner" not in roles and "admin" not in roles and user.user_id != company.owner_user_id:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return user, company


def _load_settings(company: Company) -> CompanySearchProviders:
    try:
        return CompanySearchProviders.from_metadata(company.metadata)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=500, detail=f"company.metadata.search_providers повреждён: {exc}")


async def _save_settings(
    company: Company,
    container: "FrontendContainer",
    settings: CompanySearchProviders,
) -> None:
    metadata = dict(company.metadata)
    serialized = settings.to_metadata_dict()
    if serialized:
        metadata[COMPANY_SEARCH_METADATA_KEY] = serialized
    else:
        _ = metadata.pop(COMPANY_SEARCH_METADATA_KEY, None)
    company.metadata = metadata
    _ = await container.company_repository.set(company)


def _provider_id(raw: str) -> SearchProviderId:
    value = raw.strip().lower()
    if value in _PROVIDER_IDS:
        return value
    raise HTTPException(status_code=400, detail=f"Неизвестный search provider: {raw!r}")


def _api_key_encrypted(
    *,
    provider_id: SearchProviderId,
    payload: SearchProviderUpdateRequest,
    existing: CompanySearchProviderBase,
) -> str | None:
    if payload.credential_source == "platform":
        return None
    if payload.api_key is not None and payload.api_key.strip():
        return encrypt_secret(payload.api_key.strip())
    if existing.credential_source == "company" and existing.api_key_encrypted is not None:
        return existing.api_key_encrypted
    raise HTTPException(
        status_code=400,
        detail=f"API key обязателен для provider {provider_id} при credential_source='company'",
    )


def _clean_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _build_provider_override(
    provider_id: SearchProviderId,
    payload: SearchProviderUpdateRequest,
    existing: CompanySearchProviderBase,
) -> CompanySearchProviderBase:
    common: JsonObject = {
        "enabled": payload.enabled,
        "credential_source": payload.credential_source,
        "api_key_encrypted": _api_key_encrypted(
            provider_id=provider_id,
            payload=payload,
            existing=existing,
        ),
        "base_url": _clean_optional_string(payload.base_url),
        "timeout_seconds": payload.timeout_seconds,
    }
    if provider_id == "tinyfish":
        return CompanyTinyFishSearchProvider.model_validate(common)
    if provider_id == "serper":
        return CompanySerperSearchProvider.model_validate(common)
    if provider_id == "linkup":
        depth = _clean_optional_string(payload.depth)
        if depth is not None:
            common["depth"] = depth
        return CompanyLinkupSearchProvider.model_validate(common)
    if provider_id == "tavily":
        search_depth = _clean_optional_string(payload.search_depth)
        topic = _clean_optional_string(payload.topic)
        if search_depth is not None:
            common["search_depth"] = search_depth
        if topic is not None:
            common["topic"] = topic
        if payload.include_answer is not None:
            common["include_answer"] = payload.include_answer
        return CompanyTavilySearchProvider.model_validate(common)


def _provider_public(
    provider_id: SearchProviderId,
    settings: CompanySearchProviders,
) -> JsonObject:
    provider = settings.provider(provider_id)
    raw_platform_provider = _platform_provider_config(provider_id)
    platform_enabled = bool(raw_platform_provider.enabled)
    key_masked = (
        mask_encrypted_secret(provider.api_key_encrypted)
        if provider.credential_source == "company" and provider.api_key_encrypted is not None
        else None
    )
    out: JsonObject = {
        "id": provider_id,
        "enabled": provider.enabled,
        "credential_source": provider.credential_source,
        "configured": provider.credential_source == "company" and provider.api_key_encrypted is not None,
        "key_masked": key_masked,
        "base_url": provider.base_url,
        "timeout_seconds": provider.timeout_seconds,
        "platform_enabled": platform_enabled,
        "platform_base_url": raw_platform_provider.base_url,
        "platform_key_configured": bool(raw_platform_provider.api_key.strip()),
    }
    if isinstance(provider, CompanyLinkupSearchProvider):
        out["depth"] = provider.depth
    if isinstance(provider, CompanyTavilySearchProvider):
        out["search_depth"] = provider.search_depth
        out["topic"] = provider.topic
        out["include_answer"] = provider.include_answer
    return out


def _platform_provider_config(
    provider_id: SearchProviderId,
) -> SearchTinyFishConfig | SearchLinkupConfig | SearchSerperConfig | SearchTavilyConfig:
    platform_config = get_search_settings().search
    if provider_id == "tinyfish":
        return platform_config.tinyfish
    if provider_id == "linkup":
        return platform_config.linkup
    if provider_id == "serper":
        return platform_config.serper
    if provider_id == "tavily":
        return platform_config.tavily


def _catalog() -> list[JsonObject]:
    return [
        {
            "id": "tinyfish",
            "label": "TinyFish",
            "logo": "TF",
            "tone": "cyan",
            "description": "Fast low-cost SERP API for lightweight web search and prototypes.",
            "tooltip": "Хорош для дешевого первичного поиска. В billing считается как search:tinyfish.",
            "docs_url": "https://app.tinyfish.ai",
        },
        {
            "id": "linkup",
            "label": "Linkup",
            "logo": "LU",
            "tone": "green",
            "description": "LLM-oriented web search with controllable depth.",
            "tooltip": "Можно выбирать глубину fast/standard/deep. BYOK не списывает баланс Humanitec.",
            "docs_url": "https://app.linkup.so",
        },
        {
            "id": "serper",
            "label": "Serper",
            "logo": "G",
            "tone": "blue",
            "description": "Google SERP through Serper.dev with normalized organic results.",
            "tooltip": "Google-like выдача. При platform key тарифицируется как search:serper.",
            "docs_url": "https://serper.dev",
        },
        {
            "id": "tavily",
            "label": "Tavily",
            "logo": "TV",
            "tone": "violet",
            "description": "AI-search API with basic/advanced depth and topic controls.",
            "tooltip": "Дороже, но полезен для deep/research flow и RAG-friendly результатов.",
            "docs_url": "https://tavily.com",
        },
    ]


@router.get("")
async def get_search_providers() -> JsonObject:
    _, company = _require_admin()
    settings = _load_settings(company)
    return {
        "provider_order": list(settings.provider_order),
        "providers": [_provider_public(provider_id, settings) for provider_id in _PROVIDER_IDS],
        "catalog": _catalog(),
    }


@router.put("/order")
async def put_search_provider_order(
    payload: SearchProviderOrderRequest,
    container: ContainerDep,
) -> JsonObject:
    _, company = _require_admin()
    settings = _load_settings(company)
    try:
        updated = settings.model_copy(update={"provider_order": payload.provider_order})
        updated = CompanySearchProviders.model_validate(updated.model_dump(mode="json"))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _save_settings(company, container, updated)
    return {"success": True}


@router.put("/{provider_id}")
async def put_search_provider(
    provider_id: str,
    payload: SearchProviderUpdateRequest,
    container: ContainerDep,
) -> JsonObject:
    _, company = _require_admin()
    pid = _provider_id(provider_id)
    settings = _load_settings(company)
    try:
        override = _build_provider_override(pid, payload, settings.provider(pid))
        updated = settings.model_copy(update={pid: override})
        updated = CompanySearchProviders.model_validate(updated.model_dump(mode="json"))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _save_settings(company, container, updated)
    return {"success": True}


@router.delete("/{provider_id}")
async def delete_search_provider(
    provider_id: str,
    container: ContainerDep,
) -> JsonObject:
    _, company = _require_admin()
    pid = _provider_id(provider_id)
    settings = _load_settings(company)
    defaults = CompanySearchProviders()
    try:
        updated = settings.model_copy(update={pid: defaults.provider(pid)})
        updated = CompanySearchProviders.model_validate(updated.model_dump(mode="json"))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _save_settings(company, container, updated)
    return {"success": True}
