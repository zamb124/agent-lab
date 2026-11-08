"""Таблица программы лояльности витрины — «N-я покупка — награда».

``shop_loyalty_programs`` — настройка директора, одна на магазин:
``orders_goal`` выполненных заказов даёт награду (скидка фиксом или
процентом). Флаг темы ``features.loyalty`` включает механику.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

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
