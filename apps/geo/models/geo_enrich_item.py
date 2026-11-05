"""Задача фонового обогащения геоданных из внешних источников.

Таблица ``geo_enrich_queue`` (``__global_model__``). Медленные
rate-limited источники (НСПД и др.) дрейнит тик ``GEO_ENRICH_TICK`` в
geo_worker по приоритету; ``payload`` — локатор объекта (адрес, bbox,
source_ref) в наших канонических терминах, не чужих.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel
from core.types import JsonObject


class GeoEnrichStatus(StrEnum):
    """Состояние задачи обогащения."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class GeoEnrichItem(PlatformModel):
    """Строка очереди обогащения."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_enrich_queue"
        indexes: list[Index] = [Index(["status", "priority"])]

    id: int | None = DbField(default=None, db_pk=True)
    kind: str = DbField(max_length=64)
    payload: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    priority: int = DbField(default=0)
    status: GeoEnrichStatus = DbField(default=GeoEnrichStatus.PENDING, max_length=32)
    attempts: int = DbField(default=0)
    last_error: str = DbField(default="", db_type="TEXT")
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    done_at: datetime | None = DbField(default=None)

    @classmethod
    async def list_by_priority_desc(
        cls,
        *,
        status: GeoEnrichStatus | None = None,
        limit: int,
        offset: int = 0,
    ) -> list[Self]:
        """Страница очереди по приоритету; ``status`` — необязательный фильтр."""
        rows = cls.objects
        if status is not None:
            rows = rows.filter(status=status)
        return (
            await rows.order_by("-priority", "id").limit(limit).offset(offset).all()
        )

    @classmethod
    async def count_for_status(cls, status: GeoEnrichStatus) -> int:
        """Число задач в статусе (для бейджа очереди)."""
        return await cls.objects.filter(status=status).count()
