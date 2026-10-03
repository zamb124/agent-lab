"""Таблица durable execution."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import ClassVar

from oxyde import Field as DbField
from oxyde import Index, atomic
from oxyde.exceptions import IntegrityError

from apps.flows.src.durable_execution.models.activity_attempt import ActivityAttempt
from apps.flows.src.durable_execution.models.contracts import (
    ACTIVITY_LEASE_SECONDS,
    ActivityRecord,
    ActivityRescheduleResult,
    ActivityStatus,
    SideEffectPolicy,
)
from core.models.platform_model import PlatformModel
from core.types import JsonObject
from core.utils.time import utcnow


class ActivityTask(PlatformModel):
    """Команда внешней операции. Таблица ``activity_tasks``."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "activity_tasks"
        unique_together: list[tuple[str, str, str, str]] = [
            ("company_id", "session_id", "execution_branch_id", "idempotency_key"),
        ]
        indexes: list[Index] = [
            Index(["company_id", "session_id"]),
            Index(["execution_branch_id"]),
            Index(["node_id"]),
        ]

    activity_id: str = DbField(db_pk=True, db_type="TEXT")
    company_id: str = DbField()
    session_id: str = DbField()
    execution_branch_id: str = DbField()
    activity_type: str = DbField()
    input_hash: str = DbField()
    side_effect_policy: SideEffectPolicy = DbField()
    created_at: datetime = DbField()
    node_id: str | None = DbField(default=None)
    tool_call_id: str | None = DbField(default=None)
    idempotency_key: str | None = DbField(default=None, db_type="TEXT")



    @staticmethod
    def _require_side_effect_policy(value: SideEffectPolicy) -> SideEffectPolicy:
        if type(value) is not SideEffectPolicy:
            raise TypeError("side_effect_policy must be SideEffectPolicy")
        return value

    @staticmethod
    def _attempt_id(activity_id: str, attempt: int) -> str:
        return f"{activity_id}:attempt:{attempt}"

    @staticmethod
    def _activity_record(
        task: ActivityTask,
        attempt: ActivityAttempt,
        *,
        was_created: bool = False,
    ) -> ActivityRecord:
        return ActivityRecord(
            activity_id=task.activity_id,
            activity_attempt_id=attempt.activity_attempt_id,
            company_id=task.company_id,
            session_id=task.session_id,
            execution_branch_id=task.execution_branch_id,
            node_id=task.node_id,
            tool_call_id=task.tool_call_id,
            activity_type=task.activity_type,
            status=attempt.status,
            attempt=attempt.attempt,
            input_hash=task.input_hash,
            idempotency_key=task.idempotency_key,
            side_effect_policy=task.side_effect_policy,
            result_json=attempt.result_json,
            error=attempt.error,
            lease_until=attempt.lease_until,
            was_created=was_created,
        )

    @classmethod
    async def cache_activity(
        cls,
        *,
        company_id: str,
        session_id: str,
        execution_branch_id: str,
        activity_id: str,
        activity_type: str,
        input_hash: str,
        node_id: str | None = None,
        tool_call_id: str | None = None,
        idempotency_key: str | None = None,
        side_effect_policy: SideEffectPolicy,
    ) -> ActivityRecord:
        resolved_side_effect_policy = cls._require_side_effect_policy(side_effect_policy)
        now = utcnow()
        task = ActivityTask(
            activity_id=activity_id,
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=execution_branch_id,
            node_id=node_id,
            tool_call_id=tool_call_id,
            activity_type=activity_type,
            input_hash=input_hash,
            idempotency_key=idempotency_key,
            side_effect_policy=resolved_side_effect_policy,
            created_at=now,
        )
        attempt = ActivityAttempt(
            activity_attempt_id=cls._attempt_id(activity_id, 1),
            activity_id=activity_id,
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=execution_branch_id,
            attempt=1,
            status=ActivityStatus.scheduled,
            scheduled_at=now,
        )
        try:
            async with atomic(using="flows"):
                _ = await ActivityTask.objects.create(instance=task)
                _ = await ActivityAttempt.objects.create(instance=attempt)
        except IntegrityError:
            record = await cls.get_activity(
                company_id=company_id,
                session_id=session_id,
                execution_branch_id=execution_branch_id,
                activity_id=activity_id,
                idempotency_key=idempotency_key,
            )
            if record is None:
                raise
            if record.input_hash != input_hash:
                raise ValueError(
                    "Activity idempotency collision with different input: "
                    + f"activity_id={activity_id!r}, idempotency_key={idempotency_key!r}"
                )
            return record
        return cls._activity_record(task, attempt, was_created=True)

    @classmethod
    async def get_activity(
        cls,
        *,
        company_id: str,
        session_id: str,
        execution_branch_id: str,
        activity_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ActivityRecord | None:
        if activity_id is None and idempotency_key is None:
            raise ValueError("activity_id or idempotency_key is required")
        tasks = ActivityTask.objects.filter(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=execution_branch_id,
        )
        if idempotency_key is not None:
            task = await tasks.filter(idempotency_key=idempotency_key).first()
        else:
            task = await tasks.filter(activity_id=activity_id).first()
        if task is None:
            return None
        attempt = await (
            ActivityAttempt.objects.filter(activity_id=task.activity_id)
            .order_by("-attempt")
            .first()
        )
        if attempt is None:
            raise RuntimeError(f"Activity has no attempts: {task.activity_id!r}")
        return cls._activity_record(task, attempt)

    @classmethod
    async def get_completed_activity_result(
        cls,
        *,
        company_id: str,
        session_id: str,
        execution_branch_id: str,
        activity_id: str | None = None,
        idempotency_key: str | None = None,
        input_hash: str,
    ) -> JsonObject | None:
        record = await cls.get_activity(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=execution_branch_id,
            activity_id=activity_id,
            idempotency_key=idempotency_key,
        )
        if record is None:
            return None
        if record.input_hash != input_hash:
            raise ValueError(
                "Activity replay requested with different input hash: "
                + f"activity_id={activity_id!r}, idempotency_key={idempotency_key!r}"
            )
        if record.status is not ActivityStatus.completed:
            return None
        return record.result_json

    @classmethod
    async def complete_activity(
        cls,
        *,
        activity_id: str,
        result_json: JsonObject | None = None,
        error: str | None = None,
    ) -> ActivityRecord | None:
        status = ActivityStatus.failed if error else ActivityStatus.completed
        now = utcnow()
        task = await ActivityTask.objects.filter(activity_id=activity_id).first()
        if task is None:
            return None
        latest = await (
            ActivityAttempt.objects.filter(activity_id=activity_id).order_by("-attempt").first()
        )
        if latest is None or latest.status != ActivityStatus.started:
            return None
        updated_rows = await ActivityAttempt.objects.filter(
            activity_attempt_id=latest.activity_attempt_id,
            status=ActivityStatus.started,
        ).update(
            returning=False,
            using="flows",
            status=status,
            result_json=result_json,
            error=error,
            completed_at=now,
            lease_until=None,
        )
        if updated_rows != 1:
            return None
        attempt = await ActivityAttempt.objects.filter(
            activity_attempt_id=latest.activity_attempt_id
        ).first()
        if attempt is None:
            raise RuntimeError(f"Activity attempt disappeared: {latest.activity_attempt_id!r}")
        return cls._activity_record(task, attempt)

    @classmethod
    async def start_activity(
        cls,
        *,
        activity_id: str,
    ) -> ActivityRecord | None:
        now = utcnow()
        lease_until = now + timedelta(seconds=ACTIVITY_LEASE_SECONDS)
        task = await ActivityTask.objects.filter(activity_id=activity_id).first()
        if task is None:
            return None
        latest = await (
            ActivityAttempt.objects.filter(activity_id=activity_id).order_by("-attempt").first()
        )
        if latest is None or latest.status != ActivityStatus.scheduled:
            return None
        updated_rows = await ActivityAttempt.objects.filter(
            activity_attempt_id=latest.activity_attempt_id,
            status=ActivityStatus.scheduled,
        ).update(
            returning=False,
            using="flows",
            status=ActivityStatus.started,
            lease_until=lease_until,
            started_at=now,
        )
        if updated_rows != 1:
            return None
        attempt = await ActivityAttempt.objects.filter(
            activity_attempt_id=latest.activity_attempt_id
        ).first()
        if attempt is None:
            raise RuntimeError(f"Activity attempt disappeared: {latest.activity_attempt_id!r}")
        return cls._activity_record(task, attempt)

    @classmethod
    async def reschedule_activity_attempt(
        cls,
        *,
        activity_id: str,
    ) -> ActivityRescheduleResult | None:
        now = utcnow()
        async with atomic(using="flows"):
            task = await ActivityTask.objects.filter(activity_id=activity_id).first()
            if task is None or task.side_effect_policy == SideEffectPolicy.non_idempotent:
                return None
            latest = await (
                ActivityAttempt.objects.filter(activity_id=activity_id)
                .order_by("-attempt")
                .for_update()
                .first()
            )
            if latest is None:
                return None
            expired_attempt: ActivityAttempt | None = None
            if latest.status == ActivityStatus.started:
                if latest.lease_until is None or latest.lease_until > now:
                    return None
                updated_rows = await ActivityAttempt.objects.filter(
                    activity_attempt_id=latest.activity_attempt_id,
                    status=ActivityStatus.started,
                ).update(
                    returning=False,
                    using="flows",
                    status=ActivityStatus.failed,
                    error="activity lease expired",
                    completed_at=now,
                    lease_until=None,
                )
                if updated_rows != 1:
                    return None
                expired_attempt = await ActivityAttempt.objects.filter(
                    activity_attempt_id=latest.activity_attempt_id
                ).first()
                if expired_attempt is None:
                    raise RuntimeError(
                        f"Activity attempt disappeared: {latest.activity_attempt_id!r}"
                    )
            elif latest.status != ActivityStatus.failed:
                return None
            scheduled = ActivityAttempt(
                activity_attempt_id=cls._attempt_id(activity_id, latest.attempt + 1),
                activity_id=activity_id,
                company_id=task.company_id,
                session_id=task.session_id,
                execution_branch_id=task.execution_branch_id,
                attempt=latest.attempt + 1,
                status=ActivityStatus.scheduled,
                scheduled_at=now,
            )
            _ = await ActivityAttempt.objects.create(instance=scheduled)
        return ActivityRescheduleResult(
            expired_attempt=(
                cls._activity_record(task, expired_attempt)
                if expired_attempt is not None
                else None
            ),
            scheduled_attempt=cls._activity_record(task, scheduled),
        )
