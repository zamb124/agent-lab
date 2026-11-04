"""Pydantic-модели API/WS домена shop."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from apps.shop.models.enums import (
    ShopAllergen,
    ShopDeliveryType,
    ShopKind,
    ShopMeasureUnit,
    ShopMenuStatus,
    ShopOrderSource,
    ShopOrderStatus,
    ShopStatus,
)
from apps.shop.models.menu_section import ShopMenuSection
from apps.shop.models.nutrition import ShopNutrition
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


class ShopBadge(StrictBaseModel):
    """Метка из собственного набора магазина.

    ``key`` можно не передавать — сервер сгенерирует уникальный;
    ``icon`` — имя иконки из серверного каталога ``BADGE_ICONS``.
    """

    key: str = Field(default="", pattern=r"^[a-z0-9_]{0,30}$")
    label: str = Field(min_length=1, max_length=60)
    icon: str = Field(min_length=1, max_length=60)


class ShopBadgeResponse(StrictBaseModel):
    key: str
    label: str
    icon: str
    icon_path: str


class ShopBadgeIconsResponse(StrictBaseModel):
    """Каталог иконок меток: имя → SVG path (viewBox 0 -960 960 960)."""

    icons: dict[str, str]


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
    badges: list[ShopBadgeResponse]
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
    badges: list[ShopBadge] | None = Field(default=None, max_length=20)


class ShopProductResponse(StrictBaseModel):
    shop_product_id: str
    shop_id: str
    name: str
    description: str
    measure: int | None
    measure_unit: ShopMeasureUnit
    ingredients: list[str]
    nutrition: ShopNutrition | None
    allergens: list[ShopAllergen]
    badges: list[str]
    price_minor: int
    photo_file_id: str | None
    is_available: bool
    ai_unverified: bool
    similar_shop_product_id: str | None
    sort: int


class ShopProductCreateRequest(StrictBaseModel):
    """Новое блюдо каталога; ``ai_unverified`` ставит агентный импорт."""

    name: str = Field(min_length=1, max_length=300)
    description: str = ""
    measure: int | None = Field(default=None, ge=0)
    measure_unit: ShopMeasureUnit = ShopMeasureUnit.G
    ingredients: list[str] = Field(default_factory=list, max_length=100)
    nutrition: ShopNutrition | None = None
    allergens: list[ShopAllergen] = Field(default_factory=list)
    badges: list[str] = Field(default_factory=list, max_length=5)
    price_minor: int = Field(ge=0)
    photo_file_id: str | None = None
    ai_unverified: bool = False


class ShopProductUpdateRequest(StrictBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    measure: int | None = Field(default=None, ge=0)
    measure_unit: ShopMeasureUnit | None = None
    ingredients: list[str] | None = Field(default=None, max_length=100)
    nutrition: ShopNutrition | None = None
    allergens: list[ShopAllergen] | None = None
    badges: list[str] | None = Field(default=None, max_length=5)
    price_minor: int | None = Field(default=None, ge=0)
    photo_file_id: str | None = None
    is_available: bool | None = None
    sort: int | None = None


class ShopProductsReorderRequest(StrictBaseModel):
    """Новый порядок позиций: ids в желаемой последовательности."""

    product_ids: list[str] = Field(min_length=1, max_length=1000)


class ShopProductSimilarResponse(StrictBaseModel):
    """Кандидат на объединение: блюдо каталога и pg_trgm similarity названия."""

    product: ShopProductResponse
    score: float


ShopProductMergeField = Literal[
    "name",
    "description",
    "measure",
    "measure_unit",
    "ingredients",
    "nutrition",
    "allergens",
    "badges",
    "price_minor",
    "photo_file_id",
]


class ShopProductMergeRequest(StrictBaseModel):
    """Слияние блюда в ``into_shop_product_id``.

    Поля из ``fields`` переносятся с исходного блюда в целевое, позиции меню
    исходного блюда переходят к целевому, исходное блюдо удаляется.
    """

    into_shop_product_id: str = Field(min_length=1)
    fields: list[ShopProductMergeField] = Field(default_factory=list)


class ShopMenuItemResponse(StrictBaseModel):
    """Позиция меню с итоговой ценой: override позиции или цена каталога."""

    shop_menu_item_id: str
    shop_menu_id: str
    shop_menu_section_id: str
    shop_product_id: str
    price_minor_override: int | None
    is_available: bool
    sort: int
    effective_price_minor: int


class ShopMenuResponse(StrictBaseModel):
    """Меню целиком: разделы по sort и позиции по (раздел, sort)."""

    shop_menu_id: str
    shop_id: str
    name: str
    status: ShopMenuStatus
    sort: int
    sections: list[ShopMenuSection]
    items: list[ShopMenuItemResponse]


class ShopMenuCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, max_length=200)


class ShopMenuUpdateRequest(StrictBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class ShopMenusReorderRequest(StrictBaseModel):
    """Новый порядок меню заведения: ids в желаемой последовательности."""

    shop_menu_ids: list[str] = Field(min_length=1, max_length=200)


class ShopMenuSetStatusRequest(StrictBaseModel):
    status: ShopMenuStatus


class ShopMenuSectionCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: str | None = None


class ShopMenuSectionUpdateRequest(StrictBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class ShopMenuSectionReorderItem(StrictBaseModel):
    """Узел дерева разделов: раздел и его родитель после перестановки."""

    shop_menu_section_id: str = Field(min_length=1)
    parent_id: str | None = None


class ShopMenuSectionsReorderRequest(StrictBaseModel):
    """Полное дерево разделов меню: все узлы в depth-first порядке.

    ``sort`` каждого раздела вычисляется сервером — позиция среди siblings
    в порядке обхода ``items``. Все разделы меню обязаны присутствовать.
    """

    items: list[ShopMenuSectionReorderItem] = Field(min_length=1, max_length=500)


class ShopMenuItemAddRequest(StrictBaseModel):
    shop_menu_section_id: str = Field(min_length=1)
    shop_product_id: str = Field(min_length=1)
    price_minor_override: int | None = Field(default=None, ge=0)
    is_available: bool = True


class ShopMenuItemUpdateRequest(StrictBaseModel):
    """Patch позиции: явный ``price_minor_override: null`` возвращает цену каталога."""

    price_minor_override: int | None = Field(default=None, ge=0)
    is_available: bool | None = None


class ShopMenuItemMoveRequest(StrictBaseModel):
    """Перенос позиции в другой раздел того же меню — в конец раздела."""

    shop_menu_section_id: str = Field(min_length=1)


class ShopMenuItemsReorderRequest(StrictBaseModel):
    """Новый порядок позиций раздела: ids в желаемой последовательности."""

    shop_menu_section_id: str = Field(min_length=1)
    shop_menu_item_ids: list[str] = Field(min_length=1, max_length=1000)


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
    """Строка корзины: позиция активного меню витрины — она задаёт блюдо и цену."""

    shop_menu_item_id: str = Field(min_length=1)
    qty: int = Field(ge=1, le=99)
    selections: list[ShopOrderItemSelection] = Field(default_factory=list, max_length=50)


class ShopOrderItemModifierResponse(StrictBaseModel):
    group_name: str
    option_name: str
    price_minor: int
    qty: int


class ShopOrderItemResponse(StrictBaseModel):
    product_id: str
    shop_menu_item_id: str | None
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
    shop_menu_item_id: str
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
