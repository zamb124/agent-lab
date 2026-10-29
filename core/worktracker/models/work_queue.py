"""Таблица worktracker."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel


class WorkQueue(PlatformModel):
    """Очередь. Колонка slug в таблице называется ``slug``."""

    __database_alias__: ClassVar[str | None] = "worktracker"
    __global_model__: ClassVar[bool] = True

    work_queue_id: str = DbField(db_pk=True, max_length=64, min_length=1)
    company_id: str = DbField(max_length=100, min_length=1, db_index=True)
    name: str = DbField(max_length=255, min_length=1)
    work_queue_slug: str = DbField(max_length=120, min_length=1, db_column="slug")
    owner_user_id: str = DbField(max_length=100, min_length=1)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    description: str | None = DbField(default=None, db_type="TEXT")

    class Meta:
        is_table: bool = True
        table_name: str = "work_queues"
        unique_together: list[tuple[str, str]] = [("company_id", "work_queue_slug")]

    @classmethod
    async def list_by_work_queue_id_asc(cls, *, limit: int | None) -> list[Self]:
        """Все очереди, ORDER BY work_queue_id ASC. limit is None не ограничивает. limit < 1 — ValueError."""
        query = cls.objects.order_by("work_queue_id")
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be >= 1")
            query = query.limit(limit)
        return await query.all()

    @classmethod
    async def list_unordered_for_company(cls, company_id: str) -> list[Self]:
        """Все очереди компании. Порядка и limit нет."""
        return await cls.objects.filter(company_id=company_id).all()

    @classmethod
    async def list_by_created_at_asc(cls, company_id: str) -> list[Self]:
        """Все очереди компании, ORDER BY created_at ASC. Предела нет."""
        return await (
            cls.objects.filter(company_id=company_id)
            .order_by("created_at")
            .all()
        )

    @classmethod
    async def by_slug(cls, company_id: str, slug: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            work_queue_slug=slug,
        ).get_or_none()

    @classmethod
    async def by_id(cls, company_id: str, work_queue_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            work_queue_id=work_queue_id,
        ).get_or_none()

    @classmethod
    async def create(cls, queue: Self) -> Self:
        return await cls.objects.create(instance=queue)

    @classmethod
    async def delete_for_company(cls, company_id: str, work_queue_id: str) -> int:
        return await cls.objects.filter(
            company_id=company_id,
            work_queue_id=work_queue_id,
        ).delete()

