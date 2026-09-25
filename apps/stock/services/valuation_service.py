"""Запросы стоимости и ручные корректировки журнала `StockValueLayer`.

Писать слои умеет только журнал (`write_for_done_move` в tx движка,
`write_adjustment` — revalue/correction). Сервис — адаптер сценариев и
агрегация для `stock/valuation/*` команд.
"""

from __future__ import annotations

from decimal import Decimal

from apps.stock.models import (
    StockLocation,
    StockProduct,
    StockQuant,
    StockValueLayer,
    ValueEntryKind,
)
from apps.stock.models.valuation import quantize
from apps.stock.services.ids import new_id
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.pagination import OffsetPage


class ProductValue:
    """`stock/valuation/product_value`: qty/value/avg по продукту."""

    def __init__(
        self,
        *,
        product_id: str,
        quantity: Decimal,
        value: Decimal,
        avg_cost: Decimal,
        warehouse_id: str | None,
    ) -> None:
        self.product_id: str = product_id
        self.quantity: Decimal = quantity
        self.value: Decimal = value
        self.avg_cost: Decimal = avg_cost
        self.warehouse_id: str | None = warehouse_id


class ValuationService:
    """Чтение журнала + `revalue`/`correction` (единственная точка ручных слоёв)."""

    async def list_layers(
        self,
        *,
        company_id: str,
        product_id: str | None,
        warehouse_id: str | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[StockValueLayer]:
        rows = await StockValueLayer.list_for_company(
            company_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            limit=limit,
            offset=offset,
        )
        total = await StockValueLayer.count_for_company(
            company_id, product_id=product_id, warehouse_id=warehouse_id
        )
        return OffsetPage(items=rows, total=total, limit=limit, offset=offset)

    async def product_value(
        self,
        *,
        company_id: str,
        product_id: str,
        warehouse_id: str | None,
    ) -> ProductValue:
        product = await StockProduct.by_id(company_id, product_id)
        if product is None:
            raise PlatformNotFoundError(
                "Product not found", error_code="product_not_found"
            )
        last = await StockValueLayer.last_for_product(company_id, product_id)
        total_value = last.value_after if last is not None else Decimal("0")
        total_qty = last.qty_after if last is not None else Decimal("0")
        if warehouse_id is not None:
            warehouse = await self._warehouse_stock_location_ids(
                company_id, warehouse_id
            )
            quants = await StockQuant.list_for_warehouse(company_id, warehouse)
            qty = sum(
                (q.quantity for q in quants if q.product_id == product_id),
                Decimal("0"),
            )
            avg = (
                quantize(total_value / total_qty)
                if total_qty > Decimal("0")
                else Decimal("0")
            )
            return ProductValue(
                product_id=product_id,
                quantity=qty,
                value=quantize(avg * qty),
                avg_cost=avg,
                warehouse_id=warehouse_id,
            )
        avg = (
            quantize(total_value / total_qty)
            if total_qty > Decimal("0")
            else Decimal("0")
        )
        return ProductValue(
            product_id=product_id,
            quantity=total_qty,
            value=total_value,
            avg_cost=avg,
            warehouse_id=None,
        )

    async def revalue(
        self,
        *,
        company_id: str,
        product_id: str,
        value_delta: Decimal | None,
        new_price: Decimal | None,
        description: str,
    ) -> StockValueLayer:
        """Ручная переоценка: `Δvalue` явно или через `new_price` на остаток."""
        if (value_delta is None) == (new_price is None):
            raise PlatformConflictError(
                "Pass exactly one of value_delta/new_price",
                error_code="revalue_input_invalid",
            )
        delta = value_delta
        if new_price is not None:
            last = await StockValueLayer.last_for_product(company_id, product_id)
            qty = last.qty_after if last is not None else Decimal("0")
            if qty <= Decimal("0"):
                raise PlatformConflictError(
                    "Cannot revalue by price with zero on-hand",
                    error_code="revalue_empty_stock",
                )
            current = last.value_after if last is not None else Decimal("0")
            delta = quantize(new_price * qty - current)
        if delta is None or delta == Decimal("0"):
            raise PlatformConflictError(
                "Revaluation delta is zero", error_code="revalue_delta_zero"
            )
        return await StockValueLayer.write_adjustment(
            company_id=company_id,
            product_id=product_id,
            entry_kind=ValueEntryKind.REVALUATION,
            value_delta=delta,
            quantity_delta=Decimal("0"),
            description=description,
            origin_layer_id=None,
            layer_id_factory=lambda: new_id("svl"),
        )

    async def correction(
        self,
        *,
        company_id: str,
        origin_layer_id: str,
        quantity_delta: Decimal,
        value_delta: Decimal,
        description: str,
    ) -> StockValueLayer:
        """Корректирующий слой к существующему (`origin_layer_id`)."""
        origin = await StockValueLayer.objects.filter(
            company_id=company_id, layer_id=origin_layer_id
        ).get_or_none()
        if origin is None:
            raise PlatformNotFoundError(
                "Origin layer not found", error_code="layer_not_found"
            )
        return await StockValueLayer.write_adjustment(
            company_id=company_id,
            product_id=origin.product_id,
            entry_kind=ValueEntryKind.CORRECTION,
            value_delta=value_delta,
            quantity_delta=quantity_delta,
            description=description,
            origin_layer_id=origin_layer_id,
            layer_id_factory=lambda: new_id("svl"),
        )

    async def _warehouse_stock_location_ids(
        self, company_id: str, warehouse_id: str
    ) -> list[str]:
        from apps.stock.models import StockWarehouse

        warehouse = await StockWarehouse.by_id(company_id, warehouse_id)
        if warehouse is None:
            raise PlatformNotFoundError(
                "Warehouse not found", error_code="warehouse_not_found"
            )
        return await StockLocation.list_subtree_ids(
            company_id, warehouse.stock_location_id
        )
