"""REST-зеркало настроек Search-провайдеров компании (`search/providers/*`)."""

from __future__ import annotations

from fastapi import APIRouter

from apps.search.di import Di
from apps.search.realtime.operations import (
    SearchOkResult,
    SearchProviderIdPayload,
    SearchProviderOrderPayload,
    SearchProviderUpdatePayload,
    SearchProviderUpdateRequest,
    op_providers_list,
    op_providers_order_update,
    op_providers_reset,
    op_providers_update,
)
from core.company_search import CompanySearchProvidersResponse, SearchProviderId
from core.context import require_context
from core.websocket import EmptyPayload

router = APIRouter(prefix="/providers/company", tags=["search-providers"])


@router.get("", response_model=CompanySearchProvidersResponse)
async def get_company_search_providers(di: Di) -> CompanySearchProvidersResponse:
    return await op_providers_list(EmptyPayload(), user=require_context().user, di=di)


@router.put("/order", response_model=SearchOkResult)
async def put_company_search_provider_order(
    body: SearchProviderOrderPayload, di: Di
) -> SearchOkResult:
    return await op_providers_order_update(body, user=require_context().user, di=di)


@router.put("/{provider_id}", response_model=SearchOkResult)
async def put_company_search_provider(
    provider_id: SearchProviderId, body: SearchProviderUpdateRequest, di: Di
) -> SearchOkResult:
    return await op_providers_update(
        SearchProviderUpdatePayload.model_validate({**body.model_dump(exclude_unset=True), "provider_id": provider_id}),
        user=require_context().user,
        di=di,
    )


@router.delete("/{provider_id}", response_model=SearchOkResult)
async def delete_company_search_provider(provider_id: SearchProviderId, di: Di) -> SearchOkResult:
    return await op_providers_reset(
        SearchProviderIdPayload(provider_id=provider_id), user=require_context().user, di=di
    )
