"""LLM catalog registry: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from apps.flows.realtime.operations import (
    require_company_member,
)
from apps.flows.src.container import FlowContainer
from apps.flows.src.models.registry_contracts import (
    RegistryCatalogPayload,
    RegistryProviderOption,
)
from core.ai.company_settings import CUSTOM_PROVIDER_REF_PREFIX, CompanyAIProviders
from core.ai.providers import HUMANITEC_LLM_PROVIDER, AICapability
from core.config import get_settings
from core.config.models import PlatformBrandConfig
from core.context import require_active_company
from core.models.identity_models import User
from core.pagination import ListResponse
from core.platform_brand.resolver import (
    UnknownPlatformDomainError,
    resolve_brand,
    resolve_context_host,
)
from core.types import JsonObject
from core.websocket import (
    raise_invalid,
)

_LLM_CAPABILITY_VALUES = {
    AICapability.LLM_CHAT.value,
    AICapability.LLM_SUMMARIZE.value,
    AICapability.LLM_FORMAT_MARKDOWN.value,
    AICapability.LLM_CODEGEN.value,
    AICapability.LLM_VISION.value,
    AICapability.IMAGE_GEN.value,
}


def _company_ai_from_context() -> CompanyAIProviders:
    return CompanyAIProviders.from_metadata(require_active_company().metadata)


def _capability_from_query(raw: str | None) -> AICapability:
    if raw is None or not raw.strip():
        return AICapability.LLM_CHAT
    try:
        capability = AICapability(raw.strip())
    except ValueError as exc:
        raise_invalid(exc)
    if capability.value not in _LLM_CAPABILITY_VALUES:
        raise_invalid(
            ValueError(
                f"Capability {capability.value!r} не поддерживается registry LLM catalog"
            )
        )
    return capability


def _custom_provider_options(
    aip: CompanyAIProviders,
    capability: AICapability,
) -> list[RegistryProviderOption]:
    items: list[RegistryProviderOption] = []
    for provider in aip.custom_providers:
        if capability.value not in provider.capabilities:
            continue
        items.append(
            RegistryProviderOption(
                value=f"{CUSTOM_PROVIDER_REF_PREFIX}{provider.id}",
                label=provider.label,
                kind="custom",
                custom_id=provider.id,
            )
        )
    return items


def _resolve_brand_for_registry(host: str | None) -> PlatformBrandConfig:
    if host is not None and str(host).strip():
        try:
            return resolve_brand(str(host).strip())
        except UnknownPlatformDomainError:
            pass
    settings = get_settings()
    return settings.platform_brands[settings.primary_platform_domain]


def _platform_provider_options(
    providers: list[str],
    *,
    llms_display_label: str,
) -> list[str | RegistryProviderOption]:
    out: list[str | RegistryProviderOption] = []
    for provider in providers:
        if provider == HUMANITEC_LLM_PROVIDER:
            out.append(
                RegistryProviderOption(
                    value=HUMANITEC_LLM_PROVIDER,
                    label=llms_display_label,
                    kind="virtual",
                )
            )
            continue
        out.append(provider)
    return out


def _custom_provider_models(
    aip: CompanyAIProviders,
    provider_ref: str,
    capability: AICapability,
) -> list[str]:
    if not provider_ref.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        raise ValueError(f"Не custom-провайдер: {provider_ref!r}")
    custom_id = provider_ref[len(CUSTOM_PROVIDER_REF_PREFIX) :].strip()
    try:
        provider = aip.find_custom(custom_id)
    except KeyError as exc:
        raise ValueError(f"Неизвестный custom-провайдер: {custom_id!r}") from exc
    model = provider.model_by_capability.get(capability.value)
    return [model] if model else []


async def op_flows_registry_providers_list(
    payload: RegistryCatalogPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[str | RegistryProviderOption]:
    _ = user
    _ = await require_company_member(container)
    capability = _capability_from_query(payload.capability)
    brand = _resolve_brand_for_registry(resolve_context_host())
    platform_items = _platform_provider_options(
        container.llm_models_service.get_configured_providers_by_capability(capability),
        llms_display_label=brand.llms_display_label,
    )
    return ListResponse[str | RegistryProviderOption](
        items=[
            *platform_items,
            *_custom_provider_options(_company_ai_from_context(), capability),
        ]
    )


async def op_flows_registry_models_list(
    payload: RegistryCatalogPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[str | JsonObject]:
    _ = user
    _ = await require_company_member(container)
    capability = _capability_from_query(payload.capability)
    provider = payload.provider
    catalog: list[str | JsonObject] = []
    try:
        if provider and provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
            catalog.extend(
                _custom_provider_models(
                    _company_ai_from_context(),
                    provider,
                    capability,
                )
            )
        elif provider:
            catalog.extend(
                await container.llm_models_service.get_model_ids_by_provider_capability(
                    provider,
                    capability,
                )
            )
        else:
            catalog.extend(
                await container.llm_models_service.get_default_model_ids_by_capability(
                    capability,
                )
            )
    except ValueError as exc:
        raise_invalid(exc)
    return ListResponse[str | JsonObject](items=catalog)
