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


class ShopTheme(StrictBaseModel):
    """Визуальная тема витрины: акцентный цвет и пресет раскладки."""

    accent_color: str = Field(default="#e2553f", max_length=16)
    preset: str = Field(default="menu", max_length=32)


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
    storefront_url: str
    plan: str


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
    price_minor: int
    photo_file_id: str | None
    is_available: bool
    sort: int


class ShopProductCreateRequest(StrictBaseModel):
    category_id: str | None = None
    name: str = Field(min_length=1, max_length=300)
    description: str = ""
    price_minor: int = Field(ge=0)
    photo_file_id: str | None = None


class ShopProductUpdateRequest(StrictBaseModel):
    category_id: str | None = None
    name: str | None = Field(default=None, max_length=300)
    description: str | None = None
    price_minor: int | None = Field(default=None, ge=0)
    photo_file_id: str | None = None
    is_available: bool | None = None
    sort: int | None = None


class ShopOrderItemRequest(StrictBaseModel):
    product_id: str = Field(min_length=1)
    qty: int = Field(ge=1, le=99)


class ShopOrderItemResponse(StrictBaseModel):
    product_id: str
    name: str
    price_minor: int
    qty: int


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
    delivery_fee_minor: int
    total_minor: int
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
