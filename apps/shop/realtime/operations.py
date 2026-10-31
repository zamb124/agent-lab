"""Бизнес-функции shop: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from pydantic import Field

from apps.shop.di import Di
from apps.shop.models import ShopDomain
from apps.shop.models.api import (
    ShopCategoryCreateRequest,
    ShopCategoryResponse,
    ShopCategoryUpdateRequest,
    ShopCreateRequest,
    ShopOrderCreatedResponse,
    ShopOrderCreateRequest,
    ShopOrderResponse,
    ShopOrderStatusResponse,
    ShopProductCreateRequest,
    ShopProductResponse,
    ShopProductUpdateRequest,
    ShopResponse,
    ShopTheme,
    ShopUpdateRequest,
)
from apps.shop.models.enums import ShopOrderStatus
from apps.shop.tasks.task_names import (
    SHOP_NOTIFY_ORDER,
    SHOP_PROVISION_DOMAIN,
    SHOP_REBUILD_STOREFRONT,
)
from core.errors.boundary import (
    PlatformBoundaryError,
    PlatformConflictError,
    PlatformNotFoundError,
)
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.pagination import ListResponse, OffsetPage
from core.request_scope import require_company_admin, require_company_viewer
from core.tasks import enqueue
from core.websocket import (
    EmptyPayload,
    raise_conflict,
    raise_not_found,
)


class ShopIdPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)


class ShopUpdatePayload(ShopUpdateRequest):
    shop_id: str = Field(min_length=1)


class ShopDomainAddPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    domain: str = Field(min_length=4, max_length=253)


class ShopDomainIdPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    shop_domain_id: str = Field(min_length=1)


class ShopCategoryIdPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    shop_category_id: str = Field(min_length=1)


class ShopCategoryCreatePayload(ShopCategoryCreateRequest):
    shop_id: str = Field(min_length=1)


class ShopCategoryUpdatePayload(ShopCategoryUpdateRequest):
    shop_id: str = Field(min_length=1)
    shop_category_id: str = Field(min_length=1)


class ShopProductIdPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    shop_product_id: str = Field(min_length=1)


class ShopProductCreatePayload(ShopProductCreateRequest):
    shop_id: str = Field(min_length=1)


class ShopProductUpdatePayload(ShopProductUpdateRequest):
    shop_id: str = Field(min_length=1)
    shop_product_id: str = Field(min_length=1)


class ShopOrderListPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    status: ShopOrderStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ShopOrderIdPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    shop_order_id: str = Field(min_length=1)


class ShopOrderSetStatusPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    shop_order_id: str = Field(min_length=1)
    status: ShopOrderStatus


class ShopOrderCreatePayload(ShopOrderCreateRequest):
    """Заказ с витрины: магазин резолвится по slug — анонимный вызов."""

    slug: str = Field(min_length=3, max_length=40)


class ShopPublicOrderStatusPayload(StrictBaseModel):
    public_code: str = Field(min_length=4, max_length=16)


def _shop_response(shop, di: Di) -> ShopResponse:  # noqa: ANN001 — Shop из сервиса
    return ShopResponse(
        shop_id=shop.shop_id,
        slug=shop.slug,
        kind=shop.kind,
        name=shop.name,
        description=shop.description,
        logo_file_id=shop.logo_file_id,
        cover_file_id=shop.cover_file_id,
        phone=shop.phone,
        city=shop.city,
        address=shop.address,
        timezone=shop.timezone,
        working_hours=shop.working_hours.get("days", {}),
        delivery_enabled=shop.delivery_enabled,
        pickup_enabled=shop.pickup_enabled,
        delivery_fee_minor=shop.delivery_fee_minor,
        min_order_minor=shop.min_order_minor,
        currency=shop.currency,
        theme=ShopTheme.model_validate(shop.theme or {}),
        status=shop.status,
        telegram_chat_id=shop.telegram_chat_id,
        storefront_url=f"https://{shop.slug}.{di.settings.storefront_domain_suffix}",
        plan=shop.plan,
    )


def _category_response(category) -> ShopCategoryResponse:  # noqa: ANN001
    return ShopCategoryResponse(
        shop_category_id=category.shop_category_id,
        shop_id=category.shop_id,
        name=category.name,
        sort=category.sort,
        is_active=category.is_active,
    )


def _product_response(product) -> ShopProductResponse:  # noqa: ANN001
    return ShopProductResponse(
        shop_product_id=product.shop_product_id,
        shop_id=product.shop_id,
        category_id=product.category_id,
        name=product.name,
        description=product.description,
        price_minor=product.price_minor,
        photo_file_id=product.photo_file_id,
        is_available=product.is_available,
        sort=product.sort,
    )


async def _enqueue_rebuild(di: Di, shop_id: str, slug: str) -> None:
    """Инвалидация витрины после мутации: ключ удаляется синхронно
    (suspend/unavailable скрываются немедленно), воркер прогревает кэш."""
    await di.storefront_service.invalidate_snapshot(shop_id)
    await enqueue(SHOP_REBUILD_STOREFRONT, slug=slug)


# --- Витрины (админ) ---


async def op_shops_list(
    payload: EmptyPayload, *, user: User, di: Di
) -> ListResponse[ShopResponse]:
    scope = await require_company_admin(di.authz_service)
    _ = (payload, user)
    shops = await di.shop_service.list_shops(scope.company_id)
    return ListResponse(items=[_shop_response(s, di) for s in shops])


async def op_shops_create(
    payload: ShopCreateRequest, *, user: User, di: Di
) -> ShopResponse:
    scope = await require_company_admin(di.authz_service)
    try:
        shop = await di.shop_service.create_shop(scope.company_id, scope.user_id, payload)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    return _shop_response(shop, di)


async def op_shops_get(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ShopResponse:
    scope = await require_company_viewer(di.authz_service)
    _ = user
    try:
        shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return _shop_response(shop, di)


async def op_shops_update(
    payload: ShopUpdatePayload, *, user: User, di: Di
) -> ShopResponse:
    scope = await require_company_admin(di.authz_service)
    try:
        shop = await di.shop_service.update_shop(scope.company_id, payload.shop_id, payload)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return _shop_response(shop, di)


async def op_shops_publish(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ShopResponse:
    scope = await require_company_admin(di.authz_service)
    try:
        shop = await di.shop_service.publish_shop(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return _shop_response(shop, di)


async def op_shops_suspend(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ShopResponse:
    scope = await require_company_admin(di.authz_service)
    try:
        shop = await di.shop_service.suspend_shop(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return _shop_response(shop, di)


async def op_shops_remove(
    payload: ShopIdPayload, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    try:
        shop = await di.shop_service.delete_shop(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return EmptyPayload()


# --- Категории ---


async def op_categories_list(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ListResponse[ShopCategoryResponse]:
    scope = await require_company_viewer(di.authz_service)
    try:
        categories = await di.shop_service.list_categories(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ListResponse(items=[_category_response(c) for c in categories])


async def op_categories_create(
    payload: ShopCategoryCreatePayload, *, user: User, di: Di
) -> ShopCategoryResponse:
    scope = await require_company_admin(di.authz_service)
    try:
        category = await di.shop_service.create_category(scope.company_id, payload.shop_id, payload)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return _category_response(category)


async def op_categories_update(
    payload: ShopCategoryUpdatePayload, *, user: User, di: Di
) -> ShopCategoryResponse:
    scope = await require_company_admin(di.authz_service)
    try:
        category = await di.shop_service.update_category(
            scope.company_id, payload.shop_id, payload.shop_category_id, payload
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return _category_response(category)


async def op_categories_remove(
    payload: ShopCategoryIdPayload, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    try:
        await di.shop_service.delete_category(
            scope.company_id, payload.shop_id, payload.shop_category_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return EmptyPayload()


# --- Товары ---


async def op_products_list(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ListResponse[ShopProductResponse]:
    scope = await require_company_viewer(di.authz_service)
    try:
        products = await di.shop_service.list_products(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ListResponse(items=[_product_response(p) for p in products])


async def op_products_create(
    payload: ShopProductCreatePayload, *, user: User, di: Di
) -> ShopProductResponse:
    scope = await require_company_admin(di.authz_service)
    try:
        product = await di.shop_service.create_product(scope.company_id, payload.shop_id, payload)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return _product_response(product)


async def op_products_update(
    payload: ShopProductUpdatePayload, *, user: User, di: Di
) -> ShopProductResponse:
    scope = await require_company_admin(di.authz_service)
    try:
        product = await di.shop_service.update_product(
            scope.company_id, payload.shop_id, payload.shop_product_id, payload
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return _product_response(product)


async def op_products_remove(
    payload: ShopProductIdPayload, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    try:
        await di.shop_service.delete_product(
            scope.company_id, payload.shop_id, payload.shop_product_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return EmptyPayload()


# --- Заказы (админ) ---


async def op_orders_list(
    payload: ShopOrderListPayload, *, user: User, di: Di
) -> OffsetPage[ShopOrderResponse]:
    scope = await require_company_viewer(di.authz_service)
    try:
        shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
        orders, total = await di.order_service.list_orders(
            shop, status=payload.status, limit=payload.limit, offset=payload.offset
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return OffsetPage(
        items=[await di.order_service.order_response(o) for o in orders],
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_orders_get(
    payload: ShopOrderIdPayload, *, user: User, di: Di
) -> ShopOrderResponse:
    scope = await require_company_viewer(di.authz_service)
    try:
        shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
        order = await di.order_service.get_order(shop, payload.shop_order_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return await di.order_service.order_response(order)


async def op_orders_set_status(
    payload: ShopOrderSetStatusPayload, *, user: User, di: Di
) -> ShopOrderResponse:
    scope = await require_company_admin(di.authz_service)
    try:
        shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
        order = await di.order_service.set_status(shop, payload.shop_order_id, payload.status)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    await enqueue(SHOP_NOTIFY_ORDER, shop_order_id=order.shop_order_id)
    return await di.order_service.order_response(order)


# --- Домены ---


async def op_domains_add(payload: ShopDomainAddPayload, *, user: User, di: Di) -> ShopDomain:
    scope = await require_company_admin(di.authz_service)
    try:
        return await di.shop_service.add_domain(scope.company_id, payload.shop_id, payload.domain)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)


async def op_domains_remove(
    payload: ShopDomainIdPayload, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    try:
        await di.shop_service.remove_domain(scope.company_id, payload.shop_id, payload.shop_domain_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return EmptyPayload()


async def op_domains_provision(
    payload: ShopDomainIdPayload, *, user: User, di: Di
) -> ShopDomain:
    """DNS-проверка и провиженинг через воркер: HTTP ждёт wait_result."""
    _ = await require_company_admin(di.authz_service)
    task = await enqueue(SHOP_PROVISION_DOMAIN, shop_domain_id=payload.shop_domain_id)
    await task.wait_result(timeout=di.settings.taskiq_wait_timeout)
    record = await ShopDomain.objects.filter(
        shop_domain_id=payload.shop_domain_id
    ).get_or_none()
    if record is None:
        raise_not_found(PlatformNotFoundError("Домен не найден", error_code="domain_not_found"))
    return record


# --- Публичные операции (анонимный вызов витрины) ---


async def op_public_order_create(
    payload: ShopOrderCreatePayload, *, user: User, di: Di
) -> ShopOrderCreatedResponse:
    """Создать заказ на витрине по slug: анонимный путь, авторизация не нужна."""
    _ = user
    try:
        shop = await di.order_service.resolve_published_shop(payload.slug)
        order = await di.order_service.create_order(shop, payload)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    except PlatformBoundaryError as exc:
        raise_conflict(exc)
    await enqueue(SHOP_NOTIFY_ORDER, shop_order_id=order.shop_order_id)
    return ShopOrderCreatedResponse(
        public_code=order.public_code,
        status=order.status,
        total_minor=order.total_minor,
        currency=order.currency,
    )


async def op_public_order_status(
    payload: ShopPublicOrderStatusPayload, *, user: User, di: Di
) -> ShopOrderStatusResponse:
    """Статус заказа по публичному коду: анонимный путь."""
    _ = user
    try:
        order = await di.order_service.get_order_by_code(payload.public_code)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ShopOrderStatusResponse(
        public_code=order.public_code,
        status=order.status,
        total_minor=order.total_minor,
        currency=order.currency,
        delivery_type=order.delivery_type,
        created_at=order.created_at.isoformat(),
    )
