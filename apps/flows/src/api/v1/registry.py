"""Каталог LLM-провайдеров и моделей для редактора flows."""

from fastapi import APIRouter

from apps.flows.di import Di
from apps.flows.realtime.registry_operations import (
    op_flows_registry_models_list,
    op_flows_registry_providers_list,
)
from apps.flows.src.models.registry_contracts import (
    RegistryCatalogPayload,
    RegistryProviderOption,
)
from core.context import require_context
from core.pagination import ListResponse
from core.types import JsonObject

router = APIRouter(prefix="/registry", tags=["registry"])


@router.get("/providers/values", response_model=ListResponse[str | RegistryProviderOption])
async def get_providers_values(
    di: Di,
    capability: str | None = None,
) -> ListResponse[str | RegistryProviderOption]:
    return await op_flows_registry_providers_list(
        RegistryCatalogPayload(capability=capability),
        user=require_context().user,
        di=di,
    )


@router.get("/models/values", response_model=ListResponse[str | JsonObject])
async def get_models_values(
    di: Di,
    provider: str | None = None,
    capability: str | None = None,
) -> ListResponse[str | JsonObject]:
    return await op_flows_registry_models_list(
        RegistryCatalogPayload(provider=provider, capability=capability),
        user=require_context().user,
        di=di,
    )
