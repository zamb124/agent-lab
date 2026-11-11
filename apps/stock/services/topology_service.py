"""Топология склада: дерево локаций, типы хранения/контейнеров/ресурсов.

Агрегат «как устроена площадка»: адресное дерево (зоны → ячейки →
тара), политики типов хранения и шаблоны тары, оборудование.

Контейнер — `StockLocation` с `usage=container` (не отдельная таблица):
содержимое — его quant'ы и дочерние контейнеры, перемещение — rebind
поддерева (`StockMove.move_container_in_lane`, полосы обоих складов).
Упаковки товаров — ``CatalogService`` (AUoM в ``catalog_uoms``).
"""

from __future__ import annotations

from decimal import Decimal

from oxyde.exceptions import UniqueViolationError

from apps.stock.models import (
    StockBarcodeEntityType,
    StockContainerKind,
    StockContainerPolicy,
    StockContainerType,
    StockLocation,
    StockLocationUsage,
    StockMove,
    StockProductMixing,
    StockPutawayStrategy,
    StockQuant,
    StockRemovalStrategy,
    StockResource,
    StockResourceType,
    StockStorageType,
    StockWarehouse,
)
from apps.stock.models.common import STOCK_DB
from apps.stock.models.resource import StockResourceLogoutResult
from apps.stock.services.barcode_service import BarcodeService
from apps.stock.services.ids import new_id
from apps.stock.services.maintenance_service import DEFAULT_CYCLE_COUNT_INTERVAL
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.lanes import publish_lane_run
from core.request_scope import command_idempotency_key
from core.utils.time import utcnow


def _not_found(message: str, code: str) -> PlatformNotFoundError:
    return PlatformNotFoundError(message, error_code=code)


def _conflict(message: str, code: str) -> PlatformConflictError:
    return PlatformConflictError(message, error_code=code)


class StockContainerContents:
    """Что лежит в таре: кванты товара + вложенные контейнеры.

    «Содержимое паллеты» = все строки остатков по этой локации
    (``quants``: товар × партия × владелец) плюс дочерние контейнеры
    (``children``: коробки на этой паллете). Тара может нести и товар,
    и тару — поэтому отчёт двухуровневый.
    """

    def __init__(
        self,
        *,
        container: StockLocation,
        quants: list[StockQuant],
        children: list[StockLocation],
    ) -> None:
        self.container: StockLocation = container
        self.quants: list[StockQuant] = quants
        self.children: list[StockLocation] = children


class TopologyService:
    """Настройка «карты» склада и оборудования.

    Справочники, по которым система решает «куда класть» и «чем везти»:

    * типы хранения — политики ячеек (что принимают: только тару или
      россыпь; сколько контейнеров вмещают; лимиты веса/объёма; можно
      ли смешивать товары);
    * типы контейнеров — шаблоны тары (паллета, короб, корзина) с
      габаритами и правилами вложения;
    * типы и единицы ресурсов — классы техники и конкретные машины;
      оператор «садится» на ресурс сканом в начале смены;
    * сами контейнеры (тара-локации) и адресное дерево локаций.

    Справочные операции прямые; физическое перемещение контейнера —
    ``move_container`` через полосу склада, потому что оно меняет
    адреса запаса.
    """

    def __init__(self, barcode: BarcodeService) -> None:
        self._barcode: BarcodeService = barcode

    async def _require_warehouse(
        self, company_id: str, warehouse_id: str
    ) -> StockWarehouse:
        warehouse = await StockWarehouse.by_id(company_id, warehouse_id)
        if warehouse is None:
            raise _not_found("Warehouse not found", "warehouse_not_found")
        return warehouse

    # --- Локации ---

    async def create_location(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        parent_id: str | None,
        name: str,
        usage: StockLocationUsage,
        barcode: str | None,
        allow_negative: bool = False,
        storage_type_id: str | None = None,
        container_type_id: str | None = None,
        pick_sequence: int = 0,
        level: int = 1,
    ) -> StockLocation:
        """Создать локацию в дереве склада (зону, ячейку или контейнер).

        Бизнес-правила адресации:

        * внутри склада заводятся только ``view`` (зона/ряд — не хранит
          запас), ``bin`` (ячейка — реальный адрес запаса) и
          ``container`` (тара); виртуальные локации компании
          (``partner``, ``adjustment``, ``transit``) создаёт только
          ``stock/company/init`` — руками их создать нельзя;
        * дети разрешены только под ``view`` (зона → ячейка) и под
          ``container`` (короб внутри паллеты); под ячейкой ничего
          нельзя — она листовая точка хранения;
        * контейнер обязан иметь ``container_type_id`` — без типа тары
          система не знает её габариты и правила вложения;
        * без ``parent_id`` локация вешается под корень склада
          (``view_location_id``).

        ``pick_sequence`` задаёт порядок обхода при сборке,
        ``level`` — ярус (для проверки «достаёт ли ресурс»).
        """
        warehouse = await self._require_warehouse(company_id, warehouse_id)
        if usage not in {
            StockLocationUsage.VIEW,
            StockLocationUsage.BIN,
            StockLocationUsage.CONTAINER,
        }:
            raise _conflict(
                "Warehouse locations must be view|bin|container",
                "location_usage_invalid",
            )
        parent: StockLocation | None = None
        if parent_id is not None:
            parent = await StockLocation.by_id(company_id, parent_id)
            if parent is None or parent.warehouse_id != warehouse_id:
                raise _not_found("Parent location not found", "location_not_found")
            if parent.usage != StockLocationUsage.VIEW and not (
                usage == StockLocationUsage.CONTAINER
                and parent.usage == StockLocationUsage.CONTAINER
            ):
                raise _conflict(
                    "Children allowed under view or container (container-in-container)",
                    "location_parent_invalid",
                )
        else:
            parent = await StockLocation.by_id(
                company_id, warehouse.view_location_id
            )
        if usage == StockLocationUsage.CONTAINER and container_type_id is None:
            raise _conflict(
                "Container location requires container_type_id",
                "container_type_missing",
            )
        location = await StockLocation.create_with_parent_path(
            company_id=company_id,
            warehouse_id=warehouse_id,
            parent=parent,
            name=name,
            usage=usage,
            allow_negative=allow_negative,
            storage_type_id=storage_type_id,
            container_type_id=container_type_id,
            pick_sequence=pick_sequence,
            level=level,
        )
        if barcode is not None:
            _ = await self._barcode.register(
                company_id=company_id,
                barcode=barcode,
                entity_type=StockBarcodeEntityType.LOCATION,
                entity_id=location.location_id,
            )
        return location

    async def update_location(
        self,
        *,
        company_id: str,
        location_id: str,
        name: str | None,
        barcode: str | None,
        is_active: bool | None,
        allow_negative: bool | None = None,
        storage_type_id: str | None = None,
        pick_sequence: int | None = None,
        putaway_blocked: bool | None = None,
        removal_blocked: bool | None = None,
    ) -> StockLocation:
        """Править карточку локации.

        ``putaway_blocked`` — «ячейка закрыта для размещения» (уборка,
        ремонт стеллажа): правила putaway её пропустят, но уже лежащий
        товар отдавать можно. ``removal_blocked`` — наоборот: «из ячейки
        не отбирать» (контроль качества/карантин): запас там числится,
        но сборка его не трогает.
        """
        location = await StockLocation.by_id(company_id, location_id)
        if location is None:
            raise _not_found("Location not found", "location_not_found")
        location.name = name if name is not None else location.name
        location.is_active = is_active if is_active is not None else location.is_active
        if allow_negative is not None:
            location.allow_negative = allow_negative
        if storage_type_id is not None:
            location.storage_type_id = storage_type_id
        if pick_sequence is not None:
            location.pick_sequence = pick_sequence
        if putaway_blocked is not None:
            location.putaway_blocked = putaway_blocked
        if removal_blocked is not None:
            location.removal_blocked = removal_blocked
        if barcode is not None:
            _ = await self._barcode.replace(
                company_id=company_id,
                barcode=barcode,
                entity_type=StockBarcodeEntityType.LOCATION,
                entity_id=location.location_id,
            )
        _ = await location.save()
        return location

    async def list_locations(
        self, *, company_id: str, warehouse_id: str | None
    ) -> list[StockLocation]:
        rows = await StockLocation.list_by_usage_and_name_asc(company_id)
        if warehouse_id is not None:
            rows = [r for r in rows if r.warehouse_id == warehouse_id]
        return rows

    async def get_location(
        self, *, company_id: str, location_id: str
    ) -> StockLocation:
        location = await StockLocation.by_id(company_id, location_id)
        if location is None:
            raise _not_found("Location not found", "location_not_found")
        return location

    # --- Типы хранения ---

    async def list_storage_types(
        self, *, company_id: str, warehouse_id: str
    ) -> list[StockStorageType]:
        return await StockStorageType.list_for_warehouse_by_name_asc(company_id, warehouse_id)

    async def create_storage_type(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        name: str,
        putaway_strategies: list[StockPutawayStrategy],
        allowed_container_type_ids: list[str],
        container_policy: StockContainerPolicy = StockContainerPolicy.ANY,
        max_containers: int | None = None,
        product_mixing: StockProductMixing = StockProductMixing.MIXED,
        allow_mixed_lots: bool = True,
        max_weight: Decimal | None = None,
        max_volume: Decimal | None = None,
        removal_strategy: StockRemovalStrategy | None = None,
        cycle_count_days: int | None = None,
    ) -> StockStorageType:
        """Завести тип хранения — «класс ячеек с одинаковыми правилами».

        Пример: тип «Стеллаж B» = «только паллеты, не более 2-х на
        ячейку, товары смешивать нельзя». Дальше ячейкам назначают этот
        тип, и все проверки размещения (``check_placement``) исполняют
        эти правила единообразно.

        ``putaway_strategies`` — обязательная цепочка поиска ячейки
        (пустая цепочка = «не размещать автоматически»: лучше явный
        ``[manual]``); ``removal_strategy=None`` — ячейки типа
        наследуют стратегию склада.
        """
        _ = await self._require_warehouse(company_id, warehouse_id)
        now = utcnow()
        try:
            return await StockStorageType.create(
                StockStorageType(
                    storage_type_id=new_id("sst"),
                    company_id=company_id,
                    warehouse_id=warehouse_id,
                    name=name,
                    container_policy=container_policy,
                    allowed_container_type_ids=allowed_container_type_ids,
                    max_containers=max_containers,
                    product_mixing=product_mixing,
                    allow_mixed_lots=allow_mixed_lots,
                    max_weight=max_weight,
                    max_volume=max_volume,
                    putaway_strategies=putaway_strategies,
                    removal_strategy=removal_strategy,
                    cycle_count_days=cycle_count_days,
                    created_at=now,
                    updated_at=now,
                )
            )
        except UniqueViolationError as exc:
            raise _conflict(
                "Storage type name already exists", "storage_type_conflict"
            ) from exc

    # --- Типы контейнеров ---

    async def list_container_types(
        self, *, company_id: str, warehouse_id: str
    ) -> list[StockContainerType]:
        return await StockContainerType.list_for_warehouse_by_name_asc(company_id, warehouse_id)

    async def create_container_type(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        name: str,
        kind: StockContainerKind = StockContainerKind.OTHER,
        max_weight: Decimal | None = None,
        tare_weight: Decimal | None = None,
        max_volume: Decimal | None = None,
        length: Decimal | None = None,
        width: Decimal | None = None,
        height: Decimal | None = None,
        is_reusable: bool = False,
        allowed_parent_type_ids: list[str],
    ) -> StockContainerType:
        """Завести шаблон тары (паллета, короб, корзина, тележка).

        Габариты и ``tare_weight`` нужны расчётам ёмкости ячеек и
        грузоподъёмности; ``allowed_parent_type_ids`` ограничивает
        вложение («мешок можно только в короб/паллету»).
        """
        _ = await self._require_warehouse(company_id, warehouse_id)
        now = utcnow()
        try:
            return await StockContainerType.create(
                StockContainerType(
                    container_type_id=new_id("sct"),
                    company_id=company_id,
                    warehouse_id=warehouse_id,
                    name=name,
                    kind=kind,
                    max_weight=max_weight,
                    tare_weight=tare_weight,
                    max_volume=max_volume,
                    length=length,
                    width=width,
                    height=height,
                    is_reusable=is_reusable,
                    allowed_parent_type_ids=allowed_parent_type_ids,
                    created_at=now,
                    updated_at=now,
                )
            )
        except UniqueViolationError as exc:
            raise _conflict(
                "Container type name already exists", "container_type_conflict"
            ) from exc

    # --- Типы и единицы ресурсов ---

    async def list_resource_types(
        self, *, company_id: str, warehouse_id: str
    ) -> list[StockResourceType]:
        return await StockResourceType.list_for_warehouse_by_name_asc(company_id, warehouse_id)

    async def create_resource_type(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        name: str,
        allowed_container_type_ids: list[str],
        storage_type_ids: list[str],
        handles_loose: bool = True,
        max_level: int | None = None,
        max_load_weight: Decimal | None = None,
    ) -> StockResourceType:
        """Завести класс техники с его возможностями.

        По этой карточке ``resource_allows`` решает, может ли конкретная
        машина исполнить задание: до какого яруса достаёт, сколько веса
        берёт за рейс, с какой тарой и в каких зонах работает.
        """
        _ = await self._require_warehouse(company_id, warehouse_id)
        now = utcnow()
        try:
            return await StockResourceType.create(
                StockResourceType(
                    resource_type_id=new_id("srt"),
                    company_id=company_id,
                    warehouse_id=warehouse_id,
                    name=name,
                    allowed_container_type_ids=allowed_container_type_ids,
                    handles_loose=handles_loose,
                    max_level=max_level,
                    max_load_weight=max_load_weight,
                    storage_type_ids=storage_type_ids,
                    created_at=now,
                    updated_at=now,
                )
            )
        except UniqueViolationError as exc:
            raise _conflict(
                "Resource type name already exists", "resource_type_conflict"
            ) from exc

    async def list_resources(
        self, *, company_id: str, warehouse_id: str
    ) -> list[StockResource]:
        return await StockResource.list_for_warehouse_by_code_asc(company_id, warehouse_id)

    async def create_resource(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        resource_type_id: str,
        code: str,
        barcode: str | None,
    ) -> StockResource:
        """Поставить на учёт конкретную единицу техники.

        ``code`` — инвентарный номер («Погрузчик-3», уникален на склад),
        ``barcode`` — наклейка для входа оператора сканом. Без типа
        ресурса создать единицу нельзя — у неё не было бы возможностей.
        """
        _ = await self._require_warehouse(company_id, warehouse_id)
        if await StockResourceType.by_id(company_id, resource_type_id) is None:
            raise _not_found("Resource type not found", "resource_type_not_found")
        now = utcnow()
        try:
            resource = await StockResource.create(
                StockResource(
                    resource_id=new_id("src"),
                    company_id=company_id,
                    warehouse_id=warehouse_id,
                    resource_type_id=resource_type_id,
                    code=code,
                    created_at=now,
                    updated_at=now,
                )
            )
        except UniqueViolationError as exc:
            raise _conflict("Resource code already exists", "resource_conflict") from exc
        if barcode is not None:
            _ = await self._barcode.register(
                company_id=company_id,
                barcode=barcode,
                entity_type=StockBarcodeEntityType.RESOURCE,
                entity_id=resource.resource_id,
            )
        return resource

    # --- Цикл пересчёта ---

    async def list_due_bins(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        limit: int,
    ) -> list[StockLocation]:
        """Ячейки склада, для которых пора пересчёт — то же окно,
        что воркер cycle-count планирует (``due_before`` = now −
        ``DEFAULT_CYCLE_COUNT_INTERVAL``, per-type ``cycle_count_days``
        учитывает сама модель). UI «Инвентаризация» читает этот список,
        не дублируя логику воркера."""
        _ = await self._require_warehouse(company_id, warehouse_id)
        return await StockLocation.list_due_bins_by_last_count_at_asc(
            company_id,
            warehouse_id,
            due_before=utcnow() - DEFAULT_CYCLE_COUNT_INTERVAL,
            limit=limit,
        )

    # --- Справочные update ---

    async def update_storage_type(
        self,
        *,
        company_id: str,
        storage_type_id: str,
        name: str | None = None,
        container_policy: StockContainerPolicy | None = None,
        allowed_container_type_ids: list[str] | None = None,
        max_containers: int | None = None,
        product_mixing: StockProductMixing | None = None,
        allow_mixed_lots: bool | None = None,
        max_weight: Decimal | None = None,
        max_volume: Decimal | None = None,
        putaway_strategies: list[StockPutawayStrategy] | None = None,
        removal_strategy: StockRemovalStrategy | None = None,
        cycle_count_days: int | None = None,
    ) -> StockStorageType:
        """Править политику типа хранения; None-поле не пишется."""
        row = await StockStorageType.by_id(company_id, storage_type_id)
        if row is None:
            raise _not_found("Storage type not found", "storage_type_not_found")
        if name is not None:
            row.name = name
        if container_policy is not None:
            row.container_policy = container_policy
        if allowed_container_type_ids is not None:
            row.allowed_container_type_ids = allowed_container_type_ids
        if max_containers is not None:
            row.max_containers = max_containers
        if product_mixing is not None:
            row.product_mixing = product_mixing
        if allow_mixed_lots is not None:
            row.allow_mixed_lots = allow_mixed_lots
        if max_weight is not None:
            row.max_weight = max_weight
        if max_volume is not None:
            row.max_volume = max_volume
        if putaway_strategies is not None:
            row.putaway_strategies = putaway_strategies
        if removal_strategy is not None:
            row.removal_strategy = removal_strategy
        if cycle_count_days is not None:
            row.cycle_count_days = cycle_count_days
        row.updated_at = utcnow()
        try:
            return await row.save()
        except UniqueViolationError as exc:
            raise _conflict(
                "Storage type name already exists", "storage_type_conflict"
            ) from exc

    async def update_container_type(
        self,
        *,
        company_id: str,
        container_type_id: str,
        name: str | None = None,
        kind: StockContainerKind | None = None,
        max_weight: Decimal | None = None,
        tare_weight: Decimal | None = None,
        max_volume: Decimal | None = None,
        length: Decimal | None = None,
        width: Decimal | None = None,
        height: Decimal | None = None,
        is_reusable: bool | None = None,
        allowed_parent_type_ids: list[str] | None = None,
    ) -> StockContainerType:
        """Править шаблон тары; None-поле не пишется."""
        row = await StockContainerType.by_id(company_id, container_type_id)
        if row is None:
            raise _not_found("Container type not found", "container_type_not_found")
        if name is not None:
            row.name = name
        if kind is not None:
            row.kind = kind
        if max_weight is not None:
            row.max_weight = max_weight
        if tare_weight is not None:
            row.tare_weight = tare_weight
        if max_volume is not None:
            row.max_volume = max_volume
        if length is not None:
            row.length = length
        if width is not None:
            row.width = width
        if height is not None:
            row.height = height
        if is_reusable is not None:
            row.is_reusable = is_reusable
        if allowed_parent_type_ids is not None:
            row.allowed_parent_type_ids = allowed_parent_type_ids
        row.updated_at = utcnow()
        try:
            return await row.save()
        except UniqueViolationError as exc:
            raise _conflict(
                "Container type name already exists", "container_type_conflict"
            ) from exc

    async def update_resource_type(
        self,
        *,
        company_id: str,
        resource_type_id: str,
        name: str | None = None,
        allowed_container_type_ids: list[str] | None = None,
        handles_loose: bool | None = None,
        max_level: int | None = None,
        max_load_weight: Decimal | None = None,
        storage_type_ids: list[str] | None = None,
    ) -> StockResourceType:
        """Править класс техники; None-поле не пишется."""
        row = await StockResourceType.by_id(company_id, resource_type_id)
        if row is None:
            raise _not_found("Resource type not found", "resource_type_not_found")
        if name is not None:
            row.name = name
        if allowed_container_type_ids is not None:
            row.allowed_container_type_ids = allowed_container_type_ids
        if handles_loose is not None:
            row.handles_loose = handles_loose
        if max_level is not None:
            row.max_level = max_level
        if max_load_weight is not None:
            row.max_load_weight = max_load_weight
        if storage_type_ids is not None:
            row.storage_type_ids = storage_type_ids
        row.updated_at = utcnow()
        try:
            return await row.save()
        except UniqueViolationError as exc:
            raise _conflict(
                "Resource type name already exists", "resource_type_conflict"
            ) from exc

    async def update_resource(
        self,
        *,
        company_id: str,
        resource_id: str,
        resource_type_id: str | None = None,
        code: str | None = None,
        barcode: str | None = None,
    ) -> StockResource:
        """Править единицу техники; смена ``barcode`` — replace
        в баркод-реестре (как у локаций)."""
        row = await StockResource.by_id(company_id, resource_id)
        if row is None:
            raise _not_found("Resource not found", "resource_not_found")
        if resource_type_id is not None:
            if await StockResourceType.by_id(company_id, resource_type_id) is None:
                raise _not_found(
                    "Resource type not found", "resource_type_not_found"
                )
            row.resource_type_id = resource_type_id
        if code is not None:
            row.code = code
        if barcode is not None:
            _ = await self._barcode.replace(
                company_id=company_id,
                barcode=barcode,
                entity_type=StockBarcodeEntityType.RESOURCE,
                entity_id=row.resource_id,
            )
        row.updated_at = utcnow()
        try:
            return await row.save()
        except UniqueViolationError as exc:
            raise _conflict("Resource code already exists", "resource_conflict") from exc

    async def resource_login(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        resource_id: str | None,
        barcode: str | None,
        user_id: str,
        idempotency_key: str | None = None,
    ) -> StockResource:
        """Начало смены: оператор «садится» на ресурс сканом штрихкода.

        Полосой склада — два оператора одновременно не разделят одну
        машину. Занятая машина → ``resource_occupied``, оператор уже на
        другой технике → ``resource_user_bound``.
        """
        if resource_id is None and barcode is None:
            raise _conflict(
                "Pass resource_id or barcode", "resource_login_input_invalid"
            )
        run = await StockResource.login_in_lane(
            company_id=company_id,
            warehouse_id=warehouse_id,
            resource_id=resource_id,
            barcode=barcode,
            user_id=user_id,
            idempotency_key=command_idempotency_key(idempotency_key),
            command_type="stock/resources/login_requested",
        )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

    async def resource_logout(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        user_id: str,
        idempotency_key: str | None = None,
    ) -> StockResourceLogoutResult:
        """Конец смены: оператор сходит с ресурса (no-op без входа)."""
        run = await StockResource.logout_in_lane(
            company_id=company_id,
            warehouse_id=warehouse_id,
            user_id=user_id,
            idempotency_key=command_idempotency_key(idempotency_key),
            command_type="stock/resources/logout_requested",
        )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

    # --- Контейнеры ---

    async def list_containers(
        self,
        *,
        company_id: str,
        warehouse_id: str | None,
        parent_location_id: str | None,
    ) -> list[StockLocation]:
        return await StockLocation.list_active_containers_by_complete_name_asc(
            company_id,
            warehouse_id=warehouse_id,
            parent_location_id=parent_location_id,
        )

    async def create_container(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        parent_location_id: str,
        container_type_id: str,
        name: str,
        barcode: str | None,
    ) -> StockLocation:
        """Поставить на учёт тару — новую паллету/короб/корзину.

        Контейнер — это локация ``usage=container``: у неё свой адрес
        в дереве, свои остатки, свой штрихкод (SSCC). Ставится либо в
        ячейку («паллета стоит в A-03-02»), либо в другую тару
        («короб на паллете») — тогда тип контейнера обязан быть в
        ``allowed_parent_type_ids`` родителя, иначе
        ``container_parent_denied``.
        """
        _ = await self._require_warehouse(company_id, warehouse_id)
        container_type = await StockContainerType.by_id(company_id, container_type_id)
        if container_type is None or container_type.warehouse_id != warehouse_id:
            raise _not_found("Container type not found", "container_type_not_found")
        parent = await StockLocation.by_id(company_id, parent_location_id)
        if parent is None or parent.warehouse_id != warehouse_id:
            raise _not_found("Parent location not found", "location_not_found")
        if parent.usage not in {
            StockLocationUsage.BIN,
            StockLocationUsage.CONTAINER,
            StockLocationUsage.VIEW,
        }:
            raise _conflict(
                "Container parent must be view/bin/container",
                "location_parent_invalid",
            )
        if (
            parent.usage == StockLocationUsage.CONTAINER
            and container_type.allowed_parent_type_ids
            and parent.container_type_id not in container_type.allowed_parent_type_ids
        ):
            raise _conflict(
                "Container type is not allowed inside this parent",
                "container_parent_denied",
            )
        container = await StockLocation.create_with_parent_path(
            company_id=company_id,
            warehouse_id=warehouse_id,
            parent=parent,
            name=name,
            usage=StockLocationUsage.CONTAINER,
            container_type_id=container_type_id,
        )
        if barcode is not None:
            _ = await self._barcode.register(
                company_id=company_id,
                barcode=barcode,
                entity_type=StockBarcodeEntityType.CONTAINER,
                entity_id=container.location_id,
            )
        return container

    async def container_contents(
        self, *, company_id: str, container_id: str
    ) -> StockContainerContents:
        """Показать содержимое тары — «что на этой паллете».

        Возвращает кванты по локации-контейнеру (товар × партия ×
        владелец с количествами) и вложенные контейнеры — то, что увидит
        оператор, отсканировав SSCC.
        """
        container = await StockLocation.by_id(company_id, container_id)
        if container is None or container.usage != StockLocationUsage.CONTAINER:
            raise _not_found("Container not found", "container_not_found")
        quants = await StockQuant.list_unordered_for_locations(company_id, [container_id])
        children = await StockLocation.list_active_containers_by_complete_name_asc(
            company_id, parent_location_id=container_id
        )
        return StockContainerContents(
            container=container, quants=quants, children=children
        )

    async def move_container(
        self,
        *,
        company_id: str,
        container_id: str,
        dest_location_id: str,
        user_id: str,
        idempotency_key: str | None = None,
    ) -> StockLocation:
        """Переместить тару целиком — «перевези паллету в зону B».

        Физическая операция: контейнер со всем содержимым (и вложенной
        тарой) переподвешивается под новую локацию. Идёт полосой склада:
        одновременно с этим никто не изменит остатки внутри, а проверка
        размещения (тип хранения, ёмкость, смешивание) происходит в той
        же сериализованной транзакции.
        """
        run = await StockMove.move_container_in_lane(
            company_id=company_id,
            container_id=container_id,
            dest_location_id=dest_location_id,
            actor_user_id=user_id,
            idempotency_key=command_idempotency_key(idempotency_key),
            command_type="stock/containers/move_requested",
        )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result
