"""Таблицы лояльности витрины — программа «N-я покупка — награда».

``shop_loyalty_programs`` — настройка директора, одна на магазин:
``orders_goal`` выполненных заказов даёт награду (скидка фиксом или
процентом). ``shop_loyalty_accounts`` — прогресс покупателя: ``progress``
заказов до награды и число доступных к применению наград. Флаг темы
``features.loyalty`` включает механику; атомарные инкременты — одним
UPDATE, чтобы конкурентные done-заказы не теряли прогресс.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, execute_raw

from apps.shop.models.common import new_id
from apps.shop.models.enums import ShopLoyaltyRewardKind
from core.models.platform_model import PlatformModel
from core.utils.time import utcnow

DEFAULT_ORDERS_GOAL = 5
DEFAULT_REWARD_MINOR = 50000
MAX_REWARD_PERCENT = 90


class ShopLoyaltyProgram(PlatformModel):
    """Программа лояльности магазина. Таблица ``shop_loyalty_programs``."""

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_loyalty_programs"
        indexes: list[Index] = [
            Index(["shop_id"], unique=True),
        ]

    shop_loyalty_program_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    orders_goal: int = DbField(default=DEFAULT_ORDERS_GOAL, ge=1, le=100)
    reward_kind: ShopLoyaltyRewardKind = DbField(
        default=ShopLoyaltyRewardKind.DISCOUNT_MINOR
    )
    # minor-единицы скидки или процент 1..90 — по reward_kind.
    reward_value: int = DbField(default=DEFAULT_REWARD_MINOR, ge=1)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def create(cls, program: Self) -> Self:
        return await cls.objects.create(instance=program)

    @classmethod
    async def get_by_shop(cls, shop_id: str) -> Self | None:
        return await cls.objects.filter(shop_id=shop_id).get_or_none()

    @classmethod
    async def upsert_by_shop(
        cls,
        shop_id: str,
        *,
        orders_goal: int,
        reward_kind: ShopLoyaltyRewardKind,
        reward_value: int,
    ) -> Self:
        """Создать или обновить программу магазина (одна на shop_id)."""
        program = await cls.get_by_shop(shop_id)
        now = utcnow()
        if program is None:
            program = cls(
                shop_loyalty_program_id=new_id("shoployaltyprogram"),
                shop_id=shop_id,
                orders_goal=orders_goal,
                reward_kind=reward_kind,
                reward_value=reward_value,
                created_at=now,
                updated_at=now,
            )
            return await cls.create(program)
        program.orders_goal = orders_goal
        program.reward_kind = reward_kind
        program.reward_value = reward_value
        program.updated_at = now
        _ = await program.save()
        return program


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
