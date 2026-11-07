"""Декларативные спеки demo-витрин: типизированное содержимое сида.

Один ``DemoShopSpec`` = одна эталонная витрина. Ключи сущностей
(`key`, ≤ 12 символов, ``[a-z0-9_]``) входят в детерминированные PK
``demo:{tpl}:{h16}:{et}:{key}`` — переименование ключа создаёт новую
сущность при досеве, старая строка не переиспользуется.

JSONB-поля (``theme``, ``working_hours``, ``delivery_zone``, промо
``condition``/``action``/``window``) хранятся в wire-форме моделей:
витрина читает их без преобразований.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.shop.models.enums import (
    ModifierGroupKind,
    ModifierPriceMode,
    ModifierSelectionMode,
    PromoStacking,
    ShopDeliveryType,
    ShopKind,
    ShopOrderStatus,
    ShopShelfKind,
    ShopShelfLayout,
    ShopShelfPlacement,
)
from core.types import JsonObject


@dataclass(frozen=True)
class DemoOptionSpec:
    """Опция группы модификаторов.

    ``photo`` — имя файла в ``assets/<tpl>/`` (пусто — без фото);
    ``nutrition_delta`` — прибавка КБЖУ при выборе опции, wire-форма
    ``ShopNutrition`` без None-полей.
    """

    key: str
    name: str
    price_minor: int = 0
    is_default: bool = False
    max_per_option: int = 1
    photo: str = ""
    nutrition_delta: dict[str, float] = field(default_factory=dict)
    nested_group_key: str | None = None


@dataclass(frozen=True)
class DemoModifierGroupSpec:
    """Группа модификаторов магазина."""

    key: str
    name: str
    kind: ModifierGroupKind = ModifierGroupKind.ADDON
    selection_mode: ModifierSelectionMode = ModifierSelectionMode.SINGLE
    price_mode: ModifierPriceMode = ModifierPriceMode.DELTA
    min_selected: int = 0
    max_selected: int | None = None
    options: tuple[DemoOptionSpec, ...] = ()


@dataclass(frozen=True)
class DemoCategorySpec:
    """Раздел каталога; ``children`` — вложенные категории (parent_id)."""

    key: str
    name: str
    children: tuple["DemoCategorySpec", ...] = ()


@dataclass(frozen=True)
class DemoProductSpec:
    """Позиция каталога с фото из ``assets/<tpl>/<photo>``.

    ``nutrition`` — КБЖУ порции (wire-форма ``ShopNutrition`` без
    None-полей); ``is_available=False`` — витрина рисует «скоро
    вернётся» с подпиской вместо кнопки заказа.
    """

    key: str
    category_key: str
    name: str
    price_minor: int
    portion: str
    photo: str
    description: str = ""
    badges: tuple[str, ...] = ()
    nutrition: dict[str, float] = field(default_factory=dict)
    is_available: bool = True
    modifier_group_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class DemoPromoSpec:
    """Акция: condition + action + window в JSONB-форме ``ShopPromo``."""

    key: str
    name: str
    condition: JsonObject
    action: JsonObject
    window: JsonObject = field(default_factory=dict)
    priority: int = 0
    stacking: PromoStacking = PromoStacking.ALL
    is_active: bool = True


@dataclass(frozen=True)
class DemoTableSpec:
    """Стол зала: ``label`` попадает в QR-ссылку и снапшот заказа."""

    key: str
    label: str


@dataclass(frozen=True)
class DemoShelfSpec:
    """Полка витринной ленты: источник ``kind`` + раскладка + место.

    ``product_keys`` — для ``manual``/``upsell``; ``category_key`` —
    для ``category``; вычисляемые ``new``/``hits``/``comeback``/
    ``usual`` источника не требуют (данные собирает FeedService).
    """

    key: str
    kind: ShopShelfKind = ShopShelfKind.MANUAL
    layout: ShopShelfLayout = ShopShelfLayout.RAIL
    placement: ShopShelfPlacement = ShopShelfPlacement.FEED
    title: str = ""
    subtitle: str = ""
    product_keys: tuple[str, ...] = ()
    category_key: str = ""
    limit: int = 10


@dataclass(frozen=True)
class DemoBannerSpec:
    """Сторис-баннер верха ленты с картинкой из ``assets/<tpl>/``.

    ``link`` — deeplink: ``product:<key>``, ``category:<key>``,
    ``shelf:<key>`` (ключи сида, резолвятся в реальные id) либо
    ``url:<https…>`` (внешняя ссылка); ``window`` — JSONB-окно показа.
    """

    key: str
    photo: str
    title: str = ""
    subtitle: str = ""
    link: str = ""
    window: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class DemoOrderItemSpec:
    """Строка демо-заказа; ``selections`` — пары (group_key, option_key)."""

    product_key: str
    qty: int = 1
    selections: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class DemoOrderGeoSpec:
    """Гео-снапшот доставки: точка клиента, точка магазина, маршрут."""

    delivery_lat: float
    delivery_lng: float
    shop_lat: float
    shop_lng: float
    route: JsonObject


@dataclass(frozen=True)
class DemoOrderSpec:
    """Демо-заказ: статус + лесенка переходов по минутам от created_at.

    ``history_minutes`` — смещения (мин) переходов между статусами
    ``new → … → status``; длина = номеру конечного статуса в цепочке.
    """

    status: ShopOrderStatus
    delivery_type: ShopDeliveryType
    items: tuple[DemoOrderItemSpec, ...]
    customer_name: str
    customer_phone: str
    age_hours: float
    history_minutes: tuple[int, ...]
    address: str = ""
    table_key: str = ""
    comment: str = ""
    geo: DemoOrderGeoSpec | None = None


@dataclass(frozen=True)
class DemoShopSpec:
    """Эталонная витрина-шаблон, создаваемая демо-сидом."""

    key: str
    kind: ShopKind
    name: str
    description: str
    phone: str
    city: str
    address: str
    timezone: str
    theme: JsonObject
    working_hours: JsonObject
    features: JsonObject
    delivery_enabled: bool
    pickup_enabled: bool
    onsite_enabled: bool
    delivery_zone: JsonObject
    delivery_fee_minor: int
    min_order_minor: int
    prep_minutes: int
    courier_mode: str
    cover_photo: str
    badges: tuple[dict[str, str], ...]
    categories: tuple[DemoCategorySpec, ...]
    modifier_groups: tuple[DemoModifierGroupSpec, ...]
    products: tuple[DemoProductSpec, ...]
    promos: tuple[DemoPromoSpec, ...]
    tables: tuple[DemoTableSpec, ...]
    shelves: tuple[DemoShelfSpec, ...]
    banners: tuple[DemoBannerSpec, ...]
    orders: tuple[DemoOrderSpec, ...]
