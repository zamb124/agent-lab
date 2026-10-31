"""Enum'ы домена shop."""

from __future__ import annotations

from enum import StrEnum


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
    """Способ получения заказа."""

    DELIVERY = "delivery"
    PICKUP = "pickup"


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


