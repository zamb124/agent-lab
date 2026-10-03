"""Курсор полосы: строка-мьютекс и счётчик без пропусков. Таблица ``lane_cursors``."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import execute_raw

from core.lanes.databases import LANE_DATABASES
from core.models.platform_model import PlatformModel
from core.types import require_json_object
from core.utils.time import utcnow

_NEXT_SEQ = """
INSERT INTO lane_cursors (lane_id, company_id, last_seq, updated_at)
VALUES ($1, $2, $4, $3::timestamptz)
ON CONFLICT (lane_id) DO UPDATE SET
    last_seq = lane_cursors.last_seq + $4,
    updated_at = EXCLUDED.updated_at
RETURNING last_seq - $4 + 1 AS last_seq
"""

_LOCK = """
INSERT INTO lane_cursors (lane_id, company_id, last_seq, updated_at)
VALUES ($1, $2, 0, $3::timestamptz)
ON CONFLICT (lane_id) DO NOTHING
"""

_LOCK_SELECT = "SELECT lane_id FROM lane_cursors WHERE lane_id = $1 FOR UPDATE"


class LaneCursor(PlatformModel):
    """Строка полосы в базе её данных.

    Захват — один ``INSERT … ON CONFLICT DO UPDATE … RETURNING``: строка блокируется
    до конца транзакции, ожидающие стоят в очереди блокировок PostgreSQL в порядке
    прихода. ``last_seq`` растёт на единицу за транзакцию и откатывается вместе с ней,
    поэтому тот же курсор служит последовательностью без пропусков.
    """

    __global_model__: ClassVar[bool] = True
    __database_aliases__: ClassVar[tuple[str, ...]] = LANE_DATABASES

    class Meta:
        is_table: bool = True
        table_name: str = "lane_cursors"

    lane_id: str = DbField(db_pk=True, max_length=200)
    company_id: str = DbField(max_length=100)
    last_seq: int = DbField(default=0)
    updated_at: datetime = DbField()

    @classmethod
    async def next_seq(
        cls,
        lane_ids: Sequence[str],
        *,
        company_id: str,
        using: str,
        count: int = 1,
    ) -> dict[str, int]:
        """Первый номер блока из ``count`` номеров каждой полосы.

        Строки блокируются в отсортированном порядке. При ``count > 1``
        курсор выделяет непрерывный диапазон ``[ret, ret+count-1]`` —
        так журналы пишут пачку записей одним захватом.
        """
        if not lane_ids:
            raise ValueError("next_seq requires at least one lane_id")
        if count < 1:
            raise ValueError("count must be >= 1")
        now = utcnow()
        seqs: dict[str, int] = {}
        for lane_id in sorted(set(lane_ids)):
            if lane_id == "":
                raise ValueError("lane_id must be non-empty")
            rows = await execute_raw(
                _NEXT_SEQ, [lane_id, company_id, now, count], using=using
            )
            if len(rows) != 1:
                raise RuntimeError(f"lane_cursors upsert returned {len(rows)} rows for {lane_id}")
            value = require_json_object(rows[0], "lane_cursors").get("last_seq")
            if not isinstance(value, int):
                raise TypeError(f"lane_cursors.last_seq must be int for {lane_id}")
            seqs[lane_id] = value
        return seqs

    @classmethod
    async def lock(
        cls, lane_id: str, *, company_id: str, using: str
    ) -> None:
        """Сериализующая точка без выделения номера.

        Гарантирует, что строка курсора существует и держит её
        ``FOR UPDATE`` до конца транзакции: вызывающий ждёт
        незакоммиченных писателей этой полосы, но ``last_seq`` не
        расходует. Используется, когда надо увидеть только
        зафиксированные записи полосы (например, смена метода оценки
        ждёт завершения записи слоёв журнала).
        """
        if lane_id == "":
            raise ValueError("lane_id must be non-empty")
        _ = await execute_raw(
            _LOCK, [lane_id, company_id, utcnow()], using=using
        )
        _ = await execute_raw(_LOCK_SELECT, [lane_id], using=using)

    @classmethod
    async def by_lane_id(cls, lane_id: str, *, using: str) -> Self | None:
        return await cls.objects.filter(lane_id=lane_id).get_or_none(using=using)
