"""Пульс склада: transfers, остатки со стоимостью, активность по продуктам."""

from __future__ import annotations

from datetime import UTC
from decimal import Decimal

from apps.stock.models import (
    StockMove,
    StockOperationType,
    StockProduct,
    StockQuant,
    StockTransfer,
    StockValueLayer,
    StockWarehouse,
)
from apps.stock.models.api import (
    StockPulseQuantRow,
    StockPulseTransferRow,
    StockWarehousePulseResponse,
)
from apps.stock.models.valuation import quantize
from core.errors.boundary import PlatformNotFoundError
from core.utils.time import utcnow


class PulseService:
    """Сборка `StockWarehousePulseResponse` — витрина склада (факты, не пороги)."""

    async def warehouse_pulse(
        self, *, company_id: str, warehouse_id: str
    ) -> StockWarehousePulseResponse:
        warehouse = await StockWarehouse.by_id(company_id, warehouse_id)
        if warehouse is None:
            raise PlatformNotFoundError(
                "Warehouse not found", error_code="warehouse_not_found"
            )
        op_types = await StockOperationType.list_for_warehouse(
            company_id, warehouse_id
        )
        op_code_by_id = {op.operation_type_id: op.code.value for op in op_types}
        transfers = await StockTransfer.list_for_company(
            company_id, warehouse_id=warehouse_id, state=None, limit=200, offset=0
        )
        now = utcnow()
        transfer_rows = [
            StockPulseTransferRow(
                transfer_id=t.transfer_id,
                name=t.name,
                operation_code=op_code_by_id.get(t.operation_type_id, "internal"),
                state=t.state,
                scheduled_at=(
                    t.scheduled_at.isoformat() if t.scheduled_at is not None else None
                ),
                age_seconds=(
                    now - t.created_at.replace(tzinfo=UTC)
                ).total_seconds(),
            )
            for t in transfers
        ]
        quants = await StockQuant.list_for_warehouse(company_id, warehouse_id)
        product_ids = sorted({q.product_id for q in quants})
        products = await StockProduct.by_ids(company_id, product_ids)
        last_moves = await StockMove.list_last_move_at(company_id, product_ids)
        avg_by_product = await self._avg_costs(company_id, product_ids, products)
        quant_rows = [
            StockPulseQuantRow(
                product_id=q.product_id,
                location_id=q.location_id,
                quantity=q.quantity,
                reserved_quantity=q.reserved_quantity,
                available_quantity=q.available_quantity,
                avg_cost=avg_by_product.get(q.product_id, Decimal("0")),
                value=quantize(
                    avg_by_product.get(q.product_id, Decimal("0")) * q.quantity
                ),
                last_move_at=(
                    last_moves[q.product_id].isoformat()
                    if q.product_id in last_moves
                    else None
                ),
            )
            for q in quants
            if q.quantity != Decimal("0") or q.reserved_quantity != Decimal("0")
        ]
        return StockWarehousePulseResponse(
            warehouse_id=warehouse_id,
            transfers=transfer_rows,
            quants=quant_rows,
        )

    async def _avg_costs(
        self,
        company_id: str,
        product_ids: list[str],
        products: dict[str, StockProduct],
    ) -> dict[str, Decimal]:
        """`product_id → avg_cost`: running balance слоёв, иначе `standard_price`."""
        result: dict[str, Decimal] = {}
        for product_id in product_ids:
            last = await StockValueLayer.last_for_product(company_id, product_id)
            if last is not None and last.qty_after > Decimal("0"):
                result[product_id] = quantize(last.value_after / last.qty_after)
                continue
            product = products.get(product_id)
            result[product_id] = (
                product.standard_price if product is not None else Decimal("0")
            )
        return result
