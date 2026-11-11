"""Overlay'ы контента товара (catalog_product_overrides).

Полевой override наследуемых атрибутов карточки: ``(facet,
instance_id)`` задаёт контекст — ``("shop", shop_id)`` = одна витрина,
``("shop", NULL)`` = все витрины компании, ``("stock", NULL)`` = склад
целиком. ``NULL`` в колонке = «наследовать базу» (пустая строка —
легальное явное значение). Строка, у которой все колонки-override
NULL, бессмысленна и удаляется — цепочка наследования держится на
отсутствии записи.

Цепочка резолва (первое не-NULL значение побеждает):
``(facet, instance)`` → ``(facet, NULL)`` → база ``catalog_products``.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


class CatalogProductOverride(PlatformModel):
    """Полевые override'ы карточки в контексте сервиса. Таблица ``catalog_product_overrides``."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "catalog_product_overrides"
        indexes: list[Index] = [
            Index(
                ["product_id", "facet"],
                unique=True,
                where="instance_id IS NULL",
            ),
            Index(
                ["product_id", "facet", "instance_id"],
                unique=True,
                where="instance_id IS NOT NULL",
            ),
            Index(["facet", "instance_id"]),
        ]

    override_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    product_id: str = DbField(max_length=64)
    facet: str = DbField(max_length=32)
    """Сервис-владелец scope: ``stock`` | ``shop`` (имя сервиса)."""
    instance_id: str | None = DbField(default=None, max_length=64)
    """Экземпляр сервиса (``shop_id``) либо NULL — уровень сервиса целиком."""
    name: str | None = DbField(default=None, max_length=300)
    description: str | None = DbField(default=None, db_type="TEXT")
    image_file_ids: list[str] | None = DbField(default=None, db_type="JSONB")
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def by_scope(
        cls,
        company_id: str,
        product_id: str,
        facet: str,
        instance_id: str | None,
    ) -> Self | None:
        query = cls.objects.filter(
            company_id=company_id,
            product_id=product_id,
            facet=facet,
        )
        if instance_id is None:
            query = query.filter(instance_id__isnull=True)
        else:
            query = query.filter(instance_id=instance_id)
        return await query.get_or_none()

    @classmethod
    async def list_for_scopes(
        cls,
        company_id: str,
        product_ids: list[str],
        scopes: list[tuple[str, str | None]],
    ) -> list[Self]:
        """Overlay'ы заданных продуктов в заданных scope'ах. Пустой вход — []."""
        if not product_ids or not scopes:
            return []
        facets = list({facet for facet, _ in scopes})
        query = cls.objects.filter(
            company_id=company_id,
            product_id__in=product_ids,
            facet__in=facets,
        )
        rows = await query.all()
        wanted = set(scopes)
        return [row for row in rows if (row.facet, row.instance_id) in wanted]

    @classmethod
    async def list_by_product_by_facet_asc(cls, company_id: str, product_id: str) -> list[Self]:
        """Все overlay'ы товара (master card: «кто что переопределил»)."""
        return await cls.objects.filter(
            company_id=company_id, product_id=product_id
        ).order_by("facet", "instance_id").all()

    @classmethod
    async def list_by_instance(
        cls, company_id: str, facet: str, instance_id: str
    ) -> list[Self]:
        """Overlay'ы всех товаров в одном контексте (оверлеи витрины)."""
        return await cls.objects.filter(
            company_id=company_id, facet=facet, instance_id=instance_id
        ).all()

    @classmethod
    async def list_product_ids_by_facet(
        cls, company_id: str, facet: str, instance_id: str | None
    ) -> list[str]:
        """product_id, у которых есть overlay в данном scope (фан-аут инвалидации)."""
        query = cls.objects.filter(company_id=company_id, facet=facet)
        if instance_id is None:
            query = query.filter(instance_id__isnull=True)
        else:
            query = query.filter(instance_id=instance_id)
        rows = await query.all()
        return [row.product_id for row in rows]

    @classmethod
    async def delete_by_scope(
        cls,
        company_id: str,
        product_id: str,
        facet: str,
        instance_id: str | None,
    ) -> None:
        query = cls.objects.filter(
            company_id=company_id,
            product_id=product_id,
            facet=facet,
        )
        if instance_id is None:
            query = query.filter(instance_id__isnull=True)
        else:
            query = query.filter(instance_id=instance_id)
        _ = await query.delete()

    @classmethod
    async def delete_scope(
        cls, company_id: str, facet: str, instance_id: str | None
    ) -> int:
        """Удалить все overlay'ы scope (витрина удалена → её переопределения уходят)."""
        query = cls.objects.filter(company_id=company_id, facet=facet)
        if instance_id is None:
            query = query.filter(instance_id__isnull=True)
        else:
            query = query.filter(instance_id=instance_id)
        return await query.delete()

    @classmethod
    async def delete_for_product(cls, company_id: str, product_id: str) -> int:
        """Удалить все overlay'ы товара (detach последнего фасета)."""
        return await cls.objects.filter(
            company_id=company_id, product_id=product_id
        ).delete()
