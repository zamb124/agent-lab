"""Шаблон пространства CRM и типы внутри него."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel
from core.pagination import OffsetPage
from core.types import JsonObject
from core.utils.time import utcnow


class NamespaceTemplate(PlatformModel):
    """Строка ``namespace_templates``. Ключ внутри компании — ``template_id``."""

    __database_alias__: ClassVar[str | None] = "crm"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "namespace_templates"
        unique_together: list[tuple[str, str]] = [("company_id", "template_id")]
        indexes: list[Index] = [
            Index(["company_id", "is_system"]),
        ]

    template_key: str = DbField(db_pk=True, max_length=100)
    company_id: str = DbField(max_length=100, db_index=True)
    template_id: str = DbField(max_length=100, db_index=True)
    name: str = DbField(max_length=200)
    created_at: datetime = DbField(default_factory=utcnow)
    updated_at: datetime = DbField(default_factory=utcnow)
    description: str | None = DbField(default=None, db_type="TEXT")
    icon: str | None = DbField(default=None, max_length=50)
    is_system: bool = DbField(default=False)
    crm_settings: JsonObject | None = DbField(default=None, db_type="JSONB")

    @classmethod
    async def by_template_id(
        cls,
        company_id: str,
        template_id: str,
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            template_id=template_id,
        ).get_or_none()

    @classmethod
    async def page_for_company_by_created_at_and_template_id_desc(
        cls,
        company_id: str,
        *,
        limit: int,
        offset: int,
    ) -> OffsetPage[NamespaceTemplate]:
        """Страница шаблонов компании, ORDER BY created_at DESC, template_id DESC. limit < 1 и offset < 0 — ValueError."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        rows = cls.objects.filter(company_id=company_id)
        total = await rows.count()
        templates = await (
            rows.order_by("-created_at", "-template_id").limit(limit).offset(offset).all()
        )
        return OffsetPage[NamespaceTemplate](
            items=[*templates],
            total=total,
            limit=limit,
            offset=offset,
        )

    @classmethod
    async def create(cls, template: Self) -> Self:
        return await cls.objects.create(instance=template)

    @classmethod
    async def update_name_description_icon_and_crm_settings(
        cls,
        template: Self,
        *,
        name: str | None,
        description: str | None,
        icon: str | None,
        crm_settings: JsonObject | None,
        crm_settings_is_set: bool,
    ) -> Self:
        """Пишет name, description и icon, если значение передано. crm_settings пишет только при crm_settings_is_set. Всегда обновляет updated_at."""
        if name is not None:
            template.name = name
        if description is not None:
            template.description = description
        if icon is not None:
            template.icon = icon
        if crm_settings_is_set:
            template.crm_settings = crm_settings
        template.updated_at = utcnow()
        return await template.save(using="crm")
