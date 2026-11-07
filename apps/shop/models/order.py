"""Таблица shop_orders — заказ покупателя в витрине."""

from __future__ import annotations

import secrets
import string
from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.shop.models.enums import (
    ShopDeliveryType,
    ShopOrderSource,
    ShopOrderStatus,
)
from core.models.platform_model import PlatformModel
from core.types import JsonObject

_PUBLIC_CODE_ALPHABET = string.ascii_uppercase + string.digits


def new_public_code(length: int = 8) -> str:
    return "".join(secrets.choice(_PUBLIC_CODE_ALPHABET) for _ in range(length))


def delivery_details_label(order: "ShopOrder") -> str:
    """«кв. 12, подъезд 2, этаж 3, домофон 45» — подробности адреса для курьера."""
    parts = [
        f"{label} {value}"
        for label, value in (
            ("кв.", order.delivery_flat),
            ("подъезд", order.delivery_entrance),
            ("этаж", order.delivery_floor),
            ("домофон", order.delivery_intercom),
        )
        if value
    ]
    return ", ".join(parts)


class ShopOrder(PlatformModel):
    """Заказ анонимного покупателя. Таблица ``shop_orders``.

    ``public_code`` — публичный идентификатор для статуса без авторизации.
    ``idempotency_key`` — ключ идемпотентности клиента (повторный submit формы),
    уникален в пределах магазина.
    """

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_orders"
        indexes: list[Index] = [
            Index(["shop_id", "created_at"]),
            Index(["shop_id", "status", "created_at"]),
            Index(["customer_id", "created_at"]),
        ]

    shop_order_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    public_code: str = DbField(max_length=16, db_index=True)
    status: ShopOrderStatus = DbField(default=ShopOrderStatus.NEW)
    customer_name: str = DbField(max_length=200)
    customer_phone: str = DbField(max_length=32)
    customer_id: str = DbField(default="", max_length=64, db_index=True)
    delivery_type: ShopDeliveryType = DbField()
    address: str = DbField(default="", max_length=500)
    delivery_eta_minutes: int | None = DbField(default=None)
    table_id: str = DbField(default="", max_length=64)
    table_label: str = DbField(default="", max_length=64)
    comment: str = DbField(default="", max_length=1000)
    items_total_minor: int = DbField(ge=0)
    discount_minor: int = DbField(default=0, ge=0)
    delivery_fee_minor: int = DbField(default=0, ge=0)
    total_minor: int = DbField(ge=0)
    promos: list[dict[str, object]] = DbField(default_factory=list, db_type="JSONB")
    currency: str = DbField(default="RUB", max_length=3)
    source: ShopOrderSource = DbField(default=ShopOrderSource.WEB)
    idempotency_key: str = DbField(default="", max_length=128, db_index=True)
    # Таймлайн статусов для кабинета покупателя: [{status, at}].
    status_history: list[dict[str, object]] = DbField(default_factory=list, db_type="JSONB")
    # Гео-снапшот доставки: точка покупателя, маршрут курьера, точка магазина.
    delivery_lat: float | None = DbField(default=None)
    delivery_lng: float | None = DbField(default=None)
    delivery_route: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    shop_lat: float | None = DbField(default=None)
    shop_lng: float | None = DbField(default=None)
    # Детали доставки для курьера: адрес-точка отдельно, подробности — полями.
    delivery_flat: str = DbField(default="", max_length=32)
    delivery_entrance: str = DbField(default="", max_length=32)
    delivery_floor: str = DbField(default="", max_length=32)
    delivery_intercom: str = DbField(default="", max_length=64)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    status_changed_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, shop_order_id: str) -> Self | None:
        return await cls.objects.filter(shop_order_id=shop_order_id).get_or_none()

    @classmethod
    async def get_by_public_code(cls, public_code: str) -> Self | None:
        return await cls.objects.filter(public_code=public_code).get_or_none()

    @classmethod
    async def get_by_idempotency_key(cls, shop_id: str, idempotency_key: str) -> Self | None:
        return await cls.objects.filter(
            shop_id=shop_id, idempotency_key=idempotency_key
        ).get_or_none()

    @classmethod
    async def list_by_shop_by_created_desc(
        cls,
        shop_id: str,
        *,
        status: ShopOrderStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Self]:
        """Заказы магазина по created_at DESC."""
        qs = cls.objects.filter(shop_id=shop_id)
        if status is not None:
            qs = qs.filter(status=status)
        return await qs.order_by("-created_at").offset(offset).limit(limit).all()

    @classmethod
    async def count_by_shop(cls, shop_id: str, *, status: ShopOrderStatus | None = None) -> int:
        qs = cls.objects.filter(shop_id=shop_id)
        if status is not None:
            qs = qs.filter(status=status)
        return await qs.count()

    @classmethod
    async def list_by_customer_by_created_desc(
        cls,
        customer_id: str,
        *,
        statuses: list[ShopOrderStatus] | None = None,
        limit: int = 30,
        offset: int = 0,
    ) -> list[Self]:
        """Сквозная история заказов покупателя по всем витринам платформы."""
        qs = cls.objects.filter(customer_id=customer_id)
        if statuses:
            qs = qs.filter(status__in=statuses)
        return await qs.order_by("-created_at").offset(offset).limit(limit).all()

    @classmethod
    async def count_by_customer(
        cls, customer_id: str, *, statuses: list[ShopOrderStatus] | None = None
    ) -> int:
        qs = cls.objects.filter(customer_id=customer_id)
        if statuses:
            qs = qs.filter(status__in=statuses)
        return await qs.count()

    @classmethod
    async def list_by_customer_shop_by_created_desc(
        cls, customer_id: str, shop_id: str, *, limit: int = 50
    ) -> list[Self]:
        """Заказы покупателя конкретной витрины — источник полки «как всегда»."""
        return (
            await cls.objects.filter(customer_id=customer_id, shop_id=shop_id)
            .order_by("-created_at")
            .limit(limit)
            .all()
        )

    @classmethod
    async def create(cls, order: Self) -> Self:
        return await cls.objects.create(instance=order)
