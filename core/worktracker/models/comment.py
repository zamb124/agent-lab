"""Таблица worktracker."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar, Self

from oxyde import Field as DbField

from core.files.file_ref import FileRef
from core.models.platform_model import PlatformModel
from core.worktracker.models.types import SystemActor, UserActor


class WorkItemCommentRole(StrEnum):
    OPERATOR = "operator"
    USER = "user"
    SYSTEM = "system"
    AGENT = "agent"


class WorkItemComment(PlatformModel):
    """Комментарий задачи. ``author`` и ``files`` — JSON этой строки."""

    __database_alias__: ClassVar[str | None] = "worktracker"
    __global_model__: ClassVar[bool] = True

    comment_id: str = DbField(db_pk=True, max_length=64, min_length=1)
    work_item_id: str = DbField(max_length=64, min_length=1, db_index=True)
    company_id: str = DbField(max_length=100, min_length=1, db_index=True)
    author: UserActor | SystemActor = DbField(db_type="JSONB", discriminator="actor_kind")
    created_at: datetime = DbField()
    role: WorkItemCommentRole = DbField(default=WorkItemCommentRole.SYSTEM, max_length=16, db_type="TEXT")
    text: str = DbField(default="", db_type="TEXT")
    files: list[FileRef] = DbField(default_factory=list, db_type="JSONB")

    class Meta:
        is_table: bool = True
        table_name: str = "work_item_comments"

    @classmethod
    async def create(cls, comment: Self) -> Self:
        return await cls.objects.create(instance=comment)

    @classmethod
    async def list_for_work_item(cls, company_id: str, work_item_id: str) -> list[Self]:
        return await (
            cls.objects.filter(company_id=company_id, work_item_id=work_item_id)
            .order_by("created_at")
            .all()
        )


# === Корневая модель ===

