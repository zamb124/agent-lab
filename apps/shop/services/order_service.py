"""ShopOrderService — сценарии заказа: приём с витрины, статусная машина.

Авторитетный слой — PostgreSQL; публичный ответ содержит только
``public_code``. Идемпотентность по (shop_id, idempotency_key): повторный
submit формы возвращает тот же заказ без дубля строк.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from apps.shop.models import (
    Shop,
    ShopDeliveryType,
    ShopOrder,
    ShopOrderItem,
    ShopOrderStatus,
    ShopProduct,
    ShopPromo,
    ShopStatus,
    ShopTable,
)
from apps.shop.models.api import (
    ShopCartPriceLineResponse,
    ShopCartPriceRequest,
    ShopCartPriceResponse,
    ShopOrderCreateRequest,
    ShopOrderItemModifierResponse,
    ShopOrderItemRequest,
    ShopOrderItemResponse,
    ShopOrderResponse,
    ShopPromoAppliedResponse,
)
from apps.shop.models.common import new_id
from apps.shop.models.order import new_public_code
from apps.shop.services.modifier_pricing import (
    load_modifier_tree_by_sort_asc,
    nested_lookup,
    validate_and_price,
)
from apps.shop.services.promo_engine import CartLine, PricedCart, evaluate
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.utils.time import utcnow


@dataclass
class _PricedItem:
    """Строка корзины с авторитетной ценой за единицу и снапшотом опций."""

    product: ShopProduct
    qty: int
    unit_minor: int
    modifiers_snapshot: list[dict[str, object]]


# Допустимые переходы статуса: каждый ключ — из каких статусов можно в него перейти.
_ALLOWED_TRANSITIONS: dict[ShopOrderStatus, frozenset[ShopOrderStatus]] = {
    ShopOrderStatus.ACCEPTED: frozenset({ShopOrderStatus.NEW}),
    ShopOrderStatus.PREPARING: frozenset({ShopOrderStatus.ACCEPTED}),
    ShopOrderStatus.DELIVERING: frozenset({ShopOrderStatus.PREPARING}),
    ShopOrderStatus.DONE: frozenset({ShopOrderStatus.DELIVERING, ShopOrderStatus.PREPARING}),
    ShopOrderStatus.CANCELLED: frozenset(
        {ShopOrderStatus.NEW, ShopOrderStatus.ACCEPTED, ShopOrderStatus.PREPARING}
    ),
}


class ShopOrderService:
    """Заказы витрины: приём анонимного заказа и жизненный цикл для владельца."""

    async def resolve_published_shop(self, slug: str) -> Shop:
        """Опубликованная витрина по slug для публичного заказа."""
        shop = await Shop.get_by_slug(slug)
        if shop is None or shop.status != ShopStatus.PUBLISHED:
            raise PlatformNotFoundError("Storefront not found", error_code="storefront_not_found")
        return shop

    async def create_order(self, shop: Shop, payload: ShopOrderCreateRequest) -> ShopOrder:
        """Новый заказ: идемпотентность, расчёт суммы по живым ценам каталога."""
        if shop.status != ShopStatus.PUBLISHED:
            raise PlatformNotFoundError(
                "Storefront unavailable", error_code="storefront_unavailable"
            )
        if payload.honeypot:
            raise PlatformConflictError("Order rejected", error_code="order_rejected")
        if payload.delivery_type == ShopDeliveryType.DELIVERY:
            if not shop.delivery_enabled:
                raise PlatformConflictError(
                    "Delivery is not supported by the shop",
                    error_code="delivery_disabled",
                )
            if not payload.address:
                raise PlatformConflictError(
                    "Delivery address is required", error_code="address_required"
                )
        elif payload.delivery_type == ShopDeliveryType.PICKUP:
            if not shop.pickup_enabled:
                raise PlatformConflictError(
                    "Pickup is not supported by the shop",
                    error_code="pickup_disabled",
                )
        elif payload.delivery_type == ShopDeliveryType.ONSITE:
            if not shop.onsite_enabled:
                raise PlatformConflictError(
                    "Onsite ordering is not supported by the shop",
                    error_code="onsite_disabled",
                )
        if (
            payload.delivery_type != ShopDeliveryType.ONSITE
            and len(payload.customer_phone.strip()) < 5
        ):
            raise PlatformConflictError(
                "Customer phone is required", error_code="phone_required"
            )
        table_id = ""
        table_label = ""
        if payload.delivery_type == ShopDeliveryType.ONSITE:
            if not payload.table_id:
                raise PlatformConflictError(
                    "Table is required for onsite orders", error_code="table_required"
                )
            table = await ShopTable.get_by_id(payload.table_id)
            if table is None or table.shop_id != shop.shop_id:
                raise PlatformConflictError(
                    "Table not found", error_code="table_unknown"
                )
            table_id = table.shop_table_id
            table_label = table.label
        if payload.idempotency_key:
            existing = await ShopOrder.get_by_idempotency_key(shop.shop_id, payload.idempotency_key)
            if existing is not None:
                return existing
        priced = await self._price_items(shop, payload.items)
        priced_cart = await self._evaluate_promos(shop, priced, payload.delivery_type)
        items_total = sum(p.unit_minor * p.qty for p in priced)
        delivery_fee = (
            shop.delivery_fee_minor if payload.delivery_type == ShopDeliveryType.DELIVERY else 0
        )
        if shop.min_order_minor and items_total < shop.min_order_minor:
            raise PlatformConflictError(
                "Order total is below the minimum", error_code="below_min_order"
            )
        discount_total = sum(priced_cart.line_discounts) + priced_cart.order_discount_minor
        order_id = new_id("shoporder")
        order_items = [
            ShopOrderItem(
                shop_order_item_id=new_id("shoporderitem"),
                order_id=order_id,
                product_id=p.product.shop_product_id,
                name_snapshot=p.product.name,
                price_minor=p.unit_minor,
                qty=p.qty,
                modifiers=p.modifiers_snapshot,
                discount_minor=priced_cart.line_discounts[idx],
            )
            for idx, p in enumerate(priced)
        ]
        now = utcnow()
        order = ShopOrder(
            shop_order_id=order_id,
            shop_id=shop.shop_id,
            public_code=await self._allocate_public_code(),
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            delivery_type=payload.delivery_type,
            address=payload.address,
            table_id=table_id,
            table_label=table_label,
            comment=payload.comment,
            items_total_minor=items_total,
            discount_minor=discount_total,
            delivery_fee_minor=max(0, delivery_fee - priced_cart.delivery_discount_minor),
            total_minor=items_total
            - discount_total
            + max(0, delivery_fee - priced_cart.delivery_discount_minor),
            promos=[
                {"promo_id": a.promo_id, "name": a.name, "saved_minor": a.saved_minor}
                for a in priced_cart.applied
            ],
            currency=shop.currency,
            source=payload.source,
            idempotency_key=payload.idempotency_key,
            created_at=now,
            updated_at=now,
            status_changed_at=now,
        )
        _ = await ShopOrder.create(order)
        _ = await ShopOrderItem.create_many(order_items)
        return order

    async def _price_items(
        self, shop: Shop, items: list[ShopOrderItemRequest]
    ) -> list[_PricedItem]:
        """Авторитетная цена позиций: каталог + модификаторы, клиентские
        цены не участвуют. Общий шаг для preview и создания заказа."""
        product_ids = [item.product_id for item in items]
        products = await ShopProduct.list_many_by_ids(product_ids)
        by_id = {p.shop_product_id: p for p in products}
        modifier_tree = await load_modifier_tree_by_sort_asc(product_ids)
        nested = nested_lookup(modifier_tree.get("__nested__", []))
        priced: list[_PricedItem] = []
        for item in items:
            product = by_id.get(item.product_id)
            if product is None or product.shop_id != shop.shop_id:
                raise PlatformNotFoundError(
                    "Item not found in catalog", error_code="product_not_found"
                )
            if not product.is_available:
                raise PlatformConflictError(
                    f"Item {product.name} is unavailable",
                    error_code="product_unavailable",
                )
            unit_minor, modifiers_snapshot = validate_and_price(
                product,
                item.selections,
                modifier_tree.get(product.shop_product_id, []),
                nested,
            )
            priced.append(_PricedItem(product, item.qty, unit_minor, modifiers_snapshot))
        return priced

    async def _evaluate_promos(
        self,
        shop: Shop,
        priced: list[_PricedItem],
        delivery_type: ShopDeliveryType,
    ) -> PricedCart:
        """Акции магазина поверх авторитетных цен — один движок для
        preview корзины и создания заказа."""
        promos = await ShopPromo.list_active_by_shop_by_priority_desc(shop.shop_id)
        if not promos:
            return PricedCart(line_discounts=[0] * len(priced))
        delivery_fee = shop.delivery_fee_minor if delivery_type == ShopDeliveryType.DELIVERY else 0
        lines = [
            CartLine(p.product.shop_product_id, p.product.category_id, p.qty, p.unit_minor)
            for p in priced
        ]
        try:
            tz = ZoneInfo(shop.timezone)
        except Exception:
            tz = ZoneInfo("Europe/Moscow")
        return evaluate(promos, lines, delivery_fee_minor=delivery_fee, now=datetime.now(tz))

    async def price_cart(self, shop: Shop, payload: ShopCartPriceRequest) -> ShopCartPriceResponse:
        """Живой расчёт корзины для витрины: цены, скидки, акции — без создания заказа."""
        if shop.status != ShopStatus.PUBLISHED:
            raise PlatformNotFoundError(
                "Storefront unavailable", error_code="storefront_unavailable"
            )
        priced = await self._price_items(shop, payload.items)
        priced_cart = await self._evaluate_promos(shop, priced, payload.delivery_type)
        items_total = sum(p.unit_minor * p.qty for p in priced)
        delivery_fee = (
            shop.delivery_fee_minor if payload.delivery_type == ShopDeliveryType.DELIVERY else 0
        )
        delivery_after = max(0, delivery_fee - priced_cart.delivery_discount_minor)
        discount_total = sum(priced_cart.line_discounts) + priced_cart.order_discount_minor
        return ShopCartPriceResponse(
            lines=[
                ShopCartPriceLineResponse(
                    product_id=p.product.shop_product_id,
                    qty=p.qty,
                    unit_minor=p.unit_minor,
                    discount_minor=priced_cart.line_discounts[idx],
                )
                for idx, p in enumerate(priced)
            ],
            items_total_minor=items_total,
            discount_minor=discount_total,
            delivery_fee_minor=delivery_after,
            total_minor=items_total - discount_total + delivery_after,
            applied_promos=[
                ShopPromoAppliedResponse(
                    promo_id=a.promo_id, name=a.name, saved_minor=a.saved_minor
                )
                for a in priced_cart.applied
            ],
            below_min_order=bool(shop.min_order_minor and items_total < shop.min_order_minor),
        )

    async def get_by_public_code(self, public_code: str) -> ShopOrder:
        order = await ShopOrder.get_by_public_code(public_code)
        if order is None:
            raise PlatformNotFoundError("Order not found", error_code="order_not_found")
        return order

    async def list_orders(
        self,
        company_shop: Shop,
        *,
        status: ShopOrderStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ShopOrder], int]:
        orders = await ShopOrder.list_by_shop_by_created_desc(
            company_shop.shop_id, status=status, limit=limit, offset=offset
        )
        total = await ShopOrder.count_by_shop(company_shop.shop_id, status=status)
        return orders, total

    async def get_order(self, company_shop: Shop, order_id: str) -> ShopOrder:
        order = await ShopOrder.get_by_id(order_id)
        if order is None or order.shop_id != company_shop.shop_id:
            raise PlatformNotFoundError("Order not found", error_code="order_not_found")
        return order

    async def set_status(
        self, company_shop: Shop, order_id: str, status: ShopOrderStatus
    ) -> ShopOrder:
        """Переход статуса по разрешённой матрице; конфликт → 409."""
        order = await self.get_order(company_shop, order_id)
        allowed_from = _ALLOWED_TRANSITIONS.get(status, frozenset())
        if order.status not in allowed_from:
            raise PlatformConflictError(
                f"Transition {order.status} -> {status} is not allowed",
                error_code="order_transition_invalid",
            )
        now = utcnow()
        order.status = ShopOrderStatus(status)
        order.status_changed_at = now
        order.updated_at = now
        _ = await order.save()
        return order

    async def order_response(self, order: ShopOrder) -> ShopOrderResponse:
        items = await ShopOrderItem.list_by_order(order.shop_order_id)
        return ShopOrderResponse(
            shop_order_id=order.shop_order_id,
            shop_id=order.shop_id,
            public_code=order.public_code,
            status=ShopOrderStatus(order.status),
            customer_name=order.customer_name,
            customer_phone=order.customer_phone,
            delivery_type=order.delivery_type,
            address=order.address,
            table_id=order.table_id,
            table_label=order.table_label,
            comment=order.comment,
            items_total_minor=order.items_total_minor,
            discount_minor=order.discount_minor,
            delivery_fee_minor=order.delivery_fee_minor,
            total_minor=order.total_minor,
            promos=[ShopPromoAppliedResponse.model_validate(p) for p in order.promos],
            currency=order.currency,
            source=order.source,
            created_at=order.created_at.isoformat(),
            items=[
                ShopOrderItemResponse(
                    product_id=i.product_id,
                    name=i.name_snapshot,
                    price_minor=i.price_minor,
                    qty=i.qty,
                    discount_minor=i.discount_minor,
                    modifiers=[
                        ShopOrderItemModifierResponse.model_validate(m) for m in i.modifiers
                    ],
                )
                for i in items
            ],
        )

    async def _allocate_public_code(self) -> str:
        for _ in range(5):
            code = new_public_code()
            if await ShopOrder.get_by_public_code(code) is None:
                return code
        raise PlatformConflictError(
            "Failed to allocate order code", error_code="order_code_exhausted"
        )
