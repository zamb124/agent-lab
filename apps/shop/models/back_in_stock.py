"""Таблица shop_back_in_stock — подписка покупателя на возврат товара.

Когда недоступная позиция снова получает ``is_available=True``,
подписчики получают уведомление через ``CustomerNotifyService``
(личка бота бренда TG/MAX). ``notified_at`` фиксирует отправку —
повторный возврат товара обслуживает новый виток подписок:
отработанная запись удаляется, при повторной подписке создаётся новая.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


class ShopBackInStock(PlatformModel):
    """Подписка «сообщить о появлении». Таблица ``shop_back_in_stock``."""

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_back_in_stock"
        indexes: list[Index] = [
            Index(["product_id"]),
            Index(["customer_id"]),
        ]
        unique_together: list[tuple[str, str]] = [
            ("product_id", "customer_id"),
        ]

    shop_back_in_stock_id: str = DbField(db_pk=True, max_length=64)
    product_id: str = DbField(max_length=64)
    customer_id: str = DbField(max_length=64)
    notified_at: datetime | None = DbField(default=None)
    created_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, subscription_id: str) -> Self | None:
        return await cls.objects.filter(
            shop_back_in_stock_id=subscription_id
        ).get_or_none()

    @classmethod
    async def find_by_product_and_customer(
        cls, product_id: str, customer_id: str
    ) -> Self | None:
        return await cls.objects.filter(
            product_id=product_id, customer_id=customer_id
        ).get_or_none()

    @classmethod
    async def list_pending_by_product(cls, product_id: str) -> list[Self]:
        """Подписки без отправленного уведомления — виток возврата товара."""
        return await cls.objects.filter(
            product_id=product_id, notified_at=None
        ).all()

    @classmethod
    async def list_by_customer(cls, customer_id: str) -> list[Self]:
        return await cls.objects.filter(customer_id=customer_id).all()

    @classmethod
    async def create(cls, subscription: Self) -> Self:
        return await cls.objects.create(instance=subscription)
