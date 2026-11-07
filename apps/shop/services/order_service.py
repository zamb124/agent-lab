"""ShopOrderService — сценарии заказа: приём с витрины, статусная машина.

Авторитетный слой — PostgreSQL; публичный ответ содержит только
``public_code``. Идемпотентность по (shop_id, idempotency_key): повторный
submit формы возвращает тот же заказ без дубля строк.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from apps.shop.config import ShopSettings
from apps.shop.events import (
    SHOP_ORDER_CREATED,
    SHOP_ORDER_STATUS_CHANGED,
    publish_shop_order_event,
)
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
    order_status_label,
)
from apps.shop.models.api import (
    ShopCartPriceLineResponse,
    ShopCartPriceRequest,
    ShopCartPriceResponse,
    ShopMyOrderDetailResponse,
    ShopMyOrderListItemResponse,
    ShopMyOrderShopBlock,
    ShopOrderCreateRequest,
    ShopOrderItemModifierResponse,
    ShopOrderItemPreview,
    ShopOrderItemRequest,
    ShopOrderItemResponse,
    ShopOrderResponse,
    ShopOrderStatusEntry,
    ShopPromoAppliedResponse,
)
from apps.shop.models.common import new_id
from apps.shop.models.order import new_public_code
from apps.shop.services.hours import shop_open_state
from apps.shop.services.modifier_pricing import (
    load_modifier_tree_by_sort_asc,
    nested_lookup,
    validate_and_price,
)
from apps.shop.services.promo_engine import CartLine, PricedCart, evaluate
from apps.shop.tasks.task_names import SHOP_NOTIFY_CUSTOMER, SHOP_NOTIFY_ORDER
from core.clients.geo_client import GeoClient
from core.clients.geocoding.base import Geocoder
from core.clients.service_client import ServiceClient, ServiceClientError
from core.customers.models import CustomerAddress
from core.errors.boundary import (
    PlatformAccessDeniedError,
    PlatformConflictError,
    PlatformNotFoundError,
)
from core.request_scope import CustomerScope
from core.tasks import enqueue
from core.types import JsonObject
from core.utils.geo import is_valid_delivery_zone, point_in_polygon, polygon_ring
from core.utils.time import utcnow


@dataclass
class _PricedItem:
    """Строка корзины с авторитетной ценой за единицу и снапшотом опций."""

    product: ShopProduct
    qty: int
    unit_minor: int
    modifiers_snapshot: list[dict[str, object]]


@dataclass
class _CourierRoute:
    """Метрика дороги курьера + точка магазина (геокод идёт в тот же вызов)."""

    distance_m: float
    duration_s: float
    geometry: JsonObject | None
    shop_lat: float
    shop_lng: float


@dataclass
class _ResolvedPoint:
    """Точка доставки: координаты + каноническое имя адреса источника резолва."""

    lat: float
    lng: float
    normalized: str


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

    def __init__(
        self,
        settings: ShopSettings,
        geocoder: Geocoder,
        service_client: ServiceClient,
    ) -> None:
        self._settings: ShopSettings = settings
        self._geocoder: Geocoder = geocoder
        self._service_client: ServiceClient = service_client

    def _geo(self, shop: Shop) -> GeoClient:
        """GeoClient от имени компании витрины — для анонимных вызовов покупателя."""
        return GeoClient(http=self._service_client, company_id=shop.company_id)

    async def _resolve_point(
        self, shop: Shop, *, address: str, lat: float | None, lng: float | None
    ) -> _ResolvedPoint | None:
        """Точка доставки: явные координаты → geo-справочник → внешний геокодер.

        Свободный текст резолвится сначала тем же адресным справочником geo,
        что и автокомплит витрины — один источник истины; при промахе или
        недоступности geo — ``Geocoder`` (Nominatim). ``None`` — точку
        установить не удалось.
        """
        if lat is not None and lng is not None:
            return _ResolvedPoint(lat=lat, lng=lng, normalized=address)
        if not address.strip():
            return None
        zone = shop.delivery_zone if is_valid_delivery_zone(shop.delivery_zone) else None
        try:
            hits = await self._geo(shop).suggest(q=address.strip(), zone=zone, limit=1)
        except ServiceClientError:
            hits = None
        if hits is not None and hits.items:
            hit = hits.items[0]
            return _ResolvedPoint(lat=hit.lat, lng=hit.lng, normalized=hit.display_name)
        geo = await self._geocoder.geocode(address)
        if geo is None:
            return None
        return _ResolvedPoint(
            lat=geo.lat, lng=geo.lng, normalized=geo.normalized_address or address
        )

    async def _resolve_delivery_point(
        self, shop: Shop, payload: ShopOrderCreateRequest, customer: CustomerScope
    ) -> _ResolvedPoint | None:
        """Точка заказа: сохранённый адрес покупателя, иначе общий резолвер.

        Побочно подменяет ``payload.address`` текстом сохранённого адреса
        (снапшот). Координаты сохранённого адреса авторитетнее клиентских.
        """
        if payload.customer_address_id:
            row = await CustomerAddress.get_for_customer(
                customer.customer_id, payload.customer_address_id
            )
            if row is None:
                raise PlatformConflictError(
                    "Saved address not found", error_code="address_unknown"
                )
            payload.address = row.address
            await CustomerAddress.touch_used(row.customer_address_id)
            if row.lat is not None and row.lng is not None:
                return _ResolvedPoint(lat=row.lat, lng=row.lng, normalized=row.address)
        return await self._resolve_point(
            shop,
            address=payload.address,
            lat=payload.delivery_lat,
            lng=payload.delivery_lng,
        )

    async def check_delivery(
        self,
        shop: Shop,
        address: str,
        lat: float | None = None,
        lng: float | None = None,
    ) -> JsonObject:
        """Живой чек «доставим ли по адресу» для витрины до оформления заказа."""
        if not shop.delivery_enabled:
            return {"ok": False, "reason": "delivery_disabled"}
        ring = polygon_ring(shop.delivery_zone)
        point = await self._resolve_point(shop, address=address, lat=lat, lng=lng)
        if point is None:
            return {
                "ok": ring is None,
                "reason": "address_unverifiable" if ring is not None else "ok",
                "requires_zone": ring is not None,
            }
        result: JsonObject = {
            "ok": True,
            "normalized": point.normalized,
            "lat": point.lat,
            "lng": point.lng,
            "requires_zone": ring is not None,
        }
        if ring is not None:
            inside = point_in_polygon(point.lng, point.lat, ring)
            result["ok"] = inside
            result["inside_zone"] = inside
            if not inside:
                result["reason"] = "out_of_delivery_zone"
        if result["ok"]:
            await self._enrich_route(shop, point.lat, point.lng, result)
        return result

    async def address_reverse(self, shop: Shop, *, lat: float, lng: float) -> JsonObject:
        """Ближайший адрес к точке пина — имя для отображения в чекауте.

        Координаты пина остаются точкой заказа; имя адреса — только подпись,
        дальше ``address_snap_max_m`` считается нерелевантной.
        """
        try:
            hits = await self._geo(shop).nearest(lat=lat, lng=lng, limit=1)
        except ServiceClientError:
            return {"found": False, "geo_unavailable": True}
        if not hits.items:
            return {"found": False}
        hit = hits.items[0]
        if hit.distance_m is not None and hit.distance_m > self._settings.address_snap_max_m:
            return {"found": False}
        return {
            "found": True,
            "display_name": hit.display_name,
            "lat": hit.lat,
            "lng": hit.lng,
            "distance_m": hit.distance_m,
        }

    async def _courier_route(
        self, shop: Shop, cust_lat: float, cust_lng: float
    ) -> _CourierRoute | None:
        """Дистанция/время дороги курьера до адреса по ``shop.courier_mode``.

        Деградация: geo недоступен → ``None``; чек и заказ остаются рабочими.
        """
        shop_lat: float | None = shop.lat
        shop_lng: float | None = shop.lng
        if shop_lat is None or shop_lng is None:
            if not shop.address.strip():
                return None
            shop_geo = await self._geocoder.geocode(shop.address)
            if shop_geo is None:
                return None
            shop_lat, shop_lng = shop_geo.lat, shop_geo.lng
        try:
            route = await self._geo(shop).route_calculate(
                from_lat=shop_lat,
                from_lng=shop_lng,
                to_lat=cust_lat,
                to_lng=cust_lng,
                mode=shop.courier_mode,
            )
        except ServiceClientError:
            return None
        return _CourierRoute(
            distance_m=route.distance_m,
            duration_s=route.duration_s,
            geometry=route.geometry,
            shop_lat=shop_lat,
            shop_lng=shop_lng,
        )

    async def _enrich_route(
        self, shop: Shop, cust_lat: float, cust_lng: float, result: JsonObject
    ) -> None:
        """Дорожная метрика курьера + ETA (готовка + дорога) в чек доставки.

        Деградация явная: geo недоступен → метрик в ответе просто нет,
        чек доставки остаётся рабочим.
        """
        routed = await self._courier_route(shop, cust_lat, cust_lng)
        if routed is None:
            return
        result["distance_m"] = routed.distance_m
        result["duration_s"] = routed.duration_s
        result["courier_travel_s"] = routed.duration_s
        result["courier_mode"] = shop.courier_mode
        result["prep_minutes"] = shop.prep_minutes
        result["eta_minutes"] = int(
            -(-(shop.prep_minutes * 60 + routed.duration_s) // 60)
        )

    async def address_suggest(
        self,
        shop: Shop,
        query: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
    ) -> JsonObject:
        """Автокомплит адреса покупателя по справочнику внутри зоны доставки.

        ``lat``/``lng`` — необязательная точка покупателя (геолокация/пин):
        сортировка выдачи по близости. Деградация: geo недоступен → пустой
        список, витрина откатывается на свободный ввод.
        """
        zone = shop.delivery_zone if is_valid_delivery_zone(shop.delivery_zone) else None
        try:
            hits = await self._geo(shop).suggest(q=query, zone=zone, lat=lat, lng=lng, limit=8)
        except ServiceClientError:
            return {"items": [], "geo_unavailable": True}
        return {
            "items": [
                {
                    "display_name": h.display_name,
                    "lat": h.lat,
                    "lng": h.lng,
                    "city": h.city,
                    "street": h.street,
                    "housenumber": h.housenumber,
                    "postcode": h.postcode,
                }
                for h in hits.items
            ]
        }

    async def resolve_published_shop(self, slug: str) -> Shop:
        """Опубликованная витрина по slug для публичного заказа."""
        shop = await Shop.get_by_slug(slug)
        if shop is None or shop.status != ShopStatus.PUBLISHED:
            raise PlatformNotFoundError("Storefront not found", error_code="storefront_not_found")
        return shop

    async def create_order(
        self, shop: Shop, payload: ShopOrderCreateRequest, *, customer: CustomerScope
    ) -> ShopOrder:
        """Новый заказ: идемпотентность, расчёт суммы по живым ценам каталога.

        Телефон и имя покупателя — из верифицированной сессии `customer`
        (customers.mdc), не из ввода формы; компания витрины обязана входить
        во `scope_company_ids` сессии (витрины, где номер подтверждали).
        """
        if str(shop.company_id) not in customer.company_ids:
            raise PlatformAccessDeniedError(
                "Customer session scope does not match this storefront",
                error_code="forbidden_scope",
            )
        open_state = shop_open_state(shop.working_hours, shop.timezone, utcnow())
        if not open_state.open:
            raise PlatformConflictError(
                "Shop is closed now",
                error_code="shop_closed",
                error_params={"next_open": open_state.next_open or ""},
            )
        if shop.status != ShopStatus.PUBLISHED:
            raise PlatformNotFoundError(
                "Storefront unavailable", error_code="storefront_unavailable"
            )
        if payload.honeypot:
            raise PlatformConflictError("Order rejected", error_code="order_rejected")
        delivery_eta: int | None = None
        delivery_route: JsonObject = {}
        delivery_lat: float | None = None
        delivery_lng: float | None = None
        shop_lat: float | None = None
        shop_lng: float | None = None
        if payload.delivery_type == ShopDeliveryType.DELIVERY:
            if not shop.delivery_enabled:
                raise PlatformConflictError(
                    "Delivery is not supported by the shop",
                    error_code="delivery_disabled",
                )
            if not payload.address and not payload.customer_address_id:
                raise PlatformConflictError(
                    "Delivery address is required", error_code="address_required"
                )
            point = await self._resolve_delivery_point(shop, payload, customer)
            if point is not None:
                delivery_lat, delivery_lng = point.lat, point.lng
                if point.normalized.strip():
                    payload.address = point.normalized
            ring = polygon_ring(shop.delivery_zone)
            if ring is not None:
                if point is None:
                    raise PlatformConflictError(
                        "Delivery address could not be verified",
                        error_code="address_unverifiable",
                    )
                if not point_in_polygon(point.lng, point.lat, ring):
                    raise PlatformConflictError(
                        "Address is outside the delivery zone",
                        error_code="out_of_delivery_zone",
                    )
            if point is not None:
                routed = await self._courier_route(shop, point.lat, point.lng)
                if routed is not None:
                    delivery_eta = int(
                        -(-(shop.prep_minutes * 60 + routed.duration_s) // 60)
                    )
                    delivery_route = routed.geometry or {}
                    shop_lat, shop_lng = routed.shop_lat, routed.shop_lng
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
            customer_phone=customer.phone_e164,
            customer_id=customer.customer_id,
            delivery_type=payload.delivery_type,
            address=payload.address,
            delivery_eta_minutes=delivery_eta,
            delivery_route=delivery_route,
            delivery_lat=delivery_lat,
            delivery_lng=delivery_lng,
            shop_lat=shop_lat,
            shop_lng=shop_lng,
            delivery_flat=payload.delivery_flat,
            delivery_entrance=payload.delivery_entrance,
            delivery_floor=payload.delivery_floor,
            delivery_intercom=payload.delivery_intercom,
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
            status_history=[{"status": ShopOrderStatus.NEW.value, "at": now.isoformat()}],
        )
        _ = await ShopOrder.create(order)
        _ = await ShopOrderItem.create_many(order_items)
        await self._after_created(shop, order)
        return order

    async def _after_created(self, shop: Shop, order: ShopOrder) -> None:
        """Факт создания: доменное событие + уведомления владельцу и покупателю."""
        await publish_shop_order_event(
            SHOP_ORDER_CREATED,
            shop_id=shop.shop_id,
            shop_order_id=order.shop_order_id,
            public_code=order.public_code,
            status=ShopOrderStatus(order.status),
            status_label=order_status_label(
                ShopOrderStatus(order.status), order.delivery_type
            ),
            delivery_type=order.delivery_type,
            total_minor=order.total_minor,
            currency=order.currency,
            company_id=str(shop.company_id),
        )
        _ = await enqueue(SHOP_NOTIFY_ORDER, shop_order_id=order.shop_order_id)
        _ = await enqueue(SHOP_NOTIFY_CUSTOMER, shop_order_id=order.shop_order_id)

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
        if (
            order.status not in allowed_from
            or (
                ShopOrderStatus(status) == ShopOrderStatus.DELIVERING
                and order.delivery_type != ShopDeliveryType.DELIVERY
            )
        ):
            raise PlatformConflictError(
                f"Transition {order.status} -> {status} is not allowed",
                error_code="order_transition_invalid",
            )
        now = utcnow()
        order.status = ShopOrderStatus(status)
        order.status_changed_at = now
        order.updated_at = now
        history = list(order.status_history or [])
        history.append({"status": ShopOrderStatus(status).value, "at": now.isoformat()})
        order.status_history = history
        _ = await order.save()
        await self._after_status_change(company_shop, order)
        return order

    async def _after_status_change(self, shop: Shop, order: ShopOrder) -> None:
        """Факт смены статуса: доменное событие + уведомления обеим сторонам."""
        await publish_shop_order_event(
            SHOP_ORDER_STATUS_CHANGED,
            shop_id=shop.shop_id,
            shop_order_id=order.shop_order_id,
            public_code=order.public_code,
            status=ShopOrderStatus(order.status),
            status_label=order_status_label(
                ShopOrderStatus(order.status), order.delivery_type
            ),
            delivery_type=order.delivery_type,
            total_minor=order.total_minor,
            currency=order.currency,
            company_id=str(shop.company_id),
        )
        _ = await enqueue(SHOP_NOTIFY_ORDER, shop_order_id=order.shop_order_id)
        _ = await enqueue(SHOP_NOTIFY_CUSTOMER, shop_order_id=order.shop_order_id)

    async def list_customer_orders(
        self,
        customer_id: str,
        *,
        statuses: list[ShopOrderStatus] | None = None,
        limit: int = 30,
        offset: int = 0,
    ) -> tuple[list[ShopOrder], dict[str, Shop], dict[str, list[ShopOrderItem]], int]:
        """Сквозная история покупателя: заказы всех витрин + магазины и
        позиции пачкой (без N+1)."""
        orders = await ShopOrder.list_by_customer_by_created_desc(
            customer_id, statuses=statuses, limit=limit, offset=offset
        )
        total = await ShopOrder.count_by_customer(customer_id, statuses=statuses)
        shops = await Shop.list_many_by_ids([o.shop_id for o in orders])
        items = await ShopOrderItem.list_many_by_order_ids(
            [o.shop_order_id for o in orders]
        )
        items_by_order: dict[str, list[ShopOrderItem]] = {}
        for i in items:
            items_by_order.setdefault(i.order_id, []).append(i)
        return orders, {s.shop_id: s for s in shops}, items_by_order, total

    async def customer_order_detail(
        self, customer_id: str, public_code: str
    ) -> tuple[ShopOrder, Shop | None, list[ShopOrderItem]]:
        """Детали заказа покупателя; чужой `public_code` — not-found."""
        order = await ShopOrder.get_by_public_code(public_code)
        if order is None or order.customer_id != customer_id:
            raise PlatformNotFoundError("Order not found", error_code="order_not_found")
        items = await ShopOrderItem.list_by_order(order.shop_order_id)
        shop = await Shop.get_by_id(order.shop_id)
        return order, shop, items

    async def customer_cancel(self, customer_id: str, public_code: str) -> ShopOrder:
        """Отмена покупателем из кабинета: только пока заказ новый."""
        order = await ShopOrder.get_by_public_code(public_code)
        if order is None or order.customer_id != customer_id:
            raise PlatformNotFoundError("Order not found", error_code="order_not_found")
        shop = await Shop.get_by_id(order.shop_id)
        if shop is None:
            raise PlatformNotFoundError(
                "Storefront not found", error_code="storefront_not_found"
            )
        return await self.set_status(shop, order.shop_order_id, ShopOrderStatus.CANCELLED)

    async def order_response(self, order: ShopOrder) -> ShopOrderResponse:
        items = await ShopOrderItem.list_by_order(order.shop_order_id)
        photos = await self._item_photos(items)
        return ShopOrderResponse(
            shop_order_id=order.shop_order_id,
            shop_id=order.shop_id,
            public_code=order.public_code,
            status=ShopOrderStatus(order.status),
            status_label=order_status_label(
                ShopOrderStatus(order.status), order.delivery_type
            ),
            customer_id=order.customer_id,
            customer_name=order.customer_name,
            customer_phone=order.customer_phone,
            delivery_type=order.delivery_type,
            address=order.address,
            delivery_eta_minutes=order.delivery_eta_minutes,
            delivery_flat=order.delivery_flat,
            delivery_entrance=order.delivery_entrance,
            delivery_floor=order.delivery_floor,
            delivery_intercom=order.delivery_intercom,
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
                    photo_file_id=photos.get(i.product_id),
                    modifiers=[
                        ShopOrderItemModifierResponse.model_validate(m) for m in i.modifiers
                    ],
                )
                for i in items
            ],
        )

    @staticmethod
    async def _item_photos(items: list[ShopOrderItem]) -> dict[str, str]:
        """Фото позиций заказа — join по текущему товару (дисплейные данные)."""
        ids = [i.product_id for i in items if i.product_id]
        products = await ShopProduct.list_many_by_ids(ids) if ids else []
        return {p.shop_product_id: p.photo_file_id for p in products if p.photo_file_id}

    async def _allocate_public_code(self) -> str:
        for _ in range(5):
            code = new_public_code()
            if await ShopOrder.get_by_public_code(code) is None:
                return code
        raise PlatformConflictError(
            "Failed to allocate order code", error_code="order_code_exhausted"
        )

    # --- Кабинет покупателя: сборка ответов `my/orders` ---

    @staticmethod
    def _active(status: ShopOrderStatus) -> bool:
        return ShopOrderStatus(status) not in (
            ShopOrderStatus.DONE,
            ShopOrderStatus.CANCELLED,
        )

    def _shop_block(
        self,
        shop: Shop | None,
        order: ShopOrder,
        *,
        storefront_url: str,
    ) -> ShopMyOrderShopBlock:
        """Блок «магазин» в ответе кабинета; витрина могла быть удалена."""
        if shop is None:
            return ShopMyOrderShopBlock(
                shop_id=order.shop_id,
                slug="",
                name="",
                lat=order.shop_lat,
                lng=order.shop_lng,
            )
        open_state = shop_open_state(shop.working_hours, shop.timezone, utcnow())
        return ShopMyOrderShopBlock(
            shop_id=shop.shop_id,
            slug=shop.slug,
            name=shop.name,
            kind=shop.kind,
            logo_file_id=shop.logo_file_id,
            phone=shop.phone,
            address=shop.address,
            city=shop.city,
            working_hours=shop.working_hours,
            open_now=open_state.open,
            is_published=shop.status == ShopStatus.PUBLISHED,
            storefront_url=storefront_url,
            lat=order.shop_lat,
            lng=order.shop_lng,
        )

    def my_order_list_item(
        self,
        order: ShopOrder,
        shop: Shop | None,
        *,
        storefront_url: str,
        items_preview: list[ShopOrderItemPreview] | None = None,
    ) -> ShopMyOrderListItemResponse:
        """Строка ленты `my/orders`: заказ + витрина, где он исполняется."""
        return ShopMyOrderListItemResponse(
            public_code=order.public_code,
            status=ShopOrderStatus(order.status),
            status_label=order_status_label(
                ShopOrderStatus(order.status), order.delivery_type
            ),
            status_changed_at=order.status_changed_at.isoformat(),
            created_at=order.created_at.isoformat(),
            active=self._active(ShopOrderStatus(order.status)),
            total_minor=order.total_minor,
            currency=order.currency,
            delivery_type=order.delivery_type,
            address=order.address,
            table_label=order.table_label,
            delivery_eta_minutes=order.delivery_eta_minutes,
            items_preview=items_preview or [],
            items_count=len(items_preview or []),
            shop=self._shop_block(shop, order, storefront_url=storefront_url),
        )

    async def my_order_detail(
        self,
        order: ShopOrder,
        shop: Shop | None,
        items: list[ShopOrderItem],
        *,
        storefront_url: str,
    ) -> ShopMyOrderDetailResponse:
        """Полная карточка заказа кабинета: позиции, таймлайн, гео доставки."""
        photos = await self._item_photos(items)
        base = self.my_order_list_item(
            order,
            shop,
            storefront_url=storefront_url,
            items_preview=[
                ShopOrderItemPreview(name=i.name_snapshot, qty=i.qty) for i in items
            ],
        )
        data = base.model_dump()
        return ShopMyOrderDetailResponse.model_validate(
            {
                **data,
                "items_total_minor": order.items_total_minor,
                "discount_minor": order.discount_minor,
                "delivery_fee_minor": order.delivery_fee_minor,
                "comment": order.comment,
                "promos": [
                    ShopPromoAppliedResponse.model_validate(p).model_dump()
                    for p in order.promos
                ],
                "items": [
                    ShopOrderItemResponse(
                        product_id=i.product_id,
                        name=i.name_snapshot,
                        price_minor=i.price_minor,
                        qty=i.qty,
                        discount_minor=i.discount_minor,
                        photo_file_id=photos.get(i.product_id),
                        modifiers=[
                            ShopOrderItemModifierResponse.model_validate(m)
                            for m in i.modifiers
                        ],
                    ).model_dump()
                    for i in items
                ],
                "status_history": [
                    ShopOrderStatusEntry.model_validate(e).model_dump()
                    for e in (order.status_history or [])
                ],
                "status_labels": {
                    s.value: order_status_label(s, order.delivery_type)
                    for s in ShopOrderStatus
                },
                "can_cancel": ShopOrderStatus(order.status) == ShopOrderStatus.NEW,
                "delivery_lat": order.delivery_lat,
                "delivery_lng": order.delivery_lng,
                "delivery_flat": order.delivery_flat,
                "delivery_entrance": order.delivery_entrance,
                "delivery_floor": order.delivery_floor,
                "delivery_intercom": order.delivery_intercom,
                "delivery_route": order.delivery_route or {},
                "delivery_zone": (shop.delivery_zone if shop is not None else {}) or {},
            }
        )
