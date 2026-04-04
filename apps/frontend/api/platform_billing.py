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
    PlatformBillingPricesResponse,
    PlatformBillingSettlementRulesResponse,
    PlatformBillingUsageReportResponse,
)
from core.billing.service import STORAGE_SETTLEMENT_RULES_JSON, company_resource_prices_storage_key
from core.billing.settlement_rules import parse_settlement_rules_json
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID

router = APIRouter(prefix="/api/platform-billing", tags=["platform-billing"])

_STORAGE_PRICES_KEY = "billing:resource_base_prices_json"


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
    "/settlement-rules",
    response_model=PlatformBillingSettlementRulesResponse,
)
async def get_settlement_rules(request: Request, container: ContainerDep) -> PlatformBillingSettlementRulesResponse:
    _require_system(request)
    doc = await container.billing_service.load_settlement_rules_document()
    return PlatformBillingSettlementRulesResponse(document=doc.model_dump(mode="json"))


@router.put("/settlement-rules")
async def put_settlement_rules(
    request: Request,
    container: ContainerDep,
    body: Dict[str, Any] = Body(...),
) -> dict[str, str]:
    _require_system(request)
    try:
        parse_settlement_rules_json(json.dumps(body))
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    await container.shared_storage.set(
        STORAGE_SETTLEMENT_RULES_JSON,
        json.dumps(body),
        force_global=True,
    )
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


@router.get("/usage-report", response_model=PlatformBillingUsageReportResponse)
async def get_usage_report(
    request: Request,
    container: ContainerDep,
    company_id: Optional[str] = Query(default=None),
    usage_type: Optional[str] = Query(default=None),
    from_time: Optional[datetime] = Query(default=None, alias="from"),
    to_time: Optional[datetime] = Query(default=None, alias="to"),
    limit: int = Query(default=200, ge=1, le=5000),
) -> PlatformBillingUsageReportResponse:
    _require_system(request)
    items = await container.usage_repository.admin_search_usage_records(
        company_id=company_id,
        usage_type=usage_type,
        from_time=from_time,
        to_time=to_time,
        limit=limit,
    )
    serialized = [rec.model_dump(mode="json") for rec in items]
    return PlatformBillingUsageReportResponse(items=serialized)
