"""Таблица shop_domains — кастомный домен витрины (CNAME → платформа)."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.shop.models.enums import ShopDomainStatus
from core.models.platform_model import PlatformModel


class ShopDomain(PlatformModel):
    """Собственный домен магазина вида ``menu.restaurant.ru``.

    Жизненный цикл: ``pending_dns`` → DNS-resolve указывает на платформу →
    ``provisioning`` (создан Ingress + Certificate) → ``active``. Имя хранится
    в punycode-нормализации, lowercase.
    """

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_domains"
        indexes: list[Index] = [
            Index(["shop_id", "status"]),
            Index(["status", "updated_at"]),
        ]

    shop_domain_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    company_id: str = DbField(max_length=100)
    domain: str = DbField(max_length=253, unique=True)
    status: ShopDomainStatus = DbField(default=ShopDomainStatus.PENDING_DNS)
    last_error: str = DbField(default="", db_type="TEXT")
    verify_attempts: int = DbField(default=0, ge=0)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def get_by_domain(cls, domain: str) -> Self | None:
        return await cls.objects.filter(domain=domain).get_or_none()

    @classmethod
    async def get_by_shop(cls, shop_id: str) -> Self | None:
        """Домен магазина: один активный домен на витрину."""
        return await cls.objects.filter(shop_id=shop_id).get_or_none()

    @classmethod
    async def list_unfinished(cls) -> list[Self]:
        """Домены, требующие reconcile: DNS не проверен или провиженинг не завершён."""
        return await cls.objects.filter(
            status__in=[
                ShopDomainStatus.PENDING_DNS,
                ShopDomainStatus.AWAITING_DNS,
                ShopDomainStatus.PROVISIONING,
            ]
        ).all()

    @classmethod
    async def create(cls, domain: Self) -> Self:
        return await cls.objects.create(instance=domain)
