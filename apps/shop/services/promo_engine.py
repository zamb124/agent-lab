"""Движок акций — детерминированный расчёт скидок корзины.

Один вход → один выход: промо сортируются по ``priority``/``sort``, каждая
единица корзины участвует максимум в одном бандле (bundle locking,
паттерн FrontOrbit), ``exclusive``-акция закрывает остальные.

Применение идентично для preview (``/cart/price``) и авторитетного
расчёта в ``create_order`` — один движок, два входа.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from apps.shop.models.enums import PromoStacking
from apps.shop.models.promo import ShopPromo
from core.types import JsonObject, JsonValue


def _as_int(v: object) -> int:
    """Число из JSON-значения с безопасным нулём по умолчанию."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            return 0
    return 0


@dataclass
class CartLine:
    """Входная строка корзины (уже с модификаторами в unit_minor)."""

    product_id: str
    category_id: str | None
    qty: int
    unit_minor: int


@dataclass
class _Unit:
    line_idx: int
    product_id: str
    category_id: str | None
    unit_minor: int
    locked: bool = False


@dataclass(frozen=True)
class AppliedPromo:
    promo_id: str
    name: str
    saved_minor: int


@dataclass
class PricedCart:
    """Итог расчёта: скидки по строкам, order-скидка, доставка, применённые."""

    line_discounts: list[int]
    order_discount_minor: int = 0
    delivery_discount_minor: int = 0
    applied: list[AppliedPromo] = field(default_factory=list)


def _window_active(window: JsonObject, now: datetime) -> bool:
    """Окно активности: даты ISO, weekdays (0=Пн), time_from/to «HH:MM»."""
    if not window:
        return True
    starts = window.get("starts_at")
    if isinstance(starts, str) and starts:
        if now < datetime.fromisoformat(starts):
            return False
    ends = window.get("ends_at")
    if isinstance(ends, str) and ends:
        if now > datetime.fromisoformat(ends):
            return False
    weekdays = window.get("weekdays")
    if isinstance(weekdays, list) and weekdays:
        if now.weekday() not in [_as_int(d) for d in weekdays]:
            return False
    time_from = window.get("time_from")
    time_to = window.get("time_to")
    if isinstance(time_from, str) and isinstance(time_to, str) and time_from and time_to:
        hm = now.hour * 60 + now.minute
        f = int(time_from.split(":")[0]) * 60 + int(time_from.split(":")[1])
        t = int(time_to.split(":")[0]) * 60 + int(time_to.split(":")[1])
        if f <= t:
            if not (f <= hm < t):
                return False
        elif not (hm >= f or hm < t):
            return False
    return True


def _scope(units: list[_Unit], product_ids: JsonValue) -> list[_Unit]:
    """Свободные юниты, отфильтрованные по product_ids (None/пусто = все)."""
    free = [u for u in units if not u.locked]
    if isinstance(product_ids, list) and product_ids:
        ids: set[str] = set()
        for pid in product_ids:
            if isinstance(pid, (str, int)):
                ids.add(str(pid))
        free = [u for u in free if u.product_id in ids]
    return free


def _condition_met(
    condition: JsonObject,
    units: list[_Unit],
    subtotal_minor: int,
) -> bool:
    ctype = str(condition.get("type", "always"))
    if ctype == "always":
        return True
    if ctype == "min_qty":
        n = _as_int(condition.get("n", 0))
        return len(_scope(units, condition.get("product_ids"))) >= n
    if ctype == "min_total":
        return subtotal_minor >= _as_int(condition.get("minor", 0))
    if ctype == "category_qty":
        cat = condition.get("category_id")
        n = _as_int(condition.get("n", 0))
        return len([u for u in units if not u.locked and u.category_id == cat]) >= n
    if ctype == "items_present":
        ids = condition.get("product_ids")
        if not isinstance(ids, list):
            return False
        free_ids = {u.product_id for u in units if not u.locked}
        return all(str(pid) in free_ids for pid in ids)
    return False


def _apply_action(
    action: JsonObject,
    units: list[_Unit],
    priced: PricedCart,
    running_subtotal: int,
    delivery_fee_minor: int,
) -> int:
    """Применяет action, локает юниты, возвращает сэкономленное."""
    atype = str(action.get("type", ""))
    saved = 0
    if atype == "percent_items":
        pct = _as_int(action.get("pct", 0))
        for u in _scope(units, action.get("product_ids")):
            d = u.unit_minor * pct // 100
            priced.line_discounts[u.line_idx] += d
            u.locked = True
            saved += d
    elif atype == "n_plus_m_free":
        n = _as_int(action.get("n", 0))
        m = _as_int(action.get("m", 0))
        if n <= 0 or m <= 0:
            return 0
        while True:
            group = sorted(
                _scope(units, action.get("product_ids")),
                key=lambda u: u.unit_minor,
            )
            if len(group) < n + m:
                break
            claimed = group[: n + m]
            for i, u in enumerate(claimed):
                if i < m:
                    priced.line_discounts[u.line_idx] += u.unit_minor
                u.locked = True
            saved += sum(u.unit_minor for u in claimed[:m])
    elif atype == "fixed_bundle_price":
        bundle_price = _as_int(action.get("price_minor", 0))
        raw_items = action.get("items")
        required: dict[str, int] = {}
        if isinstance(raw_items, dict):
            required = {str(k): _as_int(v) for k, v in raw_items.items()}
        elif isinstance(raw_items, list):
            for it in raw_items:
                if isinstance(it, dict):
                    required[str(it["product_id"])] = _as_int(it.get("qty", 1))
        while required:
            claimed: list[_Unit] = []
            for pid, qty in required.items():
                free = [u for u in _scope(units, None) if u.product_id == pid][:qty]
                if len(free) < qty:
                    claimed = []
                    break
                claimed.extend(free)
            if not claimed:
                break
            discount = sum(u.unit_minor for u in claimed) - bundle_price
            if discount <= 0:
                break
            for u in claimed:
                u.locked = True
            saved += discount
            priced.line_discounts[claimed[0].line_idx] += discount
    elif atype == "percent_order":
        pct = _as_int(action.get("pct", 0))
        d = max(0, running_subtotal) * pct // 100
        priced.order_discount_minor += d
        saved += d
    elif atype == "amount_order":
        d = min(_as_int(action.get("minor", 0)), max(0, running_subtotal))
        priced.order_discount_minor += d
        saved += d
    elif atype == "free_delivery":
        priced.delivery_discount_minor = delivery_fee_minor
        saved += delivery_fee_minor
    return saved


def evaluate(
    promos: list[ShopPromo],
    lines: list[CartLine],
    *,
    delivery_fee_minor: int,
    now: datetime,
) -> PricedCart:
    """Единый проход: окно → condition → bundle-lock → action.

    ``now`` — локальное время магазина (timezone-aware), промо уже
    отсортированы по priority/sort на уровне запроса.
    """
    units = [
        _Unit(idx, line.product_id, line.category_id, line.unit_minor)
        for idx, line in enumerate(lines)
        for _ in range(line.qty)
    ]
    subtotal = sum(u.unit_minor for u in units)
    priced = PricedCart(line_discounts=[0] * len(lines))
    for promo in promos:
        if not _window_active(promo.window, now):
            continue
        if not _condition_met(promo.condition, units, subtotal):
            continue
        running = subtotal - sum(priced.line_discounts) - priced.order_discount_minor
        saved = _apply_action(promo.action, units, priced, running, delivery_fee_minor)
        if saved <= 0:
            continue
        priced.applied.append(AppliedPromo(promo.shop_promo_id, promo.name, saved))
        if promo.stacking == PromoStacking.EXCLUSIVE:
            break
    total_discount = sum(priced.line_discounts) + priced.order_discount_minor
    if total_discount > subtotal:
        priced.order_discount_minor -= total_discount - subtotal
    return priced
