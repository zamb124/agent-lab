"""
Админ-API тарифов и отчёта по usage (только компания system).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Body, HTTPException, Query

from apps.frontend.dependencies import ContainerDep

if TYPE_CHECKING:
    from apps.frontend.container import FrontendContainer
from apps.frontend.models import (
    PlatformBillingBalanceGrantRequest,
    PlatformBillingBalanceGrantResponse,
    PlatformBillingCompaniesOverviewResponse,
    PlatformBillingCompanyOverviewItem,
    PlatformBillingCompanyPricesResponse,
    PlatformBillingCompanyResolveResponse,
    PlatformBillingPricesResponse,
    PlatformBillingSettlementRulesResponse,
    PlatformBillingUsageReportResponse,
    PlatformTracingFacetItem,
    PlatformTracingFacetItemsResponse,
)
from core.billing.default_settlement_rules import default_settlement_rules_document
from core.billing.service import company_resource_prices_storage_key
from core.billing.settlement_rules import SettlementRulesDocument
from core.context import get_context
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID, SYSTEM_COMPANY_SUBDOMAIN
from core.models.billing_models import UsageType
from core.models.identity_models import Company
from core.tracing.repository import ADMIN_FACETS_MAX_LIMIT, facet_query_fragment
from core.types import JsonObject, parse_json_object, require_json_object

router = APIRouter(prefix="/api/platform-billing", tags=["platform-billing"])

_STORAGE_PRICES_KEY = "billing:resource_base_prices_json"

BILLING_COMPANY_LIST_CAP = 2000
_COMPANIES_OVERVIEW_MAX_LIMIT = 500


def _billing_overview_subdomain(c: Company) -> str | None:
    """Для system без subdomain в storage отдаём каноническое значение (админка биллинга)."""
    if c.company_id != SYSTEM_COMPANY_ID:
        return c.subdomain
    if not (c.subdomain or "").strip():
        return SYSTEM_COMPANY_SUBDOMAIN
    return c.subdomain


def _billing_company_facet_label(co: Company) -> str:
    if co.subdomain:
        return f"{co.name} ({co.subdomain})"
    return f"{co.name} ({co.company_id})"


async def _resolve_company_for_billing_admin(container: "FrontendContainer", raw: str) -> Company:
    q = raw.strip()
    if not q:
        raise HTTPException(status_code=422, detail="Пустой запрос")

    candidates: list[str] = [q]
    if q.endswith(")") and "(" in q:
        open_idx = q.rfind("(")
        before = q[:open_idx].strip()
        inside = q[open_idx + 1 : -1].strip()
        for candidate in (inside, before):
            if candidate and candidate not in candidates:
                candidates.append(candidate)

    for candidate in candidates:
        direct = await container.company_repository.get(candidate)
        if direct is not None:
            return direct

    for candidate in candidates:
        mapped_id = await container.subdomain_repository.get_company_id(candidate.lower())
        if mapped_id:
            co = await container.company_repository.get(mapped_id)
            if co is not None:
                return co

    companies = await container.company_repository.list(limit=BILLING_COMPANY_LIST_CAP)
    lowered = [candidate.lower() for candidate in candidates]
    for q_lower in lowered:
        for co in companies:
            if co.company_id.lower() == q_lower:
                return co
            if co.subdomain and co.subdomain.lower() == q_lower:
                return co
            if co.name.lower() == q_lower:
                return co
    raise HTTPException(
        status_code=404,
        detail=f"Компания не найдена по id или slug: {q!r}",
    )


def company_matches_billing_facet_query(co: Company, frag_lower: str) -> bool:
    if not frag_lower:
        return True
    cid = co.company_id.lower()
    if frag_lower == cid:
        return True
    sub = (co.subdomain or "").lower()
    if sub and frag_lower == sub:
        return True
    if frag_lower in cid:
        return True
    if sub and frag_lower in sub:
        return True
    if frag_lower in co.name.lower():
        return True
    return False


def _require_system_user_id() -> str:
    context = get_context()
    if context is None:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    company = context.active_company
    if company is None or company.company_id != SYSTEM_COMPANY_ID:
        raise HTTPException(status_code=403, detail="Доступно только для компании system")
    return context.user.user_id


def _validate_price_catalog(data: JsonObject) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for cat, resources in data.items():
        if cat == "tool":
            raise HTTPException(
                status_code=422,
                detail="Категория tool в прайсе не поддерживается: инструменты не тарифицируются",
            )
        try:
            resource_prices = require_json_object(resources, f"billing.price_catalog.{cat}")
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Категория {cat!r} должна быть объектом resource->price")
        if not resource_prices:
            raise HTTPException(status_code=422, detail=f"Категория {cat!r} не должна быть пустой")
        bucket: dict[str, float] = {}
        for res_name, price in resource_prices.items():
            if isinstance(price, bool) or not isinstance(price, int | float):
                raise HTTPException(
                    status_code=422,
                    detail=f"Цена для {cat}:{res_name} должна быть числом",
                )
            bucket[res_name] = float(price)
        out[cat] = bucket
    return out


@router.get(
    "/companies-billing-overview",
    response_model=PlatformBillingCompaniesOverviewResponse,
)
async def companies_billing_overview(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=_COMPANIES_OVERVIEW_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlatformBillingCompaniesOverviewResponse:
    _ = _require_system_user_id()
    all_companies = await container.company_repository.list(
        limit=BILLING_COMPANY_LIST_CAP, offset=0
    )
    sorted_companies = sorted(
        all_companies,
        key=lambda c: (0 if c.company_id == SYSTEM_COMPANY_ID else 1, (c.name or "").lower()),
    )
    slice_end = offset + limit + 1
    window = sorted_companies[offset:slice_end]
    has_more = len(window) > limit
    page = window[:limit]
    items = [
        PlatformBillingCompanyOverviewItem(
            company_id=c.company_id,
            name=c.name,
            subdomain=_billing_overview_subdomain(c),
            status=c.status,
            tariff_plan=c.tariff_plan.value,
            balance=c.balance,
            monthly_budget=c.monthly_budget,
            current_month_spent=c.current_month_spent,
        )
        for c in page
    ]
    return PlatformBillingCompaniesOverviewResponse(items=items, has_more=has_more)


@router.post(
    "/balance-grant",
    response_model=PlatformBillingBalanceGrantResponse,
)
async def post_balance_grant(
    container: ContainerDep,
    body: PlatformBillingBalanceGrantRequest,
) -> PlatformBillingBalanceGrantResponse:
    user_id = _require_system_user_id()
    cid = body.company_id.strip()
    if not cid:
        raise HTTPException(status_code=422, detail="company_id не может быть пустым")
    company = await container.company_repository.get(cid)
    if company is None:
        raise HTTPException(status_code=404, detail=f"Компания {cid} не найдена")
    out = await container.payment_service.apply_balance_grant(
        company_id=cid,
        amount=body.amount,
        grantor_user_id=user_id,
        note=body.note,
    )
    return PlatformBillingBalanceGrantResponse(
        transaction_id=out.transaction_id,
        company_id=out.company_id,
        amount=out.amount,
        balance=out.balance,
    )


@router.get(
    "/company-resolve",
    response_model=PlatformBillingCompanyResolveResponse,
)
async def resolve_billing_company(
    container: ContainerDep,
    q: Annotated[str, Query(min_length=1)],
) -> PlatformBillingCompanyResolveResponse:
    _ = _require_system_user_id()
    co = await _resolve_company_for_billing_admin(container, q)
    return PlatformBillingCompanyResolveResponse(
        company_id=co.company_id,
        name=co.name,
        subdomain=co.subdomain,
    )


@router.get(
    "/facets/billing-companies",
    response_model=PlatformTracingFacetItemsResponse,
)
async def facet_billing_companies(
    container: ContainerDep,
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=ADMIN_FACETS_MAX_LIMIT)] = 20,
) -> PlatformTracingFacetItemsResponse:
    _ = _require_system_user_id()
    frag = (q or "").strip().lower()
    companies = await container.company_repository.list(limit=BILLING_COMPANY_LIST_CAP)
    matched = [c for c in companies if company_matches_billing_facet_query(c, frag)]

    def sort_key(c: Company) -> tuple[int, str]:
        if not frag:
            return (0, (c.name or "").lower())
        fl = frag
        cid = c.company_id.lower()
        sub = (c.subdomain or "").lower()
        if fl == cid or (sub and fl == sub):
            return (0, (c.name or "").lower())
        return (1, (c.name or "").lower())

    matched.sort(key=sort_key)
    sliced = matched[:limit]
    return PlatformTracingFacetItemsResponse(
        items=[
            PlatformTracingFacetItem(
                value=c.company_id,
                label=_billing_company_facet_label(c),
            )
            for c in sliced
        ],
    )


@router.get("/prices", response_model=PlatformBillingPricesResponse)
async def get_billing_prices(container: ContainerDep) -> PlatformBillingPricesResponse:
    _ = _require_system_user_id()
    raw = await container.shared_storage.get(_STORAGE_PRICES_KEY, force_global=True)
    override: dict[str, dict[str, float]] | None = None
    if raw:
        parsed = parse_json_object(raw, "billing:resource_base_prices_json")
        override = _validate_price_catalog(parsed)
    effective = await container.billing_service.get_effective_resource_base_prices()
    return PlatformBillingPricesResponse(
        static_base=container.billing_service.get_static_resource_base_prices(),
        effective=effective,
        storage_override=override,
    )


@router.put("/prices")
async def put_billing_prices(
    container: ContainerDep,
    body: Annotated[JsonObject, Body()],
) -> dict[str, str]:
    _ = _require_system_user_id()
    catalog = _validate_price_catalog(body)
    _ = await container.shared_storage.set(
        _STORAGE_PRICES_KEY,
        json.dumps(catalog),
        force_global=True,
    )
    return {"status": "ok"}


@router.get(
    "/default-settlement-rules",
    response_model=PlatformBillingSettlementRulesResponse,
)
async def get_default_settlement_rules_template(
) -> PlatformBillingSettlementRulesResponse:
    """Кодовый дефолт правил (без сохранения) — для подстановки в админке."""
    _ = _require_system_user_id()
    doc = default_settlement_rules_document()
    return PlatformBillingSettlementRulesResponse(document=doc)


@router.get(
    "/settlement-rules/{company_id}",
    response_model=PlatformBillingSettlementRulesResponse,
)
async def get_settlement_rules(
    container: ContainerDep,
    company_id: str,
) -> PlatformBillingSettlementRulesResponse:
    _ = _require_system_user_id()
    cid = company_id.strip()
    if not cid:
        raise HTTPException(status_code=422, detail="company_id не может быть пустым")
    company = await container.company_repository.get(cid)
    if company is None:
        raise HTTPException(status_code=404, detail=f"Компания {cid} не найдена")
    doc = await container.billing_service.load_settlement_rules_document_for_company(cid)
    return PlatformBillingSettlementRulesResponse(document=doc)


@router.put("/settlement-rules/{company_id}")
async def put_settlement_rules(
    container: ContainerDep,
    company_id: str,
    document: Annotated[SettlementRulesDocument, Body()],
) -> dict[str, str]:
    _ = _require_system_user_id()
    cid = company_id.strip()
    if not cid:
        raise HTTPException(status_code=422, detail="company_id не может быть пустым")
    company = await container.company_repository.get(cid)
    if company is None:
        raise HTTPException(status_code=404, detail=f"Компания {cid} не найдена")
    for rule in document.rules:
        rn = rule.resource_name
        if rn.startswith("tool:"):
            raise HTTPException(
                status_code=422,
                detail=f"Правило {rule.rule_id}: resource_name с префиксом tool: запрещён (инструменты вне биллинга)",
            )
    await container.billing_service.save_settlement_rules_document_for_company(cid, document)
    return {"status": "ok"}


@router.get(
    "/prices/company/{company_id}",
    response_model=PlatformBillingCompanyPricesResponse,
)
async def get_company_billing_prices(
    container: ContainerDep,
    company_id: str,
) -> PlatformBillingCompanyPricesResponse:
    _ = _require_system_user_id()
    cid = company_id.strip()
    if not cid:
        raise HTTPException(status_code=422, detail="company_id не может быть пустым")
    key = company_resource_prices_storage_key(cid)
    raw = await container.shared_storage.get(key, force_global=True)
    override: dict[str, dict[str, float]] | None = None
    if raw:
        parsed = parse_json_object(raw, key)
        override = _validate_price_catalog(parsed)
    effective = await container.billing_service.get_effective_resource_base_prices_for_company(cid)
    company = await container.company_repository.get(cid)
    tariff_plan = company.tariff_plan if company is not None else None
    tariff_multipliers = (
        container.billing_service.get_tariff_multipliers_for_plan(tariff_plan)
        if tariff_plan is not None
        else {}
    )
    unit_effective = (
        container.billing_service.apply_tariff_multipliers_to_base_prices(effective, tariff_plan)
        if tariff_plan is not None
        else None
    )
    return PlatformBillingCompanyPricesResponse(
        company_id=cid,
        static_base=container.billing_service.get_static_resource_base_prices(),
        effective=effective,
        unit_effective=unit_effective,
        tariff_plan=tariff_plan.value if tariff_plan is not None else None,
        tariff_multipliers=tariff_multipliers,
        storage_override=override,
    )


@router.put("/prices/company/{company_id}")
async def put_company_billing_prices(
    container: ContainerDep,
    company_id: str,
    body: Annotated[JsonObject, Body()],
) -> dict[str, str]:
    _ = _require_system_user_id()
    cid = company_id.strip()
    if not cid:
        raise HTTPException(status_code=422, detail="company_id не может быть пустым")
    catalog = _validate_price_catalog(body)
    _ = await container.shared_storage.set(
        company_resource_prices_storage_key(cid),
        json.dumps(catalog),
        force_global=True,
    )
    return {"status": "ok"}


@router.get("/facets/usage-types", response_model=PlatformTracingFacetItemsResponse)
async def facet_usage_types(
    container: ContainerDep,
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=ADMIN_FACETS_MAX_LIMIT)] = 20,
) -> PlatformTracingFacetItemsResponse:
    _ = _require_system_user_id()
    enum_values = {e.value for e in UsageType}
    frag = facet_query_fragment(q)
    from_db = await container.usage_repository.admin_facet_distinct_usage_types(
        q=q if frag is not None else None,
        limit=limit,
    )
    merged = sorted(enum_values | set(from_db))
    if frag is not None:
        fl = frag.lower()
        merged = [x for x in merged if fl in x.lower()]
    merged = merged[:limit]
    return PlatformTracingFacetItemsResponse(
        items=[PlatformTracingFacetItem(value=v, label=v) for v in merged],
    )


@router.get("/facets/resource-names", response_model=PlatformTracingFacetItemsResponse)
async def facet_resource_names(
    container: ContainerDep,
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=ADMIN_FACETS_MAX_LIMIT)] = 20,
) -> PlatformTracingFacetItemsResponse:
    _ = _require_system_user_id()
    names = await container.usage_repository.admin_facet_distinct_resource_names(q=q, limit=limit)
    return PlatformTracingFacetItemsResponse(
        items=[PlatformTracingFacetItem(value=n, label=n) for n in names],
    )


@router.get("/usage-report", response_model=PlatformBillingUsageReportResponse)
async def get_usage_report(
    container: ContainerDep,
    company_id: Annotated[str | None, Query()] = None,
    usage_type: Annotated[str | None, Query()] = None,
    resource_name: Annotated[str | None, Query()] = None,
    from_time: Annotated[datetime | None, Query(alias="from")] = None,
    to_time: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlatformBillingUsageReportResponse:
    _ = _require_system_user_id()
    items = await container.usage_repository.admin_search_usage_records(
        company_id=company_id,
        usage_type=usage_type,
        resource_name=resource_name,
        from_time=from_time,
        to_time=to_time,
        limit=limit,
        offset=offset,
    )
    serialized = [
        require_json_object(rec.model_dump(mode="json"), f"usage_record.{rec.usage_id}")
        for rec in items
    ]
    company_ids = {rec.company_id for rec in items}
    companies = (
        await container.company_repository.get_many(list(company_ids)) if company_ids else {}
    )
    for rec, row in zip(items, serialized, strict=True):
        co = companies.get(rec.company_id)
        row["company_name"] = co.name if co else None
        metadata = rec.metadata
        row["span_id"] = metadata.get("span_id")
        row["trace_id"] = metadata.get("trace_id")
        row["rule_id"] = metadata.get("rule_id")
        row["settlement_source"] = metadata.get("settlement_source")
        if rec.quantity > 0:
            row["unit_cost"] = rec.cost / rec.quantity
        else:
            row["unit_cost"] = None
    return PlatformBillingUsageReportResponse(items=serialized)
