"""Таблица склада (stock_quants) — материализованная проекция остатков.

Это единственная таблица, которая отвечает на вопрос «сколько товара
сейчас лежит в этой ячейке». Она не является источником истины сама по
себе: истина — журнал StockMove (каждое движение), а quant — быстрая
проекция «итог по каждой ячейке», которую движок поддерживает в той же
транзакции, что и само движение.

Аналогия для бухгалтера: если StockMove — это книга складских ордеров
(каждая запись — факт «принял/отдал/переложил»), то stock_quants — это
оборотная ведомость по ячейкам: по одной строке на «товар × ячейка ×
партия × владелец» видно остаток на любой момент без перечитывания всех
ордеров.

Математика остатка:

    quantity          — физически присутствует в ячейке (посчитано руками
                        или подтверждено документами)
    reserved_quantity — обещано другим документам, ещё не выдало со склада
    available = quantity - reserved_quantity — можно обещать новым заказам

Пример жизни строки (приёмка 10 шт по ордеру, потом продажа 4 шт):

    Событие                       quantity  reserved  available
    --------------------------    --------  --------  ---------
    приёмка подтверждена (done)        10        0        10
    заказ зарезервировал 4 шт          10        4         6
    отгрузка проведена (done)           6        0         6

Инварианты:
    * quantity и reserved_quantity меняются только внутри lane-транзакции
      (методы post_step/reserve_step/release_step на StockMove) — два
      конкурирующих документа не «раздерут» один и тот же остаток.
    * Строка quant существует только на «оцениваемых» локациях
      (STOCK_QUANT_USAGES = bin/container/transit). На виртуальных
      локациях (поставщик, клиент, инвентаризация) остатка нет — это
      концы движения, а не полки.
    * Отрицательный quantity запрещён по умолчанию (insufficient_stock);
      локация может явно разрешить минус флагом allow_negative
      (напр. зона инвентаризации, чтобы списать «лишнее» обнаруженное
      физически отсутствие).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index
from oxyde.exceptions import UniqueViolationError

from apps.stock.models.common import (
    QTY_DB,
    STOCK_DB,
    STOCK_ZERO,
    stock_command_lane,
)
from apps.stock.models.location import StockLocation
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.lanes import LaneOutcome, LaneRun, LaneScope, run_in_lanes
from core.models.platform_model import PlatformModel
from core.utils.time import utcnow


class StockQuant(PlatformModel):
    """Строка остатка «товар × ячейка × партия × владелец». Таблица ``stock_quants``.

    Уникальный ключ — (company_id, product_id, location_id, lot_id,
    owner_entity_id) с ``NULLS NOT DISTINCT``: «без партии» и «без владельца»
    — тоже значения ключа, дублей строки на одну ячейку быть не может.

    Роль полей для читателя-непрограммиста:

    * ``location_id`` — ячейка или контейнер (контейнер — это локация
      ``usage=container``, т.е. «паллета» сама может нести остаток).
    * ``lot_id`` — партия/серийник; без неё — обычный товар без трекинга.
    * ``owner_entity_id`` — владелец консигнационного запаса (CRM-сущность
      поставщика); ``NULL`` — товар наш, оценивается.
    * ``warehouse_id``, ``removal_at`` — денормализованные копии склада
      локации и даты отбора партии (чтобы отчёты и FEFO не джойнили
      справочники).
    * ``in_date`` — момент первого появления строки: основа FIFO
      (раньше пришло — раньше уйдёт).
    * ``inventory_*`` — черновик инвентаризации, ничего не двигает до
      приказа ``inventory_apply``.

    Писатель один — движок леджера внутри полосы склада:
    ``reserved_quantity`` крутится шагами reserve/release, ``quantity`` —
    только шагом done-постинга. См. модульный docstring сверху за
    таблицей-примером.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_quants"
        indexes: list[Index] = [
            Index(["company_id", "product_id", "location_id"]),
            Index(["company_id", "location_id", "in_date"]),
            Index(["company_id", "warehouse_id", "product_id"]),
        ]

    quant_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str | None = DbField(default=None, max_length=64)
    """Денормализация склада локации — фильтры и FEFO без join локаций."""
    product_id: str = DbField(max_length=64)
    location_id: str = DbField(max_length=64)
    lot_id: str | None = DbField(default=None, max_length=64)
    owner_entity_id: str | None = DbField(default=None, max_length=64)
    quantity: Decimal = DbField(default=STOCK_ZERO, db_type=QTY_DB)
    reserved_quantity: Decimal = DbField(default=STOCK_ZERO, db_type=QTY_DB)
    inventory_quantity: Decimal | None = DbField(default=None, db_type=QTY_DB)
    inventory_counted_at: datetime | None = DbField(default=None)
    inventory_user_id: str | None = DbField(default=None, max_length=64)
    removal_at: datetime | None = DbField(default=None)
    """Дата отбора партии (FEFO) — денормализация `StockLot.removal_at`."""
    in_date: datetime = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @property
    def available_quantity(self) -> Decimal:
        """Свободный остаток, который можно обещать новым документам.

        ``available = quantity - reserved_quantity``. Пример: на полке
        10 шт, под заказ №5 зарезервировано 4 → доступно 6. Отгрузка
        заказа №5 спишет сначала резерв (4 шт уйдут «из-под заказа»),
        остальное — из доступного.
        """
        return self.quantity - self.reserved_quantity

    @classmethod
    async def by_id(cls, company_id: str, quant_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, quant_id=quant_id
        ).get_or_none()

    @classmethod
    async def by_id_locked(cls, company_id: str, quant_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, quant_id=quant_id
        ).for_update().get_or_none()

    @classmethod
    async def by_key_locked(
        cls,
        *,
        company_id: str,
        product_id: str,
        location_id: str,
        lot_id: str | None,
        owner_entity_id: str | None,
    ) -> Self | None:
        """Чтение строки под ``SELECT FOR UPDATE`` — перед любой записью.

        Блокировка строки гарантирует, что два документа в одной lane
        (один склад = одна полоса) не будут одновременно считать, что
        «свободно 6 шт», и не распределят их дважды.
        """
        return await cls.objects.filter(
            company_id=company_id,
            product_id=product_id,
            location_id=location_id,
            lot_id=lot_id,
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
        owner_entity_id: str | None,
    ) -> Self | None:
        """Неблокирующий lookup по составному ключу (для чтения после commit)."""
        return await cls.objects.filter(
            company_id=company_id,
            product_id=product_id,
            location_id=location_id,
            lot_id=lot_id,
            owner_entity_id=owner_entity_id,
        ).get_or_none()

    @classmethod
    async def ensure_locked(
        cls,
        *,
        company_id: str,
        product_id: str,
        location_id: str,
        lot_id: str | None,
        owner_entity_id: str | None,
        warehouse_id: str | None,
        removal_at: datetime | None = None,
        quant_id: str,
    ) -> Self:
        """Строка под ``FOR UPDATE``; отсутствующая создаётся нулевой.

        Бизнес-смысл: «ячейка впервые увидела этот товар» — заводим
        чистую строку остатка (quantity=0, reserved=0, in_date=сейчас),
        чтобы дальше её наполнить done-постингом. Гонка создания
        ловится UniqueViolationError → возвращаем уже созданную строку.
        """
        found = await cls.by_key_locked(
            company_id=company_id,
            product_id=product_id,
            location_id=location_id,
            lot_id=lot_id,
            owner_entity_id=owner_entity_id,
        )
        if found is not None:
            return found
        now = utcnow()
        quant = cls(
            quant_id=quant_id,
            company_id=company_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            location_id=location_id,
            lot_id=lot_id,
            owner_entity_id=owner_entity_id,
            quantity=STOCK_ZERO,
            reserved_quantity=STOCK_ZERO,
            removal_at=removal_at,
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
                owner_entity_id=owner_entity_id,
            )
            if raced is None:
                raise
            return raced

    @classmethod
    async def list_available_by_in_date_and_quant_id_asc_locked(
        cls,
        *,
        company_id: str,
        product_id: str,
        location_ids: list[str],
        owner_entity_id: str | None,
    ) -> list[Self]:
        """Доступные остатки, ORDER BY in_date, quant_id ASC, под SELECT FOR UPDATE. Пустой location_ids — []. owner_entity_id is None оставляет строки без владельца. available_quantity > 0 отсекается в Python."""
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
        return [row for row in rows if row.available_quantity > STOCK_ZERO]

    @classmethod
    async def list_by_product_and_location_asc(
        cls,
        company_id: str,
        *,
        location_id: str | None,
        product_id: str | None,
        owner_entity_id: str | None = None,
        limit: int,
        offset: int,
    ) -> list[Self]:
        """Окно остатков компании, ORDER BY product_id, location_id ASC. location_id, product_id и owner_entity_id равные None не фильтруют."""
        query = cls.objects.filter(company_id=company_id)
        if location_id is not None:
            query = query.filter(location_id=location_id)
        if product_id is not None:
            query = query.filter(product_id=product_id)
        if owner_entity_id is not None:
            query = query.filter(owner_entity_id=owner_entity_id)
        return await query.order_by("product_id", "location_id").limit(limit).offset(
            offset
        ).all()

    @classmethod
    async def count_by_location_product_and_owner(
        cls,
        company_id: str,
        *,
        location_id: str | None,
        product_id: str | None,
        owner_entity_id: str | None = None,
    ) -> int:
        """Счёт остатков компании. location_id, product_id и owner_entity_id равные None не фильтруют."""
        query = cls.objects.filter(company_id=company_id)
        if location_id is not None:
            query = query.filter(location_id=location_id)
        if product_id is not None:
            query = query.filter(product_id=product_id)
        if owner_entity_id is not None:
            query = query.filter(owner_entity_id=owner_entity_id)
        return await query.count()

    @classmethod
    async def list_unordered_for_warehouse(
        cls, company_id: str, warehouse_id: str
    ) -> list[Self]:
        """Все остатки склада. Порядка и limit нет."""
        return await cls.objects.filter(
            company_id=company_id, warehouse_id=warehouse_id
        ).all()

    @classmethod
    async def list_unordered_for_locations(
        cls, company_id: str, location_ids: list[str], *, for_update: bool = False
    ) -> list[Self]:
        """Остатки в этих локациях. Пустой location_ids — []. Порядка нет. for_update=True блокирует строки."""
        if not location_ids:
            return []
        query = cls.objects.filter(
            company_id=company_id, location_id__in=location_ids
        )
        if for_update:
            query = query.for_update()
        return await query.all()

    @classmethod
    async def update_inventory_quantity_counted_at_and_user(
        cls,
        quant_id: str,
        inventory_quantity: Decimal | None,
        counted_at: datetime | None = None,
        user_id: str | None = None,
    ) -> None:
        """Пишет черновик подсчёта: inventory_quantity, inventory_counted_at, inventory_user_id и updated_at. None тоже записывается. Книжный quantity не меняется. Нет строки — ничего не меняет."""
        _ = await cls.objects.filter(quant_id=quant_id).update(
            using=STOCK_DB,
            inventory_quantity=inventory_quantity,
            inventory_counted_at=counted_at,
            inventory_user_id=user_id,
            updated_at=utcnow(),
        )

    @classmethod
    async def sum_quantity_for_lot(cls, company_id: str, lot_id: str) -> Decimal:
        """Σ quantity по партии/серийнику — инвариант `serial ≤ 1` под блоком."""
        rows = await cls.objects.filter(
            company_id=company_id, lot_id=lot_id
        ).all()
        return sum((row.quantity for row in rows), STOCK_ZERO)

    @classmethod
    async def rebind_warehouse(
        cls, company_id: str, location_ids: list[str], warehouse_id: str | None
    ) -> None:
        """Денормализованный `warehouse_id` поддерева после перемещения контейнера."""
        if not location_ids:
            return
        _ = await cls.objects.filter(
            company_id=company_id, location_id__in=location_ids
        ).update(using=STOCK_DB, warehouse_id=warehouse_id, updated_at=utcnow())

    # --- Команды леджера: граница транзакции = полоса ---

    @classmethod
    async def update_inventory_quantity_in_lane(
        cls,
        *,
        company_id: str,
        quant_id: str,
        warehouse_id: str | None,
        inventory_quantity: Decimal,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
    ) -> LaneRun[Self]:
        """Пишет черновик inventory_quantity в полосе склада и отмечает last_count локации. Книжный quantity не меняется. Нет остатка — PlatformNotFoundError. Количество < 0 — PlatformConflictError. Возвращает LaneRun."""

        async def body(_scope: LaneScope) -> LaneOutcome[Self]:
            quant = await cls.by_id_locked(company_id, quant_id)
            if quant is None:
                raise PlatformNotFoundError(
                    "Quant not found", error_code="quant_not_found"
                )
            if inventory_quantity < STOCK_ZERO:
                raise PlatformConflictError(
                    "Inventory quantity must be >= 0",
                    error_code="inventory_qty_invalid",
                )
            now = utcnow()
            await cls.update_inventory_quantity_counted_at_and_user(
                quant_id, inventory_quantity, counted_at=now, user_id=actor_user_id
            )
            await StockLocation.touch_counted(
                company_id, [quant.location_id], at=now
            )
            quant.inventory_quantity = inventory_quantity
            quant.inventory_counted_at = now
            quant.inventory_user_id = actor_user_id
            return LaneOutcome(result=quant, events=[])

        return await run_in_lanes(
            [stock_command_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            result_type=cls,
            body=body,
        )
