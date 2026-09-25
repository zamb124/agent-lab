"""
Доменные модели склада (WMS, apps/stock, БД platform_stock).

Модель Odoo 19 `stock`: любое изменение количества — `StockMove` из локации A
в локацию B. Приход = supplier→internal, отгрузка = internal→customer,
инвентаризация = internal↔inventory. Отдельных сущностей «приход»/«списание» нет.

Писатели:
- `StockQuant` — только движок (`assign`/`unreserve` → `reserved_quantity`,
  `done` → `quantity`). Проекция ведётся только по `internal` локациям:
  виртуальные (supplier/customer/inventory/…) не имеют остатка, их факт — сам move.
- `StockValueLayer` — только done-фаза движка в той же транзакции (append-only,
  `entry_no` nogap per company через `StockLedgerCounter` SELECT FOR UPDATE;
  PG sequence не годится — даёт пропуски при rollback).

Канон — `.cursor/rules/stock.mdc`. `objects`/`atomic`/`execute_raw` живут только
в classmethod'ах моделей, не в сервисах и `op_*`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Self

from oxyde import F, Index, atomic, execute_raw
from oxyde import Field as DbField
from oxyde.exceptions import UniqueViolationError

from apps.stock.models.enums import (
    STOCK_VIRTUAL_LOCATION_KINDS,
    BackorderPolicy,
    ReflexMode,
    ReflexPoint,
    ReservationPolicy,
    StockBarcodeEntityType,
    StockDecisionStatus,
    StockLocationUsage,
    StockMoveState,
    StockOperationCode,
    StockTracking,
    StockTransferState,
    ValuationMethod,
    ValuationPriceSource,
    ValueEntryKind,
)
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.models.platform_model import PlatformModel
from core.types import require_json_object
from core.utils.time import utcnow

STOCK_DB = "stock"

QTY_DB = "NUMERIC(20,6)"
MONEY_DB = "NUMERIC(24,6)"
_ZERO = Decimal("0")

__all__ = [
    "STOCK_VIRTUAL_LOCATION_KINDS",
    "BackorderPolicy",
    "ReflexMode",
    "ReflexPoint",
    "ReservationPolicy",
    "StockBarcodeEntityType",
    "StockDecisionStatus",
    "StockLocationUsage",
    "StockMoveState",
    "StockOperationCode",
    "StockTracking",
    "StockTransferState",
    "ValuationMethod",
    "ValuationPriceSource",
    "ValueEntryKind",
]


_REMOVABLE_STATES = {StockMoveState.DRAFT, StockMoveState.CONFIRMED, StockMoveState.WAITING}
_RESERVABLE_STATES = {
    StockMoveState.CONFIRMED,
    StockMoveState.PARTIALLY_AVAILABLE,
    StockMoveState.ASSIGNED,
}


def _require(condition: bool, message: str, *, error_code: str) -> None:
    if not condition:
        raise PlatformConflictError(message, error_code=error_code)


class UnitOfMeasure(PlatformModel):
    """Единица измерения. Таблица ``stock_uom``."""

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_uom"
        indexes: list[Index] = [Index(["company_id", "name"], unique=True)]

    uom_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    name: str = DbField(max_length=64)
    category: str = DbField(max_length=64)
    factor: Decimal = DbField(db_type=QTY_DB)
    is_reference: bool = DbField(default=False)

    @classmethod
    async def by_id(cls, company_id: str, uom_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, uom_id=uom_id
        ).get_or_none()

    @classmethod
    async def convert(
        cls,
        quantity: Decimal,
        from_uom_id: str,
        to_uom_id: str,
    ) -> Decimal:
        """Перевод количества между ЕИ одной категории через reference-фактор."""
        if from_uom_id == to_uom_id:
            return quantity
        pair = await cls.get_many([from_uom_id, to_uom_id])
        src = pair.get(from_uom_id)
        dst = pair.get(to_uom_id)
        if src is None or dst is None:
            raise PlatformNotFoundError(
                "Unit of measure not found", error_code="uom_not_found"
            )
        if src.category != dst.category:
            raise PlatformConflictError(
                "UoM category mismatch",
                error_code="uom_category_mismatch",
            )
        if src.factor == _ZERO or dst.factor == _ZERO:
            raise PlatformConflictError(
                "UoM factor is zero", error_code="uom_factor_zero"
            )
        return quantity * src.factor / dst.factor


class StockProductTemplate(PlatformModel):
    """Карточка продукта: tracking и метод оценки. Таблица ``stock_product_templates``."""

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_product_templates"
        indexes: list[Index] = [Index(["company_id", "name"])]

    product_template_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    name: str = DbField(max_length=255)
    tracking: StockTracking = DbField(default=StockTracking.NONE)
    is_storable: bool = DbField(default=True)
    category: str = DbField(default="", max_length=128)
    valuation_method: ValuationMethod = DbField()
    standard_price: Decimal = DbField(default=_ZERO, db_type=MONEY_DB)
    uom_id: str = DbField(max_length=64)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def by_id(cls, company_id: str, product_template_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, product_template_id=product_template_id
        ).get_or_none()

    @classmethod
    async def update_valuation_method(
        cls,
        *,
        company_id: str,
        product_template_id: str,
        valuation_method: ValuationMethod,
        standard_price: Decimal | None,
    ) -> Self:
        """Смена метода оценки. Запрещена при наличии слоёв по продуктам шаблона."""
        async with atomic(using=STOCK_DB):
            template = await cls.objects.filter(
                company_id=company_id, product_template_id=product_template_id
            ).for_update().get_or_none()
            if template is None:
                raise PlatformNotFoundError(
                    "Product template not found", error_code="product_not_found"
                )
            if template.valuation_method != valuation_method:
                has_layers = await StockValueLayer.objects.filter(
                    company_id=company_id,
                    product_id__in=await cls._product_ids(company_id, product_template_id),
                ).exists()
                if has_layers:
                    raise PlatformConflictError(
                        "Valuation method is locked by existing layers",
                        error_code="valuation_method_locked",
                    )
            template.valuation_method = valuation_method
            if standard_price is not None:
                template.standard_price = standard_price
            template.updated_at = utcnow()
            _ = await template.save()
            return template

    @classmethod
    async def _product_ids(cls, company_id: str, product_template_id: str) -> list[str]:
        rows = await StockProduct.objects.filter(
            company_id=company_id, template_id=product_template_id
        ).all()
        return [row.product_id for row in rows]


class StockProduct(PlatformModel):
    """Вариант продукта (SKU). Таблица ``stock_products``."""

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_products"
        indexes: list[Index] = [
            Index(["company_id", "sku"], unique=True),
            Index(["company_id", "template_id"]),
            Index(["company_id", "barcode"]),
        ]

    product_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    template_id: str = DbField(max_length=64)
    sku: str = DbField(max_length=128)
    barcode: str | None = DbField(default=None, max_length=128)
    uom_id: str = DbField(max_length=64)
    is_active: bool = DbField(default=True)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def by_id(cls, company_id: str, product_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, product_id=product_id
        ).get_or_none()

    @classmethod
    async def by_ids(cls, company_id: str, product_ids: list[str]) -> dict[str, Self]:
        if not product_ids:
            return {}
        rows = await cls.objects.filter(
            company_id=company_id, product_id__in=product_ids
        ).all()
        return {row.product_id: row for row in rows}

    @classmethod
    async def list_for_company(
        cls, company_id: str, *, limit: int, offset: int
    ) -> list[Self]:
        return await cls.objects.filter(company_id=company_id).order_by("sku").limit(
            limit
        ).offset(offset).all()

    @classmethod
    async def count_for_company(cls, company_id: str) -> int:
        return await cls.objects.filter(company_id=company_id).count()


class StockLocation(PlatformModel):
    """Локация склада. Таблица ``stock_locations``.

    Виртуальные локации компании (`supplier`, `customer`, `inventory`,
    `production`, `transit`) создаются `init_company_stock` и делают приход,
    отгрузку и инвентаризацию одним механизмом `StockMove` A→B.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_locations"
        indexes: list[Index] = [
            Index(["company_id", "warehouse_id", "parent_id"]),
            Index(["company_id", "usage"]),
            Index(["company_id", "barcode"]),
        ]

    location_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str | None = DbField(default=None, max_length=64)
    parent_id: str | None = DbField(default=None, max_length=64)
    name: str = DbField(max_length=255)
    usage: StockLocationUsage = DbField()
    removal_method: str = DbField(default="fifo", max_length=32)
    barcode: str | None = DbField(default=None, max_length=128)
    is_active: bool = DbField(default=True)
    created_at: datetime = DbField()

    @classmethod
    async def by_id(cls, company_id: str, location_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, location_id=location_id
        ).get_or_none()

    @classmethod
    async def by_ids(cls, company_id: str, location_ids: list[str]) -> dict[str, Self]:
        if not location_ids:
            return {}
        rows = await cls.objects.filter(
            company_id=company_id, location_id__in=location_ids
        ).all()
        return {row.location_id: row for row in rows}

    @classmethod
    async def list_for_company(cls, company_id: str) -> list[Self]:
        return await cls.objects.filter(company_id=company_id).order_by(
            "usage", "name"
        ).all()

    @classmethod
    async def list_subtree_ids(cls, company_id: str, root_id: str) -> list[str]:
        """`root_id` + все потомки (обход по уровням)."""
        rows = await cls.objects.filter(company_id=company_id).all()
        by_parent: dict[str | None, list[str]] = {}
        for row in rows:
            by_parent.setdefault(row.parent_id, []).append(row.location_id)
        collected: list[str] = []
        queue = [root_id]
        while queue:
            current = queue.pop()
            collected.append(current)
            queue.extend(by_parent.get(current, []))
        return collected

    @classmethod
    async def virtual_by_usage(
        cls, company_id: str, usage: StockLocationUsage
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, usage=usage, warehouse_id=None
        ).get_or_none()


class StockWarehouse(PlatformModel):
    """Площадка склада компании. Таблица ``stock_warehouses``."""

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_warehouses"
        indexes: list[Index] = [Index(["company_id", "code"], unique=True)]

    warehouse_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    code: str = DbField(max_length=32)
    name: str = DbField(max_length=255)
    view_location_id: str = DbField(max_length=64)
    stock_location_id: str = DbField(max_length=64)
    created_at: datetime = DbField()

    @classmethod
    async def by_id(cls, company_id: str, warehouse_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, warehouse_id=warehouse_id
        ).get_or_none()

    @classmethod
    async def list_for_company(
        cls, company_id: str, *, limit: int, offset: int
    ) -> list[Self]:
        return await cls.objects.filter(company_id=company_id).order_by("code").limit(
            limit
        ).offset(offset).all()

    @classmethod
    async def count_for_company(cls, company_id: str) -> int:
        return await cls.objects.filter(company_id=company_id).count()


class StockLot(PlatformModel):
    """Партия/серийный номер продукта. Таблица ``stock_lots``."""

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_lots"
        indexes: list[Index] = [
            Index(["company_id", "product_id", "name"], unique=True),
            Index(["company_id", "barcode"]),
        ]

    lot_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    product_id: str = DbField(max_length=64)
    name: str = DbField(max_length=128)
    barcode: str | None = DbField(default=None, max_length=128)
    expiration_at: datetime | None = DbField(default=None)
    created_at: datetime = DbField()

    @classmethod
    async def by_id(cls, company_id: str, lot_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, lot_id=lot_id
        ).get_or_none()


class StockPackageType(PlatformModel):
    """Тип упаковки. Таблица ``stock_package_types``."""

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_package_types"
        indexes: list[Index] = [Index(["company_id", "name"], unique=True)]

    package_type_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    name: str = DbField(max_length=128)
    created_at: datetime = DbField()


class StockPackage(PlatformModel):
    """Упаковка (паллета/короб). Таблица ``stock_packages``."""

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_packages"
        indexes: list[Index] = [Index(["company_id", "barcode"])]

    package_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    package_type_id: str | None = DbField(default=None, max_length=64)
    parent_package_id: str | None = DbField(default=None, max_length=64)
    location_id: str | None = DbField(default=None, max_length=64)
    barcode: str | None = DbField(default=None, max_length=128)
    created_at: datetime = DbField()


class StockOperationType(PlatformModel):
    """Тип операции склада. Таблица ``stock_operation_types``."""

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_operation_types"
        indexes: list[Index] = [
            Index(["company_id", "code", "warehouse_id"], unique=True),
            Index(["company_id", "warehouse_id"]),
        ]

    operation_type_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str = DbField(max_length=64)
    code: StockOperationCode = DbField()
    name: str = DbField(max_length=255)
    default_source_location_id: str | None = DbField(default=None, max_length=64)
    default_dest_location_id: str | None = DbField(default=None, max_length=64)
    reservation_policy: ReservationPolicy = DbField(default=ReservationPolicy.MANUAL)
    backorder_policy: BackorderPolicy = DbField(default=BackorderPolicy.ALWAYS)
    putaway_mode: ReflexMode = DbField(default=ReflexMode.RULE)
    putaway_flow_id: str | None = DbField(default=None, max_length=64)
    auto_validate: bool = DbField(default=False)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def by_id(cls, company_id: str, operation_type_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, operation_type_id=operation_type_id
        ).get_or_none()

    @classmethod
    async def list_for_warehouse(
        cls, company_id: str, warehouse_id: str
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id, warehouse_id=warehouse_id
        ).order_by("code").all()


class StockTransfer(PlatformModel):
    """Документ-группировка движений. Таблица ``stock_transfers``.

    `state` — проекция состояний его `StockMove`; пишет только движок.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_transfers"
        indexes: list[Index] = [
            Index(["company_id", "name"], unique=True),
            Index(["company_id", "warehouse_id", "state"]),
            Index(["company_id", "operation_type_id", "state"]),
            Index(["company_id", "barcode"]),
        ]

    transfer_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str = DbField(max_length=64)
    operation_type_id: str = DbField(max_length=64)
    partner_entity_id: str | None = DbField(default=None, max_length=64)
    owner_entity_id: str | None = DbField(default=None, max_length=64)
    name: str = DbField(max_length=64)
    barcode: str | None = DbField(default=None, max_length=128)
    state: StockTransferState = DbField(default=StockTransferState.DRAFT)
    scheduled_at: datetime | None = DbField(default=None)
    origin_document_type: str | None = DbField(default=None, max_length=64)
    origin_document_id: str | None = DbField(default=None, max_length=64)
    backorder_of_id: str | None = DbField(default=None, max_length=64)
    return_of_id: str | None = DbField(default=None, max_length=64)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def by_id(cls, company_id: str, transfer_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, transfer_id=transfer_id
        ).get_or_none()

    @classmethod
    async def by_id_locked(cls, company_id: str, transfer_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, transfer_id=transfer_id
        ).for_update().get_or_none()

    @classmethod
    async def list_for_company(
        cls,
        company_id: str,
        *,
        warehouse_id: str | None,
        state: StockTransferState | None,
        limit: int,
        offset: int,
    ) -> list[Self]:
        query = cls.objects.filter(company_id=company_id)
        if warehouse_id is not None:
            query = query.filter(warehouse_id=warehouse_id)
        if state is not None:
            query = query.filter(state=state)
        return await query.order_by("-created_at").limit(limit).offset(offset).all()

    @classmethod
    async def count_for_company(
        cls,
        company_id: str,
        *,
        warehouse_id: str | None,
        state: StockTransferState | None,
    ) -> int:
        query = cls.objects.filter(company_id=company_id)
        if warehouse_id is not None:
            query = query.filter(warehouse_id=warehouse_id)
        if state is not None:
            query = query.filter(state=state)
        return await query.count()

    @classmethod
    async def next_name(cls, company_id: str, code: str) -> str:
        """`WH/IN/00001` — счётчик по префиксу внутри компании."""
        prefix = f"{code}/"
        count = await cls.objects.filter(
            company_id=company_id, name__istartswith=prefix
        ).count()
        return f"{prefix}{count + 1:05d}"

    @classmethod
    async def refresh_state(cls, company_id: str, transfer_id: str) -> StockTransferState:
        """Проекция состояния по move. Вызывается только из движка."""
        moves = await StockMove.objects.filter(
            company_id=company_id, transfer_id=transfer_id
        ).all()
        states = {m.state for m in moves}
        if not moves or states == {StockMoveState.CANCEL}:
            projected = StockTransferState.CANCEL
        elif states == {StockMoveState.DONE} or states <= {
            StockMoveState.DONE,
            StockMoveState.CANCEL,
        }:
            projected = StockTransferState.DONE
        elif states == {StockMoveState.DRAFT}:
            projected = StockTransferState.DRAFT
        elif states <= {StockMoveState.CONFIRMED, StockMoveState.WAITING}:
            projected = StockTransferState.CONFIRMED
        elif StockMoveState.ASSIGNED in states and states <= {
            StockMoveState.ASSIGNED,
            StockMoveState.DONE,
            StockMoveState.CANCEL,
        }:
            projected = StockTransferState.ASSIGNED
        else:
            projected = StockTransferState.PARTIALLY_AVAILABLE
        _ = await cls.objects.filter(
            company_id=company_id, transfer_id=transfer_id
        ).update(using=STOCK_DB, state=projected, updated_at=utcnow())
        return projected

    @classmethod
    async def create_backorder_locked(
        cls,
        *,
        company_id: str,
        transfer_id: str,
        residual_move_ids: list[str],
        transfer_id_factory: Callable[[], str],
        move_id_factory: Callable[[], str],
    ) -> Self | None:
        """Backorder по остатку частично исполненных move (`backorder_of_id`).

        Residual move копирует строку спроса с `product_uom_qty = остаток`,
        `state=confirmed`. Вызывается из tx validate по `backorder_policy`.
        """
        if not residual_move_ids:
            return None
        source = await cls.by_id_locked(company_id, transfer_id)
        if source is None:
            raise PlatformNotFoundError(
                "Transfer not found", error_code="transfer_not_found"
            )
        now = utcnow()
        backorder = cls(
            transfer_id=transfer_id_factory(),
            company_id=company_id,
            warehouse_id=source.warehouse_id,
            operation_type_id=source.operation_type_id,
            partner_entity_id=source.partner_entity_id,
            owner_entity_id=source.owner_entity_id,
            name=await cls.next_name(company_id, source.name.split("/")[0]),
            barcode=source.barcode,
            state=StockTransferState.CONFIRMED,
            scheduled_at=source.scheduled_at,
            origin_document_type=source.origin_document_type,
            origin_document_id=source.origin_document_id,
            backorder_of_id=transfer_id,
            created_at=now,
            updated_at=now,
        )
        _ = await cls.objects.create(instance=backorder)
        for move_id in residual_move_ids:
            move = await StockMove.by_id_locked(company_id, move_id)
            if move is None:
                continue
            lines = await StockMoveLine.list_for_move(company_id, move_id)
            done_qty = sum((line.done_quantity for line in lines), _ZERO)
            residual = move.product_uom_qty - done_qty
            if residual <= _ZERO:
                continue
            _ = await StockMove.objects.create(
                instance=StockMove(
                    move_id=move_id_factory(),
                    company_id=company_id,
                    transfer_id=backorder.transfer_id,
                    product_id=move.product_id,
                    product_qty=residual,
                    product_uom_qty=residual,
                    uom_id=move.uom_id,
                    location_id=move.location_id,
                    location_dest_id=move.location_dest_id,
                    state=StockMoveState.CONFIRMED,
                    operation_type_id=move.operation_type_id,
                    origin_document_type=move.origin_document_type,
                    origin_document_id=move.origin_document_id,
                    unit_price=move.unit_price,
                    date=now,
                    created_at=now,
                )
            )
        return backorder


class StockMove(PlatformModel):
    """Движение товара A→B. Таблица ``stock_moves``.

    Единственный механизм изменения количества. `unit_price` — входная цена
    документа (`price_source=document`), вычисленная оценка на move не живёт —
    она в `StockValueLayer`.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_moves"
        indexes: list[Index] = [
            Index(["company_id", "transfer_id"]),
            Index(["company_id", "product_id", "state"]),
            Index(["company_id", "location_id", "state"]),
            Index(["company_id", "location_dest_id", "state"]),
        ]

    move_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    transfer_id: str | None = DbField(default=None, max_length=64)
    product_id: str = DbField(max_length=64)
    product_qty: Decimal = DbField(db_type=QTY_DB)
    product_uom_qty: Decimal = DbField(db_type=QTY_DB)
    uom_id: str = DbField(max_length=64)
    location_id: str = DbField(max_length=64)
    location_dest_id: str = DbField(max_length=64)
    state: StockMoveState = DbField(default=StockMoveState.DRAFT)
    operation_type_id: str | None = DbField(default=None, max_length=64)
    origin_document_type: str | None = DbField(default=None, max_length=64)
    origin_document_id: str | None = DbField(default=None, max_length=64)
    returned_move_id: str | None = DbField(default=None, max_length=64)
    predecessor_move_id: str | None = DbField(default=None, max_length=64)
    unit_price: Decimal | None = DbField(default=None, db_type=MONEY_DB)
    date: datetime = DbField()
    done_at: datetime | None = DbField(default=None)
    created_at: datetime = DbField()

    @classmethod
    async def by_id(cls, company_id: str, move_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, move_id=move_id
        ).get_or_none()

    @classmethod
    async def by_id_locked(cls, company_id: str, move_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, move_id=move_id
        ).for_update().get_or_none()

    @classmethod
    async def list_for_transfer(
        cls, company_id: str, transfer_id: str
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id, transfer_id=transfer_id
        ).order_by("created_at").all()

    # --- Движок: транзакционные шаги (вызываются только из StockMoveEngine) ---

    @classmethod
    async def confirm_locked(cls, *, company_id: str, move_id: str) -> Self:
        """`draft → confirmed` (или `waiting` при незакрытом predecessor)."""
        async with atomic(using=STOCK_DB):
            move = await cls.by_id_locked(company_id, move_id)
            if move is None:
                raise PlatformNotFoundError(
                    "Move not found", error_code="move_not_found"
                )
            if move.state in {StockMoveState.CONFIRMED, StockMoveState.WAITING}:
                return move
            _require(
                move.state == StockMoveState.DRAFT,
                "Move cannot be confirmed from its state",
                error_code="move_state_conflict",
            )
            state = StockMoveState.CONFIRMED
            if move.predecessor_move_id is not None:
                predecessor = await cls.by_id_locked(
                    company_id, move.predecessor_move_id
                )
                if predecessor is not None and predecessor.state != StockMoveState.DONE:
                    state = StockMoveState.WAITING
            _ = await cls.objects.filter(
                company_id=company_id, move_id=move_id
            ).update(using=STOCK_DB, state=state)
            move.state = state
            return move

    @classmethod
    async def assign_locked(
        cls,
        *,
        company_id: str,
        move_id: str,
        dest_location_id: str | None = None,
        line_id_factory: Callable[[], str],
    ) -> Self:
        """Резерв под движение: `StockMoveLine` + `reserved_quantity` на quant.

        `dest_location_id` — решение putaway-рефлекса (применено вне этой tx).
        Источник виртуальный (supplier/…) — полная доступность, state=assigned.
        """
        async with atomic(using=STOCK_DB):
            move = await cls.by_id_locked(company_id, move_id)
            if move is None:
                raise PlatformNotFoundError(
                    "Move not found", error_code="move_not_found"
                )
            _require(
                move.state in _RESERVABLE_STATES,
                "Move cannot be reserved from its state",
                error_code="move_state_conflict",
            )
            if dest_location_id is not None:
                move.location_dest_id = dest_location_id
            src = await StockLocation.by_id(company_id, move.location_id)
            dst = await StockLocation.by_id(company_id, move.location_dest_id)
            if src is None or dst is None:
                raise PlatformNotFoundError(
                    "Move location not found", error_code="location_not_found"
                )
            lines = await StockMoveLine.list_for_move(company_id, move_id)
            reserved = sum((line.quantity for line in lines), _ZERO)
            needed = move.product_uom_qty - reserved
            if needed <= _ZERO:
                await cls._write_state(company_id, move, StockMoveState.ASSIGNED)
                move.state = StockMoveState.ASSIGNED
                return move
            if src.usage != StockLocationUsage.INTERNAL:
                line = StockMoveLine(
                    move_line_id=line_id_factory(),
                    company_id=company_id,
                    move_id=move.move_id,
                    product_id=move.product_id,
                    quantity=needed,
                    location_id=move.location_id,
                    location_dest_id=move.location_dest_id,
                    created_at=utcnow(),
                )
                _ = await StockMoveLine.objects.create(instance=line)
                await cls._write_state(company_id, move, StockMoveState.ASSIGNED)
                move.state = StockMoveState.ASSIGNED
                return move
            location_ids = await StockLocation.list_subtree_ids(
                company_id, move.location_id
            )
            candidates = await StockQuant.fifo_candidates(
                company_id=company_id,
                product_id=move.product_id,
                location_ids=location_ids,
                owner_entity_id=None,
            )
            remaining = needed
            for quant in candidates:
                if remaining <= _ZERO:
                    break
                take = min(quant.available_quantity, remaining)
                line = StockMoveLine(
                    move_line_id=line_id_factory(),
                    company_id=company_id,
                    move_id=move.move_id,
                    product_id=move.product_id,
                    lot_id=quant.lot_id,
                    package_id=quant.package_id,
                    owner_entity_id=quant.owner_entity_id,
                    quantity=take,
                    location_id=quant.location_id,
                    location_dest_id=move.location_dest_id,
                    created_at=utcnow(),
                )
                _ = await StockMoveLine.objects.create(instance=line)
                await StockQuant.reserve(quant.quant_id, take)
                remaining -= take
            state = (
                StockMoveState.ASSIGNED
                if remaining <= _ZERO
                else StockMoveState.PARTIALLY_AVAILABLE
            )
            await cls._write_state(company_id, move, state)
            move.state = state
            return move

    @classmethod
    async def _write_state(
        cls, company_id: str, move: Self, state: StockMoveState
    ) -> None:
        _ = await cls.objects.filter(
            company_id=company_id, move_id=move.move_id
        ).update(
            using=STOCK_DB,
            state=state,
            location_dest_id=move.location_dest_id,
        )

    @classmethod
    async def unreserve_locked(cls, *, company_id: str, move_id: str) -> Self:
        """Снятие резерва: quant.reserved_quantity -= line.quantity, строки удаляются."""
        async with atomic(using=STOCK_DB):
            move = await cls.by_id_locked(company_id, move_id)
            if move is None:
                raise PlatformNotFoundError(
                    "Move not found", error_code="move_not_found"
                )
            _require(
                move.state in _RESERVABLE_STATES,
                "Move cannot be unreserved from its state",
                error_code="move_state_conflict",
            )
            lines = await StockMoveLine.list_for_move(company_id, move_id)
            for line in lines:
                if line.quantity > _ZERO:
                    quant = await StockQuant.by_key_locked(
                        company_id=company_id,
                        product_id=line.product_id,
                        location_id=line.location_id,
                        lot_id=line.lot_id,
                        package_id=line.package_id,
                        owner_entity_id=line.owner_entity_id,
                    )
                    if quant is not None:
                        await StockQuant.unreserve(quant.quant_id, line.quantity)
            _ = await StockMoveLine.objects.filter(
                company_id=company_id, move_id=move_id
            ).delete()
            _ = await cls.objects.filter(
                company_id=company_id, move_id=move_id
            ).update(using=STOCK_DB, state=StockMoveState.CONFIRMED)
            move.state = StockMoveState.CONFIRMED
            return move

    @classmethod
    async def complete_locked(
        cls,
        *,
        company_id: str,
        move_id: str,
        warehouse_id: str | None,
        quant_id_factory: Callable[[], str],
        layer_id_factory: Callable[[], str],
        consumption_id_factory: Callable[[], str],
    ) -> tuple[Self, list["StockValueLayer"], list[Self]]:
        """Фаза done: quant-дельта, слои оценки в той же tx, пробуждение преемников.

        Возвращает `(move, layers, backorder_moves)`: частичное исполнение порождает
        residual-move в backorder-transfer (создаётся вызывающим по policy).
        """
        async with atomic(using=STOCK_DB):
            move = await cls.by_id_locked(company_id, move_id)
            if move is None:
                raise PlatformNotFoundError(
                    "Move not found", error_code="move_not_found"
                )
            if move.state == StockMoveState.DONE:
                existing = await StockValueLayer.objects.filter(
                    company_id=company_id, move_id=move_id
                ).all()
                return move, existing, []
            _require(
                move.state in _RESERVABLE_STATES,
                "Move cannot be completed from its state",
                error_code="move_state_conflict",
            )
            src = await StockLocation.by_id(company_id, move.location_id)
            dst = await StockLocation.by_id(company_id, move.location_dest_id)
            if src is None or dst is None:
                raise PlatformNotFoundError(
                    "Move location not found", error_code="location_not_found"
                )
            product = await StockProduct.by_id(company_id, move.product_id)
            template = (
                await StockProductTemplate.by_id(company_id, product.template_id)
                if product is not None
                else None
            )
            if template is None:
                raise PlatformNotFoundError(
                    "Product template not found", error_code="product_not_found"
                )
            lines = await StockMoveLine.list_for_move(company_id, move_id)
            if not lines:
                line = StockMoveLine(
                    move_line_id=quant_id_factory(),
                    company_id=company_id,
                    move_id=move.move_id,
                    product_id=move.product_id,
                    quantity=move.product_uom_qty,
                    done_quantity=move.product_uom_qty,
                    location_id=move.location_id,
                    location_dest_id=move.location_dest_id,
                    created_at=utcnow(),
                )
                _ = await StockMoveLine.objects.create(instance=line)
                lines = [line]
            done_total = _ZERO
            for line in lines:
                qty = line.done_quantity if line.done_quantity > _ZERO else line.quantity
                if qty <= _ZERO:
                    continue
                if line.done_quantity <= _ZERO:
                    _ = await StockMoveLine.objects.filter(
                        company_id=company_id, move_line_id=line.move_line_id
                    ).update(using=STOCK_DB, done_quantity=qty)
                cls._check_tracking(template.tracking, line.lot_id, qty)
                if src.usage == StockLocationUsage.INTERNAL:
                    src_quant = await StockQuant.get_or_create_locked(
                        company_id=company_id,
                        product_id=move.product_id,
                        location_id=line.location_id,
                        lot_id=line.lot_id,
                        package_id=line.package_id,
                        owner_entity_id=line.owner_entity_id,
                        quant_id=quant_id_factory(),
                    )
                    await StockQuant.apply_quantity(
                        src_quant.quant_id, -qty, -min(qty, line.quantity)
                    )
                if dst.usage == StockLocationUsage.INTERNAL:
                    dst_quant = await StockQuant.get_or_create_locked(
                        company_id=company_id,
                        product_id=move.product_id,
                        location_id=line.location_dest_id,
                        lot_id=line.lot_id,
                        package_id=(
                            line.result_package_id or line.package_id
                        ),
                        owner_entity_id=line.owner_entity_id,
                        quant_id=quant_id_factory(),
                    )
                    await StockQuant.apply_quantity(dst_quant.quant_id, qty, _ZERO)
                done_total += qty
            layers = await StockValueLayer.write_for_done_move(
                company_id=company_id,
                move=move,
                done_qty=done_total,
                template=template,
                src_usage=src.usage,
                dst_usage=dst.usage,
                warehouse_id=warehouse_id,
                layer_id_factory=layer_id_factory,
                consumption_id_factory=consumption_id_factory,
            )
            now = utcnow()
            _ = await cls.objects.filter(
                company_id=company_id, move_id=move_id
            ).update(using=STOCK_DB, state=StockMoveState.DONE, done_at=now)
            move.state = StockMoveState.DONE
            move.done_at = now
            await cls._wake_successors(company_id, move.move_id)
            return move, layers, []

    @classmethod
    def _check_tracking(
        cls, tracking: StockTracking, lot_id: str | None, qty: Decimal
    ) -> None:
        if tracking == StockTracking.NONE and lot_id is not None:
            raise PlatformConflictError(
                "Lot is not allowed for untracked product",
                error_code="lot_not_allowed",
            )
        if tracking == StockTracking.SERIAL and qty not in {_ZERO, Decimal("1")}:
            raise PlatformConflictError(
                "Serial-tracked move requires quantity 0 or 1",
                error_code="serial_quantity_invalid",
            )

    @classmethod
    async def _wake_successors(cls, company_id: str, move_id: str) -> None:
        """`waiting` преемники завершённого движения → `confirmed`."""
        _ = await cls.objects.filter(
            company_id=company_id,
            predecessor_move_id=move_id,
            state=StockMoveState.WAITING,
        ).update(using=STOCK_DB, state=StockMoveState.CONFIRMED)

    @classmethod
    async def cancel_locked(cls, *, company_id: str, move_id: str) -> Self:
        """Отмена: снятие резерва + `cancel`. Из `done` — конфликт."""
        async with atomic(using=STOCK_DB):
            move = await cls.by_id_locked(company_id, move_id)
            if move is None:
                raise PlatformNotFoundError(
                    "Move not found", error_code="move_not_found"
                )
            _require(
                move.state in _REMOVABLE_STATES | _RESERVABLE_STATES,
                "Move cannot be cancelled from its state",
                error_code="move_state_conflict",
            )
            if move.state in _RESERVABLE_STATES:
                lines = await StockMoveLine.list_for_move(company_id, move_id)
                for line in lines:
                    if line.quantity > _ZERO:
                        quant = await StockQuant.by_key_locked(
                            company_id=company_id,
                            product_id=line.product_id,
                            location_id=line.location_id,
                            lot_id=line.lot_id,
                            package_id=line.package_id,
                            owner_entity_id=line.owner_entity_id,
                        )
                        if quant is not None:
                            await StockQuant.unreserve(quant.quant_id, line.quantity)
                _ = await StockMoveLine.objects.filter(
                    company_id=company_id, move_id=move_id
                ).delete()
            _ = await cls.objects.filter(
                company_id=company_id, move_id=move_id
            ).update(using=STOCK_DB, state=StockMoveState.CANCEL)
            move.state = StockMoveState.CANCEL
            return move

    @classmethod
    async def list_last_move_at(
        cls, company_id: str, product_ids: list[str]
    ) -> dict[str, datetime]:
        """`product_id → max(done_at)` для пульса (факт последнего движения)."""
        if not product_ids:
            return {}
        params: list[str] = [company_id, *product_ids]
        placeholders = ", ".join(
            f"${index}" for index in range(2, len(product_ids) + 2)
        )
        rows = await execute_raw(
            "SELECT product_id, MAX(done_at) AS last_done_at FROM stock_moves WHERE company_id = $1 AND state = 'done' AND product_id IN ("
            + placeholders
            + ") GROUP BY product_id",
            params,
            using=STOCK_DB,
        )
        result: dict[str, datetime] = {}
        for row in rows:
            parsed = require_json_object(row, "stock_last_move_at")
            product_id = parsed.get("product_id")
            last_done_at = parsed.get("last_done_at")
            if isinstance(product_id, str) and isinstance(last_done_at, str):
                result[product_id] = datetime.fromisoformat(last_done_at)
            elif isinstance(product_id, str) and isinstance(last_done_at, datetime):
                result[product_id] = last_done_at
        return result


class StockMoveLine(PlatformModel):
    """Строка исполнения движения: lot/package/reserved/done. Таблица ``stock_move_lines``."""

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_move_lines"
        indexes: list[Index] = [
            Index(["company_id", "move_id"]),
            Index(["company_id", "lot_id"]),
        ]

    move_line_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    move_id: str = DbField(max_length=64)
    product_id: str = DbField(max_length=64)
    lot_id: str | None = DbField(default=None, max_length=64)
    package_id: str | None = DbField(default=None, max_length=64)
    result_package_id: str | None = DbField(default=None, max_length=64)
    owner_entity_id: str | None = DbField(default=None, max_length=64)
    quantity: Decimal = DbField(default=_ZERO, db_type=QTY_DB)
    done_quantity: Decimal = DbField(default=_ZERO, db_type=QTY_DB)
    picked: bool = DbField(default=False)
    location_id: str = DbField(max_length=64)
    location_dest_id: str = DbField(max_length=64)
    created_at: datetime = DbField()

    @classmethod
    async def list_for_move(cls, company_id: str, move_id: str) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id, move_id=move_id
        ).order_by("created_at").all()

    @classmethod
    async def list_for_moves(
        cls, company_id: str, move_ids: list[str]
    ) -> list[Self]:
        if not move_ids:
            return []
        return await cls.objects.filter(
            company_id=company_id, move_id__in=move_ids
        ).order_by("created_at").all()

    @classmethod
    async def by_id(cls, company_id: str, move_line_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, move_line_id=move_line_id
        ).get_or_none()

    @classmethod
    async def update_execution(
        cls,
        *,
        company_id: str,
        move_line_id: str,
        done_quantity: Decimal | None,
        picked: bool | None,
        lot_id: str | None,
        location_dest_id: str | None,
    ) -> Self:
        """Скан ТСД: правка исполнения до `done`. Только назначенные строки."""
        async with atomic(using=STOCK_DB):
            line = await cls.objects.filter(
                company_id=company_id, move_line_id=move_line_id
            ).for_update().get_or_none()
            if line is None:
                raise PlatformNotFoundError(
                    "Move line not found", error_code="move_line_not_found"
                )
            move = await StockMove.objects.filter(
                company_id=company_id, move_id=line.move_id
            ).get_or_none()
            if move is None or move.state in {
                StockMoveState.DONE,
                StockMoveState.CANCEL,
            }:
                raise PlatformConflictError(
                    "Move is already closed", error_code="move_closed"
                )
            if done_quantity is not None:
                _require(
                    done_quantity >= _ZERO and done_quantity <= line.quantity,
                    "done_quantity out of reserved range",
                    error_code="done_quantity_invalid",
                )
                line.done_quantity = done_quantity
            if picked is not None:
                line.picked = picked
            if lot_id is not None:
                line.lot_id = lot_id
            if location_dest_id is not None:
                line.location_dest_id = location_dest_id
            _ = await line.save()
            return line


class StockQuant(PlatformModel):
    """Проекция остатка. Таблица ``stock_quants``.

    Ключ: (company_id, product_id, location_id, lot_id, package_id,
    owner_entity_id) — unique NULLS NOT DISTINCT (см. миграцию).
    Писатель — только движок: `reserved_quantity` через assign/unreserve,
    `quantity` через done. `available = quantity - reserved_quantity`.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_quants"
        indexes: list[Index] = [
            Index(["company_id", "product_id", "location_id"]),
            Index(["company_id", "location_id", "in_date"]),
        ]

    quant_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    product_id: str = DbField(max_length=64)
    location_id: str = DbField(max_length=64)
    lot_id: str | None = DbField(default=None, max_length=64)
    package_id: str | None = DbField(default=None, max_length=64)
    owner_entity_id: str | None = DbField(default=None, max_length=64)
    quantity: Decimal = DbField(default=_ZERO, db_type=QTY_DB)
    reserved_quantity: Decimal = DbField(default=_ZERO, db_type=QTY_DB)
    inventory_quantity: Decimal | None = DbField(default=None, db_type=QTY_DB)
    in_date: datetime = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @property
    def available_quantity(self) -> Decimal:
        return self.quantity - self.reserved_quantity

    @classmethod
    async def by_key_locked(
        cls,
        *,
        company_id: str,
        product_id: str,
        location_id: str,
        lot_id: str | None,
        package_id: str | None,
        owner_entity_id: str | None,
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            product_id=product_id,
            location_id=location_id,
            lot_id=lot_id,
            package_id=package_id,
            owner_entity_id=owner_entity_id,
        ).for_update().get_or_none()

    @classmethod
    async def by_key(
        cls,
        *,
        company_id: str,
        product_id: str,
        location_id: str,
        lot_id: str | None,
        package_id: str | None,
        owner_entity_id: str | None,
    ) -> Self | None:
        """Неблокирующий lookup по составному ключу (для чтения после commit)."""
        return await cls.objects.filter(
            company_id=company_id,
            product_id=product_id,
            location_id=location_id,
            lot_id=lot_id,
            package_id=package_id,
            owner_entity_id=owner_entity_id,
        ).get_or_none()

    @classmethod
    async def get_or_create_locked(
        cls,
        *,
        company_id: str,
        product_id: str,
        location_id: str,
        lot_id: str | None,
        package_id: str | None,
        owner_entity_id: str | None,
        quant_id: str,
    ) -> Self:
        """Строка под FOR UPDATE; отсутствующая создаётся нулевой."""
        found = await cls.by_key_locked(
            company_id=company_id,
            product_id=product_id,
            location_id=location_id,
            lot_id=lot_id,
            package_id=package_id,
            owner_entity_id=owner_entity_id,
        )
        if found is not None:
            return found
        now = utcnow()
        quant = cls(
            quant_id=quant_id,
            company_id=company_id,
            product_id=product_id,
            location_id=location_id,
            lot_id=lot_id,
            package_id=package_id,
            owner_entity_id=owner_entity_id,
            quantity=_ZERO,
            reserved_quantity=_ZERO,
            in_date=now,
            created_at=now,
            updated_at=now,
        )
        try:
            return await cls.objects.create(instance=quant)
        except UniqueViolationError:
            raced = await cls.by_key_locked(
                company_id=company_id,
                product_id=product_id,
                location_id=location_id,
                lot_id=lot_id,
                package_id=package_id,
                owner_entity_id=owner_entity_id,
            )
            if raced is None:
                raise
            return raced

    @classmethod
    async def reserve(cls, quant_id: str, quantity: Decimal) -> None:
        _ = await cls.objects.filter(quant_id=quant_id).update(
            using=STOCK_DB,
            reserved_quantity=F("reserved_quantity") + quantity,
            updated_at=utcnow(),
        )

    @classmethod
    async def unreserve(cls, quant_id: str, quantity: Decimal) -> None:
        _ = await cls.objects.filter(quant_id=quant_id).update(
            using=STOCK_DB,
            reserved_quantity=F("reserved_quantity") - quantity,
            updated_at=utcnow(),
        )

    @classmethod
    async def apply_quantity(
        cls, quant_id: str, delta_quantity: Decimal, delta_reserved: Decimal
    ) -> None:
        """Фаза done: quantity += delta, reserved -= освобождаемое. Только движок."""
        _ = await cls.objects.filter(quant_id=quant_id).update(
            using=STOCK_DB,
            quantity=F("quantity") + delta_quantity,
            reserved_quantity=F("reserved_quantity") + delta_reserved,
            updated_at=utcnow(),
        )

    @classmethod
    async def fifo_candidates(
        cls,
        *,
        company_id: str,
        product_id: str,
        location_ids: list[str],
        owner_entity_id: str | None,
    ) -> list[Self]:
        """Доступные quant'ы в порядке removal `fifo` (in_date, quant_id)."""
        if not location_ids:
            return []
        query = cls.objects.filter(
            company_id=company_id,
            product_id=product_id,
            location_id__in=location_ids,
        )
        if owner_entity_id is None:
            query = query.filter(owner_entity_id=None)
        else:
            query = query.filter(owner_entity_id=owner_entity_id)
        rows = await query.order_by("in_date", "quant_id").for_update().all()
        return [row for row in rows if row.available_quantity > _ZERO]

    @classmethod
    async def list_for_company(
        cls,
        company_id: str,
        *,
        location_id: str | None,
        product_id: str | None,
        limit: int,
        offset: int,
    ) -> list[Self]:
        query = cls.objects.filter(company_id=company_id)
        if location_id is not None:
            query = query.filter(location_id=location_id)
        if product_id is not None:
            query = query.filter(product_id=product_id)
        return await query.order_by("product_id", "location_id").limit(limit).offset(
            offset
        ).all()

    @classmethod
    async def count_for_company(
        cls, company_id: str, *, location_id: str | None, product_id: str | None
    ) -> int:
        query = cls.objects.filter(company_id=company_id)
        if location_id is not None:
            query = query.filter(location_id=location_id)
        if product_id is not None:
            query = query.filter(product_id=product_id)
        return await query.count()

    @classmethod
    async def list_for_warehouse(
        cls, company_id: str, location_ids: list[str]
    ) -> list[Self]:
        if not location_ids:
            return []
        return await cls.objects.filter(
            company_id=company_id, location_id__in=location_ids
        ).all()

    @classmethod
    async def set_inventory_quantity(
        cls, quant_id: str, inventory_quantity: Decimal | None
    ) -> None:
        _ = await cls.objects.filter(quant_id=quant_id).update(
            using=STOCK_DB,
            inventory_quantity=inventory_quantity,
            updated_at=utcnow(),
        )


class StockPutawayRule(PlatformModel):
    """Правило putaway. Таблица ``stock_putaway_rules``."""

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_putaway_rules"
        indexes: list[Index] = [
            Index(["company_id", "warehouse_id", "location_in_id", "sequence"])
        ]

    rule_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str = DbField(max_length=64)
    product_id: str | None = DbField(default=None, max_length=64)
    category: str | None = DbField(default=None, max_length=128)
    location_in_id: str = DbField(max_length=64)
    location_out_id: str = DbField(max_length=64)
    sequence: int = DbField(default=0)

    @classmethod
    async def candidates_for(
        cls,
        *,
        company_id: str,
        warehouse_id: str,
        product_id: str,
        category: str,
        location_ids: list[str],
    ) -> list[Self]:
        """Правила, чьи location_in покрывают направление; самые специфичные первыми."""
        rows = await cls.objects.filter(
            company_id=company_id,
            warehouse_id=warehouse_id,
            location_in_id__in=location_ids,
        ).order_by("sequence").all()
        matched = [
            r
            for r in rows
            if (r.product_id is None or r.product_id == product_id)
            and (r.category is None or r.category == category)
        ]
        matched.sort(
            key=lambda r: (
                r.sequence,
                -(r.product_id is not None) - (r.category is not None),
            )
        )
        return matched


class StockDecision(PlatformModel):
    """Запись рефлекса: запрос/ответ точки принятия решения. Таблица ``stock_decisions``."""

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_decisions"
        indexes: list[Index] = [
            Index(["company_id", "transfer_id"]),
            Index(["company_id", "move_id"]),
        ]

    decision_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str = DbField(max_length=64)
    operation_type_id: str = DbField(max_length=64)
    reflex_point: ReflexPoint = DbField()
    move_id: str | None = DbField(default=None, max_length=64)
    transfer_id: str | None = DbField(default=None, max_length=64)
    mode: ReflexMode = DbField()
    flow_id: str | None = DbField(default=None, max_length=64)
    candidate_location_ids: list[str] = DbField(db_type="JSONB", default_factory=list)
    chosen_location_id: str | None = DbField(default=None, max_length=64)
    status: StockDecisionStatus = DbField(default=StockDecisionStatus.SUGGESTED)
    created_at: datetime = DbField()
    applied_at: datetime | None = DbField(default=None)

    @classmethod
    async def by_id(cls, company_id: str, decision_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, decision_id=decision_id
        ).get_or_none()

    @classmethod
    async def latest_for_transfer(
        cls, company_id: str, transfer_id: str
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, transfer_id=transfer_id
        ).order_by("-created_at").first()

    @classmethod
    async def mark_applied(cls, decision_id: str, chosen_location_id: str) -> None:
        _ = await cls.objects.filter(decision_id=decision_id).update(
            using=STOCK_DB,
            status=StockDecisionStatus.APPLIED,
            chosen_location_id=chosen_location_id,
            applied_at=utcnow(),
        )


class StockBarcodeIndex(PlatformModel):
    """Штрихкод → сущность. Таблица ``stock_barcodes``.

    `(company_id, barcode)` unique — единая атомарная точка уникальности
    «один код — один носитель» (product/location/package/lot/transfer).
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_barcodes"
        indexes: list[Index] = [
            Index(["company_id", "barcode"], unique=True),
            Index(["company_id", "entity_type", "entity_id"]),
        ]

    barcode_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    barcode: str = DbField(max_length=128)
    entity_type: StockBarcodeEntityType = DbField()
    entity_id: str = DbField(max_length=64)
    created_at: datetime = DbField()

    @classmethod
    async def resolve(
        cls, company_id: str, barcode: str
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, barcode=barcode
        ).get_or_none()

    @classmethod
    async def release_entity(cls, company_id: str, entity_id: str) -> None:
        _ = await cls.objects.filter(
            company_id=company_id, entity_id=entity_id
        ).delete()


class StockLedgerCounter(PlatformModel):
    """Nogap-счётчик `entry_no` журнала оценки. Таблица ``stock_ledger_counters``.

    `next_entry_no` инкрементируется под `SELECT FOR UPDATE` в транзакции
    записи слоя — rollback не оставляет пропусков (в отличие от PG sequence).
    Сериализация записи на компанию приемлема: слои пишутся в tx `done`.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_ledger_counters"

    company_id: str = DbField(db_pk=True, max_length=100)
    next_entry_no: int = DbField(default=1)

    @classmethod
    async def allocate(cls, company_id: str, count: int) -> int:
        """Первый `entry_no` блока из `count` номеров. Вызывать внутри atomic."""
        if count < 1:
            raise ValueError("count must be >= 1")
        row = await cls.objects.filter(company_id=company_id).for_update().get_or_none()
        if row is None:
            try:
                row = await cls.objects.create(
                    instance=cls(company_id=company_id, next_entry_no=1)
                )
            except UniqueViolationError:
                row = await cls.objects.filter(
                    company_id=company_id
                ).for_update().get_or_none()
                if row is None:
                    raise
        first = row.next_entry_no
        _ = await cls.objects.filter(company_id=company_id).update(
            using=STOCK_DB, next_entry_no=first + count
        )
        return first


class StockValueLayer(PlatformModel):
    """Append-only журнал стоимости. Таблица ``stock_value_layers``.

    Одна запись = одна хозоперация: signed `quantity`/`value`, `unit_cost`,
    `remaining_*` для FIFO-потребления, running balance `qty_after`/`value_after`
    (scope company+product) для аудита. Нет update/delete — коррекции и сторно
    пишутся новыми слоями (`origin_layer_id`).
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_value_layers"
        indexes: list[Index] = [
            Index(["company_id", "entry_no"], unique=True),
            Index(["company_id", "product_id", "entry_no"]),
            Index(
                ["company_id", "product_id", "entry_no"],
                name="stock_value_layers_fifo_scan_idx",
                where="remaining_quantity > 0",
            ),
            Index(["company_id", "move_id"]),
            Index(["company_id", "transfer_id"]),
            Index(["company_id", "warehouse_id"]),
        ]

    layer_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    entry_no: int = DbField()
    move_id: str | None = DbField(default=None, max_length=64)
    transfer_id: str | None = DbField(default=None, max_length=64)
    product_id: str = DbField(max_length=64)
    lot_id: str | None = DbField(default=None, max_length=64)
    warehouse_id: str | None = DbField(default=None, max_length=64)
    location_id: str | None = DbField(default=None, max_length=64)
    location_dest_id: str | None = DbField(default=None, max_length=64)
    entry_kind: ValueEntryKind = DbField()
    quantity: Decimal = DbField(db_type=QTY_DB)
    unit_cost: Decimal = DbField(db_type=MONEY_DB)
    value: Decimal = DbField(db_type=MONEY_DB)
    remaining_quantity: Decimal = DbField(default=_ZERO, db_type=QTY_DB)
    remaining_value: Decimal = DbField(default=_ZERO, db_type=MONEY_DB)
    qty_after: Decimal = DbField(db_type=QTY_DB)
    value_after: Decimal = DbField(db_type=MONEY_DB)
    price_source: ValuationPriceSource = DbField()
    valuation_method: ValuationMethod = DbField()
    origin_layer_id: str | None = DbField(default=None, max_length=64)
    origin_document_type: str | None = DbField(default=None, max_length=64)
    origin_document_id: str | None = DbField(default=None, max_length=64)
    description: str = DbField(default="", max_length=512)
    created_at: datetime = DbField()

    @classmethod
    async def list_for_product(
        cls, company_id: str, product_id: str, *, limit: int, offset: int
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id, product_id=product_id
        ).order_by("entry_no").limit(limit).offset(offset).all()

    @classmethod
    async def list_for_company(
        cls,
        company_id: str,
        *,
        product_id: str | None,
        warehouse_id: str | None,
        limit: int,
        offset: int,
    ) -> list[Self]:
        query = cls.objects.filter(company_id=company_id)
        if product_id is not None:
            query = query.filter(product_id=product_id)
        if warehouse_id is not None:
            query = query.filter(warehouse_id=warehouse_id)
        return await query.order_by("entry_no").limit(limit).offset(offset).all()

    @classmethod
    async def count_for_company(
        cls, company_id: str, *, product_id: str | None, warehouse_id: str | None
    ) -> int:
        query = cls.objects.filter(company_id=company_id)
        if product_id is not None:
            query = query.filter(product_id=product_id)
        if warehouse_id is not None:
            query = query.filter(warehouse_id=warehouse_id)
        return await query.count()

    @classmethod
    async def last_for_product(
        cls, company_id: str, product_id: str
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, product_id=product_id
        ).order_by("-entry_no").first()

    @classmethod
    async def fifo_remaining(
        cls, company_id: str, product_id: str
    ) -> list[Self]:
        """Открытые входящие слои в порядке потребления (entry_no)."""
        return await cls.objects.filter(
            company_id=company_id,
            product_id=product_id,
            remaining_quantity__gt=_ZERO,
        ).order_by("entry_no").for_update().all()

    @classmethod
    async def write_layer(cls, layer: Self) -> Self:
        return await cls.objects.create(instance=layer)

    # --- Запись журнала: только done-фаза движка и revalue/correction ---

    @classmethod
    async def _origin_unit_cost(
        cls, company_id: str, origin_move_id: str
    ) -> Decimal | None:
        """Средняя себестоимость исходного move (для return-слоёв)."""
        rows = await cls.objects.filter(
            company_id=company_id, move_id=origin_move_id
        ).all()
        total_qty = sum((r.quantity for r in rows), _ZERO)
        total_value = sum((r.value for r in rows), _ZERO)
        if total_qty == _ZERO:
            return None
        return abs(total_value / total_qty)

    @classmethod
    async def write_for_done_move(
        cls,
        *,
        company_id: str,
        move: StockMove,
        done_qty: Decimal,
        template: StockProductTemplate,
        src_usage: StockLocationUsage,
        dst_usage: StockLocationUsage,
        warehouse_id: str | None,
        layer_id_factory: Callable[[], str],
        consumption_id_factory: Callable[[], str],
    ) -> list[Self]:
        """Слои оценки для завершённого движения — внутри tx `done`.

        `unvalued` и virtual→virtual не пишут. Остальное — по матрице
        `classify_entry`: incoming по `unit_price` документа/карточке, outgoing
        по методу шаблона (fifo consume + consumption-развязка), internal→internal
        парой слоёв по текущей себестоимости.
        """
        from apps.stock.models.valuation import (
            classify_entry,
            fifo_allocate,
            fifo_cost_of,
            inbound_unit_cost,
            quantize,
        )

        method = template.valuation_method
        if method == ValuationMethod.UNVALUED or done_qty <= _ZERO:
            return []
        is_return = move.returned_move_id is not None
        kinds = classify_entry(src_usage, dst_usage, is_return=is_return)
        if not kinds:
            return []
        last = await cls.last_for_product(company_id, move.product_id)
        qty_balance = last.qty_after if last is not None else _ZERO
        value_balance = last.value_after if last is not None else _ZERO

        inbound_cost: Decimal | None = None
        inbound_source = ValuationPriceSource.STANDARD
        origin_cost: Decimal | None = None
        if is_return and move.returned_move_id is not None:
            origin = await cls._origin_unit_cost(company_id, move.returned_move_id)
            if origin is not None:
                origin_cost = origin
                inbound_cost = origin
                inbound_source = ValuationPriceSource.DOCUMENT
        if inbound_cost is None:
            inbound_cost, inbound_source = inbound_unit_cost(
                move.unit_price, method, template.standard_price
            )

        avg_cost = (
            quantize(value_balance / qty_balance)
            if qty_balance > _ZERO
            else template.standard_price
        )

        # FIFO-потребление — только когда запись уменьшает остаток
        # (OUTBOUND/INVENTORY_LOSS/INTERNAL_OUT); приходные виды слоёв не едят.
        has_outgoing = any(
            kind
            in {
                ValueEntryKind.OUTBOUND,
                ValueEntryKind.INVENTORY_LOSS,
                ValueEntryKind.INTERNAL_OUT,
            }
            for kind in kinds
        )
        fifo_plan: list[tuple[StockValueLayer, Decimal]] = []
        fifo_value = _ZERO
        fifo_unit = _ZERO
        if method == ValuationMethod.FIFO and has_outgoing:
            remaining_layers = await cls.fifo_remaining(company_id, move.product_id)
            fifo_plan = fifo_allocate(
                remaining_layers,
                done_qty,
                remaining_of=lambda layer: layer.remaining_quantity,
            )
            fifo_value, fifo_unit = fifo_cost_of(
                remaining_layers,
                done_qty,
                remaining_of=lambda layer: layer.remaining_quantity,
                cost_of=lambda layer: layer.unit_cost,
            )

        def outbound_pair() -> tuple[Decimal, Decimal, ValuationPriceSource]:
            # Исходящий возврат ценится по себестоимости исходного move.
            if origin_cost is not None:
                return (
                    quantize(origin_cost * done_qty),
                    origin_cost,
                    ValuationPriceSource.DOCUMENT,
                )
            if method == ValuationMethod.FIFO:
                return fifo_value, fifo_unit, ValuationPriceSource.DOCUMENT
            if method == ValuationMethod.AVERAGE:
                return (
                    quantize(avg_cost * done_qty),
                    avg_cost,
                    ValuationPriceSource.AVERAGE,
                )
            cost = template.standard_price
            return quantize(cost * done_qty), cost, ValuationPriceSource.STANDARD

        entry_no = await StockLedgerCounter.allocate(company_id, len(kinds))
        now = utcnow()
        written: list[Self] = []
        for index, kind in enumerate(kinds):
            if kind in {
                ValueEntryKind.INBOUND,
                ValueEntryKind.RETURN,
                ValueEntryKind.INVENTORY_GAIN,
            }:
                quantity = done_qty
                unit_cost = inbound_cost
                value = quantize(unit_cost * quantity)
                source = inbound_source
                remaining_qty = quantity
                remaining_val = value
            elif kind in {
                ValueEntryKind.OUTBOUND,
                ValueEntryKind.INVENTORY_LOSS,
                ValueEntryKind.INTERNAL_OUT,
            }:
                quantity = -done_qty
                if kind == ValueEntryKind.INTERNAL_OUT:
                    value, unit_cost, source = outbound_pair()
                    value = -value
                else:
                    value, unit_cost, source = outbound_pair()
                    value = -value
                remaining_qty = _ZERO
                remaining_val = _ZERO
            elif kind == ValueEntryKind.INTERNAL_IN:
                quantity = done_qty
                out_value, out_unit, _ = outbound_pair()
                unit_cost = out_unit
                value = out_value
                source = ValuationPriceSource.AVERAGE
                remaining_qty = quantity
                remaining_val = value
            else:
                raise ValueError(f"Unexpected entry kind in done: {kind}")
            qty_balance += quantity
            value_balance += value
            layer = cls(
                layer_id=layer_id_factory(),
                company_id=company_id,
                entry_no=entry_no + index,
                move_id=move.move_id,
                transfer_id=move.transfer_id,
                product_id=move.product_id,
                warehouse_id=warehouse_id,
                location_id=move.location_id,
                location_dest_id=move.location_dest_id,
                entry_kind=kind,
                quantity=quantity,
                unit_cost=unit_cost,
                value=value,
                remaining_quantity=remaining_qty,
                remaining_value=remaining_val,
                qty_after=qty_balance,
                value_after=value_balance,
                price_source=source,
                valuation_method=method,
                origin_document_type=move.origin_document_type,
                origin_document_id=move.origin_document_id,
                created_at=now,
            )
            _ = await cls.objects.create(instance=layer)
            written.append(layer)
        if method == ValuationMethod.FIFO and fifo_plan:
            out_layer = next(
                (layer for layer in written if layer.quantity < _ZERO), None
            )
            for in_layer, take in fifo_plan:
                consumed_value = quantize(in_layer.unit_cost * take)
                _ = await cls.objects.filter(
                    layer_id=in_layer.layer_id
                ).update(
                    using=STOCK_DB,
                    remaining_quantity=in_layer.remaining_quantity - take,
                    remaining_value=in_layer.remaining_value - consumed_value,
                )
                if out_layer is not None:
                    _ = await StockValueLayerConsumption.objects.create(
                        instance=StockValueLayerConsumption(
                            consumption_id=consumption_id_factory(),
                            company_id=company_id,
                            out_layer_id=out_layer.layer_id,
                            in_layer_id=in_layer.layer_id,
                            quantity=take,
                            value=consumed_value,
                            created_at=now,
                        )
                    )
        return written

    @classmethod
    async def write_adjustment(
        cls,
        *,
        company_id: str,
        product_id: str,
        entry_kind: ValueEntryKind,
        value_delta: Decimal,
        quantity_delta: Decimal,
        description: str,
        origin_layer_id: str | None,
        layer_id_factory: Callable[[], str],
    ) -> Self:
        """Корректирующий слой (`revaluation`/`correction`): append-only.

        `quantity_delta` обычно 0 — коррекция меняет стоимость, не количество.
        """
        if entry_kind not in {
            ValueEntryKind.REVALUATION,
            ValueEntryKind.CORRECTION,
        }:
            raise ValueError(f"Adjustment kind must be revaluation|correction, got {entry_kind}")
        async with atomic(using=STOCK_DB):
            product = await StockProduct.by_id(company_id, product_id)
            if product is None:
                raise PlatformNotFoundError(
                    "Product not found", error_code="product_not_found"
                )
            template = await StockProductTemplate.by_id(company_id, product.template_id)
            if template is None:
                raise PlatformNotFoundError(
                    "Product template not found", error_code="product_not_found"
                )
            entry_no = await StockLedgerCounter.allocate(company_id, 1)
            last = await cls.last_for_product(company_id, product_id)
            qty_balance = (last.qty_after if last is not None else _ZERO) + quantity_delta
            value_balance = (last.value_after if last is not None else _ZERO) + value_delta
            layer = cls(
                layer_id=layer_id_factory(),
                company_id=company_id,
                entry_no=entry_no,
                product_id=product_id,
                location_id=None,
                location_dest_id=None,
                entry_kind=entry_kind,
                quantity=quantity_delta,
                unit_cost=_ZERO,
                value=value_delta,
                remaining_quantity=_ZERO,
                remaining_value=_ZERO,
                qty_after=qty_balance,
                value_after=value_balance,
                price_source=ValuationPriceSource.MANUAL,
                valuation_method=template.valuation_method,
                origin_layer_id=origin_layer_id,
                description=description,
                created_at=utcnow(),
            )
            return await cls.objects.create(instance=layer)


class StockValueLayerConsumption(PlatformModel):
    """Развязка FIFO-потребления: какой in-layer закрыл out-layer.

    Таблица ``stock_value_layer_consumptions``.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_value_layer_consumptions"
        indexes: list[Index] = [
            Index(["company_id", "out_layer_id"]),
            Index(["company_id", "in_layer_id"]),
        ]

    consumption_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    out_layer_id: str = DbField(max_length=64)
    in_layer_id: str = DbField(max_length=64)
    quantity: Decimal = DbField(db_type=QTY_DB)
    value: Decimal = DbField(db_type=MONEY_DB)
    created_at: datetime = DbField()

    @classmethod
    async def write(cls, consumption: Self) -> Self:
        return await cls.objects.create(instance=consumption)

    @classmethod
    async def list_for_out_layer(
        cls, company_id: str, out_layer_id: str
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id, out_layer_id=out_layer_id
        ).all()
