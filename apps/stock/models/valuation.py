"""Чистая математика оценки запасов — решение «сколько стоит эта операция».

Этот модуль отвечает на вопрос бухгалтера «по какой цене ставить на склад
и по какой списывать» — без SQL, на числах.

Главная идея: **деньги меняются только на границе «мы ↔ внешний мир»**.
Переложение между своими ячейками стоимость не меняет — товар тот же,
мы просто передвинули его по полкам.

Оцениваемые локации (`STOCK_QUANT_USAGES`): ``bin``, ``container``,
``transit`` — это физический запас, который стоит денег.
Внешние (неоцениваемые): ``partner`` (поставщик/клиент/подрядчик),
``adjustment`` (виртуальная локация инвентаризации) — туда «уходит» и
«откуда приходит» товар, но это не наши полки, а бухгалтерская граница.

Таблица решений (что пишется в журнал stock_value_layers):

    Переход                          Хозоперация      Слой
    -------------------------------  ---------------  ------------------
    partner(vendor) → bin            Приход закупки   INBOUND  +qty, +value
    bin → partner(customer)          Отгрузка продажи OUTBOUND −qty, −value
    bin → adjustment                 Недостача        INVENTORY_LOSS −qty,−value
    adjustment → bin                 Излишек           INVENTORY_GAIN +qty,+value
    partner(customer)→bin (return)   Возврат клиента  RETURN   +qty,+value
    bin → partner(vendor) (return)   Возврат пост-щику OUTBOUND −qty,−value
    bin → bin / container ↔ bin      Перемещение      — (ничего не пишем)
    consignment (owner_entity_id)    Ответхранение     — (не наш товар)

Стоимость единицы по методу оценки (`ValuationMethod` на карточке):
    * standard   — фиксированная учётная цена из карточки (standard_price)
    * average    — скользящая средняя: (остаток по сумме) / (остаток по кол-ву)
    * fifo       — реальная себестоимость партий: списываем «самую старую»
                   недопотреблённую часть слоёв (см. fifo_allocate)
    * unvalued   — товар без оценки (материалы, услуги): слоёв нет вообще
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import ROUND_HALF_UP, Decimal

from apps.stock.models.enums import (
    STOCK_QUANT_USAGES,
    StockLocationUsage,
    StockPartnerRole,
    ValuationMethod,
    ValuationPriceSource,
    ValueEntryKind,
)

_Q = Decimal("0.000001")


def quantize(value: Decimal) -> Decimal:
    """Округление денег до 6 знаков (банковское правило half-up)."""
    return value.quantize(_Q, rounding=ROUND_HALF_UP)


def classify_entry(
    src_usage: StockLocationUsage,
    dst_usage: StockLocationUsage,
    *,
    is_return: bool,
    src_partner_role: StockPartnerRole | None = None,
    owner_entity_id: str | None = None,
) -> list[ValueEntryKind]:
    """Решает, какую бухгалтерскую запись делать для данного движения.

    Смотрим только на «тип» локаций (usage) концов движения, не на их
    имена. Логика «как для проводок в бухучёте»: приход/расход через
    границу с внешним миром — деньги меняются; внутреннее перемещение —
    нет.

    Правила по порядку:

    1. **Консигнация** (owner_entity_id задан): товар чужой, мы его
       только храним — денег нет, возвращаем [].
    2. **Обе стороны оцениваемые или обе внешние** (bin→bin, partner→partner):
       границы нет, стоимость не меняется — возвращаем [].
    3. **Приход на склад** (внешняя → оцениваемая):
         * из adjustment → INVENTORY_GAIN (излишек после инвентаризации)
         * возврат от клиента (is_return или partner_role=customer) →
           RETURN — ценим по себестоимости исходной отгрузки
         * иначе → INBOUND (закупка)
    4. **Расход со склада** (оцениваемая → внешняя):
         * в adjustment → INVENTORY_LOSS (недостача)
         * иначе → OUTBOUND (продажа или возврат поставщику —
           оба списывают по себестоимости)

    Пример: приёмка «поставщик → ячейка A-01» — это INBOUND: в журнал
    пишем +10 шт по цене заказа. Отгрузка «A-01 → клиент» — OUTBOUND:
    −10 шт по себестоимости (FIFO/среднему/стандарту карточки).
    """
    if owner_entity_id is not None:
        return []
    src_valued = src_usage in STOCK_QUANT_USAGES
    dst_valued = dst_usage in STOCK_QUANT_USAGES
    if src_valued == dst_valued:
        return []
    if dst_valued:
        if src_usage == StockLocationUsage.ADJUSTMENT:
            return [ValueEntryKind.INVENTORY_GAIN]
        if is_return or src_partner_role == StockPartnerRole.CUSTOMER:
            return [ValueEntryKind.RETURN]
        return [ValueEntryKind.INBOUND]
    if dst_usage == StockLocationUsage.ADJUSTMENT:
        return [ValueEntryKind.INVENTORY_LOSS]
    # Исходящий возврат поставщику — тот же расход по стоимости origin.
    return [ValueEntryKind.OUTBOUND]


def inbound_unit_cost(
    unit_price: Decimal | None,
    method: ValuationMethod,
    standard_price: Decimal,
) -> tuple[Decimal, ValuationPriceSource]:
    """Цена одной единицы прихода и откуда она взялась (price_source).

    Порядок выбора — как в первичке:
      1. ``unit_price`` с документа (поставщик выставил счёт 500 ₽/шт) —
         DOCUMENT: цена реальной сделки, самый точный источник.
      2. Если цены в документе нет — учётная из карточки товара:
         метод AVERAGE → текущая средняя; STANDARD → фиксированная
         standard_price. Источники AVERAGE/STANDARD помечают «взято
         из справочника, не из счёта».
    """
    if unit_price is not None:
        return unit_price, ValuationPriceSource.DOCUMENT
    if method == ValuationMethod.AVERAGE:
        return standard_price, ValuationPriceSource.AVERAGE
    return standard_price, ValuationPriceSource.STANDARD


def fifo_allocate[T](
    layers: Sequence[T],
    quantity: Decimal,
    *,
    remaining_of: Callable[[T], Decimal],
) -> list[tuple[T, Decimal]]:
    """План списания по FIFO: какие партии и сколько из каждой берём.

    «Первым пришёл — первым ушёл»: идём по открытым приходным слоям
    (remaining > 0) от старшего к младшему и отрезаем куски, пока не
    наберём нужное количество.

    Пример. На складе:
        слой №1: пришло 10 шт, осталось 6 шт   (самый старый)
        слой №2: пришло 20 шт, осталось 20 шт
    Отгрузка 8 шт → план: [(слой №1, 6), (слой №2, 2)].
    Слой №1 закрывается полностью, у слоя №2 остаётся 18.
    """
    plan: list[tuple[T, Decimal]] = []
    rest = quantity
    for layer in layers:
        if rest <= Decimal("0"):
            break
        take = min(remaining_of(layer), rest)
        if take > Decimal("0"):
            plan.append((layer, take))
            rest -= take
    return plan


def fifo_cost_of[T](
    layers: Sequence[T],
    quantity: Decimal,
    *,
    remaining_of: Callable[[T], Decimal],
    cost_of: Callable[[T], Decimal],
) -> tuple[Decimal, Decimal]:
    """Сумма и цена единицы отгрузки по FIFO-плану.

    Возвращает ``(value, unit_cost)``: общую себестоимость списанного и
    среднюю цену единицы (value/quantity) для записи в слой OUTBOUND.

    Пример из fifo_allocate (6 шт по 500 ₽ + 2 шт по 600 ₽):
        value      = 6*500 + 2*600 = 4 200 ₽
        unit_cost  = 4 200 / 8 = 525 ₽/шт  — «смешанная» себестоимость

    Если списываем больше, чем сумма остатков слоёв (остаток склада
    отрицательный по allow_negative), «непокрытая» часть ценится по цене
    последнего слоя — чтобы у отгрузки была осмысленная себестоимость.
    """
    plan = fifo_allocate(layers, quantity, remaining_of=remaining_of)
    covered = sum((take for _, take in plan), Decimal("0"))
    value = sum((quantize(cost_of(layer) * take) for layer, take in plan), Decimal("0"))
    uncovered = quantity - covered
    if uncovered > Decimal("0") and plan:
        last_cost = cost_of(plan[-1][0])
        value += quantize(last_cost * uncovered)
    unit = value / quantity if quantity > Decimal("0") else Decimal("0")
    return value, quantize(unit)
