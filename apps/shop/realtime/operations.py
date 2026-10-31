"""Бизнес-функции shop: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from pydantic import Field

from apps.shop.di import Di
from apps.shop.events import (
    SHOP_ORDER_CREATED,
    SHOP_ORDER_STATUS_CHANGED,
    SHOP_SHOP_CREATED,
    SHOP_SHOP_PUBLISHED,
    SHOP_SHOP_UPDATED,
    publish_shop_catalog_changed,
    publish_shop_event,
    publish_shop_order_event,
)
from apps.shop.models import Shop, ShopCategory, ShopDomain, ShopProduct
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
    ShopProductsImportRequest,
    ShopProductsImportResponse,
    ShopProductUpdateRequest,
    ShopResponse,
    ShopTheme,
    ShopUpdateRequest,
)
from apps.shop.models.enums import ShopOrderStatus
from apps.shop.tasks.task_names import (
    SHOP_AI_DESCRIBE_BATCH,
    SHOP_NOTIFY_ORDER,
    SHOP_PROVISION_DOMAIN,
    SHOP_REBUILD_STOREFRONT,
)
from core.errors.boundary import (
    PlatformBoundaryError,
    PlatformConflictError,
    PlatformNotFoundError,
    PlatformUnavailableError,
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
    raise_unavailable,
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


class ShopProductsImportPayload(ShopProductsImportRequest):
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


class ShopAiDescribePayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=300)
    category_name: str | None = Field(default=None, max_length=200)
    photo_file_id: str | None = None


class ShopAiEnhancePhotoPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    file_id: str = Field(min_length=1)


class ShopTelegramConnectPayload(StrictBaseModel):
    shop_id: str
    bot_token: str = Field(min_length=20, max_length=128)


class ShopAiGeneratePhotoPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=1000)


class ShopAiDescribeBatchPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)


class ShopAiTextResponse(StrictBaseModel):
    text: str


class ShopAiFileResponse(StrictBaseModel):
    file_id: str


class ShopAiBatchResponse(StrictBaseModel):
    enqueued: int


async def _shop_response(shop: Shop, di: Di) -> ShopResponse:
    products_count = await ShopProduct.objects.filter(shop_id=shop.shop_id).count()
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
        working_hours={
            str(day): str(hours) for day, hours in shop.working_hours.items()
        },
        delivery_enabled=shop.delivery_enabled,
        pickup_enabled=shop.pickup_enabled,
        delivery_fee_minor=shop.delivery_fee_minor,
        min_order_minor=shop.min_order_minor,
        currency=shop.currency,
        theme=ShopTheme.model_validate(shop.theme or {}),
        status=shop.status,
        telegram_chat_id=shop.telegram_chat_id,
        telegram_connected=bool(shop.telegram_bot_token),
        storefront_url=f"https://{shop.slug}.{di.settings.storefront_domain_suffix}",
        plan=shop.plan,
        products_count=products_count,
    )


def _category_response(category: ShopCategory) -> ShopCategoryResponse:
    return ShopCategoryResponse(
        shop_category_id=category.shop_category_id,
        shop_id=category.shop_id,
        name=category.name,
        sort=category.sort,
        is_active=category.is_active,
    )


def _product_response(product: ShopProduct) -> ShopProductResponse:
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


async def _enqueue_rebuild(
    di: Di, shop_id: str, slug: str, *, catalog_changed: bool = False
) -> None:
    """Инвалидация витрины после мутации: ключ удаляется синхронно
    (suspend/unavailable скрываются немедленно), воркер прогревает кэш.
    Каталожные мутации дополнительно публикуют `shop/catalog/changed` —
    по этому событию flows-триггеры реагируют на обновление меню."""
    await di.storefront_service.invalidate_snapshot(shop_id)
    if catalog_changed:
        shop = await Shop.get_by_id(shop_id)
        if shop is not None:
            await publish_shop_catalog_changed(
                shop_id, slug, str(shop.company_id)
            )
    _ = await enqueue(SHOP_REBUILD_STOREFRONT, slug=slug)


# --- Витрины (админ) ---


async def op_shops_list(
    payload: EmptyPayload, *, user: User, di: Di
) -> ListResponse[ShopResponse]:
    scope = await require_company_admin(di.authz_service)
    _ = (payload, user)
    shops = await di.shop_service.list_shops(scope.company_id)
    return ListResponse(items=[await _shop_response(s, di) for s in shops])


async def op_shops_create(
    payload: ShopCreateRequest, *, user: User, di: Di
) -> ShopResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        shop = await di.shop_service.create_shop(scope.company_id, scope.user_id, payload)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    await publish_shop_event(
        SHOP_SHOP_CREATED, shop.shop_id, shop.slug, shop.status, scope.company_id
    )
    return await _shop_response(shop, di)


async def op_shops_get(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ShopResponse:
    scope = await require_company_viewer(di.authz_service)
    _ = user
    try:
        shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return await _shop_response(shop, di)


async def op_shops_update(
    payload: ShopUpdatePayload, *, user: User, di: Di
) -> ShopResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        shop = await di.shop_service.update_shop(scope.company_id, payload.shop_id, payload)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    await publish_shop_event(
        SHOP_SHOP_UPDATED, shop.shop_id, shop.slug, shop.status, scope.company_id
    )
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return await _shop_response(shop, di)


async def op_shops_publish(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ShopResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        shop = await di.shop_service.publish_shop(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    await publish_shop_event(
        SHOP_SHOP_PUBLISHED, shop.shop_id, shop.slug, shop.status, scope.company_id
    )
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return await _shop_response(shop, di)


async def op_shops_suspend(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ShopResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        shop = await di.shop_service.suspend_shop(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    await publish_shop_event(
        SHOP_SHOP_UPDATED, shop.shop_id, shop.slug, shop.status, scope.company_id
    )
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return await _shop_response(shop, di)


async def op_shops_remove(
    payload: ShopIdPayload, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
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
    _ = user
    try:
        categories = await di.shop_service.list_categories(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ListResponse(items=[_category_response(c) for c in categories])


async def op_categories_create(
    payload: ShopCategoryCreatePayload, *, user: User, di: Di
) -> ShopCategoryResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        category = await di.shop_service.create_category(scope.company_id, payload.shop_id, payload)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug, catalog_changed=True)
    return _category_response(category)


async def op_categories_update(
    payload: ShopCategoryUpdatePayload, *, user: User, di: Di
) -> ShopCategoryResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        category = await di.shop_service.update_category(
            scope.company_id, payload.shop_id, payload.shop_category_id, payload
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug, catalog_changed=True)
    return _category_response(category)


async def op_categories_remove(
    payload: ShopCategoryIdPayload, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        await di.shop_service.delete_category(
            scope.company_id, payload.shop_id, payload.shop_category_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug, catalog_changed=True)
    return EmptyPayload()


# --- Товары ---


async def op_products_list(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ListResponse[ShopProductResponse]:
    scope = await require_company_viewer(di.authz_service)
    _ = user
    try:
        products = await di.shop_service.list_products(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ListResponse(items=[_product_response(p) for p in products])


async def op_products_create(
    payload: ShopProductCreatePayload, *, user: User, di: Di
) -> ShopProductResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        product = await di.shop_service.create_product(scope.company_id, payload.shop_id, payload)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug, catalog_changed=True)
    return _product_response(product)


async def op_products_update(
    payload: ShopProductUpdatePayload, *, user: User, di: Di
) -> ShopProductResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        product = await di.shop_service.update_product(
            scope.company_id, payload.shop_id, payload.shop_product_id, payload
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug, catalog_changed=True)
    return _product_response(product)


async def op_products_import(
    payload: ShopProductsImportPayload, *, user: User, di: Di
) -> ShopProductsImportResponse:
    """Пакетный импорт позиций меню — одна команда вместо N create."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        created = await di.shop_service.import_products(
            scope.company_id, payload.shop_id, payload
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug, catalog_changed=True)
    return ShopProductsImportResponse(created=created)


async def op_products_remove(
    payload: ShopProductIdPayload, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        await di.shop_service.delete_product(
            scope.company_id, payload.shop_id, payload.shop_product_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug, catalog_changed=True)
    return EmptyPayload()


# --- Заказы (админ) ---


async def op_orders_list(
    payload: ShopOrderListPayload, *, user: User, di: Di
) -> OffsetPage[ShopOrderResponse]:
    scope = await require_company_viewer(di.authz_service)
    _ = user
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
    _ = user
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
    _ = user
    try:
        shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
        order = await di.order_service.set_status(shop, payload.shop_order_id, payload.status)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    await publish_shop_order_event(
        SHOP_ORDER_STATUS_CHANGED,
        shop_id=shop.shop_id,
        shop_order_id=order.shop_order_id,
        public_code=order.public_code,
        status=ShopOrderStatus(order.status),
        total_minor=order.total_minor,
        currency=order.currency,
        company_id=scope.company_id,
    )
    _ = await enqueue(SHOP_NOTIFY_ORDER, shop_order_id=order.shop_order_id)
    return await di.order_service.order_response(order)


async def op_telegram_connect(
    payload: ShopTelegramConnectPayload, *, user: User, di: Di
) -> ShopResponse:
    """Подключить бота магазина: getMe + setWebhook на витринный endpoint."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        shop = await di.notification_service.connect_telegram(
            scope.company_id, payload.shop_id, payload.bot_token
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformUnavailableError as exc:
        raise_unavailable(exc)
    return await _shop_response(shop, di)


async def op_telegram_disconnect(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ShopResponse:
    """Отключить бота: deleteWebhook, чат и токен стираются."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        shop = await di.notification_service.disconnect_telegram(
            scope.company_id, payload.shop_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return await _shop_response(shop, di)


# --- Домены ---


async def op_domains_add(payload: ShopDomainAddPayload, *, user: User, di: Di) -> ShopDomain:
    scope = await require_company_admin(di.authz_service)
    _ = user
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
    _ = user
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
    _ = user
    task = await enqueue(SHOP_PROVISION_DOMAIN, shop_domain_id=payload.shop_domain_id)
    _ = await task.wait_result(timeout=di.settings.taskiq_wait_timeout)
    record = await ShopDomain.objects.filter(
        shop_domain_id=payload.shop_domain_id
    ).get_or_none()
    if record is None:
        raise_not_found(PlatformNotFoundError("Domain not found", error_code="domain_not_found"))
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
    await publish_shop_order_event(
        SHOP_ORDER_CREATED,
        shop_id=shop.shop_id,
        shop_order_id=order.shop_order_id,
        public_code=order.public_code,
        status=ShopOrderStatus(order.status),
        total_minor=order.total_minor,
        currency=order.currency,
        company_id=str(shop.company_id),
    )
    _ = await enqueue(SHOP_NOTIFY_ORDER, shop_order_id=order.shop_order_id)
    return ShopOrderCreatedResponse(
        public_code=order.public_code,
        status=ShopOrderStatus(order.status),
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
        status=ShopOrderStatus(order.status),
        total_minor=order.total_minor,
        currency=order.currency,
        delivery_type=order.delivery_type,
        created_at=order.created_at.isoformat(),
    )


# --- AI-операции (канонический core.ai runtime, биллинг внутри клиентов) ---


async def op_ai_describe_product(
    payload: ShopAiDescribePayload, *, user: User, di: Di
) -> ShopAiTextResponse:
    """AI-описание блюда: по названию, при наличии — vision по фото."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    try:
        text = await di.ai_service.describe_product(
            name=payload.name,
            category_name=payload.category_name,
            photo_file_id=payload.photo_file_id,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ShopAiTextResponse(text=text)


async def op_ai_enhance_photo(
    payload: ShopAiEnhancePhotoPayload, *, user: User, di: Di
) -> ShopAiFileResponse:
    """Улучшение фото блюда через image_gen — вернёт новый file_id."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    try:
        file_id = await di.ai_service.enhance_product_photo(file_id=payload.file_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ShopAiFileResponse(file_id=file_id)


async def op_ai_generate_photo(
    payload: ShopAiGeneratePhotoPayload, *, user: User, di: Di
) -> ShopAiFileResponse:
    """Генерация фото товара с нуля — вернёт file_id."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    try:
        file_id = await di.ai_service.generate_product_photo(
            name=payload.name, description=payload.description
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ShopAiFileResponse(file_id=file_id)


async def op_ai_describe_batch(
    payload: ShopAiDescribeBatchPayload, *, user: User, di: Di
) -> ShopAiBatchResponse:
    """Постановка фоновой AI-генерации описаний для всех позиций без текста."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    products = await ShopProduct.list_by_shop(payload.shop_id)
    pending = sum(1 for p in products if not p.description.strip())
    _ = await enqueue(
        SHOP_AI_DESCRIBE_BATCH,
        shop_id=payload.shop_id,
        company_id=scope.company_id,
    )
    return ShopAiBatchResponse(enqueued=max(pending, 0))


async def _assert_shop_in_scope(di: Di, company_id: str, shop_id: str) -> None:
    try:
        _ = await di.shop_service.get_shop(company_id, shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
