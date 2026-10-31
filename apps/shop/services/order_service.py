"""ShopOrderService — сценарии заказа: приём с витрины, статусная машина.

Авторитетный слой — PostgreSQL; публичный ответ содержит только
``public_code``. Идемпотентность по (shop_id, idempotency_key): повторный
submit формы возвращает тот же заказ без дубля строк.
"""

from __future__ import annotations

from apps.shop.models import (
    Shop,
    ShopDeliveryType,
    ShopOrder,
    ShopOrderItem,
    ShopOrderStatus,
    ShopProduct,
    ShopStatus,
)
from apps.shop.models.api import (
    ShopOrderCreateRequest,
    ShopOrderItemResponse,
    ShopOrderResponse,
)
from apps.shop.models.common import new_id
from apps.shop.models.order import new_public_code
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.utils.time import utcnow

# Допустимые переходы статуса: каждый ключ — из каких статусов можно в него перейти.
_ALLOWED_TRANSITIONS: dict[ShopOrderStatus, frozenset[ShopOrderStatus]] = {
    ShopOrderStatus.ACCEPTED: frozenset({ShopOrderStatus.NEW}),
    ShopOrderStatus.PREPARING: frozenset({ShopOrderStatus.ACCEPTED}),
    ShopOrderStatus.DELIVERING: frozenset({ShopOrderStatus.PREPARING}),
    ShopOrderStatus.DONE: frozenset(
        {ShopOrderStatus.DELIVERING, ShopOrderStatus.PREPARING}
    ),
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
            raise PlatformNotFoundError(
                "Витрина не найдена", error_code="storefront_not_found"
            )
        return shop

    async def create_order(
        self, shop: Shop, payload: ShopOrderCreateRequest
    ) -> ShopOrder:
        """Новый заказ: идемпотентность, расчёт суммы по живым ценам каталога."""
        if shop.status != ShopStatus.PUBLISHED:
            raise PlatformNotFoundError(
                "Витрина недоступна", error_code="storefront_unavailable"
            )
        if payload.honeypot:
            raise PlatformConflictError(
                "Заказ отклонён", error_code="order_rejected"
            )
        if payload.delivery_type == ShopDeliveryType.DELIVERY:
            if not shop.delivery_enabled:
                raise PlatformConflictError(
                    "Доставка не поддерживается магазином",
                    error_code="delivery_disabled",
                )
            if not payload.address:
                raise PlatformConflictError(
                    "Укажите адрес доставки", error_code="address_required"
                )
        if payload.idempotency_key:
            existing = await ShopOrder.get_by_idempotency_key(
                shop.shop_id, payload.idempotency_key
            )
            if existing is not None:
                return existing
        product_ids = [item.product_id for item in payload.items]
        products = await ShopProduct.list_many_by_ids(product_ids)
        by_id = {p.shop_product_id: p for p in products}
        items_total = 0
        order_items: list[ShopOrderItem] = []
        order_id = new_id("shoporder")
        for item in payload.items:
            product = by_id.get(item.product_id)
            if product is None or product.shop_id != shop.shop_id:
                raise PlatformNotFoundError(
                    "Позиция не найдена в каталоге", error_code="product_not_found"
                )
            if not product.is_available:
                raise PlatformConflictError(
                    f"Позиция «{product.name}» недоступна",
                    error_code="product_unavailable",
                )
            items_total += product.price_minor * item.qty
            order_items.append(
                ShopOrderItem(
                    shop_order_item_id=new_id("shoporderitem"),
                    order_id=order_id,
                    product_id=product.shop_product_id,
                    name_snapshot=product.name,
                    price_minor=product.price_minor,
                    qty=item.qty,
                )
            )
        delivery_fee = (
            shop.delivery_fee_minor
            if payload.delivery_type == ShopDeliveryType.DELIVERY
            else 0
        )
        if shop.min_order_minor and items_total < shop.min_order_minor:
            raise PlatformConflictError(
                "Сумма заказа меньше минимальной", error_code="below_min_order"
            )
        now = utcnow()
        order = ShopOrder(
            shop_order_id=order_id,
            shop_id=shop.shop_id,
            public_code=await self._allocate_public_code(),
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            delivery_type=payload.delivery_type,
            address=payload.address,
            comment=payload.comment,
            items_total_minor=items_total,
            delivery_fee_minor=delivery_fee,
            total_minor=items_total + delivery_fee,
            currency=shop.currency,
            source=payload.source,
            idempotency_key=payload.idempotency_key,
            created_at=now,
            updated_at=now,
            status_changed_at=now,
        )
        await ShopOrder.create(order)
        await ShopOrderItem.create_many(order_items)
        return order

    async def get_order_by_code(self, public_code: str) -> ShopOrder:
        order = await ShopOrder.get_by_public_code(public_code)
        if order is None:
            raise PlatformNotFoundError("Заказ не найден", error_code="order_not_found")
        return order

    async def list_orders(
        self,
        company_shop: Shop,
        *,
        status: ShopOrderStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ShopOrder], int]:
        orders = await ShopOrder.list_by_shop(
            company_shop.shop_id, status=status, limit=limit, offset=offset
        )
        total = await ShopOrder.count_by_shop(company_shop.shop_id, status=status)
        return orders, total

    async def get_order(self, company_shop: Shop, order_id: str) -> ShopOrder:
        order = await ShopOrder.get_by_id(order_id)
        if order is None or order.shop_id != company_shop.shop_id:
            raise PlatformNotFoundError("Заказ не найден", error_code="order_not_found")
        return order

    async def set_status(
        self, company_shop: Shop, order_id: str, status: ShopOrderStatus
    ) -> ShopOrder:
        """Переход статуса по разрешённой матрице; конфликт → 409."""
        order = await self.get_order(company_shop, order_id)
        allowed_from = _ALLOWED_TRANSITIONS.get(status, frozenset())
        if order.status not in allowed_from:
            raise PlatformConflictError(
                f"Переход {order.status} → {status} недопустим",
                error_code="order_transition_invalid",
            )
        now = utcnow()
        order.status = status
        order.status_changed_at = now
        order.updated_at = now
        await order.save()
        return order

    async def order_response(self, order: ShopOrder) -> ShopOrderResponse:
        items = await ShopOrderItem.list_by_order(order.shop_order_id)
        return ShopOrderResponse(
            shop_order_id=order.shop_order_id,
            shop_id=order.shop_id,
            public_code=order.public_code,
            status=order.status,
            customer_name=order.customer_name,
            customer_phone=order.customer_phone,
            delivery_type=order.delivery_type,
            address=order.address,
            comment=order.comment,
            items_total_minor=order.items_total_minor,
            delivery_fee_minor=order.delivery_fee_minor,
            total_minor=order.total_minor,
            currency=order.currency,
            source=order.source,
            created_at=order.created_at.isoformat(),
            items=[
                ShopOrderItemResponse(
                    product_id=i.product_id,
                    name=i.name_snapshot,
                    price_minor=i.price_minor,
                    qty=i.qty,
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
            "Не удалось выделить код заказа", error_code="order_code_exhausted"
        )
