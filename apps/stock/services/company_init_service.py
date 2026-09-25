"""Инициализация stock для компании: виртуальные локации + базовые ЕИ.

Идемпотентно: `location_id` виртуальных локаций детерминированы
(`{company_id}:supplier` …), повторный запуск — no-op. Вызывается из
`idle_worker` через `stock/company/init` (internal-команда).
"""

from __future__ import annotations

from decimal import Decimal

from apps.stock.models import (
    STOCK_VIRTUAL_LOCATION_KINDS,
    StockLocation,
    StockLocationUsage,
    UnitOfMeasure,
)
from apps.stock.services.ids import new_id
from core.utils.time import utcnow


def virtual_location_id(company_id: str, usage: StockLocationUsage) -> str:
    return f"{company_id}:{usage.value}"


class StockCompanyInitService:
    """`init_company_stock`: виртуальные локации + reference-ЕИ компании."""

    async def init_company_stock(self, *, company_id: str) -> list[StockLocation]:
        now = utcnow()
        created: list[StockLocation] = []
        for usage in STOCK_VIRTUAL_LOCATION_KINDS:
            location_id = virtual_location_id(company_id, usage)
            existing = await StockLocation.by_id(company_id, location_id)
            if existing is not None:
                created.append(existing)
                continue
            row = await StockLocation.objects.create(
                instance=StockLocation(
                    location_id=location_id,
                    company_id=company_id,
                    warehouse_id=None,
                    parent_id=None,
                    name=usage.value.capitalize(),
                    usage=usage,
                    created_at=now,
                )
            )
            created.append(row)
        await self._ensure_base_uoms(company_id)
        return created

    async def _ensure_base_uoms(self, company_id: str) -> None:
        """Reference-ЕИ `Units` (категория unit): нужна для create_product."""
        for name, category, factor, is_reference in (
            ("Units", "unit", Decimal("1"), True),
            ("kg", "weight", Decimal("1"), True),
            ("g", "weight", Decimal("0.001"), False),
            ("m", "length", Decimal("1"), True),
            ("l", "volume", Decimal("1"), True),
        ):
            exists = await UnitOfMeasure.objects.filter(
                company_id=company_id, name=name
            ).exists()
            if exists:
                continue
            _ = await UnitOfMeasure.objects.create(
                instance=UnitOfMeasure(
                    uom_id=new_id("uom"),
                    company_id=company_id,
                    name=name,
                    category=category,
                    factor=factor,
                    is_reference=is_reference,
                )
            )
