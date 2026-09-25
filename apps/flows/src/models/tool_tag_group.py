"""Платформенные LLM-описания групп tools по tag slug."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from pydantic import BaseModel, ConfigDict, Field

from core.models.platform_model import PlatformModel


class ToolTagGroup(PlatformModel):
    """Описание tag-группы tools. Таблица ``tool_tag_groups`` в базе flows."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    class Meta:
        is_table: bool = True
        table_name: str = "tool_tag_groups"

    tag: str = DbField(db_pk=True, min_length=1, max_length=64)
    description_ru: str = DbField(min_length=1, max_length=160)
    description_en: str = DbField(min_length=1, max_length=160)
    content_hash: str = DbField(min_length=1)
    updated_at: datetime = DbField()

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if self.tag == "":
            raise ValueError("tag is required")
        self.updated_at = datetime.now(timezone.utc)

    @classmethod
    async def list_groups(cls, *, limit: int = 200, offset: int = 0) -> list[Self]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        groups = await cls.objects.limit(limit).offset(offset).all()
        groups.sort(key=lambda item: item.tag)
        return groups


class ToolTagGroupDescribeResult(BaseModel):
    """Structured output LLM для описания tag-группы."""

    description_ru: str = Field(..., min_length=1, max_length=160)
    description_en: str = Field(..., min_length=1, max_length=160)


class ToolTagGroupTickStats(BaseModel):
    """Итог прогона describe tick."""

    tags_total: int
    tags_updated: int
    tags_skipped: int
