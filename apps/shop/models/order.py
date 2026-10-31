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

_PUBLIC_CODE_ALPHABET = string.ascii_uppercase + string.digits


def new_public_code(length: int = 8) -> str:
    return "".join(secrets.choice(_PUBLIC_CODE_ALPHABET) for _ in range(length))


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
        ]

    shop_order_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    public_code: str = DbField(max_length=16, db_index=True)
    status: ShopOrderStatus = DbField(default=ShopOrderStatus.NEW)
    customer_name: str = DbField(max_length=200)
    customer_phone: str = DbField(max_length=32)
    delivery_type: ShopDeliveryType = DbField()
    address: str = DbField(default="", max_length=500)
    comment: str = DbField(default="", max_length=1000)
    items_total_minor: int = DbField(ge=0)
    delivery_fee_minor: int = DbField(default=0, ge=0)
    total_minor: int = DbField(ge=0)
    currency: str = DbField(default="RUB", max_length=3)
    source: ShopOrderSource = DbField(default=ShopOrderSource.WEB)
    idempotency_key: str = DbField(default="", max_length=128, db_index=True)
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
    async def create(cls, order: Self) -> Self:
        return await cls.objects.create(instance=order)
