"""Стратегии отбора (removal) — «из какой ячейки брать товар первым».

Чистые функции без IO: получают уже прочитанные и заблокированные
``StockQuant``-кандидатов плюс карточки их локаций и возвращают
упорядоченный список. Вызываются из ``reserve_step`` внутри полосы
склада — порядок выбора не меняет данные, только очередь обхода.

Бизнес-стратегии (``StockRemovalStrategy``):

* ``fifo`` — «первым пришёл, первым ушёл»: по ``in_date`` остатка.
  Списываем самое старое поступление — стандарт для непортящегося
  товара и для FIFO-оценки;
* ``fefo`` — «первым истекает, первым ушёл»: по ``removal_at``
  партии (срок годности). Партии без срока — в конец очереди;
* ``lifo`` — «последним пришёл, первым ушёл»: свежие остатки
  первыми (для товара без старения — меньше лазить по складу);
* ``closest`` — по ``pick_sequence`` ячейки: ближайшая к точке
  отбора первая (минимум пути кладовщика);
* ``least_containers`` — предпочитаем целую тару: если остаток
  лежит на контейнере и его хватает на всю потребность — отгружаем
  паллету целиком одной строкой ``kind=container`` вместо перебора
  поштучно.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from apps.stock.models.enums import StockLocationUsage, StockRemovalStrategy


@dataclass(frozen=True)
class RemovalBin:
    """Минимум о локации-кандидате для упорядочивания отбора."""

    usage: StockLocationUsage
    pick_sequence: int


class QuantLike(Protocol):
    """Контракт остатка для стратегий отбора (model или test double)."""

    @property
    def quant_id(self) -> str: ...
    @property
    def location_id(self) -> str: ...
    @property
    def product_id(self) -> str: ...
    @property
    def owner_entity_id(self) -> str | None: ...
    @property
    def lot_id(self) -> str | None: ...
    @property
    def quantity(self) -> Decimal: ...
    @property
    def reserved_quantity(self) -> Decimal: ...
    @property
    def available_quantity(self) -> Decimal: ...
    @property
    def in_date(self) -> datetime | None: ...
    @property
    def removal_at(self) -> datetime | None: ...


def _by_in_date(quant: QuantLike) -> tuple[datetime, str]:
    return (quant.in_date or datetime.max, quant.quant_id)


def order_candidates[Q: QuantLike](
    candidates: list[Q],
    *,
    strategy: StockRemovalStrategy,
    needed: Decimal,
    locations: dict[str, RemovalBin],
) -> list[Q]:
    """Упорядочить остатки по стратегии отбора.

    ``needed`` нужен ``least_containers``: контейнер покрывает заказ
    целиком → идёт первым (самый маленький достаточный — не берём
    паллету на 1000, когда хватает короба на 10).

    ``locations`` — карта ``location_id → RemovalBin``; кандидат без
    карточки получает ``pick_sequence`` = бесконечность.
    """
    bins = locations

    def pick_seq(quant: Q) -> int:
        meta = bins.get(quant.location_id)
        return meta.pick_sequence if meta is not None else 1 << 30

    def is_container(quant: Q) -> bool:
        meta = bins.get(quant.location_id)
        return (
            meta is not None and meta.usage == StockLocationUsage.CONTAINER
        )

    if strategy == StockRemovalStrategy.LIFO:
        return sorted(
            candidates,
            key=lambda q: (q.in_date or datetime.min, q.quant_id),
            reverse=True,
        )
    if strategy == StockRemovalStrategy.FEFO:
        return sorted(
            candidates,
            key=lambda q: (
                q.removal_at is None,
                q.removal_at or q.in_date or datetime.max,
                q.quant_id,
            ),
        )
    if strategy == StockRemovalStrategy.CLOSEST:
        return sorted(
            candidates,
            key=lambda q: (pick_seq(q), _by_in_date(q)),
        )
    if strategy == StockRemovalStrategy.LEAST_CONTAINERS:
        covering = [
            q
            for q in candidates
            if is_container(q) and q.available_quantity >= needed
        ]
        covering.sort(key=lambda q: (q.available_quantity, _by_in_date(q)))
        rest = [q for q in candidates if q not in covering]
        rest.sort(key=_by_in_date)
        return covering + rest
    return sorted(candidates, key=_by_in_date)


def container_exact_cover[Q: QuantLike](
    inside: list[Q],
    *,
    product_id: str,
    owner_entity_id: str | None,
    needed: Decimal,
) -> Decimal | None:
    """Паллета «под заказ целиком» — проверка по всему содержимому.

    Контейнер отгружается одной строкой ``kind=container`` только если:

    * все остатки внутри — это товар строки (``product_id``) того же
      владельца (``owner_entity_id``) — смешанную паллету нельзя
      молча увезти «под чужой заказ»;
    * внутри нет чужих резервов (``reserved_quantity == 0`` у всех
      непустых остатков) — отгрузка чужого резерва крадёт чужой заказ;
    * суммарное количество покрывает потребность (``>= needed``);
      излишек — осознанная переотгрузка, проводится done-фактом.

    Возвращает физически отгружаемое количество (сумму содержимого)
    или ``None``, если контейнер «грязный»/не покрывает заказ.
    """
    holding = [q for q in inside if q.quantity > 0 or q.reserved_quantity > 0]
    if not holding:
        return None
    if any(
        q.product_id != product_id or q.owner_entity_id != owner_entity_id
        for q in holding
    ):
        return None
    if any(q.reserved_quantity > 0 for q in holding):
        return None
    total = sum((q.quantity for q in holding), Decimal("0"))
    return total if total >= needed else None
