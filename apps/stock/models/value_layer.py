"""Журнал оценки запасов (stock_value_layers) — «книга проводок» склада.

Каждое движение товара через денежную границу компании оставляет здесь
строку: сколько единиц, по какой себестоимости, на какую сумму изменился
запас. Как в главной книге — записи только добавляются, никогда не
редактируются и не удаляются (append-only): любая ошибка исправляется
новой записью-сторно, чтобы история оставалась проверяемой.

Зачем отдельная таблица, если есть StockQuant: quant отвечает «сколько
лежит сейчас» (снимок), а этот журнал — «как к этому пришли и сколько
это стоит» (история + деньги). Из журнала всегда можно пересчитать
стоимость склада на любую дату и объяснить аудитору каждую копейку.

Пример. Приняли 10 шт по 500 ₽, отгрузили 4 шт (FIFO):

    entry_no  kind      qty   unit_cost  value   qty_after  value_after
    --------  --------  ----  ---------  ------  ---------  -----------
         1    INBOUND   +10      500.00  +5000         10        5000
         2    OUTBOUND   −4      500.00  −2000          6        3000

`qty_after`/`value_after` — накопительный баланс по товару после строки
(running balance per company+product): бухгалтер видит «после этой
проводки на складе 6 шт на 3 000 ₽», а аудит может пройти цепочку
записей и сверить с карточкой.

`remaining_*` на приходных слоях — «сколько ещё не списано» для FIFO:
входящая партия уменьшается по мере отгрузок; расходные слои рождаются
уже «закрытыми» (remaining=0). Развязка «какая отгрузка съела какую
партию» — в StockValueLayerConsumption (out_layer → in_layer, qty, value).

Поле `entry_no` — сквозной номер записи по компании без пропусков
(no-gap через курсор ``stock_ledger`` в ``lane_cursors``, FOR UPDATE строки компании):
гарантия, что порядок проводок в журнале совпадает с порядком коммитов
движков — критично для FIFO и running balance.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.stock.models.common import (
    MONEY_DB,
    QTY_DB,
    STOCK_DB,
    STOCK_ZERO,
    new_id,
    stock_company_lane,
    stock_ledger_cursor,
)
from apps.stock.models.enums import (
    StockLocationUsage,
    StockPartnerRole,
    ValuationMethod,
    ValuationPriceSource,
    ValueEntryKind,
)
from apps.stock.models.events import (
    STOCK_VALUATION_CHANGED,
    StockValuationChangedPayload,
    company_event,
)
from apps.stock.models.value_layer_consumption import StockValueLayerConsumption
from core.errors.boundary import PlatformNotFoundError
from core.lanes import LaneCursor, LaneOutcome, LaneRun, LaneScope, run_in_lanes
from core.models.platform_model import PlatformModel
from core.utils.time import utcnow


class StockValueLayer(PlatformModel):
    """Одна бухгалтерская запись о стоимости запаса. Таблица ``stock_value_layers``.

    Поля, как их читает бухгалтер:

    * ``entry_kind`` — характер операции: ``inbound`` (приход закупки),
      ``outbound`` (расход продажи/возврата поставщику), ``return``
      (возврат от клиента), ``inventory_gain``/``inventory_loss``
      (излишек/недостача инвентаризации), ``revaluation``/``correction``
      (ручные переоценки и сторно).
    * ``quantity`` — знаковое изменение количества (+приход/−расход);
      ``unit_cost`` — себестоимость одной единицы; ``value`` — сумма
      строки (quantity × unit_cost со знаком).
    * ``qty_after`` / ``value_after`` — баланс «после этой записи» по
      товару (см. модульный docstring).
    * ``remaining_quantity`` / ``remaining_value`` — на приходных слоях:
      сколько ещё не выбрано FIFO-отгрузками. Расходные — всегда 0.
    * ``price_source`` — откуда взялась цена: ``document`` (счёт/сделка),
      ``standard``/``average`` (карточка), ``manual`` (руками бухгалтера).
    * ``valuation_method`` — снимок метода карточки на момент записи:
      если завтра метод сменят, старые строки останутся объяснимыми.
    * ``origin_layer_id`` — у коррекций: какую запись исправляем.

    Никаких UPDATE по содержимому записи (кроме ``remaining_*`` — это
    не исправление проводки, а «закрытие» приходной партии при FIFO) и
    никаких DELETE. Ошибка исправляется новой записью со ссылкой
    ``origin_layer_id``.
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
    remaining_quantity: Decimal = DbField(default=STOCK_ZERO, db_type=QTY_DB)
    remaining_value: Decimal = DbField(default=STOCK_ZERO, db_type=MONEY_DB)
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
    async def by_id(cls, company_id: str, layer_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, layer_id=layer_id
        ).get_or_none()

    @classmethod
    async def list_for_product_by_entry_no_asc(
        cls, company_id: str, product_id: str, *, limit: int, offset: int
    ) -> list[Self]:
        """Слои товара, ORDER BY entry_no ASC. limit и offset в теле не проверяются."""
        return await cls.objects.filter(
            company_id=company_id, product_id=product_id
        ).order_by("entry_no").limit(limit).offset(offset).all()

    @classmethod
    async def list_by_entry_no_asc(
        cls,
        company_id: str,
        *,
        product_id: str | None,
        warehouse_id: str | None,
        limit: int,
        offset: int,
    ) -> list[Self]:
        """Окно слоёв компании, ORDER BY entry_no ASC, limit и offset. product_id и warehouse_id равные None не фильтруют."""
        query = cls.objects.filter(company_id=company_id)
        if product_id is not None:
            query = query.filter(product_id=product_id)
        if warehouse_id is not None:
            query = query.filter(warehouse_id=warehouse_id)
        return await query.order_by("entry_no").limit(limit).offset(offset).all()

    @classmethod
    async def count_by_product_and_warehouse(
        cls, company_id: str, *, product_id: str | None, warehouse_id: str | None
    ) -> int:
        """Счёт слоёв компании. product_id и warehouse_id равные None не фильтруют."""
        query = cls.objects.filter(company_id=company_id)
        if product_id is not None:
            query = query.filter(product_id=product_id)
        if warehouse_id is not None:
            query = query.filter(warehouse_id=warehouse_id)
        return await query.count()

    @classmethod
    async def last_for_product_by_entry_no_desc(
        cls, company_id: str, product_id: str
    ) -> Self | None:
        """Последний слой товара, ORDER BY entry_no DESC. Несколько с одним entry_no — какое именно, не задано. Нет строки — None."""
        return await cls.objects.filter(
            company_id=company_id, product_id=product_id
        ).order_by("-entry_no").first()

    @classmethod
    async def list_remaining_by_entry_no_asc_locked(
        cls, company_id: str, product_id: str
    ) -> list[Self]:
        """Открытые слои товара, remaining_quantity > 0, ORDER BY entry_no ASC, под SELECT FOR UPDATE. Два расходных документа в одной полосе не списывают одну партию дважды."""
        return await cls.objects.filter(
            company_id=company_id,
            product_id=product_id,
            remaining_quantity__gt=STOCK_ZERO,
        ).order_by("entry_no").for_update().all()

    @classmethod
    async def write_layer(cls, layer: Self) -> Self:
        return await cls.objects.create(instance=layer)

    # --- Запись журнала: только done-фаза движка и revalue/correction ---

    @classmethod
    async def _origin_unit_cost(
        cls, company_id: str, origin_move_id: str
    ) -> Decimal | None:
        """Себестоимость исходного move — цена для записи возврата.

        Возврат должен «откатить» деньги ровно на столько, на сколько
        ушёл/пришёл исходный товар: продали по себестоимости 525 ₽/шт —
        принимаем обратно по 525 ₽/шт. Поэтому берём Σvalue/Σqty всех
        слоёв исходного движения, а не текущую карточку.

        quantize здесь не только про копейки: деление Decimal может
        вернуть экспоненциальную форму (``Decimal('0E+6')`` при
        нулевой стоимости), которая сериализуется строкой вида
        «0E+6» и ломает NUMERIC-привязку в Postgres.
        """
        from apps.stock.models.valuation import quantize

        rows = await cls.objects.filter(
            company_id=company_id, move_id=origin_move_id
        ).all()
        total_qty = sum((r.quantity for r in rows), STOCK_ZERO)
        total_value = sum((r.value for r in rows), STOCK_ZERO)
        if total_qty == STOCK_ZERO:
            return None
        return quantize(abs(total_value / total_qty))

    @classmethod
    async def exists_for_products(cls, company_id: str, product_ids: list[str]) -> bool:
        if not product_ids:
            return False
        return await cls.objects.filter(
            company_id=company_id, product_id__in=product_ids
        ).exists()

    @classmethod
    async def write_for_done_move(
        cls,
        *,
        company_id: str,
        move_id: str,
        transfer_id: str | None,
        product_id: str,
        returned_move_id: str | None,
        unit_price: Decimal | None,
        location_id: str,
        location_dest_id: str,
        origin_document_type: str | None,
        origin_document_id: str | None,
        done_qty: Decimal,
        valuation_method: ValuationMethod,
        standard_price: Decimal,
        src_usage: StockLocationUsage,
        dst_usage: StockLocationUsage,
        src_partner_role: StockPartnerRole | None = None,
        owner_entity_id: str | None = None,
        warehouse_id: str | None,
        layer_id_factory: Callable[[], str],
        consumption_id_factory: Callable[[], str],
    ) -> list[Self]:
        """Проводки оценки для проведённого движения — внутри той же tx.

        Вызывается шагом ``post_step`` в момент, когда строка переводится
        в done: количество на quant'ах уже изменилось — здесь этому
        физическому факту даём денежную оценку.

        Что НЕ пишет слоёв (деньги не затронуты):
          * товар с методом ``unvalued`` (не оцениваем вообще);
          * перемещение bin→bin / container↔bin (обе стороны наши);
          * partner→partner (внешнее→внешнее, мимо нашего запаса);
          * консигнация (owner_entity_id — товар поставщика у нас на
            ответхранении: полка наша, деньги — нет).

        Остальное — по матрице ``classify_entry``:
          * приход (INBOUND/RETURN/INVENTORY_GAIN): цена из документа,
            иначе карточка; слой рождается «открытым» для FIFO
            (remaining = quantity/value);
          * расход (OUTBOUND/INVENTORY_LOSS): цена по методу карточки —
            FIFO берёт себестоимость старых партий (и пишет развязку
            StockValueLayerConsumption: какая отгрузка съела какой слой),
            AVERAGE — скользящую среднюю, STANDARD — учётную цену;
          * возврат: цена себестоимости исходного move (_origin_unit_cost),
            чтобы деньги «откатились» ровно на ту же сумму.
        """
        from apps.stock.models.valuation import (
            classify_entry,
            fifo_allocate,
            fifo_cost_of,
            inbound_unit_cost,
            quantize,
        )

        method = valuation_method
        if method == ValuationMethod.UNVALUED or done_qty <= STOCK_ZERO:
            return []
        is_return = returned_move_id is not None
        kinds = classify_entry(
            src_usage,
            dst_usage,
            is_return=is_return,
            src_partner_role=src_partner_role,
            owner_entity_id=owner_entity_id,
        )
        if not kinds:
            return []
        # Курсор журнала блокируется до чтения баланса и FIFO-потребления:
        # писатель ждёт предыдущего commit на строке компании и видит его слои.
        entry_no = (
            await LaneCursor.next_seq(
                [stock_ledger_cursor(company_id)],
                company_id=company_id,
                using=STOCK_DB,
                count=len(kinds),
            )
        )[stock_ledger_cursor(company_id)]
        last = await cls.last_for_product_by_entry_no_desc(company_id, product_id)
        qty_balance = last.qty_after if last is not None else STOCK_ZERO
        value_balance = last.value_after if last is not None else STOCK_ZERO

        inbound_cost: Decimal | None = None
        inbound_source = ValuationPriceSource.STANDARD
        origin_cost: Decimal | None = None
        if returned_move_id is not None:
            origin = await cls._origin_unit_cost(company_id, returned_move_id)
            if origin is not None:
                origin_cost = origin
                inbound_cost = origin
                inbound_source = ValuationPriceSource.DOCUMENT
        if inbound_cost is None:
            inbound_cost, inbound_source = inbound_unit_cost(
                unit_price, method, standard_price
            )

        avg_cost = (
            quantize(value_balance / qty_balance)
            if qty_balance > STOCK_ZERO
            else standard_price
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
        fifo_value = STOCK_ZERO
        fifo_unit = STOCK_ZERO
        if method == ValuationMethod.FIFO and has_outgoing:
            remaining_layers = await cls.list_remaining_by_entry_no_asc_locked(company_id, product_id)
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
            cost = standard_price
            return quantize(cost * done_qty), cost, ValuationPriceSource.STANDARD

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
                remaining_qty = STOCK_ZERO
                remaining_val = STOCK_ZERO
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
                move_id=move_id,
                transfer_id=transfer_id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                location_id=location_id,
                location_dest_id=location_dest_id,
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
                origin_document_type=origin_document_type,
                origin_document_id=origin_document_id,
                created_at=now,
            )
            _ = await cls.objects.create(instance=layer)
            written.append(layer)
        if method == ValuationMethod.FIFO and fifo_plan:
            out_layer = next(
                (layer for layer in written if layer.quantity < STOCK_ZERO), None
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
        valuation_method: ValuationMethod,
        layer_id_factory: Callable[[], str],
    ) -> Self:
        """Ручная бухгалтерская запись: переоценка или сторно.

        Два вида ручных записей (обе — ``price_source=manual``):
          * ``revaluation`` — переоценка запаса: количество то же, меняем
            только сумму (например уценка просроченного товара −3 000 ₽
            → ``value_delta=-3000``, ``quantity_delta=0``).
          * ``correction`` — исправление конкретной ошибочной записи:
            ссылка ``origin_layer_id`` обязательна, чтобы аудитор видел,
            что именно сторнируем.

        Записи идут в общую no-gap нумерацию и running balance —
        «ручная» проводка выглядит в журнале так же, как документная.
        Транзакции нет — вызывается внутри lane-транзакции
        ``adjust_in_lane``.
        """
        if entry_kind not in {
            ValueEntryKind.REVALUATION,
            ValueEntryKind.CORRECTION,
        }:
            raise ValueError(f"Adjustment kind must be revaluation|correction, got {entry_kind}")
        entry_no = (
            await LaneCursor.next_seq(
                [stock_ledger_cursor(company_id)],
                company_id=company_id,
                using=STOCK_DB,
            )
        )[stock_ledger_cursor(company_id)]
        last = await cls.last_for_product_by_entry_no_desc(company_id, product_id)
        qty_balance = (last.qty_after if last is not None else STOCK_ZERO) + quantity_delta
        value_balance = (last.value_after if last is not None else STOCK_ZERO) + value_delta
        layer = cls(
            layer_id=layer_id_factory(),
            company_id=company_id,
            entry_no=entry_no,
            product_id=product_id,
            location_id=None,
            location_dest_id=None,
            entry_kind=entry_kind,
            quantity=quantity_delta,
            unit_cost=STOCK_ZERO,
            value=value_delta,
            remaining_quantity=STOCK_ZERO,
            remaining_value=STOCK_ZERO,
            qty_after=qty_balance,
            value_after=value_balance,
            price_source=ValuationPriceSource.MANUAL,
            valuation_method=valuation_method,
            origin_layer_id=origin_layer_id,
            description=description,
            created_at=utcnow(),
        )
        return await cls.objects.create(instance=layer)

    @classmethod
    async def adjust_in_lane(
        cls,
        *,
        company_id: str,
        product_id: str,
        entry_kind: ValueEntryKind,
        value_delta: Decimal,
        quantity_delta: Decimal,
        description: str,
        origin_layer_id: str | None,
        valuation_method: ValuationMethod,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
        causation_id: str | None = None,
    ) -> LaneRun[Self]:
        """Команда «внести бухгалтерскую поправку» — полоса компании.

        Ручные проводки (переоценка/сторно) не привязаны к складу —
        поэтому сериализуются полосой компании ``stock_company:<id>:ledger``,
        а не полосой склада. Событие ``stock/valuation/changed`` публикуется
        из LaneCommit после коммита.

        ``valuation_method`` — снимок метода карточки, прочитанный
        вызывающим до входа в полосу; ``origin_layer_id`` для
        ``correction`` проверяется уже внутри транзакции (слой должен
        существовать — иначе layer_not_found).
        """

        async def body(_: LaneScope) -> LaneOutcome[Self]:
            if entry_kind == ValueEntryKind.CORRECTION:
                if origin_layer_id is None:
                    raise ValueError("correction requires origin_layer_id")
                origin = await cls.by_id(company_id, origin_layer_id)
                if origin is None:
                    raise PlatformNotFoundError(
                        "Origin layer not found", error_code="layer_not_found"
                    )
            layer = await cls.write_adjustment(
                company_id=company_id,
                product_id=product_id,
                entry_kind=entry_kind,
                value_delta=value_delta,
                quantity_delta=quantity_delta,
                description=description,
                origin_layer_id=origin_layer_id,
                valuation_method=valuation_method,
                layer_id_factory=lambda: new_id("svl"),
            )
            event = company_event(
                STOCK_VALUATION_CHANGED,
                StockValuationChangedPayload(
                    company_id=company_id,
                    product_id=layer.product_id,
                    layer_id=layer.layer_id,
                    entry_no=layer.entry_no,
                    entry_kind=layer.entry_kind,
                    quantity=layer.quantity,
                    value=layer.value,
                    qty_after=layer.qty_after,
                    value_after=layer.value_after,
                    origin_layer_id=layer.origin_layer_id,
                ),
                company_id=company_id,
                actor_user_id=actor_user_id,
                causation_id=causation_id,
            )
            return LaneOutcome(result=layer, events=[event])

        return await run_in_lanes(
            [stock_company_lane(company_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            result_type=cls,
            body=body,
        )
