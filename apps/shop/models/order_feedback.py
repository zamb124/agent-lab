"""Таблица shop_order_feedback — отзыв покупателя на выполненный заказ.

Один отзыв на заказ (``shop_order_id`` уникален): повторная отправка —
редактирование своей оценки. ``customer_name`` — снапшот имени из заказа
для публичной ленты отзывов; телефон не хранится. Рейтинг витрины
агрегируется в снапшоте (per rebuild), лента — ``/storefront/{slug}/reviews``.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, execute_raw

from core.models.platform_model import PlatformModel
from core.types import require_json_object


class ShopOrderFeedback(PlatformModel):
    """Отзыв на заказ. Таблица ``shop_order_feedback``."""

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_order_feedback"
        indexes: list[Index] = [
            Index(["shop_id", "created_at"]),
            Index(["customer_id"]),
            Index(["shop_order_id"], unique=True),
        ]

    shop_order_feedback_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    shop_order_id: str = DbField(max_length=64)
    customer_id: str = DbField(max_length=64)
    customer_name: str = DbField(default="", max_length=200)
    rating: int = DbField(ge=1, le=5)
    chips: list[str] = DbField(default_factory=list, db_type="JSONB")
    comment: str = DbField(default="", max_length=1000)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, feedback_id: str) -> Self | None:
        return await cls.objects.filter(
            shop_order_feedback_id=feedback_id
        ).get_or_none()

    @classmethod
    async def find_by_order(cls, shop_order_id: str) -> Self | None:
        return await cls.objects.filter(shop_order_id=shop_order_id).get_or_none()

    @classmethod
    async def list_many_by_order_ids(cls, order_ids: list[str]) -> list[Self]:
        if not order_ids:
            return []
        return await cls.objects.filter(shop_order_id__in=order_ids).all()

    @classmethod
    async def list_by_shop_by_created_desc(
        cls, shop_id: str, *, limit: int = 20, offset: int = 0
    ) -> list[Self]:
        """Публичная лента отзывов витрины по created_at DESC."""
        return (
            await cls.objects.filter(shop_id=shop_id)
            .order_by("-created_at")
            .offset(offset)
            .limit(limit)
            .all()
        )

    @classmethod
    async def summary_by_shop(cls, shop_id: str) -> tuple[int, float | None]:
        """Агрегат витрины одним запросом: (число отзывов, средняя оценка)."""
        rows = await execute_raw(
            "SELECT COUNT(*) AS cnt, AVG(rating)::float8 AS avg FROM shop_order_feedback WHERE shop_id = $1",
            [shop_id],
            using="shop",
        )
        parsed = require_json_object(rows[0], "feedback summary")
        cnt = parsed["cnt"]
        if not isinstance(cnt, int):
            raise ValueError("feedback summary count required")
        avg_raw = parsed["avg"]
        avg = float(avg_raw) if isinstance(avg_raw, (int, float, str)) else None
        return cnt, avg

    @classmethod
    async def create(cls, feedback: Self) -> Self:
        return await cls.objects.create(instance=feedback)
