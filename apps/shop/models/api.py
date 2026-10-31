"""Pydantic-модели API/WS домена shop."""

from __future__ import annotations

from pydantic import Field

from apps.shop.models.enums import (
    ShopDeliveryType,
    ShopKind,
    ShopOrderSource,
    ShopOrderStatus,
    ShopStatus,
)
from core.models import StrictBaseModel
from core.types import JsonObject


class ShopTheme(StrictBaseModel):
    """Визуальная тема витрины: акцентный цвет, пресет раскладки и режим."""

    accent_color: str = Field(default="#e2553f", max_length=16)
    preset: str = Field(default="menu", max_length=32)
    mode: str = Field(default="dark", pattern=r"^(dark|light)$")


class ShopWorkingHours(StrictBaseModel):
    """Часы работы на каждый день недели (0=пн) в формате HH:MM-HH:MM."""

    days: dict[str, str] = Field(default_factory=dict)


class ShopResponse(StrictBaseModel):
    shop_id: str
    slug: str
    kind: ShopKind
    name: str
    description: str
    logo_file_id: str | None
    cover_file_id: str | None
    phone: str
    city: str
    address: str
    timezone: str
    working_hours: dict[str, str]
    delivery_enabled: bool
    pickup_enabled: bool
    delivery_fee_minor: int
    min_order_minor: int
    currency: str
    theme: ShopTheme
    status: ShopStatus
    telegram_chat_id: str | None
    telegram_connected: bool
    storefront_url: str
    plan: str
    products_count: int = 0


class ShopTelegramConnectRequest(StrictBaseModel):
    bot_token: str = Field(min_length=20, max_length=128)


class ShopCreateRequest(StrictBaseModel):
    slug: str = Field(min_length=3, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    kind: ShopKind = ShopKind.RESTAURANT


class ShopUpdateRequest(StrictBaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    kind: ShopKind | None = None
    logo_file_id: str | None = None
    cover_file_id: str | None = None
    phone: str | None = Field(default=None, max_length=32)
    city: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    timezone: str | None = Field(default=None, max_length=64)
    working_hours: dict[str, str] | None = None
    delivery_enabled: bool | None = None
    pickup_enabled: bool | None = None
    delivery_fee_minor: int | None = Field(default=None, ge=0)
    min_order_minor: int | None = Field(default=None, ge=0)
    theme: ShopTheme | None = None


class ShopCategoryResponse(StrictBaseModel):
    shop_category_id: str
    shop_id: str
    name: str
    sort: int
    is_active: bool


class ShopCategoryCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, max_length=200)


class ShopCategoryUpdateRequest(StrictBaseModel):
    name: str | None = Field(default=None, max_length=200)
    sort: int | None = None
    is_active: bool | None = None


class ShopProductResponse(StrictBaseModel):
    shop_product_id: str
    shop_id: str
    category_id: str | None
    name: str
    description: str
    portion: str
    price_minor: int
    photo_file_id: str | None
    is_available: bool
    sort: int


class ShopProductCreateRequest(StrictBaseModel):
    category_id: str | None = None
    name: str = Field(min_length=1, max_length=300)
    description: str = ""
    portion: str = Field(default="", max_length=50)
    price_minor: int = Field(ge=0)
    photo_file_id: str | None = None


class ShopProductUpdateRequest(StrictBaseModel):
    category_id: str | None = None
    name: str | None = Field(default=None, max_length=300)
    description: str | None = None
    portion: str | None = Field(default=None, max_length=50)
    price_minor: int | None = Field(default=None, ge=0)
    photo_file_id: str | None = None
    is_available: bool | None = None
    sort: int | None = None


class ShopProductImportItem(StrictBaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str = ""
    portion: str = Field(default="", max_length=50)
    price_minor: int = Field(ge=0)


class ShopProductsImportRequest(StrictBaseModel):
    category_id: str | None = None
    items: list[ShopProductImportItem] = Field(min_length=1, max_length=500)


class ShopProductsImportResponse(StrictBaseModel):
    created: int


class ShopProductsReorderRequest(StrictBaseModel):
    """Новый порядок позиций: ids в желаемой последовательности."""

    product_ids: list[str] = Field(min_length=1, max_length=1000)


class ShopCategoriesReorderRequest(StrictBaseModel):
    """Новый порядок категорий меню: ids в желаемой последовательности."""

    category_ids: list[str] = Field(min_length=1, max_length=200)


class ShopAiDescribeRequest(StrictBaseModel):
    name: str = Field(min_length=1, max_length=300)
    category_name: str | None = Field(default=None, max_length=200)
    photo_file_id: str | None = None


class ShopAiEnhancePhotoRequest(StrictBaseModel):
    file_id: str = Field(min_length=1)


class ShopAiBriefRequest(StrictBaseModel):
    """Бриф для AI-генерации: название объекта + опциональный контекст."""

    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=1000)


class ShopModifierGroupCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    kind: str = Field(default="addon", pattern=r"^(addon|remove)$")
    selection_mode: str = Field(default="multi", pattern=r"^(single|multi)$")
    min_selected: int = Field(default=0, ge=0, le=50)
    max_selected: int | None = Field(default=None, ge=1, le=99)
    price_mode: str = Field(default="delta", pattern=r"^(delta|absolute)$")


class ShopModifierGroupUpdateRequest(StrictBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    selection_mode: str | None = Field(default=None, pattern=r"^(single|multi)$")
    min_selected: int | None = Field(default=None, ge=0, le=50)
    max_selected: int | None = Field(default=None, ge=1, le=99)
    is_active: bool | None = None
    sort: int | None = None


class ShopModifierGroupResponse(StrictBaseModel):
    shop_modifier_group_id: str
    shop_id: str
    name: str
    description: str
    kind: str
    selection_mode: str
    min_selected: int
    max_selected: int | None
    price_mode: str
    is_active: bool
    sort: int
    product_ids: list[str]
    options: list["ShopModifierOptionResponse"]


class ShopModifierGroupsResponse(StrictBaseModel):
    groups: list[ShopModifierGroupResponse]


class ShopAiOptionSuggestion(StrictBaseModel):
    name: str
    price_minor: int = Field(ge=0, le=10_000_000)


class ShopAiSuggestOptionsRequest(StrictBaseModel):
    product_name: str = Field(min_length=1, max_length=300)
    group_name: str | None = Field(default=None, max_length=200)


class ShopAiSuggestOptionsResponse(StrictBaseModel):
    items: list[ShopAiOptionSuggestion]


class ShopAiMenuItem(StrictBaseModel):
    """Позиция, извлечённая AI из свободного текста меню."""

    name: str
    price_minor: int = Field(ge=0, le=10_000_000)
    description: str = ""
    portion: str = Field(default="", max_length=50)
    category: str = ""


class ShopAiParseMenuRequest(StrictBaseModel):
    text: str = Field(min_length=3, max_length=50_000)


class ShopAiParseMenuResponse(StrictBaseModel):
    items: list[ShopAiMenuItem]


class ShopModifierOptionCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, max_length=200)
    price_minor: int = Field(default=0, ge=0, le=10_000_000)
    is_default: bool = False
    max_per_option: int = Field(default=1, ge=1, le=20)
    nested_group_id: str | None = Field(default=None, max_length=64)
    external_id: str | None = Field(default=None, max_length=128)


class ShopModifierOptionUpdateRequest(StrictBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    price_minor: int | None = Field(default=None, ge=0, le=10_000_000)
    is_default: bool | None = None
    is_available: bool | None = None
    max_per_option: int | None = Field(default=None, ge=1, le=20)
    sort: int | None = None


class ShopModifierOptionResponse(StrictBaseModel):
    shop_modifier_option_id: str
    group_id: str
    name: str
    price_minor: int
    is_default: bool
    is_available: bool
    max_per_option: int
    nested_group_id: str | None
    sort: int


class ShopProductModifierGroupAttachRequest(StrictBaseModel):
    """Тело REST attach: контекстные лимиты группы для конкретного товара."""

    min_selected: int | None = Field(default=None, ge=0, le=50)
    max_selected: int | None = Field(default=None, ge=1, le=99)


class ShopOrderItemSelection(StrictBaseModel):
    """Выбранная опция модификатора: без цены — сервер считает сам."""

    option_id: str = Field(min_length=1)
    qty: int = Field(default=1, ge=1, le=20)


class ShopOrderItemRequest(StrictBaseModel):
    product_id: str = Field(min_length=1)
    qty: int = Field(ge=1, le=99)
    selections: list[ShopOrderItemSelection] = Field(default_factory=list, max_length=50)


class ShopOrderItemModifierResponse(StrictBaseModel):
    group_name: str
    option_name: str
    price_minor: int
    qty: int


class ShopOrderItemResponse(StrictBaseModel):
    product_id: str
    name: str
    price_minor: int
    qty: int
    discount_minor: int = 0
    modifiers: list[ShopOrderItemModifierResponse] = []


class ShopPromoAppliedResponse(StrictBaseModel):
    promo_id: str
    name: str
    saved_minor: int


class ShopOrderResponse(StrictBaseModel):
    shop_order_id: str
    shop_id: str
    public_code: str
    status: ShopOrderStatus
    customer_name: str
    customer_phone: str
    delivery_type: ShopDeliveryType
    address: str
    comment: str
    items_total_minor: int
    discount_minor: int
    delivery_fee_minor: int
    total_minor: int
    promos: list[ShopPromoAppliedResponse] = []
    currency: str
    source: ShopOrderSource
    created_at: str
    items: list[ShopOrderItemResponse]


class ShopOrderCreateRequest(StrictBaseModel):
    """Заказ покупателя: позиции + контакты + идемпотентность."""

    items: list[ShopOrderItemRequest] = Field(min_length=1, max_length=99)
    customer_name: str = Field(min_length=1, max_length=200)
    customer_phone: str = Field(min_length=5, max_length=32)
    delivery_type: ShopDeliveryType
    address: str = Field(default="", max_length=500)
    comment: str = Field(default="", max_length=1000)
    source: ShopOrderSource = ShopOrderSource.WEB
    idempotency_key: str = Field(default="", max_length=128)
    honeypot: str = Field(default="", max_length=64)


class ShopOrderCreatedResponse(StrictBaseModel):
    public_code: str
    status: ShopOrderStatus
    total_minor: int
    currency: str


class ShopOrderStatusResponse(StrictBaseModel):
    public_code: str
    status: ShopOrderStatus
    total_minor: int
    currency: str
    delivery_type: ShopDeliveryType
    created_at: str


class ShopCartPriceRequest(StrictBaseModel):
    """Живой расчёт корзины без создания заказа: цены, скидки, акции."""

    items: list[ShopOrderItemRequest] = Field(min_length=1, max_length=99)
    delivery_type: ShopDeliveryType = ShopDeliveryType.PICKUP


class ShopCartPriceLineResponse(StrictBaseModel):
    product_id: str
    qty: int
    unit_minor: int
    discount_minor: int


class ShopCartPriceResponse(StrictBaseModel):
    lines: list[ShopCartPriceLineResponse]
    items_total_minor: int
    discount_minor: int
    delivery_fee_minor: int
    total_minor: int
    applied_promos: list[ShopPromoAppliedResponse]
    below_min_order: bool


class ShopPromoCreateRequest(StrictBaseModel):
    """Акция: condition + action JSONB + window + политика применения."""

    name: str = Field(min_length=1, max_length=200)
    is_active: bool = True
    sort: int | None = Field(default=None, ge=0)
    priority: int = Field(default=0, ge=-100, le=100)
    stacking: str = Field(default="all", pattern=r"^(all|exclusive)$")
    window: JsonObject = Field(default_factory=dict)
    condition: JsonObject
    action: JsonObject


class ShopPromoUpdateRequest(StrictBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    sort: int | None = Field(default=None, ge=0)
    priority: int | None = Field(default=None, ge=-100, le=100)
    stacking: str | None = Field(default=None, pattern=r"^(all|exclusive)$")
    window: JsonObject | None = None
    condition: JsonObject | None = None
    action: JsonObject | None = None


class ShopPromoResponse(StrictBaseModel):
    shop_promo_id: str
    shop_id: str
    name: str
    is_active: bool
    sort: int
    priority: int
    stacking: str
    window: JsonObject
    condition: JsonObject
    action: JsonObject


class ShopPromosResponse(StrictBaseModel):
    promos: list[ShopPromoResponse]
