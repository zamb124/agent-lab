"""Таблица прогресса лояльности покупателя по витрине.

``shop_loyalty_accounts`` — ``progress`` заказов до награды и число
доступных к применению наград. Атомарные инкременты — одним UPDATE,
чтобы конкурентные done-заказы не теряли прогресс.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, execute_raw

from apps.shop.models.common import new_id
from core.models.platform_model import PlatformModel
from core.utils.time import utcnow


class ShopLoyaltyAccount(PlatformModel):
    """Прогресс и награды покупателя. Таблица ``shop_loyalty_accounts``."""

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_loyalty_accounts"
        indexes: list[Index] = [
            Index(["customer_id"]),
        ]
        unique_together: list[tuple[str, str]] = [
            ("shop_id", "customer_id"),
        ]

    shop_loyalty_account_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    customer_id: str = DbField(max_length=64)
    progress: int = DbField(default=0, ge=0)
    rewards_available: int = DbField(default=0, ge=0)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def get_by_shop_and_customer(
        cls, shop_id: str, customer_id: str
    ) -> Self | None:
        return await cls.objects.filter(
            shop_id=shop_id, customer_id=customer_id
        ).get_or_none()

    @classmethod
    async def accrue_order(cls, shop_id: str, customer_id: str, goal: int) -> None:
        """Засчитать done-заказ: прогресс +1, при цели — награда и сброс.

        Атомарный upsert: конкурентные заказы покупателя не теряют прогресс.
        """
        now = utcnow()
        _ = await execute_raw(
            "INSERT INTO shop_loyalty_accounts (shop_loyalty_account_id, shop_id, customer_id, progress, rewards_available, created_at, updated_at) VALUES ($1, $2, $3, $6, $7, $5, $5) ON CONFLICT (shop_id, customer_id) DO UPDATE SET progress = CASE WHEN shop_loyalty_accounts.progress + 1 >= $4 THEN 0 ELSE shop_loyalty_accounts.progress + 1 END, rewards_available = shop_loyalty_accounts.rewards_available + CASE WHEN shop_loyalty_accounts.progress + 1 >= $4 THEN 1 ELSE 0 END, updated_at = $5",
            [
                new_id("shoployaltyaccount"),
                shop_id,
                customer_id,
                goal,
                now,
                0 if goal <= 1 else 1,
                1 if goal <= 1 else 0,
            ],
            using="shop",
        )

    @classmethod
    async def claim_reward(cls, shop_id: str, customer_id: str) -> bool:
        """Списать одну награду атомарно. ``False`` — доступных наград нет."""
        rows = await execute_raw(
            "UPDATE shop_loyalty_accounts SET rewards_available = rewards_available - 1, updated_at = $3 WHERE shop_id = $1 AND customer_id = $2 AND rewards_available > 0 RETURNING shop_loyalty_account_id",
            [shop_id, customer_id, utcnow()],
            using="shop",
        )
        return len(rows) > 0

    @classmethod
    async def refund_reward(cls, shop_id: str, customer_id: str) -> None:
        """Вернуть награду при отмене заказа (аккаунт существует, раз был claim)."""
        _ = await execute_raw(
            "UPDATE shop_loyalty_accounts SET rewards_available = rewards_available + 1, updated_at = $3 WHERE shop_id = $1 AND customer_id = $2",
            [shop_id, customer_id, utcnow()],
            using="shop",
        )
