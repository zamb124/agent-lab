"""Коммит полосы: квитанция идемпотентности, outbox событий и аудит команды.

Таблица ``lane_commits``.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.events.contract import PlatformEvent
from core.lanes.databases import LANE_DATABASES
from core.models.platform_model import PlatformModel
from core.types import JsonArray, JsonObject, require_json_object
from core.utils.time import utcnow


class LaneCommit(PlatformModel):
    """Одна команда, исполненная в полосе.

    Пишется в той же транзакции, что и эффект команды: повтор с тем же
    ``idempotency_key`` возвращает ``result_payload`` без повторного исполнения,
    ``events`` публикуются после commit и догоняются relay, пока ``published_at``
    пуст.
    """

    __global_model__: ClassVar[bool] = True
    __database_aliases__: ClassVar[tuple[str, ...]] = LANE_DATABASES

    class Meta:
        is_table: bool = True
        table_name: str = "lane_commits"
        indexes: list[Index] = [
            Index(["company_id", "idempotency_key"], unique=True),
            Index(["lane_id", "lane_seq"], unique=True),
            Index(
                ["created_at"],
                name="lane_commits_unpublished_idx",
                where="published_at IS NULL",
            ),
            Index(["published_at"]),
        ]

    lane_commit_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    lane_id: str = DbField(max_length=200)
    lane_seq: int = DbField()
    idempotency_key: str = DbField(max_length=128)
    command_type: str = DbField(max_length=200)
    actor_user_id: str = DbField(max_length=100)
    result_payload: JsonObject = DbField(db_type="JSONB")
    events: JsonArray = DbField(db_type="JSONB")
    published_at: datetime | None = DbField(default=None)
    created_at: datetime = DbField()

    def platform_events(self) -> list[PlatformEvent]:
        return [
            PlatformEvent.model_validate(require_json_object(item, "lane_commits.events"))
            for item in self.events
        ]

    @classmethod
    async def by_idempotency_key(
        cls, company_id: str, idempotency_key: str, *, using: str
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, idempotency_key=idempotency_key
        ).get_or_none(using=using)

    @classmethod
    async def by_lane_commit_id(cls, lane_commit_id: str, *, using: str) -> Self | None:
        return await cls.objects.filter(lane_commit_id=lane_commit_id).get_or_none(using=using)

    @classmethod
    async def append(cls, row: Self, *, using: str) -> Self:
        return await cls.objects.create(instance=row, using=using)

    @classmethod
    async def mark_published(cls, lane_commit_id: str, *, using: str) -> None:
        _ = await cls.objects.filter(
            lane_commit_id=lane_commit_id, published_at=None
        ).update(using=using, published_at=utcnow())

    @classmethod
    async def list_unpublished_by_lane_id_and_lane_seq_asc(
        cls,
        *,
        created_before: datetime,
        limit: int,
        using: str,
        lane_id: str | None = None,
    ) -> list[Self]:
        """Неопубликованные коммиты старше created_before, ORDER BY lane_id ASC, lane_seq ASC, не больше limit. lane_id None не фильтрует. limit < 1 — ValueError. Relay публикует их по lane_seq."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        query = cls.objects.filter(published_at=None, created_at__lt=created_before)
        if lane_id is not None:
            query = query.filter(lane_id=lane_id)
        return await query.order_by("lane_id", "lane_seq").limit(limit).all(using=using)

    @classmethod
    async def expire_published(cls, *, published_before: datetime, using: str) -> int:
        return await cls.objects.filter(
            published_at__isnull=False, published_at__lt=published_before
        ).delete(using=using)
