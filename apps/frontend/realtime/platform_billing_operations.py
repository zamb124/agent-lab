"""Команды админки биллинга платформы (только компания system): прайс, правила settlement, гранты, отчёт usage."""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import Field

from apps.frontend.di import Di
from apps.frontend.models import (
    PlatformBillingBalanceGrantRequest,
    PlatformBillingBalanceGrantResponse,
    PlatformBillingCompaniesOverviewResponse,
    PlatformBillingCompanyOverviewItem,
    PlatformBillingCompanyPricesResponse,
    PlatformBillingCompanyResolveResponse,
    PlatformBillingPricesResponse,
    PlatformBillingSettlementRulesResponse,
    PlatformTracingFacetItem,
    PlatformTracingFacetItemsResponse,
)
from core.billing.default_settlement_rules import default_settlement_rules_document
from core.billing.service import company_resource_prices_storage_key
from core.billing.settlement_rules import SettlementRulesDocument
from core.errors.boundary import PlatformNotFoundError
from core.identity.system_bootstrap import SYSTEM_COMPANY_SUBDOMAIN
from core.models import StrictBaseModel
from core.models.billing_models import UsageRecord, UsageType
from core.models.identity_models import SYSTEM_COMPANY_ID, Company, User
from core.pagination import OffsetPage
from core.request_scope import require_system_admin
from core.tracing.facet_query import ADMIN_FACETS_MAX_LIMIT, facet_query_fragment
from core.types import JsonObject, parse_json_object, require_json_object
from core.websocket import EmptyPayload, raise_invalid

STORAGE_PRICES_KEY = "billing:resource_base_prices_json"
BILLING_COMPANY_LIST_CAP = 2000
COMPANIES_OVERVIEW_MAX_LIMIT = 500

PriceCatalog = dict[str, dict[str, float]]


class StatusOk(StrictBaseModel):
    status: str = "ok"


class PlatformBillingOverviewPayload(StrictBaseModel):
    limit: int = Field(default=50, ge=1, le=COMPANIES_OVERVIEW_MAX_LIMIT)
    offset: int = Field(default=0, ge=0)


class PlatformBillingCompanyQueryPayload(StrictBaseModel):
    q: str = Field(min_length=1)


class PlatformBillingFacetPayload(StrictBaseModel):
    q: str | None = None
    limit: int = Field(default=20, ge=1, le=ADMIN_FACETS_MAX_LIMIT)


class PlatformBillingCompanyIdPayload(StrictBaseModel):
    company_id: str = Field(min_length=1)


class PlatformBillingPricesPutPayload(StrictBaseModel):
    """Прайс `category -> resource -> price`; категория `tool` запрещена (инструменты не тарифицируются)."""

    catalog: JsonObject


class PlatformBillingCompanyPricesPutPayload(PlatformBillingCompanyIdPayload):
    catalog: JsonObject


class PlatformBillingSettlementRulesPutPayload(PlatformBillingCompanyIdPayload):
    document: SettlementRulesDocument


class PlatformBillingUsageReportPayload(StrictBaseModel):
    company_id: str | None = None
    usage_type: str | None = None
    resource_name: str | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    limit: int = Field(default=200, ge=1, le=5000)
    offset: int = Field(default=0, ge=0)


def _billing_overview_subdomain(company: Company) -> str | None:
    """Для system без subdomain в storage отдаём каноническое значение (админка биллинга)."""
    if company.company_id != SYSTEM_COMPANY_ID:
        return company.subdomain
    if not (company.subdomain or "").strip():
        return SYSTEM_COMPANY_SUBDOMAIN
    return company.subdomain


def _billing_company_facet_label(company: Company) -> str:
    if company.subdomain:
        return f"{company.name} ({company.subdomain})"
    return f"{company.name} ({company.company_id})"


def company_matches_billing_facet_query(company: Company, frag_lower: str) -> bool:
    if not frag_lower:
        return True
    cid = company.company_id.lower()
    sub = (company.subdomain or "").lower()
    return (
        frag_lower == cid
        or bool(sub and frag_lower == sub)
        or frag_lower in cid
        or bool(sub and frag_lower in sub)
        or frag_lower in company.name.lower()
    )


def validate_price_catalog(catalog: JsonObject) -> PriceCatalog:
    out: PriceCatalog = {}
    for category, resources in catalog.items():
        if category == "tool":
            raise_invalid(
                ValueError("price catalog category 'tool' is not supported: tools are not billed")
            )
        try:
            resource_prices = require_json_object(resources, f"billing.price_catalog.{category}")
        except ValueError:
            raise_invalid(ValueError(f"category {category!r} must be an object of resource->price"))
        if not resource_prices:
            raise_invalid(ValueError(f"category {category!r} must not be empty"))
        bucket: dict[str, float] = {}
        for resource_name, price in resource_prices.items():
            if isinstance(price, bool) or not isinstance(price, int | float):
                raise_invalid(ValueError(f"price for {category}:{resource_name} must be a number"))
            bucket[resource_name] = float(price)
        out[category] = bucket
    return out


async def _require_company(company_id: str) -> Company:
    cid = company_id.strip()
    if not cid:
        raise_invalid(ValueError("company_id must not be empty"))
    company = await Company.get(cid)
    if company is None:
        raise PlatformNotFoundError(f"Company {cid} not found", error_code='not_found')
    return company


async def resolve_company_for_billing_admin(raw: str) -> Company:
    """Компания по id, slug, названию или подписи фасета `Name (slug)`."""
    q = raw.strip()
    if not q:
        raise_invalid(ValueError("query must not be empty"))
    candidates: list[str] = [q]
    if q.endswith(")") and "(" in q:
        open_idx = q.rfind("(")
        for candidate in (q[open_idx + 1 : -1].strip(), q[:open_idx].strip()):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
    for candidate in candidates:
        direct = await Company.get(candidate)
        if direct is not None:
            return direct
    for candidate in candidates:
        mapped = await Company.by_subdomain(candidate.lower())
        if mapped is not None:
            return mapped
    companies = await Company.list(limit=BILLING_COMPANY_LIST_CAP)
    for q_lower in (candidate.lower() for candidate in candidates):
        for company in companies:
            if (
                company.company_id.lower() == q_lower
                or (company.subdomain and company.subdomain.lower() == q_lower)
                or company.name.lower() == q_lower
            ):
                return company
    raise PlatformNotFoundError(f"Company not found by id or slug: {q!r}", error_code='not_found')


async def op_platform_billing_companies_overview(
    payload: PlatformBillingOverviewPayload, *, user: User, di: Di
) -> PlatformBillingCompaniesOverviewResponse:
    _ = user
    _ = await require_system_admin(di.authz_service)
    companies, has_more = await Company.page_named_after_system(
        limit=payload.limit,
        offset=payload.offset,
    )
    return PlatformBillingCompaniesOverviewResponse(
        items=[
            PlatformBillingCompanyOverviewItem(
                company_id=company.company_id,
                name=company.name,
                subdomain=_billing_overview_subdomain(company),
                status=company.status,
                tariff_plan=company.tariff_plan.value,
                balance=company.balance,
                monthly_budget=company.monthly_budget,
                current_month_spent=company.current_month_spent,
            )
            for company in companies
        ],
        has_more=has_more,
    )


async def op_platform_billing_balance_grant(
    payload: PlatformBillingBalanceGrantRequest, *, user: User, di: Di
) -> PlatformBillingBalanceGrantResponse:
    _ = await require_system_admin(di.authz_service)
    company = await _require_company(payload.company_id)
    granted = await di.payment_service.apply_balance_grant(
        company_id=company.company_id, amount=payload.amount, grantor_user_id=user.user_id, note=payload.note
    )
    return PlatformBillingBalanceGrantResponse(
        transaction_id=granted.transaction_id,
        company_id=granted.company_id,
        amount=granted.amount,
        balance=granted.balance,
    )


async def op_platform_billing_company_resolve(
    payload: PlatformBillingCompanyQueryPayload, *, user: User, di: Di
) -> PlatformBillingCompanyResolveResponse:
    _ = user
    _ = await require_system_admin(di.authz_service)
    company = await resolve_company_for_billing_admin(payload.q)
    return PlatformBillingCompanyResolveResponse(
        company_id=company.company_id, name=company.name, subdomain=company.subdomain
    )


async def op_platform_billing_facet_companies(
    payload: PlatformBillingFacetPayload, *, user: User, di: Di
) -> PlatformTracingFacetItemsResponse:
    _ = user
    _ = await require_system_admin(di.authz_service)
    frag = (payload.q or "").strip().lower()
    companies = await Company.list(limit=BILLING_COMPANY_LIST_CAP)
    matched = [company for company in companies if company_matches_billing_facet_query(company, frag)]

    def sort_key(company: Company) -> tuple[int, str]:
        name_key = (company.name or "").lower()
        if not frag:
            return (0, name_key)
        sub = (company.subdomain or "").lower()
        if frag == company.company_id.lower() or (sub and frag == sub):
            return (0, name_key)
        return (1, name_key)

    matched.sort(key=sort_key)
    return PlatformTracingFacetItemsResponse(
        items=[
            PlatformTracingFacetItem(value=company.company_id, label=_billing_company_facet_label(company))
            for company in matched[: payload.limit]
        ],
    )


async def _storage_price_override(di: Di, key: str) -> PriceCatalog | None:
    raw = await di.shared_storage.get(key)
    if not raw:
        return None
    return validate_price_catalog(parse_json_object(raw, key))


async def op_platform_billing_prices(
    payload: EmptyPayload, *, user: User, di: Di
) -> PlatformBillingPricesResponse:
    _ = payload, user
    _ = await require_system_admin(di.authz_service)
    return PlatformBillingPricesResponse(
        static_base=di.billing_service.get_static_resource_base_prices(),
        effective=await di.billing_service.get_effective_resource_base_prices(),
        storage_override=await _storage_price_override(di, STORAGE_PRICES_KEY),
    )


async def op_platform_billing_prices_update(
    payload: PlatformBillingPricesPutPayload, *, user: User, di: Di
) -> StatusOk:
    _ = user
    _ = await require_system_admin(di.authz_service)
    catalog = validate_price_catalog(payload.catalog)
    _ = await di.shared_storage.set(STORAGE_PRICES_KEY, json.dumps(catalog))
    return StatusOk()


async def op_platform_billing_default_settlement_rules(
    payload: EmptyPayload, *, user: User, di: Di
) -> PlatformBillingSettlementRulesResponse:
    """Кодовый дефолт правил (без сохранения) — для подстановки в админке."""
    _ = payload, user
    _ = await require_system_admin(di.authz_service)
    return PlatformBillingSettlementRulesResponse(document=default_settlement_rules_document())


async def op_platform_billing_settlement_rules(
    payload: PlatformBillingCompanyIdPayload, *, user: User, di: Di
) -> PlatformBillingSettlementRulesResponse:
    _ = user
    _ = await require_system_admin(di.authz_service)
    company = await _require_company(payload.company_id)
    document = await di.billing_service.load_settlement_rules_document_for_company(company.company_id)
    return PlatformBillingSettlementRulesResponse(document=document)


async def op_platform_billing_settlement_rules_update(
    payload: PlatformBillingSettlementRulesPutPayload, *, user: User, di: Di
) -> StatusOk:
    _ = user
    _ = await require_system_admin(di.authz_service)
    company = await _require_company(payload.company_id)
    for rule in payload.document.rules:
        if rule.resource_name.startswith("tool:"):
            raise_invalid(
                ValueError(
                    f"rule {rule.rule_id}: resource_name with tool: prefix is forbidden (tools are not billed)"
                )
            )
    await di.billing_service.save_settlement_rules_document_for_company(company.company_id, payload.document)
    return StatusOk()


async def op_platform_billing_company_prices(
    payload: PlatformBillingCompanyIdPayload, *, user: User, di: Di
) -> PlatformBillingCompanyPricesResponse:
    _ = user
    _ = await require_system_admin(di.authz_service)
    cid = payload.company_id.strip()
    if not cid:
        raise_invalid(ValueError("company_id must not be empty"))
    override = await _storage_price_override(di, company_resource_prices_storage_key(cid))
    effective = await di.billing_service.get_effective_resource_base_prices_for_company(cid)
    company = await Company.get(cid)
    tariff_plan = company.tariff_plan if company is not None else None
    return PlatformBillingCompanyPricesResponse(
        company_id=cid,
        static_base=di.billing_service.get_static_resource_base_prices(),
        effective=effective,
        unit_effective=(
            di.billing_service.apply_tariff_multipliers_to_base_prices(effective, tariff_plan)
            if tariff_plan is not None
            else None
        ),
        tariff_plan=tariff_plan.value if tariff_plan is not None else None,
        tariff_multipliers=(
            di.billing_service.get_tariff_multipliers_for_plan(tariff_plan) if tariff_plan is not None else {}
        ),
        storage_override=override,
    )


async def op_platform_billing_company_prices_update(
    payload: PlatformBillingCompanyPricesPutPayload, *, user: User, di: Di
) -> StatusOk:
    _ = user
    _ = await require_system_admin(di.authz_service)
    cid = payload.company_id.strip()
    if not cid:
        raise_invalid(ValueError("company_id must not be empty"))
    catalog = validate_price_catalog(payload.catalog)
    _ = await di.shared_storage.set(
        company_resource_prices_storage_key(cid), json.dumps(catalog)    )
    return StatusOk()


async def op_platform_billing_facet_usage_types(
    payload: PlatformBillingFacetPayload, *, user: User, di: Di
) -> PlatformTracingFacetItemsResponse:
    _ = user
    _ = await require_system_admin(di.authz_service)
    frag = facet_query_fragment(payload.q)
    from_db = await UsageRecord.admin_facet_distinct_usage_types(
        q=payload.q if frag is not None else None, limit=payload.limit
    )
    merged = sorted({usage_type.value for usage_type in UsageType} | set(from_db))
    if frag is not None:
        frag_lower = frag.lower()
        merged = [value for value in merged if frag_lower in value.lower()]
    return PlatformTracingFacetItemsResponse(
        items=[PlatformTracingFacetItem(value=value, label=value) for value in merged[: payload.limit]],
    )


async def op_platform_billing_facet_resource_names(
    payload: PlatformBillingFacetPayload, *, user: User, di: Di
) -> PlatformTracingFacetItemsResponse:
    _ = user
    _ = await require_system_admin(di.authz_service)
    names = await UsageRecord.admin_facet_distinct_resource_names(q=payload.q, limit=payload.limit)
    return PlatformTracingFacetItemsResponse(
        items=[PlatformTracingFacetItem(value=name, label=name) for name in names],
    )


async def op_platform_billing_usage_report(
    payload: PlatformBillingUsageReportPayload, *, user: User, di: Di
) -> OffsetPage[JsonObject]:
    """Строки usage всех компаний с company_name и настроечными полями settlement из metadata."""
    _ = user
    _ = await require_system_admin(di.authz_service)
    page = await UsageRecord.admin_search_usage_records(
        company_id=payload.company_id,
        usage_type=payload.usage_type,
        resource_name=payload.resource_name,
        from_time=payload.from_time,
        to_time=payload.to_time,
        limit=payload.limit,
        offset=payload.offset,
    )
    records = page.items
    serialized = [
        require_json_object(record.model_dump(mode="json"), f"usage_record.{record.usage_id}") for record in records
    ]
    company_ids = {record.company_id for record in records}
    companies = await Company.get_many(list(company_ids)) if company_ids else {}
    for record, row in zip(records, serialized, strict=True):
        company = companies.get(record.company_id)
        row["company_name"] = company.name if company else None
        row["span_id"] = record.metadata.get("span_id")
        row["trace_id"] = record.metadata.get("trace_id")
        row["rule_id"] = record.metadata.get("rule_id")
        row["settlement_source"] = record.metadata.get("settlement_source")
        row["unit_cost"] = record.cost / record.quantity if record.quantity > 0 else None
    return OffsetPage[JsonObject](items=serialized, total=page.total, limit=page.limit, offset=page.offset)
