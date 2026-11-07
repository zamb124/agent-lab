"""Enum'ы домена shop."""

from __future__ import annotations

from enum import StrEnum
from typing import assert_never


class ShopKind(StrEnum):
    """Вид заведения: влияет на шаблон витрины и фильтры агрегатора."""

    RESTAURANT = "restaurant"
    CAFE = "cafe"
    BAKERY = "bakery"
    SHOP = "shop"
    OTHER = "other"


class ShopStatus(StrEnum):
    """Жизненный цикл витрины."""

    DRAFT = "draft"
    PUBLISHED = "published"
    SUSPENDED = "suspended"


class ShopDomainStatus(StrEnum):
    """Статус подключения кастомного домена."""

    PENDING_DNS = "pending_dns"
    AWAITING_DNS = "awaiting_dns"
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    FAILED = "failed"


class ShopOrderStatus(StrEnum):
    """Статус заказа витрины."""

    NEW = "new"
    ACCEPTED = "accepted"
    PREPARING = "preparing"
    DELIVERING = "delivering"
    DONE = "done"
    CANCELLED = "cancelled"


class ShopDeliveryType(StrEnum):
    """Способ получения заказа.

    ``onsite`` — гость заказывает из заведения (QR на столе): заказ
    помечается меткой столика и не требует адреса и телефона.
    """

    DELIVERY = "delivery"
    PICKUP = "pickup"
    ONSITE = "onsite"


def order_status_label(
    status: ShopOrderStatus,
    delivery_type: ShopDeliveryType = ShopDeliveryType.DELIVERY,
    *,
    for_notify: bool = False,
) -> str:
    """Пользовательский текст статуса — единый словарь домена.

    Подпись зависит от способа выдачи: «доставлен» у курьерского заказа,
    «выдан» у самовывоза, «завершён» у заказа в зале. `for_notify` —
    формулировка для DM покупателю («едет к вам»), иначе — нейтральный
    чип («в доставке»). Статусы вне словаря возвращаются как есть —
    новый член enum не ломает витрину, а фиксируется здесь.
    """
    if status == ShopOrderStatus.NEW:
        return "принят" if for_notify else "Новый"
    if status == ShopOrderStatus.ACCEPTED:
        return "подтверждён магазином" if for_notify else "Подтверждён"
    if status == ShopOrderStatus.PREPARING:
        return "готовится" if for_notify else "Готовится"
    if status == ShopOrderStatus.DELIVERING:
        if delivery_type == ShopDeliveryType.DELIVERY:
            return "едет к вам" if for_notify else "В доставке"
        return "почти готов, ждём вас" if for_notify else "Готовится"
    if status == ShopOrderStatus.DONE:
        if delivery_type == ShopDeliveryType.DELIVERY:
            return "доставлен" if for_notify else "Доставлен"
        if delivery_type == ShopDeliveryType.PICKUP:
            return "выдан" if for_notify else "Выдан"
        return "завершён" if for_notify else "Завершён"
    if status == ShopOrderStatus.CANCELLED:
        return "отменён" if for_notify else "Отменён"
    assert_never(status)


class ShopOrderSource(StrEnum):
    """Откуда оформлен заказ."""

    WEB = "web"
    EMBED = "embed"


class ModifierGroupKind(StrEnum):
    """Назначение группы модификаторов: добавки/варианты или исключение."""

    ADDON = "addon"
    REMOVE = "remove"


class ModifierSelectionMode(StrEnum):
    """Сколько опций можно выбрать в группе модификаторов."""

    SINGLE = "single"
    MULTI = "multi"


class ModifierPriceMode(StrEnum):
    """Как цена опции участвует в итоге позиции."""

    DELTA = "delta"
    ABSOLUTE = "absolute"


class PromoStacking(StrEnum):
    """Может ли акция суммироваться с другими.

    ``all`` — применяется вместе с остальными подходящими акциями;
    ``exclusive`` — первой сработавшей закрывает остальные.
    """

    ALL = "all"
    EXCLUSIVE = "exclusive"


class ShopShelfKind(StrEnum):
    """Источник товаров витринной полки.

    ``manual`` — ручная выборка ``product_ids``; ``category`` — зеркало
    раздела каталога; ``new``/``hits``/``comeback``/``usual`` —
    вычисляемые полки (данные собирает снапшот/персональный endpoint);
    ``upsell`` — полка «добавить к заказу» внутри корзины.
    """

    MANUAL = "manual"
    CATEGORY = "category"
    NEW = "new"
    HITS = "hits"
    COMEBACK = "comeback"
    USUAL = "usual"
    UPSELL = "upsell"


class ShopShelfLayout(StrEnum):
    """Визуальная раскладка полки на витрине.

    ``rail`` — горизонтальная карусель карточек; ``rows`` — компактные
    строки; ``grid`` — двухколоночная сетка; ``hero`` — крупные карточки.
    """

    RAIL = "rail"
    ROWS = "rows"
    GRID = "grid"
    HERO = "hero"


class ShopShelfPlacement(StrEnum):
    """Где полка показывается: лента витрины или внутри корзины."""

    FEED = "feed"
    CART = "cart"


