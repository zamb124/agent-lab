"""Pydantic-модели API/WS домена shop."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from apps.shop.models.enums import (
    ShopDeliveryType,
    ShopFeedbackChip,
    ShopKind,
    ShopLoyaltyRewardKind,
    ShopOrderSource,
    ShopOrderStatus,
    ShopStatus,
)
from core.models import StrictBaseModel
from core.types import JsonObject


class ShopThemeCustom(StrictBaseModel):
    """Мерчант-кастомизация витрины — код владельца магазина.

    Слоты — именованные точки монтажа в shell (аналог Shopify Custom
    Liquid): `head_html` — в `</head>` (метрики, шрифты), `css` — в конец
    `<style>` (переопределения), `js` — в конец `<script>` (обработчики),
    `blocks` — собственные HTML-блоки по имени слота. Статические слоты
    shell: `top` (перед `#app`), `bottom` (после `#app`). Якоря внутри
    витрины: `<anchor>:before` / `<anchor>:after`, где anchor — `hero`,
    `meta`, `catalog`; монтируются клиентом через `slot()` в
    `blocks/ui.py`. Ограничения размера защищают snapshot; рендерится
    как есть — это код владельца витрины.
    """

    head_html: str = Field(default="", max_length=32_000)
    css: str = Field(default="", max_length=64_000)
    js: str = Field(default="", max_length=64_000)
    blocks: dict[str, Annotated[str, Field(max_length=32_000)]] = Field(default_factory=dict)


class ShopTheme(StrictBaseModel):
    """Визуальная тема витрины: акцентный цвет, пресет раскладки и режим.

    ``hero_style`` — подача шапки: ``card`` — карточка поверх обложки,
    ``cover`` — иммерсивный full-bleed с затемнением, ``minimal`` —
    компактный заголовок без обложки. ``backdrop`` — фон страницы:
    ``solid`` — нейтральный цвет темы, ``blur`` — размытая обложка под
    контентом. Градиентных фонов нет — контентный интерфейс не должен
    нагружать внимание фоном.
    """

    accent_color: str = Field(default="#e2553f", max_length=16)
    preset: str = Field(default="menu", max_length=32)
    mode: str = Field(default="dark", pattern=r"^(dark|light)$")
    hero_style: str = Field(default="card", pattern=r"^(card|cover|minimal)$")
    backdrop: str = Field(default="solid", pattern=r"^(solid|blur)$")
    custom: ShopThemeCustom = Field(default_factory=ShopThemeCustom)


def normalize_shop_theme(theme: JsonObject) -> JsonObject:
    """Сырые `shop.theme` → канон: легаси-ключ `accent` мапится в `accent_color`,
    убранный фон `gradient` — в `solid`."""
    normalized = dict(theme)
    if "accent_color" not in normalized:
        accent = normalized.pop("accent", None)
        if isinstance(accent, str):
            normalized["accent_color"] = accent
    else:
        _ = normalized.pop("accent", None)
    if normalized.get("backdrop") == "gradient":
        normalized["backdrop"] = "solid"
    return normalized


class ShopFeatures(StrictBaseModel):
    """Функциональные флаги витрины: «включил → получил функционал».

    Каждый флаг выключаем без следа в UI и данных: ``nutrition`` —
    полоса КБЖУ в карточке и поля в редакторе товара; ``back_in_stock`` —
    кнопка «Сообщить о появлении» и подписки на возврат позиций;
    ``favorites`` — сердечки на карточках и полка «Избранное» (только
    для авторизованных покупателей); ``reviews`` — оценка выполненного
    заказа, вкладка «Отзывы» и бейдж рейтинга витрины. Управляемые фичи
    (полки, баннеры) флага не требуют: нет данных — нет блока на витрине.
    """

    nutrition: bool = False
    back_in_stock: bool = True
    favorites: bool = True
    reviews: bool = True
    # «N-я покупка — награда»: прогресс-бар, claim в чекауте, возврат при отмене.
    loyalty: bool = False


def normalize_shop_features(features: JsonObject) -> JsonObject:
    """Сырые `shop.features` → канон: только известные флаги, bool."""
    return ShopFeatures.model_validate(
        {k: v for k, v in features.items() if isinstance(v, bool)}
    ).model_dump()


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
    lat: float | None
    lng: float | None
    timezone: str
    working_hours: dict[str, str]
    delivery_enabled: bool
    pickup_enabled: bool
    onsite_enabled: bool
    delivery_zone: JsonObject
    delivery_fee_minor: int
    min_order_minor: int
    prep_minutes: int
    courier_mode: str
    currency: str
    theme: ShopTheme
    features: ShopFeatures
    badges: list[ShopBadgeResponse]
    status: ShopStatus
    telegram_chat_id: str | None
    telegram_connected: bool
    demo_template: str | None
    storefront_url: str
    plan: str
    products_count: int = 0


class ShopTelegramConnectRequest(StrictBaseModel):
    bot_token: str = Field(min_length=20, max_length=128)


class ShopCreateRequest(StrictBaseModel):
    slug: str = Field(min_length=3, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    kind: ShopKind = ShopKind.RESTAURANT
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _lat_lng_pair(self) -> Self:
        """Точка магазина пишется парой: lat без lng (и наоборот) — ошибка ввода."""
        if ("lat" in self.model_fields_set) != ("lng" in self.model_fields_set):
            raise ValueError("lat and lng must be provided together")
        return self


CourierMode = Literal["car", "foot", "bike", "scooter"]


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
    onsite_enabled: bool | None = None
    delivery_zone: JsonObject | None = None
    delivery_fee_minor: int | None = Field(default=None, ge=0)
    min_order_minor: int | None = Field(default=None, ge=0)
    prep_minutes: int | None = Field(default=None, ge=0, le=600)
    courier_mode: CourierMode | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    theme: ShopTheme | None = None
    features: ShopFeatures | None = None
    badges: list[ShopBadge] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _lat_lng_pair(self) -> Self:
        """Точка магазина пишется парой: lat без lng (и наоборот) — ошибка ввода."""
        if ("lat" in self.model_fields_set) != ("lng" in self.model_fields_set):
            raise ValueError("lat and lng must be provided together")
        return self


class ShopTableResponse(StrictBaseModel):
    """Стол зала: ``shop_table_id`` попадает в QR-ссылку ``?table=``."""

    shop_table_id: str
    shop_id: str
    label: str


class ShopTableCreateRequest(StrictBaseModel):
    label: str = Field(min_length=1, max_length=64)


class ShopTableUpdateRequest(StrictBaseModel):
    label: str = Field(min_length=1, max_length=64)


class ShopCategoryResponse(StrictBaseModel):
    shop_category_id: str
    shop_id: str
    parent_id: str | None
    name: str
    sort: int
    is_active: bool


class ShopCategoryCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: str | None = None


class ShopCategoryUpdateRequest(StrictBaseModel):
    name: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None


class ShopNutrition(StrictBaseModel):
    """Пищевая ценность позиции на порцию.

    Все поля опциональны: владелец заполняет то, что знает (вручную
    или AI-оценкой). Отсутствие всего блока — полоса КБЖУ на витрине
    не рисуется. ``nutrition_delta`` опции прибавляется к этим значениям
    при выборе модификатора.
    """

    kcal: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    carb_g: float | None = Field(default=None, ge=0)


class ShopProductResponse(StrictBaseModel):
    """Листинг витрины: фасет + эффективный контент каталога.

    ``product_id`` — канонический id ``catalog_products``; имя/описание/
    галерея уже resolved по цепочке ``shop:<shop_id> → shop → base``,
    ``sources[field]`` — кто дал значение (``base`` | ``shop`` |
    ``shop:<id>``) для chain-toggle UI.
    """

    shop_id: str
    product_id: str
    category_id: str | None
    name: str
    description: str
    portion: str
    badges: list[str]
    price_minor: int
    photo_file_id: str | None
    image_file_ids: list[str]
    sources: dict[str, str]
    nutrition: ShopNutrition
    is_available: bool
    is_archived: bool
    sort: int


class ShopProductCreateRequest(StrictBaseModel):
    product_id: str | None = None
    """Подключить существующий товар каталога; без него — создать новый."""
    category_id: str | None = None
    name: str = Field(min_length=1, max_length=300)
    description: str = ""
    portion: str = Field(default="", max_length=50)
    badges: list[str] = Field(default_factory=list, max_length=5)
    price_minor: int = Field(ge=0)
    photo_file_id: str | None = None
    nutrition: ShopNutrition = Field(default_factory=ShopNutrition)


class ShopProductUpdateRequest(StrictBaseModel):
    category_id: str | None = None
    name: str | None = Field(default=None, max_length=300)
    description: str | None = None
    portion: str | None = Field(default=None, max_length=50)
    badges: list[str] | None = Field(default=None, max_length=5)
    price_minor: int | None = Field(default=None, ge=0)
    photo_file_id: str | None = None
    nutrition: ShopNutrition | None = None
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


class ShopCategoryReorderItem(StrictBaseModel):
    """Узел дерева категорий: категория и её родитель после перестановки."""

    category_id: str = Field(min_length=1)
    parent_id: str | None = None


class ShopCategoriesReorderRequest(StrictBaseModel):
    """Полное дерево категорий меню: все узлы в depth-first порядке.

    ``sort`` каждой категории вычисляется сервером — позиция среди siblings
    в порядке обхода ``items``. Все категории магазина обязаны присутствовать.
    """

    items: list[ShopCategoryReorderItem] = Field(min_length=1, max_length=200)


class ShopAiCallResponse(StrictBaseModel):
    """Приём AI-вызова: результат придёт push-событием ``shop/ai_call/finished``."""

    call_id: str
    status: str = "pending"


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


class ShopAiMenuItem(StrictBaseModel):
    """Позиция, извлечённая AI из свободного текста меню."""

    name: str
    price_minor: int = Field(ge=0, le=10_000_000)
    description: str = ""
    portion: str = Field(default="", max_length=50)
    category: str = ""


class ShopAiParseMenuRequest(StrictBaseModel):
    text: str = Field(min_length=3, max_length=50_000)


class ShopModifierOptionCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, max_length=200)
    price_minor: int = Field(default=0, ge=0, le=10_000_000)
    photo_file_id: str | None = None
    nutrition_delta: ShopNutrition = Field(default_factory=ShopNutrition)
    is_default: bool = False
    max_per_option: int = Field(default=1, ge=1, le=20)
    nested_group_id: str | None = Field(default=None, max_length=64)
    external_id: str | None = Field(default=None, max_length=128)


class ShopModifierOptionUpdateRequest(StrictBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    price_minor: int | None = Field(default=None, ge=0, le=10_000_000)
    photo_file_id: str | None = None
    nutrition_delta: ShopNutrition | None = None
    is_default: bool | None = None
    is_available: bool | None = None
    max_per_option: int | None = Field(default=None, ge=1, le=20)
    sort: int | None = None


class ShopModifierOptionResponse(StrictBaseModel):
    shop_modifier_option_id: str
    group_id: str
    name: str
    price_minor: int
    photo_file_id: str | None
    nutrition_delta: ShopNutrition
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
    # Id для точного повтора заказа; пустые у заказов до введения кабинета.
    group_id: str = ""
    option_id: str = ""


class ShopOrderItemResponse(StrictBaseModel):
    product_id: str
    name: str
    price_minor: int
    qty: int
    discount_minor: int = 0
    photo_file_id: str | None = None
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
    status_label: str
    customer_id: str = ""
    customer_name: str
    customer_phone: str
    delivery_type: ShopDeliveryType
    address: str
    delivery_eta_minutes: int | None = None
    delivery_flat: str = ""
    delivery_entrance: str = ""
    delivery_floor: str = ""
    delivery_intercom: str = ""
    table_id: str
    table_label: str
    comment: str
    items_total_minor: int
    discount_minor: int
    loyalty_reward_minor: int = 0
    delivery_fee_minor: int
    total_minor: int
    promos: list[ShopPromoAppliedResponse] = []
    currency: str
    source: ShopOrderSource
    created_at: str
    items: list[ShopOrderItemResponse]


class ShopOrderCreateRequest(StrictBaseModel):
    """Заказ покупателя: позиции + контакты + идемпотентность.

    Телефон берётся из верифицированной customer-сессии (customers.mdc),
    а не из ввода формы: заказ требует ``customer_token``. ``table_id``
    обязателен при ``delivery_type == onsite`` — стол из QR-ссылки витрины.
    """

    items: list[ShopOrderItemRequest] = Field(min_length=1, max_length=99)
    customer_name: str = Field(min_length=1, max_length=200)
    delivery_type: ShopDeliveryType
    address: str = Field(default="", max_length=500)
    customer_address_id: str = Field(default="", max_length=64)
    # Точка, выбранная покупателем (подсказка geo или пин на карте) — сервер
    # проверяет её зоной и не перегеокодирует текст.
    delivery_lat: float | None = Field(default=None, ge=-90, le=90)
    delivery_lng: float | None = Field(default=None, ge=-180, le=180)
    delivery_flat: str = Field(default="", max_length=32)
    delivery_entrance: str = Field(default="", max_length=32)
    delivery_floor: str = Field(default="", max_length=32)
    delivery_intercom: str = Field(default="", max_length=64)
    table_id: str | None = Field(default=None, max_length=64)
    comment: str = Field(default="", max_length=1000)
    # Применить доступную награду лояльности (списывается на сервере).
    use_loyalty_reward: bool = False
    source: ShopOrderSource = ShopOrderSource.WEB
    idempotency_key: str = Field(default="", max_length=128)
    honeypot: str = Field(default="", max_length=64)

    @model_validator(mode="after")
    def _delivery_point_pair(self) -> Self:
        """Координаты доставки едут парой: половина точки — ошибка ввода."""
        if ("delivery_lat" in self.model_fields_set) != (
            "delivery_lng" in self.model_fields_set
        ):
            raise ValueError("delivery_lat and delivery_lng must be provided together")
        return self


class ShopOrderCreatedResponse(StrictBaseModel):
    public_code: str
    status: ShopOrderStatus
    status_label: str
    delivery_type: ShopDeliveryType = ShopDeliveryType.PICKUP
    table_label: str = ""
    loyalty_reward_minor: int = 0
    total_minor: int
    currency: str


class ShopOrderStatusResponse(StrictBaseModel):
    public_code: str
    status: ShopOrderStatus
    status_label: str
    total_minor: int
    currency: str
    delivery_type: ShopDeliveryType
    table_label: str
    created_at: str


class ShopCartPriceRequest(StrictBaseModel):
    """Живой расчёт корзины без создания заказа: цены, скидки, акции."""

    items: list[ShopOrderItemRequest] = Field(min_length=1, max_length=99)
    delivery_type: ShopDeliveryType = ShopDeliveryType.PICKUP
    # Показать строку «Награда лояльности» — предпросмотр без списания.
    use_loyalty_reward: bool = False


class ShopCartPriceLineResponse(StrictBaseModel):
    product_id: str
    qty: int
    unit_minor: int
    discount_minor: int


class ShopCartPriceResponse(StrictBaseModel):
    lines: list[ShopCartPriceLineResponse]
    items_total_minor: int
    discount_minor: int
    loyalty_reward_minor: int = 0
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


# --- Кабинет покупателя (сквозная история по всем витринам) ---


class ShopOrderStatusEntry(StrictBaseModel):
    """Одна точка таймлайна статусов заказа."""

    status: ShopOrderStatus
    at: str


class ShopOrderItemPreview(StrictBaseModel):
    name: str
    qty: int


class ShopOrderFeedbackResponse(StrictBaseModel):
    """Отзыв покупателя на заказ — его карточка в кабинете.

    ``chip_labels`` — подписи тегов в полярности его оценки (4–5 —
    позитивные, 1–3 — негативные), локальные словари в JS запрещены.
    """

    rating: int
    chips: list[str]
    chip_labels: dict[str, str] = Field(default_factory=dict)
    comment: str = ""
    created_at: str


class ShopMyOrderShopBlock(StrictBaseModel):
    """Магазин заказа — кто и где его исполняет (для кросс-витринной ленты)."""

    shop_id: str
    slug: str
    name: str
    kind: ShopKind = ShopKind.RESTAURANT
    logo_file_id: str | None = None
    phone: str = ""
    address: str = ""
    city: str = ""
    working_hours: JsonObject = Field(default_factory=dict)
    open_now: bool = False
    is_published: bool = False
    storefront_url: str = ""
    lat: float | None = None
    lng: float | None = None


class ShopMyOrderListItemResponse(StrictBaseModel):
    """Строка `GET /public/my/orders` — заказ покупателя любой витрины."""

    public_code: str
    status: ShopOrderStatus
    status_label: str
    status_changed_at: str
    created_at: str
    active: bool
    total_minor: int
    currency: str
    delivery_type: ShopDeliveryType
    address: str = ""
    table_label: str = ""
    delivery_eta_minutes: int | None = None
    items_preview: list[ShopOrderItemPreview] = Field(default_factory=list)
    items_count: int = 0
    shop: ShopMyOrderShopBlock
    # Оценка заказа: can_review — завершён и витрина принимает отзывы.
    can_review: bool = False
    feedback: ShopOrderFeedbackResponse | None = None


class ShopMyOrderDetailResponse(ShopMyOrderListItemResponse):
    """Полная карточка заказа кабинета: позиции, таймлайн, гео."""

    items_total_minor: int
    discount_minor: int
    loyalty_reward_minor: int = 0
    delivery_fee_minor: int
    comment: str = ""
    promos: list[ShopPromoAppliedResponse] = Field(default_factory=list)
    items: list[ShopOrderItemResponse] = Field(default_factory=list)
    status_history: list[ShopOrderStatusEntry] = Field(default_factory=list)
    status_labels: dict[str, str] = Field(default_factory=dict)
    can_cancel: bool = False
    delivery_lat: float | None = None
    delivery_lng: float | None = None
    delivery_flat: str = ""
    delivery_entrance: str = ""
    delivery_floor: str = ""
    delivery_intercom: str = ""
    delivery_route: JsonObject = Field(default_factory=dict)
    delivery_zone: JsonObject = Field(default_factory=dict)


class ShopStorefrontGeoResponse(StrictBaseModel):
    """`GET /public/storefront/{slug}/geo` — точка магазина и зона для карты."""

    lat: float | None = None
    lng: float | None = None
    address: str = ""
    delivery_zone: JsonObject = Field(default_factory=dict)


# --- Витринная лента: полки и баннеры ---


class ShopShelfResponse(StrictBaseModel):
    """Полка ленты витрины — секция товаров с источником и раскладкой."""

    shop_shelf_id: str
    shop_id: str
    kind: str
    layout: str
    placement: str
    title: str
    subtitle: str
    product_ids: list[str]
    category_id: str | None
    limit: int
    sort: int
    is_active: bool


class ShopShelfCreateRequest(StrictBaseModel):
    kind: str = Field(default="manual", pattern=r"^(manual|category|new|hits|comeback|usual|favorites|upsell)$")
    layout: str = Field(default="rail", pattern=r"^(rail|rows|grid|hero)$")
    placement: str = Field(default="feed", pattern=r"^(feed|cart)$")
    title: str = Field(default="", max_length=120)
    subtitle: str = Field(default="", max_length=200)
    product_ids: list[str] = Field(default_factory=list, max_length=50)
    category_id: str | None = Field(default=None, max_length=64)
    limit: int = Field(default=10, ge=1, le=50)


class ShopShelfUpdateRequest(StrictBaseModel):
    layout: str | None = Field(default=None, pattern=r"^(rail|rows|grid|hero)$")
    placement: str | None = Field(default=None, pattern=r"^(feed|cart)$")
    title: str | None = Field(default=None, max_length=120)
    subtitle: str | None = Field(default=None, max_length=200)
    product_ids: list[str] | None = Field(default=None, max_length=50)
    category_id: str | None = Field(default=None, max_length=64)
    limit: int | None = Field(default=None, ge=1, le=50)
    is_active: bool | None = None


class ShopShelvesReorderRequest(StrictBaseModel):
    """Новый порядок полок ленты — все полки магазина по разу."""

    shelf_ids: list[str] = Field(min_length=1, max_length=50)


class ShopBannerResponse(StrictBaseModel):
    """Сторис-баннер верха ленты: картинка, подпись, deeplink, окно показа."""

    shop_banner_id: str
    shop_id: str
    title: str
    subtitle: str
    image_file_id: str | None
    link: str
    window: JsonObject
    sort: int
    is_active: bool


class ShopBannerCreateRequest(StrictBaseModel):
    title: str = Field(default="", max_length=120)
    subtitle: str = Field(default="", max_length=200)
    image_file_id: str | None = None
    link: str = Field(default="", max_length=300)
    window: JsonObject = Field(default_factory=dict)


class ShopBannerUpdateRequest(StrictBaseModel):
    title: str | None = Field(default=None, max_length=120)
    subtitle: str | None = Field(default=None, max_length=200)
    image_file_id: str | None = None
    link: str | None = Field(default=None, max_length=300)
    window: JsonObject | None = None
    is_active: bool | None = None


class ShopBannersReorderRequest(StrictBaseModel):
    """Новый порядок баннеров — все баннеры магазина по разу."""

    banner_ids: list[str] = Field(min_length=1, max_length=50)


# --- Персонализация и подписки покупателя ---


class ShopPersonalUsualItem(StrictBaseModel):
    """Позиция полки «как всегда»: товар + выбор модификаторов из заказов."""

    product_id: str
    count: int
    selections: list[ShopOrderItemSelection]


class ShopPersonalLoyalty(StrictBaseModel):
    """Состояние лояльности покупателя: прогресс и доступные награды."""

    progress: int
    orders_goal: int
    rewards_available: int
    reward_kind: ShopLoyaltyRewardKind
    reward_value: int


class ShopPersonalResponse(StrictBaseModel):
    """`GET /public/storefront/{slug}/personal` — данные авторизованного
    покупателя на витрине: избранное, «как всегда», подписки на возврат."""

    favorite_ids: list[str]
    usual: list[ShopPersonalUsualItem]
    back_in_stock_ids: list[str]
    # None — механика лояльности выключена флагом витрины.
    loyalty: ShopPersonalLoyalty | None = None


class ShopNotifyBackRequest(StrictBaseModel):
    """Подписка «сообщить о появлении» — slug витрины идёт из path."""

    product_id: str = Field(min_length=1)


class ShopNotifyBackResponse(StrictBaseModel):
    subscribed: bool


class ShopFavoriteSetRequest(StrictBaseModel):
    """Сердечко на витрине — slug идёт из path, состояние задано явно
    (идемпотентно: повтор того же состояния — no-op)."""

    product_id: str = Field(min_length=1)
    favorite: bool


class ShopFavoriteResponse(StrictBaseModel):
    favorite: bool


class ShopFeedbackSetRequest(StrictBaseModel):
    """Оценка выполненного заказа — slug и код заказа идут из path.

    Один отзыв на заказ: повторная отправка — редактирование своей
    оценки (идемпотентно по ключу заказа). Теги — ключи
    ``ShopFeedbackChip``; подписи в полярности оценки отдаёт сервер.
    """

    rating: int = Field(ge=1, le=5)
    chips: list[ShopFeedbackChip] = Field(default_factory=list, max_length=6)
    comment: str = Field(default="", max_length=1000)


class ShopReviewItemResponse(StrictBaseModel):
    """Публичный отзыв на витрине — имя снапшотом из заказа, без PII."""

    rating: int
    chips: list[str]
    chip_labels: dict[str, str] = Field(default_factory=dict)
    comment: str = ""
    customer_name: str = ""
    created_at: str


class ShopReviewsResponse(StrictBaseModel):
    """`GET /storefront/{slug}/reviews` — агрегат рейтинга + лента."""

    avg_rating: float | None = None
    count: int = 0
    items: list[ShopReviewItemResponse] = Field(default_factory=list)


# --- Лояльность: программа «N-я покупка — награда» ---


class ShopLoyaltyProgramSetRequest(StrictBaseModel):
    """Настройка программы директором магазина."""

    orders_goal: int = Field(default=5, ge=1, le=100)
    reward_kind: ShopLoyaltyRewardKind = ShopLoyaltyRewardKind.DISCOUNT_MINOR
    # minor-единицы (≤10 000 000) или процент 1..90 — граница по reward_kind
    # проверяется в сервисе.
    reward_value: int = Field(ge=1)


class ShopLoyaltyProgramResponse(StrictBaseModel):
    shop_id: str
    orders_goal: int
    reward_kind: ShopLoyaltyRewardKind
    reward_value: int
