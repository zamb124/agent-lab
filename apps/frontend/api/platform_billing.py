"""
Админ-API тарифов и отчёта по usage (только компания system).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import ValidationError

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import (
    PlatformBillingCompanyPricesResponse,
    PlatformBillingCompanyResolveResponse,
    PlatformBillingPricesResponse,
    PlatformBillingSettlementRulesResponse,
    PlatformBillingUsageReportResponse,
    PlatformTracingFacetItem,
    PlatformTracingFacetItemsResponse,
)
from core.models.identity_models import Company
from core.billing.service import company_resource_prices_storage_key
from core.billing.default_settlement_rules import default_settlement_rules_document
from core.billing.settlement_rules import parse_settlement_rules_json
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.models.billing_models import UsageType
from core.tracing.repository import ADMIN_FACETS_MAX_LIMIT, _facet_query_fragment

router = APIRouter(prefix="/api/platform-billing", tags=["platform-billing"])

_STORAGE_PRICES_KEY = "billing:resource_base_prices_json"

_BILLING_COMPANY_LIST_CAP = 2000


def _billing_company_facet_label(co: Company) -> str:
    if co.subdomain:
        return f"{co.name} ({co.subdomain})"
    return f"{co.name} ({co.company_id})"


async def _resolve_company_for_billing_admin(container: ContainerDep, raw: str) -> Company:
    q = raw.strip()
    if not q:
        raise HTTPException(status_code=422, detail="Пустой запрос")
    direct = await container.company_repository.get(q)
    if direct is not None:
        return direct
    q_lower = q.lower()
    mapped_id = await container.subdomain_repository.get_company_id(q_lower)
    if mapped_id:
        co = await container.company_repository.get(mapped_id)
        if co is not None:
            return co
    companies = await container.company_repository.list_all(limit=_BILLING_COMPANY_LIST_CAP)
    for co in companies:
        if co.subdomain and co.subdomain.lower() == q_lower:
            return co
    raise HTTPException(
        status_code=404,
        detail=f"Компания не найдена по id или slug: {q!r}",
    )


def _company_matches_billing_facet_query(co: Company, frag_lower: str) -> bool:
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


def _require_system(request: Request) -> None:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    company = getattr(request.state, "company", None)
    if not company or company.company_id != SYSTEM_COMPANY_ID:
        raise HTTPException(status_code=403, detail="Доступно только для компании system")


def _validate_price_catalog(data: Any) -> Dict[str, Dict[str, float]]:
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="Тело запроса должно быть JSON-объектом категорий")
    out: Dict[str, Dict[str, float]] = {}
    for cat, resources in data.items():
        if not isinstance(cat, str):
            raise HTTPException(status_code=422, detail=f"Ключ категории должен быть строкой: {cat!r}")
        if cat == "tool":
            raise HTTPException(
                status_code=422,
                detail="Категория tool в прайсе не поддерживается: инструменты не тарифицируются",
            )
        if not isinstance(resources, dict):
            raise HTTPException(status_code=422, detail=f"Категория {cat!r} должна быть объектом resource->price")
        bucket: Dict[str, float] = {}
        for res_name, price in resources.items():
            if not isinstance(res_name, str):
                raise HTTPException(status_code=422, detail=f"Имя ресурса в {cat!r} должно быть строкой")
            try:
                bucket[res_name] = float(price)
            except (TypeError, ValueError) as e:
                raise HTTPException(
                    status_code=422,
                    detail=f"Цена для {cat}:{res_name} должна быть числом",
                ) from e
        out[cat] = bucket
    return out


@router.get(
    "/company-resolve",
    response_model=PlatformBillingCompanyResolveResponse,
)
async def resolve_billing_company(
    request: Request,
    container: ContainerDep,
    q: str = Query(..., min_length=1),
) -> PlatformBillingCompanyResolveResponse:
    _require_system(request)
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
    request: Request,
    container: ContainerDep,
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=ADMIN_FACETS_MAX_LIMIT),
) -> PlatformTracingFacetItemsResponse:
    _require_system(request)
    frag = (q or "").strip().lower()
    companies = await container.company_repository.list_all(limit=_BILLING_COMPANY_LIST_CAP)
    matched = [c for c in companies if _company_matches_billing_facet_query(c, frag)]

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
async def get_billing_prices(request: Request, container: ContainerDep) -> PlatformBillingPricesResponse:
    _require_system(request)
    raw = await container.shared_storage.get(_STORAGE_PRICES_KEY, force_global=True)
    override: Optional[Dict[str, Dict[str, float]]] = None
    if raw:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("billing:resource_base_prices_json должен быть JSON-объектом")
        override = _validate_price_catalog(parsed)
    effective = await container.billing_service.get_effective_resource_base_prices()
    return PlatformBillingPricesResponse(effective=effective, storage_override=override)


@router.put("/prices")
async def put_billing_prices(
    request: Request,
    container: ContainerDep,
    body: Dict[str, Any] = Body(...),
) -> dict[str, str]:
    _require_system(request)
    catalog = _validate_price_catalog(body)
    await container.shared_storage.set(
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
    request: Request,
) -> PlatformBillingSettlementRulesResponse:
    """Кодовый дефолт правил (без сохранения) — для подстановки в админке."""
    _require_system(request)
    doc = default_settlement_rules_document()
    return PlatformBillingSettlementRulesResponse(document=doc.model_dump(mode="json"))


@router.get(
    "/settlement-rules/{company_id}",
    response_model=PlatformBillingSettlementRulesResponse,
)
async def get_settlement_rules(
    request: Request,
    container: ContainerDep,
    company_id: str,
) -> PlatformBillingSettlementRulesResponse:
    _require_system(request)
    cid = company_id.strip()
    if not cid:
        raise HTTPException(status_code=422, detail="company_id не может быть пустым")
    company = await container.company_repository.get(cid)
    if company is None:
        raise HTTPException(status_code=404, detail=f"Компания {cid} не найдена")
    doc = await container.billing_service.load_settlement_rules_document_for_company(cid)
    return PlatformBillingSettlementRulesResponse(document=doc.model_dump(mode="json"))


@router.put("/settlement-rules/{company_id}")
async def put_settlement_rules(
    request: Request,
    container: ContainerDep,
    company_id: str,
    body: Dict[str, Any] = Body(...),
) -> dict[str, str]:
    _require_system(request)
    cid = company_id.strip()
    if not cid:
        raise HTTPException(status_code=422, detail="company_id не может быть пустым")
    company = await container.company_repository.get(cid)
    if company is None:
        raise HTTPException(status_code=404, detail=f"Компания {cid} не найдена")
    try:
        document = parse_settlement_rules_json(json.dumps(body))
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    for rule in document.rules:
        rn = rule.resource_name
        if isinstance(rn, str) and rn.startswith("tool:"):
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
    request: Request,
    container: ContainerDep,
    company_id: str,
) -> PlatformBillingCompanyPricesResponse:
    _require_system(request)
    if not company_id.strip():
        raise HTTPException(status_code=422, detail="company_id не может быть пустым")
    key = company_resource_prices_storage_key(company_id)
    raw = await container.shared_storage.get(key, force_global=True)
    override: Optional[Dict[str, Dict[str, float]]] = None
    if raw:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError(f"{key} должен быть JSON-объектом")
        override = _validate_price_catalog(parsed)
    effective = await container.billing_service.get_effective_resource_base_prices_for_company(company_id)
    return PlatformBillingCompanyPricesResponse(
        company_id=company_id,
        effective=effective,
        storage_override=override,
    )


@router.put("/prices/company/{company_id}")
async def put_company_billing_prices(
    request: Request,
    container: ContainerDep,
    company_id: str,
    body: Dict[str, Any] = Body(...),
) -> dict[str, str]:
    _require_system(request)
    if not company_id.strip():
        raise HTTPException(status_code=422, detail="company_id не может быть пустым")
    catalog = _validate_price_catalog(body)
    await container.shared_storage.set(
        company_resource_prices_storage_key(company_id),
        json.dumps(catalog),
        force_global=True,
    )
    return {"status": "ok"}


@router.get("/facets/usage-types", response_model=PlatformTracingFacetItemsResponse)
async def facet_usage_types(
    request: Request,
    container: ContainerDep,
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=ADMIN_FACETS_MAX_LIMIT),
) -> PlatformTracingFacetItemsResponse:
    _require_system(request)
    enum_values = {e.value for e in UsageType}
    frag = _facet_query_fragment(q)
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
    request: Request,
    container: ContainerDep,
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=ADMIN_FACETS_MAX_LIMIT),
) -> PlatformTracingFacetItemsResponse:
    _require_system(request)
    names = await container.usage_repository.admin_facet_distinct_resource_names(q=q, limit=limit)
    return PlatformTracingFacetItemsResponse(
        items=[PlatformTracingFacetItem(value=n, label=n) for n in names],
    )


@router.get("/usage-report", response_model=PlatformBillingUsageReportResponse)
async def get_usage_report(
    request: Request,
    container: ContainerDep,
    company_id: Optional[str] = Query(default=None),
    usage_type: Optional[str] = Query(default=None),
    resource_name: Optional[str] = Query(default=None),
    from_time: Optional[datetime] = Query(default=None, alias="from"),
    to_time: Optional[datetime] = Query(default=None, alias="to"),
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> PlatformBillingUsageReportResponse:
    _require_system(request)
    items = await container.usage_repository.admin_search_usage_records(
        company_id=company_id,
        usage_type=usage_type,
        resource_name=resource_name,
        from_time=from_time,
        to_time=to_time,
        limit=limit,
        offset=offset,
    )
    serialized = [rec.model_dump(mode="json") for rec in items]
    company_ids = {cid for row in serialized if (cid := row.get("company_id"))}
    companies = (
        await container.company_repository.get_many(list(company_ids)) if company_ids else {}
    )
    for row in serialized:
        cid = row.get("company_id")
        if not cid:
            continue
        co = companies.get(cid)
        row["company_name"] = co.name if co else None
    return PlatformBillingUsageReportResponse(items=serialized)
