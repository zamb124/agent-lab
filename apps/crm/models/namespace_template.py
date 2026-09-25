"""Шаблон пространства CRM и типы внутри него."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self
from uuid import uuid4

from oxyde import Field as DbField
from oxyde import Index
from oxyde.exceptions import UniqueViolationError

from core.models.platform_model import PlatformModel
from core.pagination import OffsetPage
from core.types import JsonObject


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
    created_at: datetime = DbField(default_factory=_utcnow)
    updated_at: datetime = DbField(default_factory=_utcnow)
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
    async def page_for_company(
        cls,
        company_id: str,
        *,
        limit: int,
        offset: int,
    ) -> OffsetPage[NamespaceTemplate]:
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
    async def update_fields(
        cls,
        template: Self,
        *,
        name: str | None,
        description: str | None,
        icon: str | None,
        crm_settings: JsonObject | None,
        crm_settings_is_set: bool,
    ) -> Self:
        if name is not None:
            template.name = name
        if description is not None:
            template.description = description
        if icon is not None:
            template.icon = icon
        if crm_settings_is_set:
            template.crm_settings = crm_settings
        template.updated_at = _utcnow()
        return await template.save(using="crm")


class NamespaceTemplateType(PlatformModel):
    """Строка ``namespace_template_types``."""

    __database_alias__: ClassVar[str | None] = "crm"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "namespace_template_types"
        unique_together: list[tuple[str, str]] = [("template_key", "type_id")]

    entry_id: str = DbField(db_pk=True, max_length=100)
    template_key: str = DbField(max_length=100, db_index=True)
    type_id: str = DbField(max_length=100, db_index=True)
    name: str = DbField(max_length=200)
    created_at: datetime = DbField(default_factory=_utcnow)
    updated_at: datetime = DbField(default_factory=_utcnow)
    parent_type_id: str | None = DbField(default=None, max_length=100, db_index=True)
    description: str | None = DbField(default=None, db_type="TEXT")
    prompt: str | None = DbField(default=None, db_type="TEXT")
    required_fields: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    optional_fields: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    icon: str | None = DbField(default=None, max_length=50)
    color: str | None = DbField(default=None, max_length=20)
    is_event: bool = DbField(default=False)
    check_duplicates: bool = DbField(default=True)
    weight_coefficient: float = DbField(default=1.0)
    namespace_ids: list[str] = DbField(default_factory=list, db_type="JSONB")
    is_context_anchor: bool = DbField(default=False)
    is_voice_target: bool = DbField(default=False)

    @classmethod
    async def list_for_template(cls, template_key: str) -> list[Self]:
        return await cls.objects.filter(template_key=template_key).order_by("type_id").all()

    @classmethod
    async def delete_by_template_key(cls, template_key: str) -> int:
        return await cls.objects.filter(template_key=template_key).delete()

    @classmethod
    async def delete_by_template_key_and_type_id(cls, template_key: str, type_id: str) -> int:
        return await cls.objects.filter(template_key=template_key, type_id=type_id).delete()

    @classmethod
    async def upsert_by_template_key_and_type_id(
        cls,
        *,
        template_key: str,
        type_id: str,
        parent_type_id: str | None,
        name: str,
        description: str | None,
        prompt: str | None,
        required_fields: JsonObject,
        optional_fields: JsonObject,
        icon: str | None,
        color: str | None,
        is_event: bool,
        check_duplicates: bool,
        weight_coefficient: float,
        namespace_ids: list[str],
        is_context_anchor: bool = False,
        is_voice_target: bool = False,
    ) -> Self:
        existing = await cls.objects.filter(
            template_key=template_key,
            type_id=type_id,
        ).get_or_none()
        if existing is None:
            created = cls(
                entry_id=str(uuid4()),
                template_key=template_key,
                type_id=type_id,
                name=name,
                parent_type_id=parent_type_id,
                description=description,
                prompt=prompt,
                required_fields=required_fields,
                optional_fields=optional_fields,
                icon=icon,
                color=color,
                is_event=is_event,
                check_duplicates=check_duplicates,
                weight_coefficient=weight_coefficient,
                namespace_ids=namespace_ids,
                is_context_anchor=is_context_anchor,
                is_voice_target=is_voice_target,
            )
            try:
                return await cls.objects.create(instance=created)
            except UniqueViolationError:
                existing = await cls.objects.filter(
                    template_key=template_key,
                    type_id=type_id,
                ).get_or_none()
                if existing is None:
                    raise RuntimeError(
                        f"NamespaceTemplateType ({template_key}, {type_id}) missing after unique violation"
                    )
        existing.parent_type_id = parent_type_id
        existing.name = name
        existing.description = description
        existing.prompt = prompt
        existing.required_fields = required_fields
        existing.optional_fields = optional_fields
        existing.icon = icon
        existing.color = color
        existing.is_event = is_event
        existing.check_duplicates = check_duplicates
        existing.weight_coefficient = weight_coefficient
        existing.namespace_ids = namespace_ids
        existing.is_context_anchor = is_context_anchor
        existing.is_voice_target = is_voice_target
        existing.updated_at = datetime.now(UTC)
        return await existing.save(using="crm")
