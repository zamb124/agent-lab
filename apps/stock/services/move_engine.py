"""`StockMoveEngine` — единственный писатель `StockQuant`, оркестратор жизненного цикла.

Вся транзакционная логика — classmethod'ы моделей (`assign_locked`,
`complete_locked`, `cancel_locked`, `create_backorder_locked`,
`write_for_done_move`); здесь — последовательность вызовов, рефлекс putaway
(вне DB-транзакции) и публикация событий после commit.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from apps.stock.events import (
    StockMoveDonePayload,
    StockQuantChangedPayload,
    StockTransferDonePayload,
    publish_stock_move_done,
    publish_stock_quant_changed,
    publish_stock_transfer_done,
)
from apps.stock.models import (
    BackorderPolicy,
    ReflexMode,
    ReservationPolicy,
    StockLocation,
    StockLocationUsage,
    StockMove,
    StockMoveLine,
    StockMoveState,
    StockOperationType,
    StockProduct,
    StockQuant,
    StockTransfer,
    StockTransferState,
    StockValueLayer,
)
from apps.stock.models.api import StockMoveSpec
from apps.stock.services.ids import new_id
from apps.stock.services.putaway_service import PutawayService
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.utils.time import utcnow


def _line_id() -> str:
    return new_id("mli")


def _quant_id() -> str:
    return new_id("qnt")


def _layer_id() -> str:
    return new_id("svl")


def _consumption_id() -> str:
    return new_id("svc")


def _move_id() -> str:
    return new_id("mov")


def _transfer_id() -> str:
    return new_id("trf")


class StockMoveEngine:
    """Жизненный цикл transfer/move: confirm → assign → done, cancel, return."""

    def __init__(self, putaway: PutawayService) -> None:
        self._putaway: PutawayService = putaway

    # --- CRUD перевода ---

    async def create_transfer(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        operation_type_id: str,
        partner_entity_id: str | None,
        owner_entity_id: str | None,
        scheduled_at: datetime | None,
        origin_document_type: str | None,
        origin_document_id: str | None,
        barcode: str | None,
        moves: list[StockMoveSpec],
    ) -> StockTransfer:
        warehouse = await self._require_warehouse(company_id, warehouse_id)
        operation_type = await self._require_operation_type(
            company_id, operation_type_id
        )
        if operation_type.warehouse_id != warehouse.warehouse_id:
            raise PlatformConflictError(
                "Operation type belongs to another warehouse",
                error_code="operation_type_warehouse_mismatch",
            )
        now = utcnow()
        prefix = f"{warehouse.code}/{operation_type.code.value.upper()}"
        transfer = StockTransfer(
            transfer_id=_transfer_id(),
            company_id=company_id,
            warehouse_id=warehouse.warehouse_id,
            operation_type_id=operation_type.operation_type_id,
            partner_entity_id=partner_entity_id,
            owner_entity_id=owner_entity_id,
            name=await StockTransfer.next_name(company_id, prefix),
            barcode=barcode,
            state=StockTransferState.DRAFT,
            scheduled_at=scheduled_at,
            origin_document_type=origin_document_type,
            origin_document_id=origin_document_id,
            created_at=now,
            updated_at=now,
        )
        _ = await StockTransfer.objects.create(instance=transfer)
        for spec in moves:
            src_id = spec.location_id or operation_type.default_source_location_id
            dst_id = spec.location_dest_id or operation_type.default_dest_location_id
            if src_id is None or dst_id is None:
                raise PlatformConflictError(
                    "Move requires location_id/location_dest_id",
                    error_code="move_locations_missing",
                )
            _ = await StockMove.objects.create(
                instance=StockMove(
                    move_id=_move_id(),
                    company_id=company_id,
                    transfer_id=transfer.transfer_id,
                    product_id=spec.product_id,
                    product_qty=spec.product_qty,
                    product_uom_qty=spec.product_qty,
                    uom_id=spec.uom_id,
                    location_id=src_id,
                    location_dest_id=dst_id,
                    state=StockMoveState.DRAFT,
                    operation_type_id=operation_type.operation_type_id,
                    origin_document_type=origin_document_type,
                    origin_document_id=origin_document_id,
                    unit_price=spec.unit_price,
                    date=now,
                    created_at=now,
                )
            )
        return transfer

    # --- Жизненный цикл ---

    async def confirm_transfer(
        self, *, company_id: str, transfer_id: str
    ) -> StockTransfer:
        transfer = await self._require_transfer(company_id, transfer_id)
        moves = await StockMove.list_for_transfer(company_id, transfer_id)
        for move in moves:
            _ = await StockMove.confirm_locked(company_id=company_id, move_id=move.move_id)
        operation_type = await self._require_operation_type(
            company_id, transfer.operation_type_id
        )
        if operation_type.reservation_policy == ReservationPolicy.AT_CONFIRM:
            await self._assign_moves(company_id, transfer, operation_type)
        _ = await StockTransfer.refresh_state(company_id, transfer_id)
        return await self._require_transfer(company_id, transfer_id)

    async def assign_transfer(
        self, *, company_id: str, transfer_id: str
    ) -> StockTransfer:
        transfer = await self._require_transfer(company_id, transfer_id)
        operation_type = await self._require_operation_type(
            company_id, transfer.operation_type_id
        )
        await self._assign_moves(company_id, transfer, operation_type)
        _ = await StockTransfer.refresh_state(company_id, transfer_id)
        return await self._require_transfer(company_id, transfer_id)

    async def _assign_moves(
        self,
        company_id: str,
        transfer: StockTransfer,
        operation_type: StockOperationType,
    ) -> None:
        warehouse = await self._require_warehouse(company_id, transfer.warehouse_id)
        moves = await StockMove.list_for_transfer(company_id, transfer.transfer_id)
        for move in moves:
            if move.state in {StockMoveState.DONE, StockMoveState.CANCEL}:
                continue
            dest: str | None = None
            dst = await StockLocation.by_id(company_id, move.location_dest_id)
            src = await StockLocation.by_id(company_id, move.location_id)
            if (
                dst is not None
                and src is not None
                and dst.usage == StockLocationUsage.INTERNAL
                and src.usage != StockLocationUsage.INTERNAL
            ):
                decision = await self._putaway.resolve_putaway(
                    company_id=company_id,
                    warehouse=warehouse,
                    operation_type=operation_type,
                    move=move,
                )
                if (
                    decision is not None
                    and decision.chosen_location_id is not None
                    and operation_type.putaway_mode != ReflexMode.SHADOW
                ):
                    dest = decision.chosen_location_id
            _ = await StockMove.assign_locked(
                company_id=company_id,
                move_id=move.move_id,
                dest_location_id=dest,
                line_id_factory=_line_id,
            )

    async def validate_transfer(
        self, *, company_id: str, transfer_id: str
    ) -> StockTransfer:
        transfer = await self._require_transfer(company_id, transfer_id)
        operation_type = await self._require_operation_type(
            company_id, transfer.operation_type_id
        )
        moves = await StockMove.list_for_transfer(company_id, transfer_id)
        pending = [
            m
            for m in moves
            if m.state
            in {
                StockMoveState.CONFIRMED,
                StockMoveState.PARTIALLY_AVAILABLE,
                StockMoveState.ASSIGNED,
            }
        ]
        residual_move_ids: list[str] = []
        done_pairs: list[tuple[StockMove, list[StockValueLayer]]] = []
        for move in pending:
            done_move, layers, _ = await StockMove.complete_locked(
                company_id=company_id,
                move_id=move.move_id,
                warehouse_id=transfer.warehouse_id,
                quant_id_factory=_quant_id,
                layer_id_factory=_layer_id,
                consumption_id_factory=_consumption_id,
            )
            done_pairs.append((done_move, layers))
            lines = await StockMoveLine.list_for_move(company_id, move.move_id)
            done_qty = sum((line.done_quantity for line in lines), Decimal("0"))
            if done_qty < move.product_uom_qty:
                residual_move_ids.append(move.move_id)
        backorder: StockTransfer | None = None
        if residual_move_ids and operation_type.backorder_policy == BackorderPolicy.ALWAYS:
            backorder = await StockTransfer.create_backorder_locked(
                company_id=company_id,
                transfer_id=transfer_id,
                residual_move_ids=residual_move_ids,
                transfer_id_factory=_transfer_id,
                move_id_factory=_move_id,
            )
        final_state = await StockTransfer.refresh_state(company_id, transfer_id)
        for done_move, layers in done_pairs:
            await self._publish_move_done(
                company_id, done_move, layers, operation_type
            )
            await self._publish_quant_changes(company_id, done_move)
        if final_state == StockTransferState.DONE:
            await self._publish_transfer_done(
                company_id,
                transfer,
                operation_type,
                done_pairs,
                backorder,
            )
        return await self._require_transfer(company_id, transfer_id)

    async def cancel_transfer(
        self, *, company_id: str, transfer_id: str
    ) -> StockTransfer:
        _ = await self._require_transfer(company_id, transfer_id)
        moves = await StockMove.list_for_transfer(company_id, transfer_id)
        for move in moves:
            if move.state == StockMoveState.DONE:
                raise PlatformConflictError(
                    "Done transfer cannot be cancelled",
                    error_code="transfer_done",
                )
            if move.state == StockMoveState.CANCEL:
                continue
            _ = await StockMove.cancel_locked(company_id=company_id, move_id=move.move_id)
        _ = await StockTransfer.refresh_state(company_id, transfer_id)
        return await self._require_transfer(company_id, transfer_id)

    async def unreserve_move(
        self, *, company_id: str, move_id: str
    ) -> StockMove:
        move = await StockMove.unreserve_locked(company_id=company_id, move_id=move_id)
        if move.transfer_id is not None:
            _ = await StockTransfer.refresh_state(company_id, move.transfer_id)
        return move

    async def return_transfer(
        self,
        *,
        company_id: str,
        transfer_id: str,
        move_quantities: dict[str, Decimal] | None = None,
    ) -> StockTransfer:
        """Возврат как обратный transfer: `return_of_id` + moves с `returned_move_id`."""
        source = await self._require_transfer(company_id, transfer_id)
        moves = await StockMove.list_for_transfer(company_id, transfer_id)
        done_moves = [m for m in moves if m.state == StockMoveState.DONE]
        if not done_moves:
            raise PlatformConflictError(
                "Only done transfers can be returned", error_code="transfer_not_done"
            )
        now = utcnow()
        prefix = f"{source.name.split('/')[0]}/RET"
        back = StockTransfer(
            transfer_id=_transfer_id(),
            company_id=company_id,
            warehouse_id=source.warehouse_id,
            operation_type_id=source.operation_type_id,
            partner_entity_id=source.partner_entity_id,
            owner_entity_id=source.owner_entity_id,
            name=await StockTransfer.next_name(company_id, prefix),
            state=StockTransferState.DRAFT,
            return_of_id=transfer_id,
            origin_document_type=source.origin_document_type,
            origin_document_id=source.origin_document_id,
            created_at=now,
            updated_at=now,
        )
        _ = await StockTransfer.objects.create(instance=back)
        for move in done_moves:
            qty = (
                move_quantities.get(move.move_id)
                if move_quantities is not None
                else move.product_uom_qty
            )
            if qty is None or qty <= Decimal("0"):
                continue
            _ = await StockMove.objects.create(
                instance=StockMove(
                    move_id=_move_id(),
                    company_id=company_id,
                    transfer_id=back.transfer_id,
                    product_id=move.product_id,
                    product_qty=qty,
                    product_uom_qty=qty,
                    uom_id=move.uom_id,
                    location_id=move.location_dest_id,
                    location_dest_id=move.location_id,
                    state=StockMoveState.DRAFT,
                    operation_type_id=move.operation_type_id,
                    origin_document_type=move.origin_document_type,
                    origin_document_id=move.origin_document_id,
                    returned_move_id=move.move_id,
                    unit_price=move.unit_price,
                    date=now,
                    created_at=now,
                )
            )
        _ = await self.confirm_transfer(
            company_id=company_id, transfer_id=back.transfer_id
        )
        _ = await self.assign_transfer(company_id=company_id, transfer_id=back.transfer_id)
        return await self.validate_transfer(
            company_id=company_id, transfer_id=back.transfer_id
        )

    # --- Инвентаризация ---

    async def inventory_set(
        self, *, company_id: str, quant_id: str, inventory_quantity: Decimal
    ) -> StockQuant:
        _ = await self._require_quant(company_id, quant_id)
        if inventory_quantity < Decimal("0"):
            raise PlatformConflictError(
                "Inventory quantity must be >= 0", error_code="inventory_qty_invalid"
            )
        await StockQuant.set_inventory_quantity(quant_id, inventory_quantity)
        return await self._require_quant(company_id, quant_id)

    async def inventory_apply(self, *, company_id: str, quant_id: str) -> StockMove:
        """Применить посчитанное: move `internal↔inventory` на дельту, тот же движок."""
        quant = await self._require_quant(company_id, quant_id)
        if quant.inventory_quantity is None:
            raise PlatformConflictError(
                "Quant has no pending inventory", error_code="inventory_empty"
            )
        delta = quant.inventory_quantity - quant.quantity
        await StockQuant.set_inventory_quantity(quant_id, None)
        if delta == Decimal("0"):
            raise PlatformConflictError(
                "Inventory delta is zero", error_code="inventory_delta_zero"
            )
        inventory = await StockLocation.virtual_by_usage(
            company_id, StockLocationUsage.INVENTORY
        )
        if inventory is None:
            raise PlatformNotFoundError(
                "Virtual inventory location missing; run stock/company/init",
                error_code="location_not_found",
            )
        now = utcnow()
        src, dst = (
            (quant.location_id, inventory.location_id)
            if delta < Decimal("0")
            else (inventory.location_id, quant.location_id)
        )
        move = await StockMove.objects.create(
            instance=StockMove(
                move_id=_move_id(),
                company_id=company_id,
                transfer_id=None,
                product_id=quant.product_id,
                product_qty=abs(delta),
                product_uom_qty=abs(delta),
                uom_id=await self._product_uom(company_id, quant.product_id),
                location_id=src,
                location_dest_id=dst,
                state=StockMoveState.CONFIRMED,
                origin_document_type="stock_inventory",
                origin_document_id=quant.quant_id,
                date=now,
                created_at=now,
            )
        )
        line = StockMoveLine(
            move_line_id=_line_id(),
            company_id=company_id,
            move_id=move.move_id,
            product_id=quant.product_id,
            lot_id=quant.lot_id,
            package_id=quant.package_id,
            owner_entity_id=quant.owner_entity_id,
            quantity=abs(delta),
            done_quantity=abs(delta),
            location_id=src,
            location_dest_id=dst,
            created_at=now,
        )
        _ = await StockMoveLine.objects.create(instance=line)
        done_move, layers, _ = await StockMove.complete_locked(
            company_id=company_id,
            move_id=move.move_id,
            warehouse_id=None,
            quant_id_factory=_quant_id,
            layer_id_factory=_layer_id,
            consumption_id_factory=_consumption_id,
        )
        await self._publish_move_done(company_id, done_move, layers, None)
        await self._publish_quant_changes(company_id, done_move)
        return done_move

    # --- Публикация событий (после commit) ---

    async def _publish_move_done(
        self,
        company_id: str,
        move: StockMove,
        layers: list[StockValueLayer],
        operation_type: StockOperationType | None,
    ) -> None:
        src = await StockLocation.by_id(company_id, move.location_id)
        dst = await StockLocation.by_id(company_id, move.location_dest_id)
        if src is None or dst is None:
            return
        lines = await StockMoveLine.list_for_move(company_id, move.move_id)
        done_qty = sum((line.done_quantity for line in lines), Decimal("0"))
        total_value = sum((layer.value for layer in layers), Decimal("0"))
        payload = StockMoveDonePayload(
            company_id=company_id,
            move_id=move.move_id,
            transfer_id=move.transfer_id,
            warehouse_id=None,
            operation_type_id=move.operation_type_id,
            operation_code=(
                operation_type.code.value if operation_type is not None else None
            ),
            product_id=move.product_id,
            location_id=move.location_id,
            location_dest_id=move.location_dest_id,
            location_usage=src.usage,
            location_dest_usage=dst.usage,
            quantity=done_qty,
            unit_price=move.unit_price,
            unit_cost=(
                abs(total_value / done_qty) if done_qty > Decimal("0") else None
            ),
            value=abs(total_value) if layers else None,
            value_layer_ids=[layer.layer_id for layer in layers],
            returned_move_id=move.returned_move_id,
            origin_document_type=move.origin_document_type,
            origin_document_id=move.origin_document_id,
            done_at=(move.done_at or utcnow()).isoformat(),
        )
        await publish_stock_move_done(company_id, payload)

    async def _publish_quant_changes(
        self, company_id: str, move: StockMove
    ) -> None:
        lines = await StockMoveLine.list_for_move(company_id, move.move_id)
        seen: set[tuple[str, str | None, str | None]] = set()
        for line in lines:
            for location_id in (line.location_id, line.location_dest_id):
                location = await StockLocation.by_id(company_id, location_id)
                if location is None or location.usage != StockLocationUsage.INTERNAL:
                    continue
                key = (location_id, line.lot_id, line.package_id)
                if key in seen:
                    continue
                seen.add(key)
                quant = await StockQuant.by_key(
                    company_id=company_id,
                    product_id=line.product_id,
                    location_id=location_id,
                    lot_id=line.lot_id,
                    package_id=line.package_id,
                    owner_entity_id=line.owner_entity_id,
                )
                if quant is None:
                    continue
                await publish_stock_quant_changed(
                    company_id,
                    StockQuantChangedPayload(
                        company_id=company_id,
                        quant_id=quant.quant_id,
                        product_id=quant.product_id,
                        location_id=quant.location_id,
                        lot_id=quant.lot_id,
                        package_id=quant.package_id,
                        owner_entity_id=quant.owner_entity_id,
                        quantity=quant.quantity,
                        reserved_quantity=quant.reserved_quantity,
                        move_id=move.move_id,
                    ),
                )

    async def _publish_transfer_done(
        self,
        company_id: str,
        transfer: StockTransfer,
        operation_type: StockOperationType,
        done_pairs: list[tuple[StockMove, list[StockValueLayer]]],
        backorder: StockTransfer | None,
    ) -> None:
        payload = StockTransferDonePayload(
            company_id=company_id,
            transfer_id=transfer.transfer_id,
            warehouse_id=transfer.warehouse_id,
            operation_type_id=transfer.operation_type_id,
            operation_code=operation_type.code.value,
            name=transfer.name,
            partner_entity_id=transfer.partner_entity_id,
            backorder_of_id=transfer.backorder_of_id,
            return_of_id=transfer.return_of_id,
            backorder_transfer_id=(
                backorder.transfer_id if backorder is not None else None
            ),
            move_ids=[move.move_id for move, _ in done_pairs],
            origin_document_type=transfer.origin_document_type,
            origin_document_id=transfer.origin_document_id,
            done_at=utcnow().isoformat(),
        )
        await publish_stock_transfer_done(company_id, payload)

    # --- helpers ---

    async def _require_warehouse(self, company_id: str, warehouse_id: str):
        from apps.stock.models import StockWarehouse

        warehouse = await StockWarehouse.by_id(company_id, warehouse_id)
        if warehouse is None:
            raise PlatformNotFoundError(
                "Warehouse not found", error_code="warehouse_not_found"
            )
        return warehouse

    async def _require_operation_type(
        self, company_id: str, operation_type_id: str
    ) -> StockOperationType:
        operation_type = await StockOperationType.by_id(company_id, operation_type_id)
        if operation_type is None:
            raise PlatformNotFoundError(
                "Operation type not found", error_code="operation_type_not_found"
            )
        return operation_type

    async def _require_transfer(
        self, company_id: str, transfer_id: str
    ) -> StockTransfer:
        transfer = await StockTransfer.by_id(company_id, transfer_id)
        if transfer is None:
            raise PlatformNotFoundError(
                "Transfer not found", error_code="transfer_not_found"
            )
        return transfer

    async def _require_quant(self, company_id: str, quant_id: str) -> StockQuant:
        quant = await StockQuant.objects.filter(
            company_id=company_id, quant_id=quant_id
        ).get_or_none()
        if quant is None:
            raise PlatformNotFoundError("Quant not found", error_code="quant_not_found")
        return quant

    async def _product_uom(self, company_id: str, product_id: str) -> str:
        product = await StockProduct.by_id(company_id, product_id)
        if product is None:
            raise PlatformNotFoundError(
                "Product not found", error_code="product_not_found"
            )
        return product.uom_id
