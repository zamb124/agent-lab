"""Лояльность витрины: программа «N-я покупка — награда».

Доменные правила: размер награды по ``reward_kind``, гейт фичи
``features.loyalty``, начисление при переходе заказа в ``done``,
атомарный claim при создании заказа и возврат при отмене. Персистентность
— только через методы ``ShopLoyaltyProgram``/``ShopLoyaltyAccount``.
"""

from __future__ import annotations

from apps.shop.models.api import ShopFeatures, normalize_shop_features
from apps.shop.models.enums import ShopLoyaltyRewardKind
from apps.shop.models.loyalty_account import ShopLoyaltyAccount
from apps.shop.models.loyalty_program import (
    MAX_REWARD_PERCENT,
    ShopLoyaltyProgram,
)
from apps.shop.models.order import ShopOrder
from apps.shop.models.shop import Shop
from apps.shop.services.shop_service import ShopService
from core.errors.boundary import PlatformConflictError
from core.utils.time import utcnow

MAX_REWARD_MINOR = 10_000_000


def loyalty_enabled(shop: Shop) -> bool:
    """Флаг ``features.loyalty`` — мастер-выключатель механики."""
    features = ShopFeatures.model_validate(normalize_shop_features(shop.features))
    return features.loyalty


def reward_minor_for(program: ShopLoyaltyProgram, payable_minor: int) -> int:
    """Скидка награды на сумму к оплате за товары (без доставки)."""
    if payable_minor <= 0:
        return 0
    if program.reward_kind == ShopLoyaltyRewardKind.DISCOUNT_PERCENT:
        return min(payable_minor * program.reward_value // 100, payable_minor)
    return min(program.reward_value, payable_minor)


class LoyaltyService:
    """Программа и аккаунты лояльности: начисление, claim, возврат."""

    def __init__(self, shop_service: ShopService) -> None:
        self._shops: ShopService = shop_service

    async def program_or_default(self, shop_id: str) -> ShopLoyaltyProgram:
        """Программа магазина; без строки — дефолты «включил и работает»."""
        program = await ShopLoyaltyProgram.get_by_shop(shop_id)
        if program is not None:
            return program
        now = utcnow()
        return ShopLoyaltyProgram(
            shop_loyalty_program_id="",
            shop_id=shop_id,
            created_at=now,
            updated_at=now,
        )

    async def get_program(
        self, company_id: str, shop_id: str
    ) -> ShopLoyaltyProgram:
        shop = await self._shops.get_shop(company_id, shop_id)
        return await self.program_or_default(shop.shop_id)

    async def set_program(
        self,
        company_id: str,
        shop_id: str,
        *,
        orders_goal: int,
        reward_kind: ShopLoyaltyRewardKind,
        reward_value: int,
    ) -> ShopLoyaltyProgram:
        shop = await self._shops.get_shop(company_id, shop_id)
        kind = ShopLoyaltyRewardKind(reward_kind)
        if kind == ShopLoyaltyRewardKind.DISCOUNT_PERCENT:
            valid = reward_value <= MAX_REWARD_PERCENT
        else:
            valid = reward_value <= MAX_REWARD_MINOR
        if not valid:
            raise PlatformConflictError(
                "Reward value is out of range for its kind",
                error_code="loyalty_program_invalid",
            )
        return await ShopLoyaltyProgram.upsert_by_shop(
            shop.shop_id,
            orders_goal=orders_goal,
            reward_kind=kind,
            reward_value=reward_value,
        )

    async def account_state(
        self, shop: Shop, customer_id: str
    ) -> tuple[ShopLoyaltyProgram, ShopLoyaltyAccount | None]:
        """Программа + прогресс покупателя для кабинета и чекаута."""
        program = await self.program_or_default(shop.shop_id)
        account = await ShopLoyaltyAccount.get_by_shop_and_customer(
            shop.shop_id, customer_id
        )
        return program, account

    async def preview_reward(
        self, shop: Shop, customer_id: str, payable_minor: int
    ) -> int:
        """Скидка награды для живого расчёта корзины — без списания."""
        if not loyalty_enabled(shop):
            return 0
        program, account = await self.account_state(shop, customer_id)
        if account is None or account.rewards_available <= 0:
            return 0
        return reward_minor_for(program, payable_minor)

    async def claim_reward(
        self, shop: Shop, customer_id: str, payable_minor: int
    ) -> int:
        """Применить награду к создаваемому заказу: атомарное списание."""
        if not loyalty_enabled(shop):
            raise PlatformConflictError(
                "Loyalty is disabled for this shop", error_code="loyalty_disabled"
            )
        if not await ShopLoyaltyAccount.claim_reward(shop.shop_id, customer_id):
            raise PlatformConflictError(
                "No loyalty rewards available",
                error_code="loyalty_reward_unavailable",
            )
        program = await self.program_or_default(shop.shop_id)
        return reward_minor_for(program, payable_minor)

    async def accrue_done_order(self, shop: Shop, order: ShopOrder) -> None:
        """done-заказ засчитывается в прогресс; цель → награда."""
        if not order.customer_id or not loyalty_enabled(shop):
            return
        program = await self.program_or_default(shop.shop_id)
        await ShopLoyaltyAccount.accrue_order(
            shop.shop_id, order.customer_id, program.orders_goal
        )

    async def refund_reward(self, order: ShopOrder) -> None:
        """Отмена заказа с наградой — возврат награды покупателю."""
        if order.loyalty_reward_minor <= 0 or not order.customer_id:
            return
        await ShopLoyaltyAccount.refund_reward(order.shop_id, order.customer_id)
