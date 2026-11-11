"""Join-группы fan-out A2A-вызовов: N pending-рядов → один join-task.

Fan-out пайплайн (например CRM dedup по кандидатам): создаётся join-ряд
``join_total=N``, каждый member-pending несёт ``join_group`` в своих
``continuation_kwargs``. Continuation member'а применяет свой результат и
зовёт ``decrement``; последний ставит ``join_task``. Deadline join'а ловит
тот же sweeper — join_task уходит с частичными результатами и
``a2a_state="deadline_exceeded"``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import ClassVar, Self

from oxyde import F
from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel
from core.types import JsonObject


class PendingJoinStatus(StrEnum):
    """Жизненный цикл join-группы."""

    pending = "pending"
    fired = "fired"
    expired = "expired"


class PlatformA2APendingJoin(PlatformModel):
    """Join-группа A2A fan-out. Таблица ``a2a_pending_joins`` в shared.

    ``__global_model__``: sweeper обслуживает строки всех компаний по ``service``.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    join_group: str = DbField(db_pk=True, max_length=255)

    class Meta:
        is_table: bool = True
        table_name: str = "a2a_pending_joins"
        indexes: list[Index] = [
            Index(("service", "status", "deadline_at")),
        ]

    service: str = DbField(db_index=True, max_length=64)
    company_id: str = DbField(db_index=True, max_length=255)
    join_task: str = DbField(max_length=255)
    join_kwargs: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    join_total: int = DbField()
    join_remaining: int = DbField()
    status: PendingJoinStatus = DbField(
        default=PendingJoinStatus.pending, db_index=True, max_length=32
    )
    deadline_at: datetime = DbField(db_index=True)
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    async def register(
        cls,
        *,
        join_group: str,
        service: str,
        company_id: str,
        join_task: str,
        join_kwargs: JsonObject,
        join_total: int,
        deadline_at: datetime,
    ) -> Self:
        """Join-ряд до fan-out submit'ов; ``join_total`` — число member-вызовов."""
        if not join_group.strip():
            raise ValueError("join_group is required")
        if not service.strip():
            raise ValueError("service is required")
        if not company_id.strip():
            raise ValueError("company_id is required")
        if not join_task.strip():
            raise ValueError("join_task is required")
        if join_total < 1:
            raise ValueError("join_total must be >= 1")
        row = cls(
            join_group=join_group,
            service=service,
            company_id=company_id,
            join_task=join_task,
            join_kwargs=dict(join_kwargs),
            join_total=join_total,
            join_remaining=join_total,
            status=PendingJoinStatus.pending,
            deadline_at=deadline_at,
        )
        return await cls.objects.create(instance=row)

    @classmethod
    async def pending_by_id(cls, join_group: str) -> Self | None:
        """Join-ряд по PK. Нет строки — None."""
        return await cls.objects.filter(join_group=join_group).first()

    @classmethod
    async def decrement(cls, join_group: str) -> Self | None:
        """Атомарный join_remaining -= 1. Строка с новым счётчиком или None
        (группа уже fired/expired/все члены съели счётчик). Чей декремент
        дал 0 — тот и ставит ``join_task`` через ``fire``."""
        now = datetime.now(timezone.utc)
        updated = await cls.objects.filter(
            join_group=join_group,
            status=PendingJoinStatus.pending,
            join_remaining__gt=0,
        ).update(
            returning=True,
            join_remaining=F("join_remaining") - 1,
            updated_at=now,
        )
        if not updated:
            return None
        return updated[0]

    @classmethod
    async def fire(cls, join_group: str) -> Self | None:
        """Атомарный pending → fired при join_remaining=0. Победитель один."""
        now = datetime.now(timezone.utc)
        updated = await cls.objects.filter(
            join_group=join_group,
            status=PendingJoinStatus.pending,
            join_remaining=0,
        ).update(
            returning=False,
            status=PendingJoinStatus.fired,
            updated_at=now,
        )
        if updated != 1:
            return None
        return await cls.pending_by_id(join_group)

    @classmethod
    async def due_for_sweep(cls, now: datetime) -> list[Self]:
        """Просроченные pending join-ряды всех сервисов."""
        return await (
            cls.objects.filter(status=PendingJoinStatus.pending)
            .filter(deadline_at__lt=now)
            .all()
        )

    @classmethod
    async def mark_expired(cls, join_group: str) -> Self | None:
        """Атомарный pending → expired."""
        now = datetime.now(timezone.utc)
        updated = await cls.objects.filter(
            join_group=join_group,
            status=PendingJoinStatus.pending,
        ).update(
            returning=False,
            status=PendingJoinStatus.expired,
            updated_at=now,
        )
        if updated != 1:
            return None
        return await cls.pending_by_id(join_group)

    @classmethod
    async def restore_pending(cls, join_group: str) -> Self | None:
        """expired|fired → pending: join_task не поставился, ретрай тика."""
        now = datetime.now(timezone.utc)
        updated = await cls.objects.filter(
            join_group=join_group,
        ).filter(
            status__in=[PendingJoinStatus.expired, PendingJoinStatus.fired],
        ).update(
            returning=False,
            status=PendingJoinStatus.pending,
            updated_at=now,
        )
        if updated != 1:
            return None
        return await cls.pending_by_id(join_group)

    @classmethod
    async def purge_finished_before(cls, before: datetime) -> int:
        """Удалить fired/expired join-ряды старше `before`. Возвращает число."""
        deleted = await (
            cls.objects.exclude(status=PendingJoinStatus.pending)
            .filter(updated_at__lt=before)
            .delete()
        )
        return int(deleted or 0)


__all__ = [
    "PendingJoinStatus",
    "PlatformA2APendingJoin",
]
