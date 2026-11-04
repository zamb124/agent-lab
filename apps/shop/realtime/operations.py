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
from apps.shop.models import (
    Shop,
    ShopCategory,
    ShopDomain,
    ShopModifierGroup,
    ShopModifierOption,
    ShopProduct,
    ShopProductModifierGroup,
    ShopPromo,
    ShopTable,
)
from apps.shop.models.api import (
    ShopAiParseMenuResponse,
    ShopAiSuggestOptionsResponse,
    ShopBadgeIconsResponse,
    ShopBadgeResponse,
    ShopCartPriceRequest,
    ShopCartPriceResponse,
    ShopCategoriesReorderRequest,
    ShopCategoryCreateRequest,
    ShopCategoryResponse,
    ShopCategoryUpdateRequest,
    ShopCreateRequest,
    ShopGeocodeRequest,
    ShopGeocodeResponse,
    ShopModifierGroupCreateRequest,
    ShopModifierGroupResponse,
    ShopModifierGroupsResponse,
    ShopModifierGroupUpdateRequest,
    ShopModifierOptionCreateRequest,
    ShopModifierOptionResponse,
    ShopModifierOptionUpdateRequest,
    ShopOrderCreatedResponse,
    ShopOrderCreateRequest,
    ShopOrderResponse,
    ShopOrderStatusResponse,
    ShopProductCreateRequest,
    ShopProductResponse,
    ShopProductsImportRequest,
    ShopProductsImportResponse,
    ShopProductsReorderRequest,
    ShopProductUpdateRequest,
    ShopPromoCreateRequest,
    ShopPromoResponse,
    ShopPromosResponse,
    ShopPromoUpdateRequest,
    ShopResponse,
    ShopTableCreateRequest,
    ShopTableResponse,
    ShopTableUpdateRequest,
    ShopTheme,
    ShopUpdateRequest,
    ShopZoneAddressesRequest,
)
from apps.shop.models.badge_icons import BADGE_ICONS
from apps.shop.models.enums import ShopOrderStatus
from apps.shop.tasks.task_names import (
    SHOP_AI_DESCRIBE_BATCH,
    SHOP_NOTIFY_ORDER,
    SHOP_PROVISION_DOMAIN,
    SHOP_REBUILD_STOREFRONT,
)
from core.clients.geo_models import GeoAddressListResult
from core.clients.service_client import ServiceClientError
from core.errors.boundary import (
    PlatformAccessDeniedError,
    PlatformBoundaryError,
    PlatformConflictError,
    PlatformNotFoundError,
    PlatformUnavailableError,
)
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.pagination import ListResponse, OffsetPage
from core.request_scope import (
    require_company_admin,
    require_company_viewer,
    require_customer,
)
from core.tasks import enqueue
from core.utils.geo import is_valid_delivery_zone
from core.websocket import (
    EmptyPayload,
    raise_conflict,
    raise_forbidden,
    raise_invalid,
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


class ShopTableIdPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    shop_table_id: str = Field(min_length=1)


class ShopTableCreatePayload(ShopTableCreateRequest):
    shop_id: str = Field(min_length=1)


class ShopTableUpdatePayload(ShopTableUpdateRequest):
    shop_id: str = Field(min_length=1)
    shop_table_id: str = Field(min_length=1)


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


class ShopProductsReorderPayload(ShopProductsReorderRequest):
    shop_id: str = Field(min_length=1)


class ShopCategoriesReorderPayload(ShopCategoriesReorderRequest):
    shop_id: str = Field(min_length=1)


class ShopModifierGroupCreatePayload(ShopModifierGroupCreateRequest):
    shop_id: str = Field(min_length=1)


class ShopModifierGroupUpdatePayload(ShopModifierGroupUpdateRequest):
    shop_id: str = Field(min_length=1)
    shop_modifier_group_id: str = Field(min_length=1)


class ShopModifierGroupIdPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    shop_modifier_group_id: str = Field(min_length=1)


class ShopModifierOptionCreatePayload(ShopModifierOptionCreateRequest):
    shop_id: str = Field(min_length=1)
    group_id: str = Field(min_length=1)


class ShopModifierOptionUpdatePayload(ShopModifierOptionUpdateRequest):
    shop_id: str = Field(min_length=1)
    shop_modifier_option_id: str = Field(min_length=1)


class ShopModifierOptionIdPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    shop_modifier_option_id: str = Field(min_length=1)


class ShopProductModifierAttachPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    group_id: str = Field(min_length=1)
    min_selected: int | None = Field(default=None, ge=0, le=50)
    max_selected: int | None = Field(default=None, ge=1, le=99)


class ShopProductModifierDetachPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    group_id: str = Field(min_length=1)


class ShopPromoCreatePayload(ShopPromoCreateRequest):
    shop_id: str = Field(min_length=1)


class ShopPromoUpdatePayload(ShopPromoUpdateRequest):
    shop_id: str = Field(min_length=1)
    shop_promo_id: str = Field(min_length=1)


class ShopPromoIdPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    shop_promo_id: str = Field(min_length=1)


class ShopCartPricePayload(ShopCartPriceRequest):
    slug: str = Field(min_length=1)


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


class ShopAiSuggestOptionsPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    product_name: str = Field(min_length=1, max_length=300)
    group_name: str | None = Field(default=None, max_length=200)


class ShopAiParseMenuPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    text: str = Field(min_length=3, max_length=50_000)


class ShopAiShopPayload(StrictBaseModel):
    """AI над карточкой магазина: имя обязательно, description — черновик из формы."""

    shop_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=1000)


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
        working_hours={str(day): str(hours) for day, hours in shop.working_hours.items()},
        delivery_enabled=shop.delivery_enabled,
        pickup_enabled=shop.pickup_enabled,
        onsite_enabled=shop.onsite_enabled,
        delivery_zone=dict(shop.delivery_zone),
        delivery_fee_minor=shop.delivery_fee_minor,
        min_order_minor=shop.min_order_minor,
        prep_minutes=shop.prep_minutes,
        courier_mode=shop.courier_mode,
        currency=shop.currency,
        theme=ShopTheme.model_validate(shop.theme or {}),
        badges=[
            ShopBadgeResponse(
                key=b["key"],
                label=b["label"],
                icon=b["icon"],
                icon_path=BADGE_ICONS.get(b["icon"], ""),
            )
            for b in shop.badges
        ],
        status=shop.status,
        telegram_chat_id=shop.telegram_chat_id,
        telegram_connected=bool(shop.telegram_bot_token),
        storefront_url=f"https://{shop.slug}.{di.settings.storefront_domain_suffix}",
        plan=shop.plan,
        products_count=products_count,
    )


def _table_response(table: ShopTable) -> ShopTableResponse:
    return ShopTableResponse(
        shop_table_id=table.shop_table_id,
        shop_id=table.shop_id,
        label=table.label,
    )


def _category_response(category: ShopCategory) -> ShopCategoryResponse:
    return ShopCategoryResponse(
        shop_category_id=category.shop_category_id,
        shop_id=category.shop_id,
        parent_id=category.parent_id,
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
        portion=product.portion,
        badges=list(product.badges),
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
            await publish_shop_catalog_changed(shop_id, slug, str(shop.company_id))
    _ = await enqueue(SHOP_REBUILD_STOREFRONT, slug=slug)


# --- Витрины (админ) ---


async def op_shops_list(payload: EmptyPayload, *, user: User, di: Di) -> ListResponse[ShopResponse]:
    scope = await require_company_admin(di.authz_service)
    _ = (payload, user)
    shops = await di.shop_service.list_shops(scope.company_id)
    return ListResponse(items=[await _shop_response(s, di) for s in shops])


async def op_shops_create(payload: ShopCreateRequest, *, user: User, di: Di) -> ShopResponse:
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


async def op_badge_icons_list(
    payload: EmptyPayload, *, user: User, di: Di
) -> ShopBadgeIconsResponse:
    scope = await require_company_viewer(di.authz_service)
    _ = (payload, user, scope)
    return ShopBadgeIconsResponse(icons=dict(BADGE_ICONS))


async def op_shops_get(payload: ShopIdPayload, *, user: User, di: Di) -> ShopResponse:
    scope = await require_company_viewer(di.authz_service)
    _ = user
    try:
        shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return await _shop_response(shop, di)


async def op_shops_update(payload: ShopUpdatePayload, *, user: User, di: Di) -> ShopResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    if "delivery_zone" in payload.model_fields_set and not is_valid_delivery_zone(
        payload.delivery_zone
    ):
        raise_invalid(
            ValueError("delivery_zone is not a valid single-ring GeoJSON Polygon"),
            error_code="invalid_delivery_zone",
        )
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


class ShopGeocodePayload(ShopGeocodeRequest):
    """Геокод адреса магазина для центрирования карты зоны доставки."""

    shop_id: str = Field(min_length=1)


async def op_shop_geocode(
    payload: ShopGeocodePayload, *, user: User, di: Di
) -> ShopGeocodeResponse:
    scope = await require_company_viewer(di.authz_service)
    _ = user
    try:
        _shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    geo = await di.geocoder.geocode(payload.address)
    if geo is None:
        raise_not_found(
            PlatformNotFoundError("Address could not be geocoded"),
            error_code="address_unverifiable",
        )
    return ShopGeocodeResponse(lat=geo.lat, lng=geo.lng, normalized=geo.normalized_address)


async def op_shop_zone_addresses(
    payload: ShopZoneAddressesRequest, *, user: User, di: Di
) -> GeoAddressListResult:
    """Адреса справочника geo внутри редактируемой зоны — для панели редактора.

    Зона приходит из payload (ещё не сохранена на сервере), поэтому
    валидируется здесь. Контекст компании ServiceClient прокидывает сам.
    """
    scope = await require_company_viewer(di.authz_service)
    _ = user
    _ = scope
    if not is_valid_delivery_zone(payload.zone):
        raise_invalid(
            ValueError("delivery_zone is not a valid single-ring GeoJSON Polygon"),
            error_code="invalid_delivery_zone",
        )
    try:
        return await di.geo_client.addresses_in_zone(
            zone=payload.zone, q=payload.q, limit=payload.limit, offset=payload.offset
        )
    except ServiceClientError as exc:
        raise_unavailable(exc, error_code="geo_unavailable")


async def op_shops_publish(payload: ShopIdPayload, *, user: User, di: Di) -> ShopResponse:
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


async def op_shops_suspend(payload: ShopIdPayload, *, user: User, di: Di) -> ShopResponse:
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


async def op_shops_remove(payload: ShopIdPayload, *, user: User, di: Di) -> EmptyPayload:
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


async def op_categories_reorder(
    payload: ShopCategoriesReorderPayload, *, user: User, di: Di
) -> EmptyPayload:
    """Замена дерева категорий меню — ``items`` в depth-first порядке."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        await di.shop_service.reorder_categories(
            scope.company_id, payload.shop_id, payload.items
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
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


async def op_products_reorder(
    payload: ShopProductsReorderPayload, *, user: User, di: Di
) -> EmptyPayload:
    """Перестановка позиций меню — стрелки в конструкторе и порядок на витрине."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        await di.shop_service.reorder_products(
            scope.company_id, payload.shop_id, payload.product_ids
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug, catalog_changed=True)
    return EmptyPayload()


async def op_products_import(
    payload: ShopProductsImportPayload, *, user: User, di: Di
) -> ShopProductsImportResponse:
    """Пакетный импорт позиций меню — одна команда вместо N create."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        created = await di.shop_service.import_products(scope.company_id, payload.shop_id, payload)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug, catalog_changed=True)
    return ShopProductsImportResponse(created=created)


async def op_products_remove(payload: ShopProductIdPayload, *, user: User, di: Di) -> EmptyPayload:
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


# --- Столы зала ---


async def op_tables_list(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ListResponse[ShopTableResponse]:
    scope = await require_company_viewer(di.authz_service)
    _ = user
    try:
        tables = await di.shop_service.list_tables(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ListResponse(items=[_table_response(t) for t in tables])


async def op_tables_create(
    payload: ShopTableCreatePayload, *, user: User, di: Di
) -> ShopTableResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        table = await di.shop_service.create_table(scope.company_id, payload.shop_id, payload)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return _table_response(table)


async def op_tables_update(
    payload: ShopTableUpdatePayload, *, user: User, di: Di
) -> ShopTableResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        table = await di.shop_service.update_table(
            scope.company_id, payload.shop_id, payload.shop_table_id, payload
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return _table_response(table)


async def op_tables_remove(payload: ShopTableIdPayload, *, user: User, di: Di) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        await di.shop_service.delete_table(
            scope.company_id, payload.shop_id, payload.shop_table_id
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


async def op_orders_get(payload: ShopOrderIdPayload, *, user: User, di: Di) -> ShopOrderResponse:
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


async def op_telegram_disconnect(payload: ShopIdPayload, *, user: User, di: Di) -> ShopResponse:
    """Отключить бота: deleteWebhook, чат и токен стираются."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        shop = await di.notification_service.disconnect_telegram(scope.company_id, payload.shop_id)
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


async def op_domains_remove(payload: ShopDomainIdPayload, *, user: User, di: Di) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        await di.shop_service.remove_domain(
            scope.company_id, payload.shop_id, payload.shop_domain_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return EmptyPayload()


async def op_domains_provision(payload: ShopDomainIdPayload, *, user: User, di: Di) -> ShopDomain:
    """DNS-проверка и провиженинг через воркер: HTTP ждёт wait_result."""
    _ = await require_company_admin(di.authz_service)
    _ = user
    task = await enqueue(SHOP_PROVISION_DOMAIN, shop_domain_id=payload.shop_domain_id)
    _ = await task.wait_result(timeout=di.settings.taskiq_wait_timeout)
    record = await ShopDomain.objects.filter(shop_domain_id=payload.shop_domain_id).get_or_none()
    if record is None:
        raise_not_found(PlatformNotFoundError("Domain not found", error_code="domain_not_found"))
    return record


# --- Публичные операции (анонимный вызов витрины) ---


async def op_public_order_create(
    payload: ShopOrderCreatePayload, *, user: User, di: Di
) -> ShopOrderCreatedResponse:
    """Создать заказ на витрине по slug: требует customer-сессию (customers.mdc)."""
    _ = user
    customer_scope = require_customer()
    try:
        shop = await di.order_service.resolve_published_shop(payload.slug)
        order = await di.order_service.create_order(shop, payload, customer=customer_scope)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise_forbidden(exc)
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
        order = await di.order_service.get_by_public_code(payload.public_code)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ShopOrderStatusResponse(
        public_code=order.public_code,
        status=ShopOrderStatus(order.status),
        total_minor=order.total_minor,
        currency=order.currency,
        delivery_type=order.delivery_type,
        table_label=order.table_label,
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


async def op_ai_suggest_options(
    payload: ShopAiSuggestOptionsPayload, *, user: User, di: Di
) -> ShopAiSuggestOptionsResponse:
    """AI-предложение опций-модификаторов по названию блюда."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    try:
        items = await di.ai_service.suggest_options(
            product_name=payload.product_name, group_name=payload.group_name
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ShopAiSuggestOptionsResponse(items=items)


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
    products = await ShopProduct.list_by_shop_by_sort_asc(payload.shop_id)
    pending = sum(1 for p in products if not p.description.strip())
    _ = await enqueue(
        SHOP_AI_DESCRIBE_BATCH,
        shop_id=payload.shop_id,
        company_id=scope.company_id,
    )
    return ShopAiBatchResponse(enqueued=max(pending, 0))


async def op_ai_parse_menu(
    payload: ShopAiParseMenuPayload, *, user: User, di: Di
) -> ShopAiParseMenuResponse:
    """AI-разбор свободного текста меню в позиции каталога (импорт-превью)."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    try:
        items = await di.ai_service.parse_menu(text=payload.text)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ShopAiParseMenuResponse(items=items)


async def op_ai_describe_shop(
    payload: ShopAiShopPayload, *, user: User, di: Di
) -> ShopAiTextResponse:
    """AI-описание магазина для витрины (улучшает черновик, если передан)."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    shop = await _shop_in_scope(di, scope.company_id, payload.shop_id)
    try:
        text = await di.ai_service.describe_shop(
            name=payload.name, description=payload.description, city=shop.city or ""
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ShopAiTextResponse(text=text)


async def op_ai_generate_cover(
    payload: ShopAiShopPayload, *, user: User, di: Di
) -> ShopAiFileResponse:
    """AI-генерация обложки витрины — вернёт file_id."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    try:
        file_id = await di.ai_service.generate_shop_cover(
            name=payload.name, description=payload.description
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ShopAiFileResponse(file_id=file_id)


async def op_ai_generate_logo(
    payload: ShopAiShopPayload, *, user: User, di: Di
) -> ShopAiFileResponse:
    """AI-генерация логотипа витрины — вернёт file_id."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    try:
        file_id = await di.ai_service.generate_shop_logo(
            name=payload.name, description=payload.description
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ShopAiFileResponse(file_id=file_id)


async def op_ai_autofill(payload: ShopIdPayload, *, user: User, di: Di) -> ShopResponse:
    """AI-оформление витрины одной командой: описание и обложка в пустые поля.

    Заполненные вручную поля не перетираются — точечная перегенерация
    остаётся на кнопках describe-shop/generate-cover в настройках.
    """
    scope = await require_company_admin(di.authz_service)
    _ = user
    shop = await _shop_in_scope(di, scope.company_id, payload.shop_id)
    patch = ShopUpdateRequest()
    description = shop.description or ""
    if not description:
        description = await di.ai_service.describe_shop(name=shop.name, city=shop.city or "")
    patch.description = description
    if not shop.cover_file_id:
        patch.cover_file_id = await di.ai_service.generate_shop_cover(
            name=shop.name, description=description
        )
    updated = await di.shop_service.update_shop(scope.company_id, shop.shop_id, patch)
    await publish_shop_event(
        SHOP_SHOP_UPDATED, updated.shop_id, updated.slug, updated.status, scope.company_id
    )
    await _enqueue_rebuild(di, updated.shop_id, updated.slug)
    return await _shop_response(updated, di)


async def _shop_in_scope(di: Di, company_id: str, shop_id: str) -> Shop:
    try:
        return await di.shop_service.get_shop(company_id, shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)


async def _assert_shop_in_scope(di: Di, company_id: str, shop_id: str) -> None:
    try:
        _ = await di.shop_service.get_shop(company_id, shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)


# --- Модификаторы ---


def _option_response(option: ShopModifierOption) -> ShopModifierOptionResponse:
    return ShopModifierOptionResponse(
        shop_modifier_option_id=option.shop_modifier_option_id,
        group_id=option.group_id,
        name=option.name,
        price_minor=option.price_minor,
        is_default=option.is_default,
        is_available=option.is_available,
        max_per_option=option.max_per_option,
        nested_group_id=option.nested_group_id,
        sort=option.sort,
    )


def _modifier_group_response(
    group: ShopModifierGroup,
    options: list[ShopModifierOption],
    product_ids: list[str] | None = None,
) -> ShopModifierGroupResponse:
    return ShopModifierGroupResponse(
        shop_modifier_group_id=group.shop_modifier_group_id,
        shop_id=group.shop_id,
        name=group.name,
        description=group.description,
        kind=group.kind.value,
        selection_mode=group.selection_mode.value,
        min_selected=group.min_selected,
        max_selected=group.max_selected,
        price_mode=group.price_mode.value,
        is_active=group.is_active,
        sort=group.sort,
        product_ids=product_ids or [],
        options=[_option_response(o) for o in options],
    )


async def _rebuild_for_shop(di: Di, company_id: str, shop_id: str) -> None:
    shop = await di.shop_service.get_shop(company_id, shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug, catalog_changed=True)


async def op_modifier_groups_list(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ShopModifierGroupsResponse:
    scope = await require_company_viewer(di.authz_service)
    _ = user
    try:
        tree = await di.shop_service.list_modifier_groups_by_sort_asc(
            scope.company_id, payload.shop_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ShopModifierGroupsResponse(
        groups=[
            _modifier_group_response(group, options, product_ids)
            for group, options, product_ids in tree
        ]
    )


async def op_modifier_groups_create(
    payload: ShopModifierGroupCreatePayload, *, user: User, di: Di
) -> ShopModifierGroupResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        group = await di.shop_service.create_modifier_group(
            scope.company_id, payload.shop_id, payload
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    await _rebuild_for_shop(di, scope.company_id, payload.shop_id)
    return _modifier_group_response(group, [])


async def op_modifier_groups_update(
    payload: ShopModifierGroupUpdatePayload, *, user: User, di: Di
) -> ShopModifierGroupResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        group = await di.shop_service.update_modifier_group(
            scope.company_id,
            payload.shop_id,
            payload.shop_modifier_group_id,
            payload,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    options = await ShopModifierOption.list_by_group_by_sort_asc(group.shop_modifier_group_id)
    links = await ShopProductModifierGroup.list_by_groups([group.shop_modifier_group_id])
    await _rebuild_for_shop(di, scope.company_id, payload.shop_id)
    return _modifier_group_response(group, options, [link.product_id for link in links])


async def op_modifier_groups_remove(
    payload: ShopModifierGroupIdPayload, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        await di.shop_service.delete_modifier_group(
            scope.company_id, payload.shop_id, payload.shop_modifier_group_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    await _rebuild_for_shop(di, scope.company_id, payload.shop_id)
    return EmptyPayload()


async def op_modifier_options_create(
    payload: ShopModifierOptionCreatePayload, *, user: User, di: Di
) -> ShopModifierOptionResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        option = await di.shop_service.create_modifier_option(
            scope.company_id, payload.shop_id, payload.group_id, payload
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    await _rebuild_for_shop(di, scope.company_id, payload.shop_id)
    return _option_response(option)


async def op_modifier_options_update(
    payload: ShopModifierOptionUpdatePayload, *, user: User, di: Di
) -> ShopModifierOptionResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        option = await di.shop_service.update_modifier_option(
            scope.company_id,
            payload.shop_id,
            payload.shop_modifier_option_id,
            payload,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    await _rebuild_for_shop(di, scope.company_id, payload.shop_id)
    return _option_response(option)


async def op_modifier_options_remove(
    payload: ShopModifierOptionIdPayload, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        await di.shop_service.delete_modifier_option(
            scope.company_id, payload.shop_id, payload.shop_modifier_option_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    await _rebuild_for_shop(di, scope.company_id, payload.shop_id)
    return EmptyPayload()


async def op_products_modifier_attach(
    payload: ShopProductModifierAttachPayload, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        await di.shop_service.attach_modifier_group(
            scope.company_id,
            payload.shop_id,
            payload.product_id,
            payload.group_id,
            payload.min_selected,
            payload.max_selected,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    await _rebuild_for_shop(di, scope.company_id, payload.shop_id)
    return EmptyPayload()


async def op_products_modifier_detach(
    payload: ShopProductModifierDetachPayload, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        await di.shop_service.detach_modifier_group(
            scope.company_id,
            payload.shop_id,
            payload.product_id,
            payload.group_id,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    await _rebuild_for_shop(di, scope.company_id, payload.shop_id)
    return EmptyPayload()


def _promo_response(promo: ShopPromo) -> ShopPromoResponse:
    return ShopPromoResponse(
        shop_promo_id=promo.shop_promo_id,
        shop_id=promo.shop_id,
        name=promo.name,
        is_active=promo.is_active,
        sort=promo.sort,
        priority=promo.priority,
        stacking=str(promo.stacking),
        window=promo.window,
        condition=promo.condition,
        action=promo.action,
    )


async def op_promos_list(payload: ShopIdPayload, *, user: User, di: Di) -> ShopPromosResponse:
    scope = await require_company_viewer(di.authz_service)
    _ = user
    promos = await di.shop_service.list_promos_by_sort_asc(scope.company_id, payload.shop_id)
    return ShopPromosResponse(promos=[_promo_response(p) for p in promos])


async def op_promos_create(
    payload: ShopPromoCreatePayload, *, user: User, di: Di
) -> ShopPromoResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        promo = await di.shop_service.create_promo(scope.company_id, payload.shop_id, payload)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    await _rebuild_for_shop(di, scope.company_id, payload.shop_id)
    return _promo_response(promo)


async def op_promos_update(
    payload: ShopPromoUpdatePayload, *, user: User, di: Di
) -> ShopPromoResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        promo = await di.shop_service.update_promo(
            scope.company_id, payload.shop_id, payload.shop_promo_id, payload
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    await _rebuild_for_shop(di, scope.company_id, payload.shop_id)
    return _promo_response(promo)


async def op_promos_remove(payload: ShopPromoIdPayload, *, user: User, di: Di) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        await di.shop_service.delete_promo(scope.company_id, payload.shop_id, payload.shop_promo_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    await _rebuild_for_shop(di, scope.company_id, payload.shop_id)
    return EmptyPayload()


async def op_public_cart_price(
    payload: ShopCartPricePayload, *, user: User, di: Di
) -> ShopCartPriceResponse:
    """Живой расчёт корзины витрины: цены + скидки, анонимный путь."""
    _ = user
    try:
        shop = await di.order_service.resolve_published_shop(payload.slug)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    try:
        return await di.order_service.price_cart(shop, payload)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
