"""REST-зеркало команд `frontend/platform_billing/*` (админка тарифов, только компания system)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Query

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import (
    PlatformBillingBalanceGrantRequest,
    PlatformBillingBalanceGrantResponse,
    PlatformBillingCompaniesOverviewResponse,
    PlatformBillingCompanyPricesResponse,
    PlatformBillingCompanyResolveResponse,
    PlatformBillingPricesResponse,
    PlatformBillingSettlementRulesResponse,
    PlatformTracingFacetItemsResponse,
)
from apps.frontend.realtime.platform_billing_operations import (
    COMPANIES_OVERVIEW_MAX_LIMIT,
    PlatformBillingCompanyIdPayload,
    PlatformBillingCompanyPricesPutPayload,
    PlatformBillingCompanyQueryPayload,
    PlatformBillingFacetPayload,
    PlatformBillingOverviewPayload,
    PlatformBillingPricesPutPayload,
    PlatformBillingSettlementRulesPutPayload,
    PlatformBillingUsageReportPayload,
    StatusOk,
    op_platform_billing_balance_grant,
    op_platform_billing_companies_overview,
    op_platform_billing_company_prices,
    op_platform_billing_company_prices_update,
    op_platform_billing_company_resolve,
    op_platform_billing_default_settlement_rules,
    op_platform_billing_facet_companies,
    op_platform_billing_facet_resource_names,
    op_platform_billing_facet_usage_types,
    op_platform_billing_prices,
    op_platform_billing_prices_update,
    op_platform_billing_settlement_rules,
    op_platform_billing_settlement_rules_update,
    op_platform_billing_usage_report,
)
from core.billing.settlement_rules import SettlementRulesDocument
from core.context import require_context
from core.pagination import OffsetPage
from core.tracing.repository import ADMIN_FACETS_MAX_LIMIT
from core.types import JsonObject
from core.websocket import EmptyPayload

router = APIRouter(prefix="/api/platform-billing", tags=["platform-billing"])


@router.get("/companies-billing-overview", response_model=PlatformBillingCompaniesOverviewResponse)
async def companies_billing_overview(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=COMPANIES_OVERVIEW_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlatformBillingCompaniesOverviewResponse:
    return await op_platform_billing_companies_overview(
        PlatformBillingOverviewPayload(limit=limit, offset=offset), user=require_context().user, container=container
    )


@router.post("/balance-grant", response_model=PlatformBillingBalanceGrantResponse)
async def post_balance_grant(
    container: ContainerDep, body: PlatformBillingBalanceGrantRequest
) -> PlatformBillingBalanceGrantResponse:
    return await op_platform_billing_balance_grant(body, user=require_context().user, container=container)


@router.get("/company-resolve", response_model=PlatformBillingCompanyResolveResponse)
async def resolve_billing_company(
    container: ContainerDep, q: Annotated[str, Query(min_length=1)]
) -> PlatformBillingCompanyResolveResponse:
    return await op_platform_billing_company_resolve(
        PlatformBillingCompanyQueryPayload(q=q), user=require_context().user, container=container
    )


@router.get("/facets/billing-companies", response_model=PlatformTracingFacetItemsResponse)
async def facet_billing_companies(
    container: ContainerDep,
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=ADMIN_FACETS_MAX_LIMIT)] = 20,
) -> PlatformTracingFacetItemsResponse:
    return await op_platform_billing_facet_companies(
        PlatformBillingFacetPayload(q=q, limit=limit), user=require_context().user, container=container
    )


@router.get("/prices", response_model=PlatformBillingPricesResponse)
async def get_billing_prices(container: ContainerDep) -> PlatformBillingPricesResponse:
    return await op_platform_billing_prices(EmptyPayload(), user=require_context().user, container=container)


@router.put("/prices", response_model=StatusOk)
async def put_billing_prices(container: ContainerDep, body: Annotated[JsonObject, Body()]) -> StatusOk:
    return await op_platform_billing_prices_update(
        PlatformBillingPricesPutPayload(catalog=body), user=require_context().user, container=container
    )


@router.get("/default-settlement-rules", response_model=PlatformBillingSettlementRulesResponse)
async def get_default_settlement_rules_template(container: ContainerDep) -> PlatformBillingSettlementRulesResponse:
    return await op_platform_billing_default_settlement_rules(
        EmptyPayload(), user=require_context().user, container=container
    )


@router.get("/settlement-rules/{company_id}", response_model=PlatformBillingSettlementRulesResponse)
async def get_settlement_rules(container: ContainerDep, company_id: str) -> PlatformBillingSettlementRulesResponse:
    return await op_platform_billing_settlement_rules(
        PlatformBillingCompanyIdPayload(company_id=company_id), user=require_context().user, container=container
    )


@router.put("/settlement-rules/{company_id}", response_model=StatusOk)
async def put_settlement_rules(
    container: ContainerDep, company_id: str, document: Annotated[SettlementRulesDocument, Body()]
) -> StatusOk:
    return await op_platform_billing_settlement_rules_update(
        PlatformBillingSettlementRulesPutPayload(company_id=company_id, document=document),
        user=require_context().user,
        container=container,
    )


@router.get("/prices/company/{company_id}", response_model=PlatformBillingCompanyPricesResponse)
async def get_company_billing_prices(container: ContainerDep, company_id: str) -> PlatformBillingCompanyPricesResponse:
    return await op_platform_billing_company_prices(
        PlatformBillingCompanyIdPayload(company_id=company_id), user=require_context().user, container=container
    )


@router.put("/prices/company/{company_id}", response_model=StatusOk)
async def put_company_billing_prices(
    container: ContainerDep, company_id: str, body: Annotated[JsonObject, Body()]
) -> StatusOk:
    return await op_platform_billing_company_prices_update(
        PlatformBillingCompanyPricesPutPayload(company_id=company_id, catalog=body),
        user=require_context().user,
        container=container,
    )


@router.get("/facets/usage-types", response_model=PlatformTracingFacetItemsResponse)
async def facet_usage_types(
    container: ContainerDep,
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=ADMIN_FACETS_MAX_LIMIT)] = 20,
) -> PlatformTracingFacetItemsResponse:
    return await op_platform_billing_facet_usage_types(
        PlatformBillingFacetPayload(q=q, limit=limit), user=require_context().user, container=container
    )


@router.get("/facets/resource-names", response_model=PlatformTracingFacetItemsResponse)
async def facet_resource_names(
    container: ContainerDep,
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=ADMIN_FACETS_MAX_LIMIT)] = 20,
) -> PlatformTracingFacetItemsResponse:
    return await op_platform_billing_facet_resource_names(
        PlatformBillingFacetPayload(q=q, limit=limit), user=require_context().user, container=container
    )


@router.get("/usage-report", response_model=OffsetPage[JsonObject])
async def get_usage_report(
    container: ContainerDep,
    company_id: Annotated[str | None, Query()] = None,
    usage_type: Annotated[str | None, Query()] = None,
    resource_name: Annotated[str | None, Query()] = None,
    from_time: Annotated[datetime | None, Query(alias="from")] = None,
    to_time: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[JsonObject]:
    return await op_platform_billing_usage_report(
        PlatformBillingUsageReportPayload(
            company_id=company_id,
            usage_type=usage_type,
            resource_name=resource_name,
            from_time=from_time,
            to_time=to_time,
            limit=limit,
            offset=offset,
        ),
        user=require_context().user,
        container=container,
    )
