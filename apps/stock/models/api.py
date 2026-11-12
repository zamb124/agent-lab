"""Типизированный контракт команд stock: один payload на `op_*` (WS≡REST).

Payload'ы — `StrictBaseModel` (`extra="forbid"`); ответы — доменные модели
Oxyde напрямую либо композитные `*Detail`/`*Response` из этого файла.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import Field

from apps.stock.models.common import StockMoveSpec
from apps.stock.models.enums import (
    BackorderPolicy,
    ReflexMode,
    ReservationPolicy,
    StockBarcodeEntityType,
    StockContainerKind,
    StockContainerPolicy,
    StockLayoutPreset,
    StockLocationUsage,
    StockMoveState,
    StockOperationCode,
    StockProductMixing,
    StockPutawayStrategy,
    StockRemovalStrategy,
    StockTracking,
    StockTransferState,
    StockWaveState,
    ValuationMethod,
    ValueEntryKind,
)
from apps.stock.models.location import StockLocation
from apps.stock.models.move import StockMove
from apps.stock.models.move_line import StockMoveLine
from apps.stock.models.quant import StockQuant
from apps.stock.models.route import StockRouteStepSpec
from apps.stock.models.scan import ScanContext, ScanFlow, ScanResolution
from apps.stock.models.transfer import StockTransfer
from apps.stock.models.value_layer import StockValueLayer
from core.catalog.contracts import CatalogOverlay
from core.models import StrictBaseModel

ItemT = TypeVar("ItemT")


class StockItemsResponse(StrictBaseModel, Generic[ItemT]):
    """Непагинированный список — WS reply обязан быть JsonObject."""

    items: list[ItemT]


class StockPagePayload(StrictBaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


# --- Продукты ---


class StockProductCreatePayload(StrictBaseModel):
    """Создать складскую позицию: новая карточка каталога + фасет.

    ``product_id`` — подключение существующего товара каталога (выбор
    из дедуп-подсказки); тогда ``name``/``uom_id``/``sku``/``weight``/
    ``volume``/``barcodes`` игнорируются — база уже создана.
    """

    product_id: str | None = None
    name: str = Field(min_length=1, max_length=300)
    sku: str | None = Field(default=None, max_length=128)
    uom_id: str = Field(min_length=1)
    valuation_method: ValuationMethod
    standard_price: Decimal = Field(default=Decimal("0"), ge=0)
    tracking: StockTracking = StockTracking.NONE
    is_storable: bool = True
    category: str = Field(default="", max_length=128)
    barcodes: list[str] = Field(default_factory=list, max_length=20)
    weight: Decimal | None = Field(default=None, ge=0)
    volume: Decimal | None = Field(default=None, ge=0)
    use_expiration: bool = False
    expiration_days: int | None = Field(default=None, ge=1)
    best_before_days: int | None = Field(default=None, ge=1)
    removal_days: int | None = Field(default=None, ge=1)
    alert_days: int | None = Field(default=None, ge=1)
    removal_strategy: StockRemovalStrategy | None = None


class StockProductUpdatePayload(StrictBaseModel):
    """Правка складской политики и overlay'а scope ``stock``.

    Базовые поля (имя/SKU/габариты) — только через мастер-карту
    ``stock/catalog_products/update``; ``overlay`` — PUT-форма
    складских переопределений контента.
    """

    product_id: str
    barcodes: list[str] | None = Field(default=None, max_length=20)
    is_active: bool | None = None
    valuation_method: ValuationMethod | None = None
    standard_price: Decimal | None = Field(default=None, ge=0)
    tracking: StockTracking | None = None
    category: str | None = Field(default=None, max_length=128)
    overlay: CatalogOverlay | None = None
    use_expiration: bool | None = None
    expiration_days: int | None = Field(default=None, ge=1)
    best_before_days: int | None = Field(default=None, ge=1)
    removal_days: int | None = Field(default=None, ge=1)
    alert_days: int | None = Field(default=None, ge=1)
    removal_strategy: StockRemovalStrategy | None = None


class StockProductIdPayload(StrictBaseModel):
    product_id: str


class StockProductView(StrictBaseModel):
    """Складская карточка товара: эффективные поля каталога + фасет.

    ``name``/``description``/``image_file_ids`` — резолв цепочки
    ``stock`` scope (``sources[поле]`` — ``base`` либо ``stock``);
    остальные ``catalog_*``-поля — прямые значения мастер-карты.
    """

    product_id: str
    name: str
    description: str
    image_file_ids: list[str]
    sources: dict[str, str]
    sku: str | None
    uom_id: str
    barcodes: list[str]
    weight: Decimal | None
    volume: Decimal | None
    is_archived: bool
    tracking: StockTracking
    is_storable: bool
    is_active: bool
    category: str
    valuation_method: ValuationMethod
    standard_price: Decimal
    use_expiration: bool
    expiration_days: int | None
    best_before_days: int | None
    removal_days: int | None
    alert_days: int | None
    removal_strategy: StockRemovalStrategy | None
    created_at: datetime
    updated_at: datetime


# --- Локации ---


class StockLocationCreatePayload(StrictBaseModel):
    warehouse_id: str
    parent_id: str | None = None
    name: str = Field(min_length=1, max_length=255)
    usage: StockLocationUsage = StockLocationUsage.BIN
    barcode: str | None = Field(default=None, max_length=128)
    allow_negative: bool = False
    storage_type_id: str | None = None
    container_type_id: str | None = None
    pick_sequence: int = 0
    level: int = Field(default=1, ge=1)


class StockLocationUpdatePayload(StrictBaseModel):
    location_id: str
    name: str | None = Field(default=None, min_length=1, max_length=255)
    barcode: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None
    allow_negative: bool | None = None
    storage_type_id: str | None = None
    pick_sequence: int | None = None
    putaway_blocked: bool | None = None
    removal_blocked: bool | None = None


class StockLocationIdPayload(StrictBaseModel):
    location_id: str


class StockLocationsListPayload(StrictBaseModel):
    warehouse_id: str | None = None
    include_virtual: bool = False
    """Добавить виртуальные концы компании (partner/transit/adjustment)
    к физическим локациям склада — ТСД показывает их в маршрутах
    документов («→ customer»), хотя остатков на них нет."""


class StockLocationsCountDuePayload(StrictBaseModel):
    """Ячейки склада, пора пересчитывать — то же окно, что воркер
    cycle-count (``last_count_at`` старше интервала или никогда)."""
    warehouse_id: str
    limit: int = Field(default=200, ge=1, le=500)


# --- Склады ---


class StockWarehouseCreatePayload(StrictBaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    layout_preset: StockLayoutPreset = StockLayoutPreset.SIMPLE
    """Каркас топологии: simple (микросклад), standard (даркстор),
    distribution_center (РЦ с QC/bulk/forward/staging/карантином)."""
    removal_strategy: StockRemovalStrategy = StockRemovalStrategy.FIFO
    """Стратегия отбора склада — обязательная настройка (цепочка
    «товар → тип хранения → склад» всегда заканчивается здесь)."""


class StockWarehouseUpdatePayload(StrictBaseModel):
    warehouse_id: str
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=32)


class StockWarehouseIdPayload(StrictBaseModel):
    warehouse_id: str


# --- Типы операций ---


class StockOperationTypesListPayload(StrictBaseModel):
    warehouse_id: str


class StockOperationTypeUpdatePayload(StrictBaseModel):
    operation_type_id: str
    name: str | None = Field(default=None, min_length=1, max_length=255)
    reservation_policy: ReservationPolicy | None = None
    backorder_policy: BackorderPolicy | None = None
    putaway_mode: ReflexMode | None = None
    putaway_flow_id: str | None = None
    auto_validate: bool | None = None
    scan_flow: Literal[ScanFlow.PACK, ScanFlow.SHIP, "default"] | None = None
    """Поток ТСД для плеча маршрута: ``pack``/``ship`` — явная семантика;
    ``"default"`` — вернуть вывод из ``code`` (поле → NULL); ``None`` —
    не трогать."""


# --- Transfers / moves ---


class StockTransferCreatePayload(StrictBaseModel):
    warehouse_id: str
    operation_type_id: str
    partner_entity_id: str | None = None
    owner_entity_id: str | None = None
    scheduled_at: datetime | None = None
    origin_document_type: str | None = Field(default=None, max_length=64)
    origin_document_id: str | None = Field(default=None, max_length=64)
    barcode: str | None = Field(default=None, max_length=128)
    priority: int = 0
    date_deadline: datetime | None = None
    moves: list[StockMoveSpec] = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, max_length=128)


class StockTransferIdPayload(StrictBaseModel):
    transfer_id: str
    idempotency_key: str | None = Field(default=None, max_length=128)


class StockTransferValidatePayload(StrictBaseModel):
    transfer_id: str
    create_backorder: bool = True
    idempotency_key: str | None = Field(default=None, max_length=128)


class StockTransfersListPayload(StockPagePayload):
    warehouse_id: str | None = None
    state: StockTransferState | None = None


class StockMovesListPayload(StrictBaseModel):
    """Журнал движений — keyset-страница ORDER BY created_at DESC.

    ``location_id`` фильтрует движения, где локация — источник ИЛИ
    приёмник; ``subtree`` расширяет её до всего поддерева."""
    warehouse_id: str | None = None
    location_id: str | None = None
    subtree: bool = False
    product_id: str | None = None
    state: StockMoveState | None = None
    limit: int = Field(default=50, ge=1, le=500)
    cursor: str | None = None


class StockTransferReturnPayload(StrictBaseModel):
    transfer_id: str
    move_quantities: dict[str, Decimal] | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class StockTransferDetail(StrictBaseModel):
    transfer: StockTransfer
    moves: list[StockMove]
    lines: list[StockMoveLine]


# --- Move lines / решения ---


class StockMoveLineUpdatePayload(StrictBaseModel):
    move_line_id: str
    done_quantity: Decimal | None = Field(default=None, ge=0)
    picked: bool | None = None
    lot_id: str | None = None
    location_dest_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class StockMoveApplyDecisionPayload(StrictBaseModel):
    move_id: str
    location_id: str
    idempotency_key: str | None = Field(default=None, max_length=128)


# --- Остатки / инвентаризация ---


class StockQuantsListPayload(StockPagePayload):
    location_id: str | None = None
    product_id: str | None = None
    owner_entity_id: str | None = None
    warehouse_id: str | None = None
    subtree_location_id: str | None = None
    """Остатки всего поддерева этой локации (отчёт «остатки по зоне»);
    вместе с location_id не сочетается — subtree берёт поддерево,
    location_id — строго одну ячейку."""


class StockQuantInventorySetPayload(StrictBaseModel):
    quant_id: str
    inventory_quantity: Decimal = Field(ge=0)
    idempotency_key: str | None = Field(default=None, max_length=128)


class StockQuantInventoryApplyPayload(StrictBaseModel):
    quant_id: str
    idempotency_key: str | None = Field(default=None, max_length=128)


# --- Оценка ---


class StockValuationLayersPayload(StockPagePayload):
    product_id: str | None = None
    warehouse_id: str | None = None
    transfer_id: str | None = None
    entry_kinds: list[ValueEntryKind] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    open_only: bool = False
    search: str | None = Field(default=None, max_length=200)


class StockValuationLayersPage(StrictBaseModel):
    """Страница журнала оценки + sidecar-карты человеческих имён для строк."""

    items: list[StockValueLayer]
    total: int
    limit: int
    offset: int
    product_names: dict[str, str] = Field(default_factory=dict)
    product_skus: dict[str, str] = Field(default_factory=dict)
    transfer_names: dict[str, str] = Field(default_factory=dict)
    warehouse_names: dict[str, str] = Field(default_factory=dict)


class StockValuationReportPayload(StockPagePayload):
    warehouse_id: str | None = None
    search: str | None = Field(default=None, max_length=200)


class StockValuationReportRow(StrictBaseModel):
    """Строка отчёта «Стоимость запасов»: остаток товара в деньгах."""

    product_id: str
    name: str
    sku: str | None
    quantity: Decimal
    avg_cost: Decimal
    value: Decimal


class StockValuationReportResponse(StrictBaseModel):
    items: list[StockValuationReportRow]
    total_value: Decimal
    products_count: int


class StockValuationProductValuePayload(StrictBaseModel):
    product_id: str
    warehouse_id: str | None = None


class StockProductValueResponse(StrictBaseModel):
    product_id: str
    quantity: Decimal
    value: Decimal
    avg_cost: Decimal
    warehouse_id: str | None = None


class StockValuationRevaluePayload(StrictBaseModel):
    product_id: str
    value_delta: Decimal | None = None
    new_price: Decimal | None = Field(default=None, ge=0)
    description: str = Field(default="", max_length=512)
    idempotency_key: str | None = Field(default=None, max_length=128)


class StockValuationCorrectionPayload(StrictBaseModel):
    origin_layer_id: str
    quantity_delta: Decimal = Decimal("0")
    value_delta: Decimal
    description: str = Field(default="", max_length=512)
    idempotency_key: str | None = Field(default=None, max_length=128)


# --- Lots ---


class StockLotCreatePayload(StrictBaseModel):
    product_id: str
    name: str = Field(min_length=1, max_length=128)
    barcode: str | None = Field(default=None, max_length=128)
    expiration_at: datetime | None = None


class StockLotsListPayload(StrictBaseModel):
    product_id: str | None = None


# --- Топология: типы, контейнеры, ресурсы, упаковки ---


class StockStorageTypesListPayload(StrictBaseModel):
    warehouse_id: str


class StockStorageTypeCreatePayload(StrictBaseModel):
    warehouse_id: str
    name: str = Field(min_length=1, max_length=128)
    container_policy: StockContainerPolicy = StockContainerPolicy.ANY
    allowed_container_type_ids: list[str] = Field(default_factory=list)
    max_containers: int | None = Field(default=None, ge=1)
    product_mixing: StockProductMixing = StockProductMixing.MIXED
    allow_mixed_lots: bool = True
    max_weight: Decimal | None = Field(default=None, ge=0)
    max_volume: Decimal | None = Field(default=None, ge=0)
    putaway_strategies: list[StockPutawayStrategy] = Field(
        default_factory=lambda: [StockPutawayStrategy.EMPTY_BIN]
    )
    removal_strategy: StockRemovalStrategy | None = None
    """Переопределение стратегии склада; None — берётся политика склада."""
    cycle_count_days: int | None = Field(default=None, ge=1)
    """Период циклического пересчёта ячеек этого типа (дней);
    None — дефолт воркера."""


class StockStorageTypeUpdatePayload(StrictBaseModel):
    """None-поле не пишется; очистки nullable-полей нет (та же
    конвенция, что у StockLocationUpdatePayload)."""
    storage_type_id: str
    name: str | None = Field(default=None, min_length=1, max_length=128)
    container_policy: StockContainerPolicy | None = None
    allowed_container_type_ids: list[str] | None = None
    max_containers: int | None = Field(default=None, ge=1)
    product_mixing: StockProductMixing | None = None
    allow_mixed_lots: bool | None = None
    max_weight: Decimal | None = Field(default=None, ge=0)
    max_volume: Decimal | None = Field(default=None, ge=0)
    putaway_strategies: list[StockPutawayStrategy] | None = None
    removal_strategy: StockRemovalStrategy | None = None
    cycle_count_days: int | None = Field(default=None, ge=1)


class StockContainerTypesListPayload(StrictBaseModel):
    warehouse_id: str


class StockContainerTypeCreatePayload(StrictBaseModel):
    warehouse_id: str
    name: str = Field(min_length=1, max_length=128)
    kind: StockContainerKind = StockContainerKind.OTHER
    max_weight: Decimal | None = Field(default=None, ge=0)
    tare_weight: Decimal | None = Field(default=None, ge=0)
    max_volume: Decimal | None = Field(default=None, ge=0)
    length: Decimal | None = Field(default=None, ge=0)
    width: Decimal | None = Field(default=None, ge=0)
    height: Decimal | None = Field(default=None, ge=0)
    is_reusable: bool = False
    allowed_parent_type_ids: list[str] = Field(default_factory=list)


class StockContainerTypeUpdatePayload(StrictBaseModel):
    container_type_id: str
    name: str | None = Field(default=None, min_length=1, max_length=128)
    kind: StockContainerKind | None = None
    max_weight: Decimal | None = Field(default=None, ge=0)
    tare_weight: Decimal | None = Field(default=None, ge=0)
    max_volume: Decimal | None = Field(default=None, ge=0)
    length: Decimal | None = Field(default=None, ge=0)
    width: Decimal | None = Field(default=None, ge=0)
    height: Decimal | None = Field(default=None, ge=0)
    is_reusable: bool | None = None
    allowed_parent_type_ids: list[str] | None = None


class StockResourceTypesListPayload(StrictBaseModel):
    warehouse_id: str


class StockResourceTypeCreatePayload(StrictBaseModel):
    warehouse_id: str
    name: str = Field(min_length=1, max_length=128)
    allowed_container_type_ids: list[str] = Field(default_factory=list)
    handles_loose: bool = True
    max_level: int | None = Field(default=None, ge=1)
    max_load_weight: Decimal | None = Field(default=None, ge=0)
    storage_type_ids: list[str] = Field(default_factory=list)


class StockResourceTypeUpdatePayload(StrictBaseModel):
    resource_type_id: str
    name: str | None = Field(default=None, min_length=1, max_length=128)
    allowed_container_type_ids: list[str] | None = None
    handles_loose: bool | None = None
    max_level: int | None = Field(default=None, ge=1)
    max_load_weight: Decimal | None = Field(default=None, ge=0)
    storage_type_ids: list[str] | None = None


class StockResourcesListPayload(StrictBaseModel):
    warehouse_id: str


class StockResourceCreatePayload(StrictBaseModel):
    warehouse_id: str
    resource_type_id: str
    code: str = Field(min_length=1, max_length=64)
    barcode: str | None = Field(default=None, max_length=128)


class StockResourceUpdatePayload(StrictBaseModel):
    resource_id: str
    resource_type_id: str | None = None
    code: str | None = Field(default=None, min_length=1, max_length=64)
    barcode: str | None = Field(default=None, max_length=128)


class StockResourceLoginPayload(StrictBaseModel):
    warehouse_id: str
    resource_id: str | None = None
    barcode: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, max_length=128)


class StockResourceLogoutPayload(StrictBaseModel):
    warehouse_id: str
    idempotency_key: str | None = Field(default=None, max_length=128)


class StockContainersListPayload(StrictBaseModel):
    warehouse_id: str | None = None
    parent_location_id: str | None = None


class StockContainerCreatePayload(StrictBaseModel):
    warehouse_id: str
    parent_location_id: str
    container_type_id: str
    name: str = Field(min_length=1, max_length=255)
    barcode: str | None = Field(default=None, max_length=128)


class StockContainerIdPayload(StrictBaseModel):
    container_id: str


class StockContainerMovePayload(StrictBaseModel):
    container_id: str
    dest_location_id: str
    idempotency_key: str | None = Field(default=None, max_length=128)


class StockContainerContentsResponse(StrictBaseModel):
    container: StockLocation
    quants: list[StockQuant]
    children: list[StockLocation]


class StockPackagingsListPayload(StrictBaseModel):
    product_id: str | None = None


class StockPackagingCreatePayload(StrictBaseModel):
    product_id: str
    name: str = Field(min_length=1, max_length=128)
    quantity: Decimal = Field(gt=0)
    barcode: str | None = Field(default=None, max_length=128)
    weight: Decimal | None = Field(default=None, ge=0)
    volume: Decimal | None = Field(default=None, ge=0)


class StockPackagingIdPayload(StrictBaseModel):
    packaging_id: str


# --- Пульс / barcode / init ---


class StockWarehousePulsePayload(StrictBaseModel):
    warehouse_id: str


class StockPulseTransferRow(StrictBaseModel):
    transfer_id: str
    name: str
    operation_code: str
    state: StockTransferState
    scheduled_at: str | None = None
    age_seconds: float


class StockPulseQuantRow(StrictBaseModel):
    product_id: str
    location_id: str
    quantity: Decimal
    reserved_quantity: Decimal
    available_quantity: Decimal
    avg_cost: Decimal
    value: Decimal
    last_move_at: str | None = None


class StockWarehousePulseResponse(StrictBaseModel):
    warehouse_id: str
    transfers: list[StockPulseTransferRow]
    quants: list[StockPulseQuantRow]


class StockOperatorPulsePayload(StrictBaseModel):
    """Показатели самого оператора за скользящее окно смены."""

    warehouse_id: str
    window_hours: int = Field(default=8, ge=1, le=24)


class StockOperatorPulseResponse(StrictBaseModel):
    warehouse_id: str
    window_hours: int
    lines_done: int
    units_done: Decimal
    count_lines_done: int
    container_lines_done: int
    lines_per_hour: Decimal
    first_done_at: str | None = None
    last_done_at: str | None = None


class StockBarcodeResolvePayload(StrictBaseModel):
    barcode: str = Field(min_length=1, max_length=128)


class StockBarcodeResolveResponse(StrictBaseModel):
    entity_type: StockBarcodeEntityType
    entity_id: str
    is_gs1: bool = False
    gtin: str | None = None
    sscc: str | None = None
    lot_name: str | None = None
    serial: str | None = None
    quantity: Decimal | None = None
    weight_kg: Decimal | None = None
    expiration_date: str | None = None


class StockCompanyInitResponse(StrictBaseModel):
    company_id: str
    location_ids: list[str]


# --- Скан-сессии ТСД ---


class StockScanStepPayload(StrictBaseModel):
    """Один скан в потоке: приехал контекст + штрихкод, уехал новый контекст."""

    warehouse_id: str
    context: ScanContext
    barcode: str = Field(min_length=1, max_length=128)
    move_id: str | None = None
    """Сессия идёт по документу — ответ принесёт `expected` подсказку."""


class StockScanQuantityPayload(StrictBaseModel):
    warehouse_id: str
    context: ScanContext
    quantity: Decimal = Field(gt=Decimal("0"))
    move_id: str | None = None


class StockScanExpected(StrictBaseModel):
    """Что экран должен подсветить оператору на текущем шаге.

    Берётся из первой открытой строки документа: «отсканируй ячейку
    A-01, возьми SKU-77, осталось 3 шт, положи в DOCK-2». Без привязки
    к документу (``move_id`` не задан) — ``None``, экран строится
    только по ``context.step``.
    """

    move_line_id: str | None = None
    location_id: str | None = None
    product_id: str | None = None
    quantity: Decimal | None = None
    location_dest_id: str | None = None


class StockScanStepResponse(StrictBaseModel):
    context: ScanContext
    resolution: ScanResolution | None = None
    error: str | None = None
    hint: str = ""
    expected: StockScanExpected | None = None


class StockScanAdhocCommitPayload(StrictBaseModel):
    """Ad-hoc коммит без документа: набранные строки → новая накладная."""

    warehouse_id: str
    operation_code: StockOperationCode
    context: ScanContext
    idempotency_key: str | None = Field(default=None, max_length=128)


class StockScanOpenPayload(StrictBaseModel):
    """Открыть скан-сессию по документу — backend выбирает поток."""

    warehouse_id: str
    move_id: str | None = None
    transfer_id: str | None = None


class StockScanOpenResponse(StrictBaseModel):
    context: ScanContext
    move_id: str
    expected: StockScanExpected | None = None


class StockScanCommitPayload(StrictBaseModel):
    """Коммит набранного: строки контекста → проводка move одной транзакцией."""

    move_id: str
    context: ScanContext
    idempotency_key: str | None = None


class StockScanCountCommitPayload(StrictBaseModel):
    warehouse_id: str
    context: ScanContext
    idempotency_key: str | None = None


class StockScanCountCommitResponse(StrictBaseModel):
    quant_ids: list[str]


# --- Очередь заданий (ТСД) ---


class StockMoveLinesQueuePayload(StrictBaseModel):
    warehouse_id: str
    assigned_user_id: str | None = None
    zone_location_id: str | None = None
    """Зона склада — очередь только её поддерева ячеек-источников."""
    wave_id: str | None = None
    """Очередь внутри волны сборки, если оператор её выбрал."""
    limit: int = Field(default=100, ge=1, le=500)


class StockMoveLineNextPayload(StrictBaseModel):
    warehouse_id: str
    resource_id: str | None = None
    zone_location_id: str | None = None
    wave_id: str | None = None
    claim: bool = True


class StockMoveLineNextResponse(StrictBaseModel):
    line: StockMoveLine | None = None


class StockMoveLinesClaimPayload(StrictBaseModel):
    warehouse_id: str
    move_line_ids: list[str] = Field(min_length=1, max_length=200)
    resource_id: str | None = None
    idempotency_key: str | None = None


class StockMoveLinesAssignPayload(StockMoveLinesClaimPayload):
    assignee_user_id: str


class StockMoveLinesReleasePayload(StrictBaseModel):
    warehouse_id: str
    move_line_ids: list[str] = Field(min_length=1, max_length=200)
    idempotency_key: str | None = None


class StockMoveLineExceptionPayload(StrictBaseModel):
    """«Пришёл — а товара нет»: недостача/бой по строке задания."""

    warehouse_id: str
    move_line_id: str
    shortage: Decimal = Field(gt=Decimal("0"))
    reason: str = Field(default="", max_length=512)
    file_ids: list[str] = Field(default_factory=list, max_length=8)
    """Фото доказательства (бой, пустая ячейка) — общие файлы платформы."""
    idempotency_key: str | None = None


# --- Волны сборки ---


class StockWavesListPayload(StrictBaseModel):
    warehouse_id: str
    state: StockWaveState | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class StockWaveCreatePayload(StrictBaseModel):
    warehouse_id: str
    name: str | None = Field(default=None, max_length=128)
    move_line_ids: list[str] = Field(default_factory=list, max_length=2000)
    move_ids: list[str] = Field(default_factory=list, max_length=500)
    priority: int = 0
    user_id: str | None = None
    stop_transfer_ids: list[str] = Field(default_factory=list, max_length=500)
    idempotency_key: str | None = None


class StockWaveIdPayload(StrictBaseModel):
    wave_id: str
    idempotency_key: str | None = None


# --- Маршруты цепочек движений ---


class StockRouteCreatePayload(StrictBaseModel):
    warehouse_id: str | None = None
    name: str = Field(max_length=255)
    code: str = Field(default="", max_length=64)
    steps: list[StockRouteStepSpec] = Field(default_factory=list, max_length=20)
    idempotency_key: str | None = None


class StockRoutesListPayload(StrictBaseModel):
    warehouse_id: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class StockRouteIdPayload(StrictBaseModel):
    route_id: str


# --- Правила пополнения (min/max) ---


class StockReorderRulesListPayload(StrictBaseModel):
    warehouse_id: str | None = None


class StockReorderRuleCreatePayload(StrictBaseModel):
    warehouse_id: str
    product_id: str
    location_id: str
    min_qty: Decimal = Field(ge=0)
    max_qty: Decimal = Field(gt=0)
    operation_type_id: str
    route_id: str | None = None
    idempotency_key: str | None = None


class StockReorderRuleUpdatePayload(StrictBaseModel):
    rule_id: str
    is_active: bool
    idempotency_key: str | None = None


class StockPutawayRulesListPayload(StrictBaseModel):
    warehouse_id: str


class StockPutawayRuleCreatePayload(StrictBaseModel):
    """Правило «из зоны приёмки location_in товар X кладём в location_out».

    Фильтры: product/category/owner — чем конкретнее, тем выше приоритет
    при равном sequence. destination не может быть партнёрской/
    корректировочной локацией.
    """

    warehouse_id: str
    location_in_id: str
    location_out_id: str
    product_id: str | None = None
    category: str | None = None
    owner_entity_id: str | None = None
    sequence: int = 0
    idempotency_key: str | None = None


class StockPutawayRuleUpdatePayload(StrictBaseModel):
    rule_id: str
    location_in_id: str | None = None
    location_out_id: str | None = None
    product_id: str | None = None
    category: str | None = None
    owner_entity_id: str | None = None
    sequence: int | None = None
    is_active: bool | None = None
    idempotency_key: str | None = None


class StockPutawayRuleDeletePayload(StrictBaseModel):
    rule_id: str
    idempotency_key: str | None = None


class StockPutawaySuggestPayload(StrictBaseModel):
    """Top-N ячеек «куда поставить» по одному товару — ad-hoc подсказка ТСД."""

    warehouse_id: str
    product_id: str
    product_qty: Decimal = Field(default=Decimal("1"), gt=0)
    location_dest_id: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class StockPutawaySuggestionItem(StrictBaseModel):
    location_id: str
    name: str
    reason_code: str
    allowed: bool


class StockPutawaySuggestResponse(StrictBaseModel):
    items: list[StockPutawaySuggestionItem]
