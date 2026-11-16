"""Задача фонового обогащения геоданных из внешних источников.

Таблица ``geo_enrich_queue`` (``__global_model__``). Медленные
rate-limited источники (НСПД и др.) дрейнит тик ``GEO_ENRICH_TICK`` в
geo_worker по приоритету; ``payload`` — локатор объекта (адрес, bbox,
source_ref) в наших канонических терминах, не чужих.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, execute_raw

from core.models.platform_model import PlatformModel
from core.types import JsonObject, SqlParameterValue


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
    run_after: datetime | None = DbField(default=None)

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

    @classmethod
    async def enqueue(cls, *, kind: str, payload: JsonObject, priority: int = 0) -> Self:
        """Постановка задачи в очередь; повтор того же (kind, payload) — update."""
        rows = await cls.objects.filter(kind=kind).all()
        for row in rows:
            if row.payload == payload and row.status in (
                GeoEnrichStatus.PENDING,
                GeoEnrichStatus.RUNNING,
            ):
                if priority > row.priority:
                    row.priority = priority
                    row.updated_at = datetime.now(UTC)
                    _ = await row.save()
                return row
        return await cls.objects.create(
            instance=cls(
                kind=kind,
                payload=payload,
                priority=priority,
                status=GeoEnrichStatus.PENDING,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )

    @classmethod
    async def enqueue_missing(
        cls,
        *,
        kind: str,
        payloads: list[JsonObject],
        dedupe_field: str,
        priority: int = 0,
        chunk_size: int = 2000,
    ) -> int:
        """Массовая постановка: создаются только payload'ы с новым dedupe-ключом.

        Дедупликация в Postgres чанками: ``NOT IN`` по ключу dedupe-поля
        среди pending/running плюс ``DISTINCT ON`` внутри чанка — ни
        очередь, ни пачка не поднимаются в память целиком.
        """
        if not payloads:
            return 0
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", dedupe_field):
            raise ValueError("dedupe_field must be an identifier")
        created = 0
        now = datetime.now(UTC)
        for offset in range(0, len(payloads), chunk_size):
            chunk = payloads[offset : offset + chunk_size]
            n = len(chunk)
            values = ",".join(f"(${k + 1}::jsonb)" for k in range(n))
            params: list[SqlParameterValue] = [
                json.dumps(payload, ensure_ascii=False) for payload in chunk
            ]
            params += [kind, dedupe_field, priority, now]
            rows = await execute_raw(
                f"""
                INSERT INTO geo_enrich_queue
                    (kind, payload, priority, status, created_at, updated_at)
                SELECT DISTINCT ON (COALESCE(t.payload ->> ${n + 2}, ''))
                       ${n + 1}, t.payload, ${n + 3}, 'pending',
                       ${n + 4}, ${n + 4}
                FROM (VALUES {values}) AS t(payload)
                WHERE COALESCE(t.payload ->> ${n + 2}, '') NOT IN (
                    SELECT COALESCE(payload ->> ${n + 2}, '')
                    FROM geo_enrich_queue
                    WHERE kind = ${n + 1}
                      AND status IN ('pending', 'running')
                )
                RETURNING id
                """,
                params,
                using="geo",
            )
            created += len(rows)
        return created

    @classmethod
    async def claim_pending(cls, *, limit: int) -> list[Self]:
        """Захват пачки задач: pending и run_after прошёл → running."""
        now = datetime.now(UTC)
        candidates = await cls.list_by_priority_desc(
            status=GeoEnrichStatus.PENDING, limit=limit * 4
        )
        claimed: list[Self] = []
        for item in candidates:
            if item.run_after is not None and item.run_after > now:
                continue
            item.status = GeoEnrichStatus.RUNNING
            item.attempts += 1
            item.updated_at = now
            _ = await item.save()
            claimed.append(item)
            if len(claimed) >= limit:
                break
        return claimed

    @classmethod
    async def defer(cls, item: Self, *, run_after: datetime) -> None:
        """Отложенная задача: снова pending с отметкой времени.

        Парковка — не попытка исполнения: ``attempts``, начисленный claim'ом,
        откатывается, чтобы deferred-задачи не сгорали в failed до появления
        своего резолвера.
        """
        item.status = GeoEnrichStatus.PENDING
        item.run_after = run_after
        item.attempts = max(0, item.attempts - 1)
        item.updated_at = datetime.now(UTC)
        _ = await item.save()

    @classmethod
    async def finish_done(cls, item: Self) -> None:
        """Задача обогащения выполнена."""
        now = datetime.now(UTC)
        item.status = GeoEnrichStatus.DONE
        item.last_error = ""
        item.done_at = now
        item.updated_at = now
        _ = await item.save()

    @classmethod
    async def finish_failed(
        cls, item: Self, *, error: str, retry_after: datetime | None, max_attempts: int
    ) -> None:
        """Провал: до max_attempts — retry с backoff, дальше — failed."""
        item.last_error = error
        item.updated_at = datetime.now(UTC)
        if item.attempts >= max_attempts or retry_after is None:
            item.status = GeoEnrichStatus.FAILED
            item.done_at = item.updated_at
        else:
            item.status = GeoEnrichStatus.PENDING
            item.run_after = retry_after
        _ = await item.save()

    @classmethod
    async def retry_failed_by_id(cls, item_id: int) -> Self | None:
        """Админский повтор failed-элемента: pending + чистые попытки.

        ``None`` — элемент не найден или не в статусе failed.
        """
        item = await cls.objects.filter(id=item_id).first()
        if item is None or item.status != GeoEnrichStatus.FAILED:
            return None
        now = datetime.now(UTC)
        item.status = GeoEnrichStatus.PENDING
        item.attempts = 0
        item.last_error = ""
        item.run_after = None
        item.done_at = None
        item.updated_at = now
        _ = await item.save()
        return item
