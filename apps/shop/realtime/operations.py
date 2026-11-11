"""Бизнес-функции shop: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from pydantic import Field

from apps.shop.di import Di
from apps.shop.events import (
    SHOP_SHOP_CREATED,
    SHOP_SHOP_PUBLISHED,
    SHOP_SHOP_UPDATED,
    publish_shop_catalog_changed,
    publish_shop_event,
)
from apps.shop.models import (
    Shop,
    ShopBanner,
    ShopCategory,
    ShopDomain,
    ShopLoyaltyProgram,
    ShopModifierGroup,
    ShopModifierOption,
    ShopProduct,
    ShopProductModifierGroup,
    ShopPromo,
    ShopShelf,
    ShopTable,
    order_status_label,
)
from apps.shop.models.api import (
    ShopAiCallResponse,
    ShopBadgeIconsResponse,
    ShopBadgeResponse,
    ShopBannerCreateRequest,
    ShopBannerResponse,
    ShopBannersReorderRequest,
    ShopBannerUpdateRequest,
    ShopCartPriceRequest,
    ShopCartPriceResponse,
    ShopCategoriesReorderRequest,
    ShopCategoryCreateRequest,
    ShopCategoryResponse,
    ShopCategoryUpdateRequest,
    ShopCreateRequest,
    ShopFavoriteResponse,
    ShopFeatures,
    ShopLoyaltyProgramResponse,
    ShopLoyaltyProgramSetRequest,
    ShopModifierGroupCreateRequest,
    ShopModifierGroupResponse,
    ShopModifierGroupsResponse,
    ShopModifierGroupUpdateRequest,
    ShopModifierOptionCreateRequest,
    ShopModifierOptionResponse,
    ShopModifierOptionUpdateRequest,
    ShopMyOrderDetailResponse,
    ShopMyOrderListItemResponse,
    ShopNotifyBackResponse,
    ShopNutrition,
    ShopOrderCreatedResponse,
    ShopOrderCreateRequest,
    ShopOrderFeedbackResponse,
    ShopOrderItemPreview,
    ShopOrderResponse,
    ShopOrderStatusResponse,
    ShopPersonalResponse,
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
    ShopReviewsResponse,
    ShopShelfCreateRequest,
    ShopShelfResponse,
    ShopShelfUpdateRequest,
    ShopShelvesReorderRequest,
    ShopStorefrontGeoResponse,
    ShopTableCreateRequest,
    ShopTableResponse,
    ShopTableUpdateRequest,
    ShopTheme,
    ShopUpdateRequest,
    normalize_shop_features,
    normalize_shop_theme,
)
from apps.shop.models.badge_icons import BADGE_ICONS
from apps.shop.models.common import new_id
from apps.shop.models.enums import (
    ShopFeedbackChip,
    ShopLoyaltyRewardKind,
    ShopOrderStatus,
)
from apps.shop.services.feed_service import feedback_response
from apps.shop.tasks.task_names import (
    SHOP_AI_CALL,
    SHOP_AI_DESCRIBE_BATCH,
    SHOP_NOTIFY_BACK_IN_STOCK,
    SHOP_PROVISION_DOMAIN,
    SHOP_REBUILD_STOREFRONT,
)
from core.catalog.events import publish_catalog_product_facet_changed
from core.errors.boundary import (
    PlatformAccessDeniedError,
    PlatformBoundaryError,
    PlatformConflictError,
    PlatformNotFoundError,
    PlatformUnavailableError,
)
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.pagination import ListResponse, OffsetPage
from core.request_scope import (
    CompanyScope,
    optional_customer,
    require_company_admin,
    require_company_viewer,
    require_customer,
)
from core.tasks import enqueue
from core.types import JsonValue
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
    product_id: str = Field(min_length=1)


class ShopProductCreatePayload(ShopProductCreateRequest):
    shop_id: str = Field(min_length=1)


class ShopProductsImportPayload(ShopProductsImportRequest):
    shop_id: str = Field(min_length=1)


class ShopProductUpdatePayload(ShopProductUpdateRequest):
    shop_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)


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


class ShopShelfIdPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    shop_shelf_id: str = Field(min_length=1)


class ShopShelfCreatePayload(ShopShelfCreateRequest):
    shop_id: str = Field(min_length=1)


class ShopShelfUpdatePayload(ShopShelfUpdateRequest):
    shop_id: str = Field(min_length=1)
    shop_shelf_id: str = Field(min_length=1)


class ShopShelvesReorderPayload(ShopShelvesReorderRequest):
    shop_id: str = Field(min_length=1)


class ShopBannerIdPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    shop_banner_id: str = Field(min_length=1)


class ShopBannerCreatePayload(ShopBannerCreateRequest):
    shop_id: str = Field(min_length=1)


class ShopBannerUpdatePayload(ShopBannerUpdateRequest):
    shop_id: str = Field(min_length=1)
    shop_banner_id: str = Field(min_length=1)


class ShopBannersReorderPayload(ShopBannersReorderRequest):
    shop_id: str = Field(min_length=1)


class ShopLoyaltyProgramPayload(StrictBaseModel):
    """Программа лояльности магазина — get/set настроек владельцем."""

    shop_id: str = Field(min_length=1)


class ShopLoyaltyProgramSetPayload(ShopLoyaltyProgramSetRequest):
    shop_id: str = Field(min_length=1)


class ShopNotifyBackPayload(StrictBaseModel):
    """Подписка «сообщить о появлении» — slug витрины + товар."""

    slug: str = Field(min_length=3, max_length=40)
    product_id: str = Field(min_length=1)


class ShopPersonalPayload(StrictBaseModel):
    """Персональные данные покупателя на витрине — ``/personal``."""

    slug: str = Field(min_length=3, max_length=40)


class ShopFavoriteSetPayload(StrictBaseModel):
    """Сердечко покупателя — slug витрины + товар + целевое состояние."""

    slug: str = Field(min_length=3, max_length=40)
    product_id: str = Field(min_length=1)
    favorite: bool


class ShopFeedbackSetPayload(StrictBaseModel):
    """Оценка покупателем выполненного заказа — slug + публичный код."""

    slug: str = Field(min_length=3, max_length=40)
    public_code: str = Field(min_length=4, max_length=16)
    rating: int = Field(ge=1, le=5)
    chips: list[ShopFeedbackChip] = Field(default_factory=list, max_length=6)
    comment: str = Field(default="", max_length=1000)


class ShopReviewsListPayload(StrictBaseModel):
    """Публичная лента отзывов витрины — анонимное чтение."""

    slug: str = Field(min_length=3, max_length=40)
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0)


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


class ShopMyOrdersListPayload(StrictBaseModel):
    """Лента `my/orders`: фильтр по статусу или «активные/завершённые»."""

    status: ShopOrderStatus | None = None
    active: bool | None = None
    limit: int = Field(default=30, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ShopMyOrderCodePayload(StrictBaseModel):
    """Детали/отмена заказа кабинета по публичному коду."""

    public_code: str = Field(min_length=4, max_length=16)


class ShopStorefrontGeoPayload(StrictBaseModel):
    slug: str = Field(min_length=3, max_length=40)


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


class ShopAiBatchResponse(StrictBaseModel):
    enqueued: int


async def _shop_response(shop: Shop, di: Di) -> ShopResponse:
    products_count = await ShopProduct.count_by_shop(shop.shop_id)
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
        lat=shop.lat,
        lng=shop.lng,
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
        theme=ShopTheme.model_validate(normalize_shop_theme(shop.theme or {})),
        features=ShopFeatures.model_validate(normalize_shop_features(shop.features or {})),
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
        demo_template=shop.demo_template,
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



def _shelf_response(shelf: ShopShelf) -> ShopShelfResponse:
    return ShopShelfResponse(
        shop_shelf_id=shelf.shop_shelf_id,
        shop_id=shelf.shop_id,
        kind=shelf.kind.value,
        layout=shelf.layout.value,
        placement=shelf.placement.value,
        title=shelf.title,
        subtitle=shelf.subtitle,
        product_ids=list(shelf.product_ids),
        category_id=shelf.category_id,
        limit=shelf.limit,
        sort=shelf.sort,
        is_active=shelf.is_active,
    )


def _banner_response(banner: ShopBanner) -> ShopBannerResponse:
    return ShopBannerResponse(
        shop_banner_id=banner.shop_banner_id,
        shop_id=banner.shop_id,
        title=banner.title,
        subtitle=banner.subtitle,
        image_file_id=banner.image_file_id,
        link=banner.link,
        window=dict(banner.window),
        sort=banner.sort,
        is_active=banner.is_active,
    )


async def _enqueue_rebuild(
    di: Di, shop_id: str, slug: str, *, catalog_changed: bool = False
) -> None:
    """Инвалидация витрины после мутации: ключ удаляется синхронно
    (suspend/unavailable скрываются немедленно), воркер прогревает кэш.
    Поисковая проекция `shop_market_items` переписывается здесь же —
    листинговая мутация видна в поиске сразу, без ожидания событий.
    Каталожные мутации дополнительно публикуют `shop/catalog/changed` —
    по этому событию flows-триггеры реагируют на обновление меню."""
    await di.storefront_service.invalidate_snapshot(shop_id)
    shop = await Shop.get_by_id(shop_id)
    if shop is not None:
        _ = await di.aggregate_service.sync_shop_items(shop)
        if catalog_changed:
            await publish_shop_catalog_changed(shop_id, slug, str(shop.company_id))
    _ = await enqueue(SHOP_REBUILD_STOREFRONT, slug=slug)


logger = get_logger(__name__)


async def _delete_orphaned_file(di: Di, file_id: str | None) -> None:
    """Заменённый файл (фото/лого/обложка) — удаление записи и всей семьи вариантов."""
    if file_id is None or file_id == "":
        return
    try:
        _ = await di.files_service.delete(file_id)
    except Exception:
        logger.warning("shop.file_cleanup_failed", file_id=file_id)


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
        before = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
        shop = await di.shop_service.update_shop(scope.company_id, payload.shop_id, payload)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    if shop.logo_file_id != before.logo_file_id:
        await _delete_orphaned_file(di, before.logo_file_id)
    if shop.cover_file_id != before.cover_file_id:
        await _delete_orphaned_file(di, before.cover_file_id)
    await publish_shop_event(
        SHOP_SHOP_UPDATED, shop.shop_id, shop.slug, shop.status, scope.company_id
    )
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return await _shop_response(shop, di)


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
    return ListResponse(items=products)


async def op_products_create(
    payload: ShopProductCreatePayload, *, user: User, di: Di
) -> ShopProductResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        product = await di.shop_service.create_product(scope.company_id, payload.shop_id, payload)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    await publish_catalog_product_facet_changed(
        product.product_id,
        scope.company_id,
        facet="shop",
        instance_id=payload.shop_id,
    )
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug, catalog_changed=True)
    return product


async def op_products_update(
    payload: ShopProductUpdatePayload, *, user: User, di: Di
) -> ShopProductResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        before = await di.shop_service.get_listing(
            scope.company_id, payload.shop_id, payload.product_id
        )
        product = await di.shop_service.update_product(
            scope.company_id, payload.shop_id, payload.product_id, payload
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    if product.photo_file_id != before.photo_file_id:
        await _delete_orphaned_file(di, before.photo_file_id)
    if product.is_available and not before.is_available:
        _ = await enqueue(
            SHOP_NOTIFY_BACK_IN_STOCK, product_id=product.product_id
        )
    await publish_catalog_product_facet_changed(
        payload.product_id,
        scope.company_id,
        facet="shop",
        instance_id=payload.shop_id,
    )
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug, catalog_changed=True)
    return product


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
        created_ids = await di.shop_service.import_products(
            scope.company_id, payload.shop_id, payload
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    for product_id in created_ids:
        await publish_catalog_product_facet_changed(
            product_id,
            scope.company_id,
            facet="shop",
            instance_id=payload.shop_id,
        )
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug, catalog_changed=True)
    return ShopProductsImportResponse(created=len(created_ids))


async def op_products_remove(payload: ShopProductIdPayload, *, user: User, di: Di) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        before = await di.shop_service.get_listing(
            scope.company_id, payload.shop_id, payload.product_id
        )
        await di.shop_service.delete_product(
            scope.company_id, payload.shop_id, payload.product_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    await _delete_orphaned_file(di, before.photo_file_id)
    await publish_catalog_product_facet_changed(
        payload.product_id,
        scope.company_id,
        facet="shop",
        instance_id=payload.shop_id,
    )
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug, catalog_changed=True)
    return EmptyPayload()


# --- Витринная лента: полки ---


async def op_shelves_list(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ListResponse[ShopShelfResponse]:
    scope = await require_company_viewer(di.authz_service)
    _ = user
    try:
        shelves = await di.feed_service.list_shelves(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ListResponse(items=[_shelf_response(s) for s in shelves])


async def op_shelves_create(
    payload: ShopShelfCreatePayload, *, user: User, di: Di
) -> ShopShelfResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        shelf = await di.feed_service.create_shelf(
            scope.company_id, payload.shop_id, payload
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return _shelf_response(shelf)


async def op_shelves_update(
    payload: ShopShelfUpdatePayload, *, user: User, di: Di
) -> ShopShelfResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        shelf = await di.feed_service.update_shelf(
            scope.company_id, payload.shop_id, payload.shop_shelf_id, payload
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return _shelf_response(shelf)


async def op_shelves_reorder(
    payload: ShopShelvesReorderPayload, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        await di.feed_service.reorder_shelves(
            scope.company_id, payload.shop_id, payload.shelf_ids
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return EmptyPayload()


async def op_shelves_remove(payload: ShopShelfIdPayload, *, user: User, di: Di) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        await di.feed_service.delete_shelf(
            scope.company_id, payload.shop_id, payload.shop_shelf_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return EmptyPayload()


# --- Витринная лента: баннеры ---


async def op_banners_list(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ListResponse[ShopBannerResponse]:
    scope = await require_company_viewer(di.authz_service)
    _ = user
    try:
        banners = await di.feed_service.list_banners(scope.company_id, payload.shop_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ListResponse(items=[_banner_response(b) for b in banners])


async def op_banners_create(
    payload: ShopBannerCreatePayload, *, user: User, di: Di
) -> ShopBannerResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        banner = await di.feed_service.create_banner(
            scope.company_id, payload.shop_id, payload
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return _banner_response(banner)


async def op_banners_update(
    payload: ShopBannerUpdatePayload, *, user: User, di: Di
) -> ShopBannerResponse:
    scope = await require_company_admin(di.authz_service)
    _ = user
    before = await ShopBanner.get_by_id(payload.shop_banner_id)
    try:
        banner = await di.feed_service.update_banner(
            scope.company_id, payload.shop_id, payload.shop_banner_id, payload
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    if before is not None and banner.image_file_id != before.image_file_id:
        await _delete_orphaned_file(di, before.image_file_id)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return _banner_response(banner)


async def op_banners_reorder(
    payload: ShopBannersReorderPayload, *, user: User, di: Di
) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        await di.feed_service.reorder_banners(
            scope.company_id, payload.shop_id, payload.banner_ids
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return EmptyPayload()


async def op_banners_remove(payload: ShopBannerIdPayload, *, user: User, di: Di) -> EmptyPayload:
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        banner = await di.feed_service.delete_banner(
            scope.company_id, payload.shop_id, payload.shop_banner_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    await _delete_orphaned_file(di, banner.image_file_id)
    shop = await di.shop_service.get_shop(scope.company_id, payload.shop_id)
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return EmptyPayload()


# --- Подписки покупателя ---


async def op_public_notify_back(
    payload: ShopNotifyBackPayload, *, user: User, di: Di
) -> ShopNotifyBackResponse:
    """«Сообщить о появлении»: подписка на недоступный товар (customer-сессия)."""
    _ = user
    customer = require_customer()
    try:
        shop = await di.order_service.resolve_published_shop(payload.slug)
        subscribed = await di.feed_service.subscribe_back_in_stock(
            shop.shop_id, payload.product_id, customer.customer_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ShopNotifyBackResponse(subscribed=subscribed)


async def op_public_personal(
    payload: ShopPersonalPayload, *, user: User, di: Di
) -> ShopPersonalResponse:
    """``/personal``: «как всегда» и подписки покупателя (customer-сессия)."""
    _ = user
    customer = require_customer()
    try:
        shop = await di.order_service.resolve_published_shop(payload.slug)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return await di.feed_service.personal(shop, customer.customer_id)


async def op_public_favorite_set(
    payload: ShopFavoriteSetPayload, *, user: User, di: Di
) -> ShopFavoriteResponse:
    """Сердечко «в избранное» — идемпотентное состояние (customer-сессия)."""
    _ = user
    customer = require_customer()
    try:
        shop = await di.order_service.resolve_published_shop(payload.slug)
        favorite = await di.feed_service.set_favorite(
            shop.shop_id, payload.product_id, customer.customer_id, payload.favorite
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ShopFavoriteResponse(favorite=favorite)


async def op_public_feedback_set(
    payload: ShopFeedbackSetPayload, *, user: User, di: Di
) -> ShopOrderFeedbackResponse:
    """Оценка выполненного заказа — идемпотентна по заказу (customer-сессия)."""
    _ = user
    customer = require_customer()
    try:
        shop = await di.order_service.resolve_published_shop(payload.slug)
        feedback = await di.feed_service.set_feedback(
            shop.shop_id,
            payload.public_code,
            customer.customer_id,
            payload.rating,
            payload.chips,
            payload.comment,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    # Рейтинг витрины живёт в снапшоте — ребилд обновляет бейдж.
    await _enqueue_rebuild(di, shop.shop_id, shop.slug)
    return feedback_response(feedback)


async def op_public_reviews_list(
    payload: ShopReviewsListPayload, *, user: User, di: Di
) -> ShopReviewsResponse:
    """Публичная лента отзывов витрины + агрегат рейтинга (анонимно)."""
    _ = user
    try:
        shop = await di.order_service.resolve_published_shop(payload.slug)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return await di.feed_service.reviews(
        shop.shop_id, limit=payload.limit, offset=payload.offset
    )


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
        # Событие и уведомления — внутри сервиса: единая точка для admin-op
        # и отмены покупателем.
        order = await di.order_service.set_status(shop, payload.shop_order_id, payload.status)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
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
    return ShopOrderCreatedResponse(
        public_code=order.public_code,
        status=ShopOrderStatus(order.status),
        status_label=order_status_label(
            ShopOrderStatus(order.status), order.delivery_type
        ),
        delivery_type=order.delivery_type,
        table_label=order.table_label,
        loyalty_reward_minor=order.loyalty_reward_minor,
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
        status_label=order_status_label(
            ShopOrderStatus(order.status), order.delivery_type
        ),
        total_minor=order.total_minor,
        currency=order.currency,
        delivery_type=order.delivery_type,
        table_label=order.table_label,
        created_at=order.created_at.isoformat(),
    )


# --- Кабинет покупателя: сквозная история и гео витрины ---


_ACTIVE_STATUSES = [
    ShopOrderStatus.NEW,
    ShopOrderStatus.ACCEPTED,
    ShopOrderStatus.PREPARING,
    ShopOrderStatus.DELIVERING,
]
_DONE_STATUSES = [ShopOrderStatus.DONE, ShopOrderStatus.CANCELLED]


def _my_statuses(payload: ShopMyOrdersListPayload) -> list[ShopOrderStatus] | None:
    if payload.status is not None:
        return [ShopOrderStatus(payload.status)]
    if payload.active is True:
        return _ACTIVE_STATUSES
    if payload.active is False:
        return _DONE_STATUSES
    return None


async def op_public_my_orders_list(
    payload: ShopMyOrdersListPayload, *, user: User, di: Di
) -> OffsetPage[ShopMyOrderListItemResponse]:
    """Сквозная история заказов покупателя по всем витринам платформы."""
    _ = user
    customer = require_customer()
    orders, shops, items_by_order, total = await di.order_service.list_customer_orders(
        customer.customer_id,
        statuses=_my_statuses(payload),
        limit=payload.limit,
        offset=payload.offset,
    )
    feedbacks = await di.feed_service.feedback_by_order_ids(
        [o.shop_order_id for o in orders]
    )
    return OffsetPage(
        items=[
            di.order_service.my_order_list_item(
                order,
                shops.get(order.shop_id),
                storefront_url=(
                    di.storefront_service.storefront_url(shops[order.shop_id])
                    if order.shop_id in shops
                    else ""
                ),
                items_preview=[
                    ShopOrderItemPreview(name=i.name_snapshot, qty=i.qty)
                    for i in items_by_order.get(order.shop_order_id, [])
                ],
                feedback=(
                    feedback_response(feedbacks[order.shop_order_id])
                    if order.shop_order_id in feedbacks
                    else None
                ),
            )
            for order in orders
        ],
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_public_my_order_get(
    payload: ShopMyOrderCodePayload, *, user: User, di: Di
) -> ShopMyOrderDetailResponse:
    """Карточка заказа покупателя: позиции, таймлайн статусов, гео доставки."""
    _ = user
    customer = require_customer()
    try:
        order, shop, items = await di.order_service.customer_order_detail(
            customer.customer_id, payload.public_code
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    feedbacks = await di.feed_service.feedback_by_order_ids([order.shop_order_id])
    own = feedbacks.get(order.shop_order_id)
    return await di.order_service.my_order_detail(
        order,
        shop,
        items,
        storefront_url=(
            di.storefront_service.storefront_url(shop) if shop is not None else ""
        ),
        feedback=feedback_response(own) if own is not None else None,
    )


async def op_public_my_order_cancel(
    payload: ShopMyOrderCodePayload, *, user: User, di: Di
) -> ShopMyOrderDetailResponse:
    """Отмена заказа покупателем: только пока статус `new` — дальше зовёт магазин."""
    _ = user
    customer = require_customer()
    try:
        order = await di.order_service.customer_cancel(
            customer.customer_id, payload.public_code
        )
        _, shop, items = await di.order_service.customer_order_detail(
            customer.customer_id, payload.public_code
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    return await di.order_service.my_order_detail(
        order,
        shop,
        items,
        storefront_url=(
            di.storefront_service.storefront_url(shop) if shop is not None else ""
        ),
    )


async def op_public_storefront_geo(
    payload: ShopStorefrontGeoPayload, *, user: User, di: Di
) -> ShopStorefrontGeoResponse:
    """Точка магазина и зона доставки для карты витрины (анонимно)."""
    _ = user
    geo = await di.storefront_service.geo_payload(payload.slug)
    if geo is None:
        raise_not_found(
            PlatformNotFoundError("Storefront not found", error_code="storefront_not_found")
        )
    return ShopStorefrontGeoResponse.model_validate(geo)


# --- AI-операции (канонический core.ai runtime, биллинг внутри клиентов) ---


async def _ai_call(
    *, verb: str, scope: CompanyScope, shop_id: str, kwargs: dict[str, JsonValue]
) -> ShopAiCallResponse:
    """Постановка AI-вызова в TaskIQ; результат — ``shop/ai_call/finished`` по ``call_id``."""
    call_id = new_id("aicall")
    _ = await enqueue(
        SHOP_AI_CALL,
        verb=verb,
        call_id=call_id,
        company_id=scope.company_id,
        user_id=scope.user_id,
        shop_id=shop_id,
        kwargs=kwargs,
    )
    return ShopAiCallResponse(call_id=call_id)


async def op_ai_describe_product(
    payload: ShopAiDescribePayload, *, user: User, di: Di
) -> ShopAiCallResponse:
    """AI-описание блюда: по названию, при наличии — vision по фото."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    return await _ai_call(
        verb="describe_product",
        scope=scope,
        shop_id=payload.shop_id,
        kwargs={
            "name": payload.name,
            "category_name": payload.category_name,
            "photo_file_id": payload.photo_file_id,
        },
    )


async def op_ai_suggest_options(
    payload: ShopAiSuggestOptionsPayload, *, user: User, di: Di
) -> ShopAiCallResponse:
    """AI-предложение опций-модификаторов по названию блюда."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    return await _ai_call(
        verb="suggest_options",
        scope=scope,
        shop_id=payload.shop_id,
        kwargs={
            "product_name": payload.product_name,
            "group_name": payload.group_name,
        },
    )


async def op_ai_enhance_photo(
    payload: ShopAiEnhancePhotoPayload, *, user: User, di: Di
) -> ShopAiCallResponse:
    """Улучшение фото блюда через image_gen — вернёт новый file_id."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    return await _ai_call(
        verb="enhance_product_photo",
        scope=scope,
        shop_id=payload.shop_id,
        kwargs={"file_id": payload.file_id},
    )


async def op_ai_generate_photo(
    payload: ShopAiGeneratePhotoPayload, *, user: User, di: Di
) -> ShopAiCallResponse:
    """Генерация фото товара с нуля — вернёт file_id."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    return await _ai_call(
        verb="generate_product_photo",
        scope=scope,
        shop_id=payload.shop_id,
        kwargs={"name": payload.name, "description": payload.description},
    )


async def op_ai_describe_batch(
    payload: ShopAiDescribeBatchPayload, *, user: User, di: Di
) -> ShopAiBatchResponse:
    """Постановка фоновой AI-генерации описаний для всех позиций без текста."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    listings = await di.shop_service.list_products(scope.company_id, payload.shop_id)
    pending = sum(1 for p in listings if not p.description.strip())
    _ = await enqueue(
        SHOP_AI_DESCRIBE_BATCH,
        shop_id=payload.shop_id,
        company_id=scope.company_id,
    )
    return ShopAiBatchResponse(enqueued=max(pending, 0))


async def op_ai_parse_menu(
    payload: ShopAiParseMenuPayload, *, user: User, di: Di
) -> ShopAiCallResponse:
    """AI-разбор свободного текста меню в позиции каталога (импорт-превью)."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    return await _ai_call(
        verb="parse_menu",
        scope=scope,
        shop_id=payload.shop_id,
        kwargs={"text": payload.text},
    )


async def op_ai_describe_shop(
    payload: ShopAiShopPayload, *, user: User, di: Di
) -> ShopAiCallResponse:
    """AI-описание магазина для витрины (улучшает черновик, если передан)."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    shop = await _shop_in_scope(di, scope.company_id, payload.shop_id)
    return await _ai_call(
        verb="describe_shop",
        scope=scope,
        shop_id=payload.shop_id,
        kwargs={
            "name": payload.name,
            "description": payload.description,
            "city": shop.city or "",
        },
    )


async def op_ai_generate_cover(
    payload: ShopAiShopPayload, *, user: User, di: Di
) -> ShopAiCallResponse:
    """AI-генерация обложки витрины — вернёт file_id."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    return await _ai_call(
        verb="generate_shop_cover",
        scope=scope,
        shop_id=payload.shop_id,
        kwargs={"name": payload.name, "description": payload.description},
    )


async def op_ai_generate_logo(
    payload: ShopAiShopPayload, *, user: User, di: Di
) -> ShopAiCallResponse:
    """AI-генерация логотипа витрины — вернёт file_id."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    await _assert_shop_in_scope(di, scope.company_id, payload.shop_id)
    return await _ai_call(
        verb="generate_shop_logo",
        scope=scope,
        shop_id=payload.shop_id,
        kwargs={"name": payload.name, "description": payload.description},
    )


async def op_ai_autofill(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ShopAiCallResponse:
    """AI-оформление витрины одной командой: описание и обложка в пустые поля.

    Заполненные вручную поля не перетираются — точечная перегенерация
    остаётся на кнопках describe-shop/generate-cover в настройках.
    """
    scope = await require_company_admin(di.authz_service)
    _ = user
    _ = await _shop_in_scope(di, scope.company_id, payload.shop_id)
    return await _ai_call(
        verb="autofill", scope=scope, shop_id=payload.shop_id, kwargs={}
    )


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
        photo_file_id=option.photo_file_id,
        nutrition_delta=ShopNutrition.model_validate(option.nutrition_delta or {}),
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


# --- Лояльность: программа «N-я покупка — награда» ---


def _loyalty_program_response(
    program: ShopLoyaltyProgram,
) -> ShopLoyaltyProgramResponse:
    return ShopLoyaltyProgramResponse(
        shop_id=program.shop_id,
        orders_goal=program.orders_goal,
        reward_kind=ShopLoyaltyRewardKind(program.reward_kind),
        reward_value=program.reward_value,
    )


async def op_loyalty_program_get(
    payload: ShopLoyaltyProgramPayload, *, user: User, di: Di
) -> ShopLoyaltyProgramResponse:
    """Настройки программы лояльности магазина (дефолты, если не задана)."""
    scope = await require_company_viewer(di.authz_service)
    _ = user
    try:
        program = await di.loyalty_service.get_program(
            scope.company_id, payload.shop_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return _loyalty_program_response(program)


async def op_loyalty_program_set(
    payload: ShopLoyaltyProgramSetPayload, *, user: User, di: Di
) -> ShopLoyaltyProgramResponse:
    """Записать программу лояльности: цель, тип и размер награды."""
    scope = await require_company_admin(di.authz_service)
    _ = user
    try:
        program = await di.loyalty_service.set_program(
            scope.company_id,
            payload.shop_id,
            orders_goal=payload.orders_goal,
            reward_kind=payload.reward_kind,
            reward_value=payload.reward_value,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    await _rebuild_for_shop(di, scope.company_id, payload.shop_id)
    return _loyalty_program_response(program)


async def op_public_cart_price(
    payload: ShopCartPricePayload, *, user: User, di: Di
) -> ShopCartPriceResponse:
    """Живой расчёт корзины витрины: цены + скидки, анонимный путь.

    С customer-сессией учитывает предпросмотр награды лояльности
    (``use_loyalty_reward``) — без списания.
    """
    _ = user
    customer = optional_customer()
    try:
        shop = await di.order_service.resolve_published_shop(payload.slug)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    try:
        return await di.order_service.price_cart(
            shop, payload, customer_id=customer.customer_id if customer else ""
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
