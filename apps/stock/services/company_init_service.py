"""Инициализация stock для компании: виртуальные локации + базовые ЕИ.

Идемпотентно: `location_id` виртуальных локаций детерминированы
(`{company_id}:partner:vendor` …), повторный запуск — no-op. Вызывается из
`idle_worker` через `stock/company/init` (internal-команда).
"""

from __future__ import annotations

from apps.stock.models import (
    STOCK_VIRTUAL_LOCATION_KINDS,
    StockLocation,
    StockLocationUsage,
    StockPartnerRole,
)
from core.catalog.service import CatalogService
from core.utils.time import utcnow


def virtual_location_id(
    company_id: str,
    usage: StockLocationUsage,
    partner_role: StockPartnerRole | str | None = None,
) -> str:
    """`{company_id}:partner:vendor`, `{company_id}:transit` и т.д."""
    if usage == StockLocationUsage.PARTNER:
        return f"{company_id}:{usage.value}:{partner_role}"
    return f"{company_id}:{usage.value}"


class StockCompanyInitService:
    """`init_company_stock`: виртуальные локации + reference-ЕИ компании."""

    def __init__(self, catalog: CatalogService) -> None:
        self._catalog: CatalogService = catalog

    async def init_company_stock(self, *, company_id: str) -> list[StockLocation]:
        """Развернуть «виртуальный контур» компании — обязателен до первого склада.

        Создаёт виртуальные локации компании — точки входа/выхода
        запаса, через которые проходит граница оценки:

        * ``partner:vendor`` — «у поставщика»: источник приходов;
        * ``partner:customer`` — «у покупателя»: назначение отгрузок;
        * ``adjustment`` — «неизвестно/подвисло»: противоположная
          сторона инвентаризационных разниц;
        * ``transit`` — «в пути»: между двумя точками одной компании.

        Эти строки — единственная причина, по которой движение
        «от поставщика на склад» меняет стоимость запасов: граница
        между виртуальной и физической стороной — это граница оценки
        (см. ``valuation.py``).

        Идемпотентно по детерминированному ``location_id``
        (``{company}:partner:vendor`` и т.д.) — повторный запуск
        возвращает существующие строки.
        """
        now = utcnow()
        created: list[StockLocation] = []
        for usage, partner_role in STOCK_VIRTUAL_LOCATION_KINDS:
            location_id = virtual_location_id(company_id, usage, partner_role)
            existing = await StockLocation.by_id(company_id, location_id)
            if existing is not None:
                created.append(existing)
                continue
            name = (
                f"Partners/{partner_role}"
                if partner_role is not None
                else usage.value.capitalize()
            )
            row = await StockLocation.create(
                StockLocation(
                    location_id=location_id,
                    company_id=company_id,
                    warehouse_id=None,
                    parent_id=None,
                    parent_path=f"/{location_id}/",
                    complete_name=name,
                    name=name,
                    usage=usage,
                    partner_role=partner_role,
                    created_at=now,
                )
            )
            created.append(row)
        await self._catalog.ensure_company_uoms(company_id=company_id)
        return created
