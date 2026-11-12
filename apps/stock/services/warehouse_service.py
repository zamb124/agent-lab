"""Агрегат «склад»: карточки площадок, типы операций, накладные.

Сервис отвечает за склад как объект учёта: создание площадки вместе
со стартовым деревом локаций и типами операций (пресеты топологии),
настройка политик вида накладной и чтение документов-накладных.
Справочники товара — ``CatalogService``, дерево локаций и тара —
``TopologyService``, правила поведения — ``RuleService``.
"""

from __future__ import annotations

from typing import Literal

from oxyde.exceptions import UniqueViolationError

from apps.stock.models import (
    BackorderPolicy,
    ReflexMode,
    ReservationPolicy,
    StockLayoutPreset,
    StockLocation,
    StockLocationUsage,
    StockMove,
    StockMoveLine,
    StockMoveState,
    StockOperationCode,
    StockOperationType,
    StockPartnerRole,
    StockRemovalStrategy,
    StockTransfer,
    StockTransferState,
    StockWarehouse,
)
from apps.stock.models.scan import ScanFlow
from apps.stock.services.ids import new_id
from apps.stock.services.stock_access_service import StockAccessService
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.pagination import CursorPage, OffsetPage
from core.utils.time import utcnow


def _conflict(message: str, error_code: str) -> PlatformConflictError:
    return PlatformConflictError(message, error_code=error_code)


# Топология пресетов склада: (имя зоны, usage, дети) — чистое описание
# каркаса бизнес-зон, разворачиваемое `create_warehouse` за один вызов.
_TopologySpec = tuple[str, StockLocationUsage, tuple["_TopologySpec", ...]]

_PRESET_TOPOLOGY: dict[StockLayoutPreset, tuple[_TopologySpec, ...]] = {
    # Микросклад/минимум: одна общая ячейка запаса.
    StockLayoutPreset.SIMPLE: (
        ("Stock", StockLocationUsage.BIN, ()),
    ),
    # Даркстор/стандартный: приёмка → запас отбора → упаковка → отгрузка.
    StockLayoutPreset.STANDARD: (
        ("Receiving", StockLocationUsage.BIN, ()),
        (
            "Stock",
            StockLocationUsage.VIEW,
            (("Pick", StockLocationUsage.BIN, ()),),
        ),
        ("Packing", StockLocationUsage.BIN, ()),
        ("Shipping", StockLocationUsage.BIN, ()),
    ),
    # РЦ: полный цикл с QC, bulk-хранением, forward-отбором,
    # стейджингом («чистый пол») и карантином.
    StockLayoutPreset.DISTRIBUTION_CENTER: (
        ("Receiving Dock", StockLocationUsage.BIN, ()),
        ("Quality Control", StockLocationUsage.BIN, ()),
        (
            "Storage",
            StockLocationUsage.VIEW,
            (
                ("Bulk", StockLocationUsage.BIN, ()),
                ("Forward Pick", StockLocationUsage.BIN, ()),
            ),
        ),
        ("Clean Floor", StockLocationUsage.BIN, ()),
        ("Packing", StockLocationUsage.BIN, ()),
        ("Shipping Dock", StockLocationUsage.BIN, ()),
        ("Quarantine", StockLocationUsage.BIN, ()),
    ),
}

# Какая ячейка пресета — «основной запас» склада (дефолт источника/
# приёмника типовых операций и точка отсчёта остатка).
_PRESET_STOCK_ZONE: dict[StockLayoutPreset, str] = {
    StockLayoutPreset.SIMPLE: "Stock",
    StockLayoutPreset.STANDARD: "Pick",
    StockLayoutPreset.DISTRIBUTION_CENTER: "Forward Pick",
}


def _flatten_topology(
    spec: _TopologySpec, parent_name: str | None = None
) -> list[tuple[str, StockLocationUsage, str | None]]:
    """Развернуть дерево пресета в плоский список (имя, usage, родитель)."""
    name, usage, children = spec
    rows = [(name, usage, parent_name)]
    for child in children:
        rows.extend(_flatten_topology(child, name))
    return rows


def _not_found(message: str, error_code: str) -> PlatformNotFoundError:
    return PlatformNotFoundError(message, error_code=error_code)


class WarehouseService:
    """Сценарии агрегата «склад»: площадки, типы операций, накладные.

    ``create_warehouse`` разворачивает готовую к работе площадку —
    дерево локаций по пресету и три типа операций; остальные методы —
    правка карточки склада, настройка политик вида накладной и чтение
    документов (накладная + её движения и строки исполнения).
    """

    def __init__(self, access: StockAccessService) -> None:
        self._access: StockAccessService = access

    # --- Warehouses ---

    async def create_warehouse(
        self,
        *,
        company_id: str,
        code: str,
        name: str,
        owner_user_id: str,
        layout_preset: StockLayoutPreset,
        removal_strategy: StockRemovalStrategy,
    ) -> StockWarehouse:
        """Открыть новый склад — одна команда разворачивает топологию.

        Создаются (созданный склад сразу готов принимать и отгружать):

        * ``stock_warehouses`` — карточка склада;
        * дерево локаций по ``layout_preset``: ``simple`` — корень
          ``view`` + ячейка «Stock» (микросклад/даркстор: один общий
          запас); ``standard`` — + дебаркадер приёмки, зона упаковки и
          отгрузки; ``distribution_center`` — РЦ: дебаркадер, QC,
          bulk-хранение, forward-отбор, «чистый пол» (staging), упаковка,
          отгрузочные ворота, карантин. Точную вилку рядов/ярусов
          администратор достраивает под конкретное здание — пресет даёт
          рабочий каркас бизнес-зон;
        * три типа операций по умолчанию: ``Receipts``
          (partner:vendor → основной запас), ``Delivery Orders``
          (запас → partner:customer), ``Internal Transfers``
          (запас → запас) — именно они определяют границу оценки:
          приход и отгрузка создают записи в журнале стоимости,
          внутренние перемещения — нет;
        * authz-дефолты склада для ``owner_user_id``.

        ``code`` уникален на компанию → ``warehouse_code_conflict``.
        Требует инициализированной компании (виртуальные локации
        partner vendor/customer уже существуют) — иначе
        ``company_not_initialized``.

        ``removal_strategy`` — обязательная бизнес-политика склада:
        цепочка «товар → тип хранения → склад» всегда кончается здесь;
        незаданная стратегия — ошибка конфигурации, а не дефолт.
        """
        preset = layout_preset
        now = utcnow()
        warehouse_id = new_id("whs")
        view = await StockLocation.create_with_parent_path(
            company_id=company_id,
            warehouse_id=warehouse_id,
            parent=None,
            name=f"{name} (view)",
            usage=StockLocationUsage.VIEW,
        )
        created: dict[str, StockLocation] = {}
        for spec in _PRESET_TOPOLOGY[preset]:
            for path_name, usage, parent_name in _flatten_topology(spec):
                parent = view if parent_name is None else created[parent_name]
                loc = await StockLocation.create_with_parent_path(
                    company_id=company_id,
                    warehouse_id=warehouse_id,
                    parent=parent,
                    name=path_name,
                    usage=usage,
                )
                created[path_name] = loc
        stock = created[_PRESET_STOCK_ZONE[preset]]
        try:
            warehouse = await StockWarehouse.create(StockWarehouse(
                    warehouse_id=warehouse_id,
                    company_id=company_id,
                    code=code,
                    name=name,
                    view_location_id=view.location_id,
                    stock_location_id=stock.location_id,
                    removal_strategy=removal_strategy,
                    created_at=now,
                )
            )
        except UniqueViolationError as exc:
            raise _conflict("Warehouse code already exists", "warehouse_code_conflict") from exc
        supplier = await StockLocation.virtual_by_usage(
            company_id, StockLocationUsage.PARTNER, StockPartnerRole.VENDOR
        )
        customer = await StockLocation.virtual_by_usage(
            company_id, StockLocationUsage.PARTNER, StockPartnerRole.CUSTOMER
        )
        if supplier is None or customer is None:
            raise _conflict(
                "Virtual locations missing; run stock/company/init first",
                "company_not_initialized",
            )
        # Приёмка ставит товар на входную зону пресета (дебаркадер),
        # отгрузка отбирает из основного запаса; межзональную логистику
        # дают маршруты (StockRoute) — см. раздел сценариев в stock.mdc.
        receipt_zone = (
            created["Receiving"]
            if preset == StockLayoutPreset.STANDARD
            else created.get("Receiving Dock", stock)
        )
        for op_code, op_name, src, dst in (
            (StockOperationCode.INCOMING, "Receipts", supplier.location_id, receipt_zone.location_id),
            (StockOperationCode.OUTGOING, "Delivery Orders", stock.location_id, customer.location_id),
            (StockOperationCode.INTERNAL, "Internal Transfers", stock.location_id, stock.location_id),
        ):
            _ = await StockOperationType.create(StockOperationType(
                    operation_type_id=new_id("opt"),
                    company_id=company_id,
                    warehouse_id=warehouse_id,
                    code=op_code,
                    name=f"{code} {op_name}",
                    default_source_location_id=src,
                    default_dest_location_id=dst,
                    reservation_policy=ReservationPolicy.AT_CONFIRM,
                    backorder_policy=BackorderPolicy.ALWAYS,
                    putaway_mode=ReflexMode.RULE,
                    created_at=now,
                    updated_at=now,
                )
            )
        await self._access.ensure_warehouse_defaults(
            warehouse_id=warehouse_id,
            company_id=company_id,
            owner_user_id=owner_user_id,
        )
        return warehouse

    async def update_warehouse(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        name: str | None,
        code: str | None,
    ) -> StockWarehouse:
        warehouse = await StockWarehouse.by_id(company_id, warehouse_id)
        if warehouse is None:
            raise _not_found("Warehouse not found", "warehouse_not_found")
        warehouse.name = name if name is not None else warehouse.name
        warehouse.code = code if code is not None else warehouse.code
        try:
            _ = await warehouse.save()
        except UniqueViolationError as exc:
            raise _conflict("Warehouse code already exists", "warehouse_code_conflict") from exc
        return warehouse

    async def list_warehouses(
        self, *, company_id: str, limit: int, offset: int
    ) -> OffsetPage[StockWarehouse]:
        rows = await StockWarehouse.list_by_code_asc(
            company_id, limit=limit, offset=offset
        )
        total = await StockWarehouse.count_for_company(company_id)
        return OffsetPage(items=rows, total=total, limit=limit, offset=offset)

    async def get_warehouse(
        self, *, company_id: str, warehouse_id: str
    ) -> StockWarehouse:
        warehouse = await StockWarehouse.by_id(company_id, warehouse_id)
        if warehouse is None:
            raise _not_found("Warehouse not found", "warehouse_not_found")
        return warehouse

    # --- Operation types ---

    async def list_operation_types(
        self, *, company_id: str, warehouse_id: str
    ) -> list[StockOperationType]:
        return await StockOperationType.list_for_warehouse_by_code_asc(company_id, warehouse_id)

    async def update_operation_type(
        self,
        *,
        company_id: str,
        operation_type_id: str,
        name: str | None,
        reservation_policy: ReservationPolicy | None,
        backorder_policy: BackorderPolicy | None,
        putaway_mode: ReflexMode | None,
        putaway_flow_id: str | None,
        auto_validate: bool | None,
        scan_flow: ScanFlow | Literal["default"] | None,
    ) -> StockOperationType:
        """Настроить политику вида накладной.

        * ``reservation_policy`` — когда резервировать: ``manual``
          (явной командой) или ``at_confirm`` (при подтверждении
          накладной);
        * ``backorder_policy`` — при нехватке: ``always`` (отгрузить
          сколько есть, остаток — доказкой), ``never`` (ошибка,
          накладная целиком или никак), ``ask`` (спросить у оператора);
        * ``putaway_mode`` — как выбирать ячейку приёмки: ``rule``
          (по правилам размещения) или ``inline`` (flow платформы
          решает — тогда обязателен ``putaway_flow_id``, иначе
          ``putaway_flow_missing``);
        * ``auto_validate`` — проводить накладную автоматически после
          резервирования (быстрый режим даркстора).
        """
        op = await StockOperationType.by_id(company_id, operation_type_id)
        if op is None:
            raise _not_found("Operation type not found", "operation_type_not_found")
        op.name = name if name is not None else op.name
        op.reservation_policy = (
            reservation_policy if reservation_policy is not None else op.reservation_policy
        )
        op.backorder_policy = (
            backorder_policy if backorder_policy is not None else op.backorder_policy
        )
        op.putaway_mode = putaway_mode if putaway_mode is not None else op.putaway_mode
        if putaway_flow_id is not None or putaway_mode == ReflexMode.RULE:
            op.putaway_flow_id = putaway_flow_id
        op.auto_validate = auto_validate if auto_validate is not None else op.auto_validate
        if scan_flow == "default":
            op.scan_flow = None
        elif scan_flow is not None:
            op.scan_flow = scan_flow
        if op.putaway_mode == ReflexMode.INLINE and op.putaway_flow_id is None:
            raise _conflict(
                "Inline putaway requires putaway_flow_id", "putaway_flow_missing"
            )
        op.updated_at = utcnow()
        _ = await op.save()
        return op

    # --- Transfers (чтение) ---

    async def list_transfers(
        self,
        *,
        company_id: str,
        warehouse_id: str | None,
        state: StockTransferState | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[StockTransfer]:
        rows = await StockTransfer.list_by_created_at_desc(
            company_id, warehouse_id=warehouse_id, state=state, limit=limit, offset=offset
        )
        total = await StockTransfer.count_by_warehouse_and_state(
            company_id, warehouse_id=warehouse_id, state=state
        )
        return OffsetPage(items=rows, total=total, limit=limit, offset=offset)

    async def list_moves_by_created_at_desc(
        self,
        *,
        company_id: str,
        warehouse_id: str | None,
        location_id: str | None,
        subtree: bool,
        product_id: str | None,
        state: StockMoveState | None,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[StockMove]:
        """Журнал движений — keyset-страница ORDER BY created_at DESC.

        ``location_id`` фильтрует движения, где локация — источник ИЛИ
        приёмник; ``subtree=True`` расширяет его до всего поддерева
        («все движения зоны»).
        """
        location_ids: list[str] | None = None
        if location_id is not None:
            if subtree:
                location_ids = (
                    await StockLocation.list_subtree_ids_by_parent_path_asc(
                        company_id, location_id
                    )
                )
            else:
                location_ids = [location_id]
        return await StockMove.list_page_by_created_at_desc(
            company_id,
            warehouse_id=warehouse_id,
            location_ids=location_ids,
            product_id=product_id,
            state=state,
            limit=limit,
            cursor=cursor,
        )

    async def get_transfer(
        self, *, company_id: str, transfer_id: str
    ) -> tuple[StockTransfer, list[StockMove], list[StockMoveLine]]:
        transfer = await StockTransfer.by_id(company_id, transfer_id)
        if transfer is None:
            raise _not_found("Transfer not found", "transfer_not_found")
        moves = await StockMove.list_for_transfer_by_created_at_asc(company_id, transfer_id)
        lines = await StockMoveLine.list_for_moves_by_created_at_asc(
            company_id, [m.move_id for m in moves]
        )
        return transfer, moves, lines
