"""Таблица проекции A2A."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from a2a.types import Task
from oxyde import Field as DbField
from oxyde import Index, atomic

from apps.flows.src.models.a2a_projection.contracts import (
    A2A_TASK_SNAPSHOT_KIND,
    ARTIFACT_UPDATE_KIND,
    STATUS_UPDATE_KIND,
    A2APendingEvent,
    A2ATaskRepositoryError,
)
from core.a2a import (
    artifact_update_from_json_dict,
    status_update_from_json_dict,
    task_from_json_dict,
)
from core.a2a.task_projection import TaskProjectionEvent
from core.models.platform_model import PlatformModel
from core.types import JsonObject, require_json_object
from core.utils.time import utcnow


class A2ATaskEvent(PlatformModel):
    """Событие доставки Task. Таблица ``a2a_task_event_dedup``."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "a2a_task_event_dedup"
        unique_together: list[tuple[str, str]] = [
            ("task_id", "event_identity"),
            ("task_id", "sequence"),
        ]
        indexes: list[Index] = [
            Index(["company_id", "task_id", "sequence"]),
            Index(["published_at", "created_at"]),
        ]

    task_event_id: str = DbField(db_pk=True)
    company_id: str = DbField()
    task_id: str = DbField()
    event_identity: str = DbField()
    sequence: int = DbField(ge=0)
    event_kind: str = DbField()
    event_json: JsonObject = DbField(db_type="JSONB")
    source_fingerprint: str = DbField()
    created_at: datetime = DbField()
    published_at: datetime | None = DbField(default=None)


    @classmethod
    async def list_unpublished(cls, *, limit: int = 100) -> list[A2APendingEvent]:
        if limit <= 0:
            raise A2ATaskRepositoryError("unpublished event limit must be positive")
        rows = await (
            A2ATaskEvent.objects.filter(published_at=None)
            .order_by("created_at")
            .limit(limit)
            .all()
        )
        return [
            A2APendingEvent(
                company_id=row.company_id,
                task_id=row.task_id,
                event_identity=row.event_identity,
                sequence=row.sequence,
                event=event_from_row(row),
            )
            for row in rows
        ]

    @classmethod
    async def get_submitted_task(cls, *, company_id: str, task_id: str) -> Task | None:
        """Sequence-0 snapshot: SUBMITTED Task with history and without artifacts.

        Every status/artifact event of the task has sequence >= 1, so a stream that
        starts with this snapshot and continues from sequence 1 never duplicates parts.
        """
        row = await A2ATaskEvent.objects.filter(
            company_id=company_id,
            task_id=task_id,
            sequence=0,
            event_kind=A2A_TASK_SNAPSHOT_KIND,
        ).first()
        if row is None:
            return None
        return task_from_json_dict(require_json_object(row.event_json, "A2ATaskEvent.task"))

    @classmethod
    async def mark_published(
        cls,
        *,
        company_id: str,
        task_id: str,
        event_identity: str,
    ) -> None:
        async with atomic(using="flows"):
            updated_rows = await cls.objects.filter(
                company_id=company_id,
                task_id=task_id,
                event_identity=event_identity,
                published_at=None,
            ).update(returning=False, using="flows", published_at=utcnow())
            if updated_rows != 1:
                existing = await cls.objects.filter(
                    company_id=company_id,
                    task_id=task_id,
                    event_identity=event_identity,
                ).first()
                if existing is None:
                    raise A2ATaskRepositoryError(
                        f"Unknown A2A event identity: {event_identity!r}"
                    )


def event_from_row(row: A2ATaskEvent) -> TaskProjectionEvent:
    payload = require_json_object(row.event_json, "A2ATaskEvent.event_json")
    if row.event_kind == ARTIFACT_UPDATE_KIND:
        return artifact_update_from_json_dict(payload)
    if row.event_kind == STATUS_UPDATE_KIND:
        return status_update_from_json_dict(payload)
    raise A2ATaskRepositoryError(
        f"Unsupported A2A task event kind: {row.event_kind!r}"
    )
