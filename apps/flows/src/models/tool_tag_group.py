"""Платформенные LLM-описания групп tools по tag slug."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class ToolTagGroup(BaseModel):
    """Описание tag-группы tools для picker (platform-wide, is_global)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={"storage_prefix": "tool_tag_group"},
        extra="forbid",
    )

    tag: str = Field(..., min_length=1, description="Slug тега (crm, browser, …)")
    description_ru: str = Field(..., min_length=1, max_length=160)
    description_en: str = Field(..., min_length=1, max_length=160)
    content_hash: str = Field(..., min_length=1, description="Хеш состава tool_id+description")
    updated_at: datetime = Field(..., description="UTC время последнего LLM/persist")


class ToolTagGroupDescribeResult(BaseModel):
    """Structured output LLM для описания tag-группы."""

    description_ru: str = Field(..., min_length=1, max_length=160)
    description_en: str = Field(..., min_length=1, max_length=160)


class ToolTagGroupTickStats(BaseModel):
    """Итог прогона describe tick."""

    tags_total: int
    tags_updated: int
    tags_skipped: int
