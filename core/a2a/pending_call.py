"""Реестр ожидающих A2A-вызовов: pending → push webhook → continuation.

Одна строка = один субмитнутый A2A Task со стороны вызывающего сервиса.
Push endpoint (`core/api/a2a_push.py`) атомарно consume'ит строку и ставит
continuation TaskIQ задачу; sweeper (`apps/idle/tasks/a2a_pending_tasks.py`)
добивает потерянные/просроченные вызовы с ``a2a_state="deadline_exceeded"``.
Доставка — каноничный ``taskPushNotificationConfig`` A2A 1.0; таблица — только
корреляция и bearer-токен вебхука.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel
from core.types import JsonObject


class PendingCallStatus(StrEnum):
    """Жизненный цикл pending-вызова."""

    pending = "pending"
    resolved = "resolved"
    consumed = "consumed"
    expired = "expired"
    canceled = "canceled"


# `a2a_state` continuation-задачи, когда вызов сгорел по deadline_at (sweeper).
A2A_STATE_DEADLINE_EXCEEDED = "deadline_exceeded"

# Сколько хранить consumed/expired строки для аудита до зачистки sweeper'ом.
CONSUMED_RETENTION_SECONDS = 7 * 86400


class PlatformA2APendingCall(PlatformModel):
    """Ожидающий завершения A2A-вызов. Таблица ``a2a_pending_calls`` в shared.

    ``__global_model__``: sweeper и push endpoint обслуживают строки всех
    компаний одним проходом; ``company_id`` — контекст владельца для
    continuation, не scope запроса.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    a2a_task_id: str = DbField(db_pk=True, max_length=255)

    class Meta:
        is_table: bool = True
        table_name: str = "a2a_pending_calls"
        indexes: list[Index] = [
            Index(("status", "deadline_at")),
            Index(("company_id",)),
            Index(("parent_task_id",)),
            Index(("join_group",)),
            Index(("service", "dedup_key")),
        ]

    service: str = DbField(max_length=64)
    company_id: str = DbField(max_length=255)
    user_id: str = DbField(max_length=255)
    base_url: str = DbField(db_type="TEXT")
    continuation_task: str = DbField(max_length=255)
    continuation_kwargs: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    callback_token_hash: str = DbField(max_length=64)
    join_group: str | None = DbField(default=None, max_length=255)
    parent_task_id: str | None = DbField(default=None, max_length=255)
    dedup_key: str | None = DbField(default=None, max_length=512)
    result_payload: JsonObject | None = DbField(default=None, db_type="JSONB")
    status: PendingCallStatus = DbField(
        default=PendingCallStatus.pending, max_length=32
    )
    deadline_at: datetime = DbField()
    consumed_at: datetime | None = DbField(default=None)
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    async def register(
        cls,
        *,
        a2a_task_id: str,
        service: str,
        company_id: str,
        user_id: str,
        base_url: str,
        continuation_task: str,
        continuation_kwargs: JsonObject,
        callback_token_hash: str,
        deadline_at: datetime,
        join_group: str | None = None,
        parent_task_id: str | None = None,
        dedup_key: str | None = None,
    ) -> Self:
        """Строка pending-вызова до submit; PK `a2a_task_id` назначает вызывающий."""
        for name, value in (
            ("a2a_task_id", a2a_task_id),
            ("service", service),
            ("company_id", company_id),
            ("user_id", user_id),
            ("base_url", base_url),
            ("continuation_task", continuation_task),
            ("callback_token_hash", callback_token_hash),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")
        row = cls(
            a2a_task_id=a2a_task_id,
            service=service,
            company_id=company_id,
            user_id=user_id,
            base_url=base_url,
            continuation_task=continuation_task,
            continuation_kwargs=dict(continuation_kwargs),
            callback_token_hash=callback_token_hash,
            join_group=join_group,
            parent_task_id=parent_task_id,
            dedup_key=dedup_key,
            status=PendingCallStatus.pending,
            deadline_at=deadline_at,
        )
        return await cls.objects.create(instance=row)

    @classmethod
    async def pending_by_id(cls, a2a_task_id: str) -> Self | None:
        """Строка по PK. Нет строки — None."""
        return await cls.objects.filter(a2a_task_id=a2a_task_id).first()

    @classmethod
    async def consume(cls, a2a_task_id: str) -> Self | None:
        """Атомарный pending → consumed (webhook принят). Повтор — None."""
        now = datetime.now(timezone.utc)
        updated = await cls.objects.filter(
            a2a_task_id=a2a_task_id,
            status=PendingCallStatus.pending,
        ).update(
            returning=False,
            status=PendingCallStatus.consumed,
            consumed_at=now,
            updated_at=now,
        )
        if updated != 1:
            return None
        return await cls.pending_by_id(a2a_task_id)

    @classmethod
    async def relink_task_id(cls, a2a_task_id: str, remote_task_id: str) -> Self:
        """Агент назначил свой Task.id: перелинковать строку на проводной id."""
        if not remote_task_id.strip():
            raise ValueError("remote_task_id is required")
        row = await cls.pending_by_id(a2a_task_id)
        if row is None:
            raise RuntimeError(f"pending call not found: {a2a_task_id!r}")
        if row.a2a_task_id == remote_task_id:
            return row
        relinked = cls(
            a2a_task_id=remote_task_id,
            service=row.service,
            company_id=row.company_id,
            user_id=row.user_id,
            base_url=row.base_url,
            continuation_task=row.continuation_task,
            continuation_kwargs=row.continuation_kwargs,
            callback_token_hash=row.callback_token_hash,
            join_group=row.join_group,
            parent_task_id=row.parent_task_id,
            status=row.status,
            deadline_at=row.deadline_at,
            consumed_at=row.consumed_at,
            created_at=row.created_at,
        )
        relinked = await cls.objects.create(instance=relinked)
        _ = await cls.objects.filter(a2a_task_id=a2a_task_id).delete()
        return relinked

    @classmethod
    async def by_dedup_key(cls, service: str, dedup_key: str) -> Self | None:
        """Активная/resolved строка по dedup-ключу вызова (повторный прогон задачи)."""
        return await (
            cls.objects.filter(service=service, dedup_key=dedup_key)
            .order_by("-created_at")
            .first()
        )

    @classmethod
    async def store_result(cls, a2a_task_id: str, result: JsonObject) -> Self | None:
        """pending|consumed → resolved с payload результата (continuation положил ответ).

        ``consumed`` — endpoint уже принял webhook и поставил continuation;
        ``pending`` — прямой вызов (continuation сам добрал результат).
        """
        now = datetime.now(timezone.utc)
        updated = await cls.objects.filter(
            a2a_task_id=a2a_task_id,
        ).filter(
            status__in=[PendingCallStatus.pending, PendingCallStatus.consumed],
        ).update(
            returning=False,
            status=PendingCallStatus.resolved,
            result_payload=dict(result),
            consumed_at=now,
            updated_at=now,
        )
        if updated != 1:
            return None
        return await cls.pending_by_id(a2a_task_id)

    @classmethod
    async def take_result(
        cls, service: str, dedup_key: str
    ) -> JsonObject | None:
        """resolved → consumed, возвращает payload. Повторный прогон забирает результат."""
        row = await cls.by_dedup_key(service, dedup_key)
        if row is None or row.status is not PendingCallStatus.resolved:
            return None
        now = datetime.now(timezone.utc)
        updated = await cls.objects.filter(
            a2a_task_id=row.a2a_task_id,
            status=PendingCallStatus.resolved,
        ).update(
            returning=False,
            status=PendingCallStatus.consumed,
            updated_at=now,
        )
        if updated != 1:
            return None
        return row.result_payload

    @classmethod
    async def due_for_sweep(cls, now: datetime) -> list[Self]:
        """Просроченные pending-строки всех сервисов: deadline_at < now."""
        return await (
            cls.objects.filter(status=PendingCallStatus.pending)
            .filter(deadline_at__lt=now)
            .all()
        )

    @classmethod
    async def mark_expired(cls, a2a_task_id: str) -> Self | None:
        """Атомарный pending → expired (гонка с webhook-consume проигрывает)."""
        now = datetime.now(timezone.utc)
        updated = await cls.objects.filter(
            a2a_task_id=a2a_task_id,
            status=PendingCallStatus.pending,
        ).update(
            returning=False,
            status=PendingCallStatus.expired,
            consumed_at=now,
            updated_at=now,
        )
        if updated != 1:
            return None
        return await cls.pending_by_id(a2a_task_id)

    @classmethod
    async def restore_pending(cls, a2a_task_id: str) -> Self | None:
        """expired|consumed → pending: continuation не поставился, честный ретрай."""
        now = datetime.now(timezone.utc)
        updated = await cls.objects.filter(
            a2a_task_id=a2a_task_id,
        ).filter(
            status__in=[PendingCallStatus.expired, PendingCallStatus.consumed],
        ).update(
            returning=False,
            status=PendingCallStatus.pending,
            consumed_at=None,
            updated_at=now,
        )
        if updated != 1:
            return None
        return await cls.pending_by_id(a2a_task_id)

    @classmethod
    async def cancel_for_parent(cls, service: str, parent_task_id: str) -> list[Self]:
        """Consume всех pending-строк сервиса по parent_task_id (CancelTask родителя)."""
        rows = await cls.objects.filter(
            service=service,
            parent_task_id=parent_task_id,
            status=PendingCallStatus.pending,
        ).all()
        consumed: list[Self] = []
        now = datetime.now(timezone.utc)
        for row in rows:
            updated = await cls.objects.filter(
                a2a_task_id=row.a2a_task_id,
                status=PendingCallStatus.pending,
            ).update(
                returning=False,
                status=PendingCallStatus.canceled,
                consumed_at=now,
                updated_at=now,
            )
            if updated == 1:
                row.status = PendingCallStatus.canceled
                consumed.append(row)
        return consumed

    @classmethod
    async def purge_consumed_before(cls, before: datetime) -> int:
        """Удалить consumed/expired/canceled строки старше `before`. Возвращает число."""
        deleted = await (
            cls.objects.exclude(status=PendingCallStatus.pending)
            .filter(consumed_at__lt=before)
            .delete()
        )
        return int(deleted or 0)


__all__ = [
    "A2A_STATE_DEADLINE_EXCEEDED",
    "CONSUMED_RETENTION_SECONDS",
    "PendingCallStatus",
    "PlatformA2APendingCall",
]
