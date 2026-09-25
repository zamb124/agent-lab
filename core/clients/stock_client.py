"""Типизированный клиент микросервиса stock (WMS).

Тонкая обвязка поверх `ServiceClient`: те же payload, что WS-команды
`stock/<entity>/<verb>_requested`. Возвращает JsonObject — контракт REST.
"""

from __future__ import annotations

from urllib.parse import quote

from core.clients.service_client import ServiceClient
from core.clients.stock_models import (
    StockMoveApplyDecisionArgs,
    StockProductCreateArgs,
    StockQuantsListArgs,
    StockTransferCreateArgs,
    StockTransfersListArgs,
    StockValuationLayersListArgs,
    StockValuationProductValueArgs,
)
from core.types import JsonObject, require_json_array, require_json_object

_API = "/stock/api/v1"


def _list_params(
    *, limit: int, offset: int, **filters: str | None
) -> dict[str, str | int]:
    params: dict[str, str | int] = {"limit": limit, "offset": offset}
    for key, value in filters.items():
        if value is not None:
            params[key] = value
    return params


class StockClient:
    """Доступ к складскому домену: quants, transfers, valuation, pulse."""

    def __init__(self, service_client: ServiceClient | None = None) -> None:
        self._http: ServiceClient = (
            service_client if service_client is not None else ServiceClient()
        )

    # --- чтение ---

    async def warehouse_pulse(self, warehouse_id: str) -> JsonObject:
        raw = await self._http.get(
            "stock", f"{_API}/warehouses/{quote(warehouse_id)}/pulse"
        )
        return require_json_object(raw, "stock.warehouse_pulse")

    async def list_quants(self, args: StockQuantsListArgs) -> JsonObject:
        raw = await self._http.get(
            "stock",
            f"{_API}/quants",
            params=_list_params(
                limit=args.limit,
                offset=args.offset,
                location_id=args.location_id,
                product_id=args.product_id,
            ),
        )
        return require_json_object(raw, "stock.list_quants")

    async def list_products(self, *, limit: int = 100, offset: int = 0) -> JsonObject:
        raw = await self._http.get(
            "stock",
            f"{_API}/products",
            params={"limit": limit, "offset": offset},
        )
        return require_json_object(raw, "stock.list_products")

    async def list_locations(self, warehouse_id: str | None = None) -> JsonObject:
        raw = await self._http.get(
            "stock",
            f"{_API}/locations",
            params={"warehouse_id": warehouse_id} if warehouse_id else None,
        )
        items = require_json_array(raw, "stock.list_locations")
        return {"items": items}

    async def list_warehouses(
        self, *, limit: int = 100, offset: int = 0
    ) -> JsonObject:
        raw = await self._http.get(
            "stock",
            f"{_API}/warehouses",
            params={"limit": limit, "offset": offset},
        )
        return require_json_object(raw, "stock.list_warehouses")

    async def list_transfers(self, args: StockTransfersListArgs) -> JsonObject:
        raw = await self._http.get(
            "stock",
            f"{_API}/transfers",
            params=_list_params(
                limit=args.limit,
                offset=args.offset,
                warehouse_id=args.warehouse_id,
                state=args.transfer_state,
            ),
        )
        return require_json_object(raw, "stock.list_transfers")

    async def get_transfer(self, transfer_id: str) -> JsonObject:
        raw = await self._http.get(
            "stock", f"{_API}/transfers/{quote(transfer_id)}"
        )
        return require_json_object(raw, "stock.get_transfer")

    async def barcode_resolve(self, barcode: str) -> JsonObject:
        raw = await self._http.get(
            "stock", f"{_API}/barcode/{quote(barcode)}"
        )
        return require_json_object(raw, "stock.barcode_resolve")

    async def valuation_product_value(
        self, args: StockValuationProductValueArgs
    ) -> JsonObject:
        raw = await self._http.get(
            "stock",
            f"{_API}/valuation/product-value",
            params={"product_id": args.product_id, "warehouse_id": args.warehouse_id}
            if args.warehouse_id
            else {"product_id": args.product_id},
        )
        return require_json_object(raw, "stock.valuation_product_value")

    async def valuation_layers(self, args: StockValuationLayersListArgs) -> JsonObject:
        raw = await self._http.get(
            "stock",
            f"{_API}/valuation/layers",
            params=_list_params(
                limit=args.limit,
                offset=args.offset,
                product_id=args.product_id,
                warehouse_id=args.warehouse_id,
            ),
        )
        return require_json_object(raw, "stock.valuation_layers")

    # --- команды ---

    async def create_product(self, args: StockProductCreateArgs) -> JsonObject:
        raw = await self._http.post(
            "stock",
            f"{_API}/products",
            json=args.model_dump(mode="json", exclude_none=True),
        )
        return require_json_object(raw, "stock.create_product")

    async def create_transfer(self, args: StockTransferCreateArgs) -> JsonObject:
        raw = await self._http.post(
            "stock",
            f"{_API}/transfers",
            json=args.model_dump(mode="json", exclude_none=True),
        )
        return require_json_object(raw, "stock.create_transfer")

    async def _transfer_action(self, transfer_id: str, action: str) -> JsonObject:
        raw = await self._http.post(
            "stock",
            f"{_API}/transfers/{quote(transfer_id)}/{action}",
            json={"transfer_id": transfer_id},
        )
        return require_json_object(raw, f"stock.transfer_{action}")

    async def confirm_transfer(self, transfer_id: str) -> JsonObject:
        return await self._transfer_action(transfer_id, "confirm")

    async def assign_transfer(self, transfer_id: str) -> JsonObject:
        return await self._transfer_action(transfer_id, "assign")

    async def validate_transfer(self, transfer_id: str) -> JsonObject:
        return await self._transfer_action(transfer_id, "validate")

    async def cancel_transfer(self, transfer_id: str) -> JsonObject:
        return await self._transfer_action(transfer_id, "cancel")

    async def move_apply_decision(
        self, args: StockMoveApplyDecisionArgs
    ) -> JsonObject:
        raw = await self._http.post(
            "stock",
            f"{_API}/moves/apply-decision",
            json=args.model_dump(mode="json"),
        )
        return require_json_object(raw, "stock.move_apply_decision")


__all__ = ["StockClient"]
