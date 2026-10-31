"""Таблица shop_shops — витрина компании (меню/каталог + заказы)."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.shop.models.enums import ShopKind, ShopStatus
from core.models.platform_model import PlatformModel
from core.types import JsonObject


class Shop(PlatformModel):
    """Интернет-магазин компании. Таблица ``shop_shops``.

    ``slug`` — адрес витрины ``<slug>.<platform wildcard domain>``: глобально
    уникален и проверяется на reserved-список в ``ShopService``. Публичная
    витрина существует только при ``status=published``.
    """

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_shops"
        indexes: list[Index] = [
            Index(["company_id", "status"]),
            Index(["status", "kind", "city"]),
        ]

    shop_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    slug: str = DbField(max_length=40, unique=True)
    kind: ShopKind = DbField(default=ShopKind.RESTAURANT)
    name: str = DbField(default="", max_length=200)
    description: str = DbField(default="", db_type="TEXT")
    logo_file_id: str | None = DbField(default=None, max_length=64)
    cover_file_id: str | None = DbField(default=None, max_length=64)
    phone: str = DbField(default="", max_length=32)
    city: str = DbField(default="", max_length=120)
    address: str = DbField(default="", max_length=300)
    timezone: str = DbField(default="Europe/Moscow", max_length=64)
    working_hours: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    delivery_enabled: bool = DbField(default=True)
    pickup_enabled: bool = DbField(default=True)
    delivery_fee_minor: int = DbField(default=0, ge=0)
    min_order_minor: int = DbField(default=0, ge=0)
    currency: str = DbField(default="RUB", max_length=3)
    theme: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    status: ShopStatus = DbField(default=ShopStatus.DRAFT)
    telegram_chat_id: str | None = DbField(default=None, max_length=64)
    telegram_bind_token_hash: str | None = DbField(default=None, max_length=128)
    telegram_bot_token: str | None = DbField(default=None, max_length=128)
    telegram_webhook_secret: str | None = DbField(default=None, max_length=128)
    plan: str = DbField(default="free", max_length=32)
    created_by_user_id: str = DbField(max_length=100)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    published_at: datetime | None = DbField(default=None)
    deleted_at: datetime | None = DbField(default=None)

    @classmethod
    async def get_by_id(cls, shop_id: str) -> Self | None:
        """Магазин по PK; удалённый не возвращается."""
        row = await cls.objects.filter(shop_id=shop_id).get_or_none()
        if row is None or row.deleted_at is not None:
            return None
        return row

    @classmethod
    async def get_by_slug(cls, slug: str) -> Self | None:
        """Магазин по slug; удалённый не возвращается."""
        row = await cls.objects.filter(slug=slug).get_or_none()
        if row is None or row.deleted_at is not None:
            return None
        return row

    @classmethod
    async def slug_exists(cls, slug: str) -> bool:
        """Slug занят живым магазином."""
        return await cls.objects.filter(slug=slug, deleted_at=None).exists()

    @classmethod
    async def list_alive_by_company(cls, company_id: str) -> list[Self]:
        """Все магазины компании по updated_at DESC. Предела нет."""
        return await cls.objects.filter(
            company_id=company_id, deleted_at=None
        ).order_by("-updated_at").all()

    @classmethod
    async def list_published(cls) -> list[Self]:
        """Все опубликованные витрины — источник каталога агрегатора."""
        return await cls.objects.filter(
            status=ShopStatus.PUBLISHED, deleted_at=None
        ).all()

    @classmethod
    async def create(cls, shop: Self) -> Self:
        return await cls.objects.create(instance=shop)
