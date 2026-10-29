"""Таблица durable execution."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar
from uuid import uuid4

from oxyde import Field as DbField
from oxyde import Index, Q, atomic

from apps.flows.src.durable_execution.hashing import hash_state_json
from apps.flows.src.durable_execution.models.contracts import (
    BranchTransitionPayload,
    ExecutionBranchReason,
    ExecutionStateDelta,
    RetryScheduledPayload,
    TimeTravelEffect,
    WorkflowAppendResult,
    WorkflowBranchRecord,
    WorkflowBranchResult,
    WorkflowConcurrencyError,
    WorkflowEventPayload,
    WorkflowEventRecord,
    WorkflowEventType,
    WorkflowProjectionMismatchError,
    WorkflowStateTransitionWrite,
    WorkflowStatus,
    apply_state_delta,
    build_state_delta,
    parse_workflow_event_payload,
    workflow_event_payload_json,
)
from apps.flows.src.durable_execution.models.execution_branch import ExecutionBranch
from apps.flows.src.durable_execution.models.workflow_event import WorkflowEvent
from apps.flows.src.durable_execution.models.workflow_snapshot import WorkflowSnapshot
from core.models.platform_model import PlatformModel
from core.state import ExecutionState
from core.types import JsonObject, JsonValue, require_json_object
from core.utils.time import utcnow


class WorkflowInstance(PlatformModel):
    """Голова сессии выполнения. Таблица ``workflow_instances``."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "workflow_instances"
        unique_together: list[tuple[str, str]] = [("company_id", "session_id")]
        indexes: list[Index] = [
            Index(["company_id", "flow_id", "updated_at"]),
            Index(["company_id", "user_id", "updated_at"]),
            Index(["company_id", "task_id"]),
            Index(["company_id", "context_id"]),
            Index(["company_id", "status"]),
            Index(["company_id", "updated_at"]),
        ]

    workflow_instance_id: str = DbField(db_pk=True)
    company_id: str = DbField()
    session_id: str = DbField()
    active_execution_branch_id: str = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    head_sequence: int = DbField(default=0, ge=0)
    status: WorkflowStatus = DbField(default=WorkflowStatus.running)
    flow_id: str | None = DbField(default=None)
    context_id: str | None = DbField(default=None)
    task_id: str | None = DbField(default=None)
    user_id: str | None = DbField(default=None)
    flow_branch_id: str | None = DbField(default=None)
    head_state_hash: str | None = DbField(default=None)
    latest_snapshot_id: str | None = DbField(default=None)
    last_event_at: datetime | None = DbField(default=None)



    @staticmethod
    def _delta_json(delta: ExecutionStateDelta) -> JsonObject:
        return require_json_object(
            delta.model_dump(mode="json", exclude_none=False),
            "WorkflowEvent.state_delta",
        )

    @staticmethod
    def _workflow_event_record(row: WorkflowEvent) -> WorkflowEventRecord:
        payload = parse_workflow_event_payload(
            row.event_type,
            require_json_object(row.payload, "WorkflowEvent.payload"),
        )
        return WorkflowEventRecord(
            event_id=row.event_id,
            session_id=row.session_id,
            execution_branch_id=row.execution_branch_id,
            sequence=row.sequence,
            event_type=row.event_type,
            payload=payload,
            state_delta=ExecutionStateDelta.model_validate(row.state_delta),
            prev_state_hash=row.prev_state_hash,
            next_state_hash=row.next_state_hash,
            created_at=row.created_at.isoformat(),
        )

    @classmethod
    async def _locked_instance(cls, company_id: str, session_id: str) -> WorkflowInstance | None:
        return await (
            WorkflowInstance.objects.filter(company_id=company_id, session_id=session_id)
            .for_update()
            .first()
        )

    @classmethod
    async def _start_instance(
        cls,
        *,
        company_id: str,
        session_id: str,
        state_json: JsonObject,
        now: datetime,
    ) -> tuple[WorkflowInstance, str]:
        execution_branch_id = str(uuid4())
        _ = await ExecutionBranch.objects.create(
            instance=ExecutionBranch(
                execution_branch_id=execution_branch_id,
                company_id=company_id,
                session_id=session_id,
                base_sequence=0,
                reason=ExecutionBranchReason.start,
                created_at=now,
            )
        )
        instance = WorkflowInstance(
            workflow_instance_id=str(uuid4()),
            company_id=company_id,
            session_id=session_id,
            flow_id=cls._flow_id_from_session_id(session_id),
            context_id=cls._context_id_from_state(state_json, session_id),
            task_id=cls._string_or_none(state_json.get("task_id")),
            user_id=cls._string_or_none(state_json.get("user_id")),
            flow_branch_id=cls._string_or_none(state_json.get("branch_id")),
            active_execution_branch_id=execution_branch_id,
            head_sequence=0,
            status=WorkflowStatus.running,
            last_event_at=now,
            created_at=now,
            updated_at=now,
        )
        _ = await WorkflowInstance.objects.create(instance=instance)
        return instance, execution_branch_id

    @classmethod
    async def any_by_company_and_session(
        cls,
        *,
        company_id: str,
        session_id: str,
    ) -> WorkflowInstance | None:
        """Первая попавшаяся голова сессии. Порядка нет. Несколько строк — какая именно, не задано. Нет строки — None. Пустые идентификаторы не проверяются."""
        return await WorkflowInstance.objects.filter(
            company_id=company_id,
            session_id=session_id,
        ).first()

    @classmethod
    async def instances_and_total_by_updated_at_desc(
        cls,
        *,
        company_id: str,
        flow_id: str | None = None,
        user_id: str | None = None,
        flow_branch_id: str | None = None,
        updated_from: datetime | None = None,
        updated_to: datetime | None = None,
        limit: int | None = 50,
        offset: int = 0,
    ) -> tuple[list[WorkflowInstance], int]:
        """Окно голов компании и total того же фильтра, ORDER BY updated_at DESC. Пустая строка в flow_id, user_id или flow_branch_id не фильтрует. updated_from и updated_to равные None не фильтруют. limit is None не ограничивает, по умолчанию 50."""
        query = WorkflowInstance.objects.filter(company_id=company_id)
        if flow_id:
            query = query.filter(flow_id=flow_id)
        if user_id:
            query = query.filter(user_id=user_id)
        if flow_branch_id:
            query = query.filter(flow_branch_id=flow_branch_id)
        if updated_from is not None:
            query = query.filter(updated_at__gte=updated_from)
        if updated_to is not None:
            query = query.filter(updated_at__lte=updated_to)
        total = await query.count()
        page = query.order_by("-updated_at")
        if limit is not None:
            page = page.limit(limit).offset(offset)
        return await page.all(), total

    @classmethod
    async def event_records_and_total_by_sequence_asc(
        cls,
        *,
        company_id: str,
        session_id: str,
        execution_branch_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[WorkflowEventRecord], int]:
        """Окно событий сессии и total того же фильтра, ORDER BY sequence ASC. execution_branch_id is None не фильтрует. limit по умолчанию 200."""
        query = WorkflowEvent.objects.filter(company_id=company_id, session_id=session_id)
        if execution_branch_id is not None:
            query = query.filter(execution_branch_id=execution_branch_id)
        total = await query.count()
        rows = await query.order_by("sequence").limit(limit).offset(offset).all()
        return [cls._workflow_event_record(row) for row in rows], total

    @classmethod
    async def event_record_by_type_or_latest_sequence_desc(
        cls,
        *,
        company_id: str,
        session_id: str,
        execution_branch_id: str,
        event_type: WorkflowEventType,
        sequence: int | None = None,
    ) -> WorkflowEventRecord | None:
        """Запись события ветки, не строка таблицы. Без sequence — ORDER BY sequence DESC. С sequence — событие этого номера. Нет строки — None."""
        query = WorkflowEvent.objects.filter(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=execution_branch_id,
            event_type=event_type,
        )
        if sequence is not None:
            query = query.filter(sequence=sequence).order_by("sequence")
        else:
            query = query.order_by("-sequence")
        row = await query.first()
        if row is None:
            return None
        return cls._workflow_event_record(row)

    @classmethod
    async def branch_records_by_created_at_asc(
        cls,
        *,
        company_id: str,
        session_id: str,
    ) -> list[WorkflowBranchRecord]:
        """Записи веток сессии, ORDER BY created_at ASC. Предела нет. Нет головы сессии — is_active ложен у всех."""
        instance = await cls.any_by_company_and_session(company_id=company_id, session_id=session_id)
        active_branch_id = instance.active_execution_branch_id if instance is not None else None
        rows = await (
            ExecutionBranch.objects.filter(company_id=company_id, session_id=session_id)
            .order_by("created_at")
            .all()
        )
        return [
            WorkflowBranchRecord(
                execution_branch_id=row.execution_branch_id,
                parent_execution_branch_id=row.parent_execution_branch_id,
                base_sequence=row.base_sequence,
                base_state_hash=row.base_state_hash,
                reason=row.reason,
                created_at=row.created_at.isoformat(),
                is_active=row.execution_branch_id == active_branch_id,
            )
            for row in rows
        ]

    @classmethod
    async def append_state_transition(
        cls,
        *,
        company_id: str,
        session_id: str,
        event_type: WorkflowEventType,
        payload: WorkflowEventPayload,
        state_delta: ExecutionStateDelta,
        state_json: JsonObject,
        status: WorkflowStatus,
        snapshot: bool,
        causation_id: str | None = None,
        correlation_id: str | None = None,
        expected_head_sequence: int | None = None,
        expected_execution_branch_id: str | None = None,
    ) -> WorkflowAppendResult:
        """Append one canonical event and update workflow head atomically."""
        state_hash = hash_state_json(state_json)
        event_id = str(uuid4())
        snapshot_id = str(uuid4()) if snapshot else None

        async with atomic(using="flows"):
            instance = await cls._locked_instance(company_id, session_id)
            now = utcnow()
            if instance is None:
                if expected_head_sequence is not None or expected_execution_branch_id is not None:
                    raise WorkflowConcurrencyError(
                        f"Workflow {session_id!r} does not exist for expected append"
                    )
                instance, _started_branch_id = await cls._start_instance(
                    company_id=company_id,
                    session_id=session_id,
                    state_json=state_json,
                    now=now,
                )

            execution_branch_id = instance.active_execution_branch_id
            if (
                expected_execution_branch_id is not None
                and execution_branch_id != expected_execution_branch_id
            ):
                raise WorkflowConcurrencyError(
                    "Workflow active branch changed during append: "
                    + f"session_id={session_id!r}, "
                    + f"expected={expected_execution_branch_id!r}, got={execution_branch_id!r}"
                )
            if (
                expected_head_sequence is not None
                and instance.head_sequence != expected_head_sequence
            ):
                raise WorkflowConcurrencyError(
                    "Workflow head sequence changed during append: "
                    + f"session_id={session_id!r}, "
                    + f"expected={expected_head_sequence}, got={instance.head_sequence}"
                )
            prev_hash = instance.head_state_hash
            sequence = instance.head_sequence + 1
            _ = await WorkflowEvent.objects.create(
                instance=WorkflowEvent(
                    event_id=event_id,
                    company_id=company_id,
                    session_id=session_id,
                    execution_branch_id=execution_branch_id,
                    sequence=sequence,
                    event_type=event_type,
                    payload=workflow_event_payload_json(payload),
                    state_delta=cls._delta_json(state_delta),
                    prev_state_hash=prev_hash,
                    next_state_hash=state_hash,
                    causation_id=causation_id,
                    correlation_id=correlation_id,
                    created_at=now,
                )
            )
            if snapshot_id is not None:
                _ = await WorkflowSnapshot.objects.create(
                    instance=WorkflowSnapshot(
                        snapshot_id=snapshot_id,
                        company_id=company_id,
                        session_id=session_id,
                        execution_branch_id=execution_branch_id,
                        sequence=sequence,
                        state_json=state_json,
                        state_hash=state_hash,
                        created_at=now,
                    )
                )
            instance.head_sequence = sequence
            instance.head_state_hash = state_hash
            if snapshot_id is not None:
                instance.latest_snapshot_id = snapshot_id
            instance.status = status
            instance.flow_id = cls._flow_id_from_session_id(session_id)
            instance.context_id = cls._context_id_from_state(state_json, session_id)
            instance.task_id = cls._string_or_none(state_json.get("task_id"))
            instance.user_id = cls._string_or_none(state_json.get("user_id"))
            instance.flow_branch_id = cls._string_or_none(state_json.get("branch_id"))
            instance.last_event_at = now
            instance.updated_at = now
            _ = await instance.save()

        return WorkflowAppendResult(
            event_id=event_id,
            execution_branch_id=execution_branch_id,
            sequence=sequence,
            state_hash=state_hash,
            snapshot_id=snapshot_id,
        )

    @classmethod
    async def append_state_transitions(
        cls,
        *,
        company_id: str,
        session_id: str,
        transitions: list[WorkflowStateTransitionWrite],
        expected_head_sequence: int | None = None,
        expected_execution_branch_id: str | None = None,
    ) -> list[WorkflowAppendResult]:
        """Append multiple canonical events and update workflow head once."""
        if not transitions:
            return []

        event_ids = [str(uuid4()) for _ in transitions]
        snapshot_ids = [str(uuid4()) if item.snapshot else None for item in transitions]
        state_hashes = [hash_state_json(item.state_json) for item in transitions]

        async with atomic(using="flows"):
            instance = await cls._locked_instance(company_id, session_id)
            now = utcnow()
            if instance is None:
                if expected_head_sequence is not None or expected_execution_branch_id is not None:
                    raise WorkflowConcurrencyError(
                        f"Workflow {session_id!r} does not exist for expected append"
                    )
                instance, _started_branch_id = await cls._start_instance(
                    company_id=company_id,
                    session_id=session_id,
                    state_json=transitions[0].state_json,
                    now=now,
                )

            execution_branch_id = instance.active_execution_branch_id
            if (
                expected_execution_branch_id is not None
                and execution_branch_id != expected_execution_branch_id
            ):
                raise WorkflowConcurrencyError(
                    "Workflow active branch changed during append: "
                    + f"session_id={session_id!r}, "
                    + f"expected={expected_execution_branch_id!r}, got={execution_branch_id!r}"
                )
            if (
                expected_head_sequence is not None
                and instance.head_sequence != expected_head_sequence
            ):
                raise WorkflowConcurrencyError(
                    "Workflow head sequence changed during append: "
                    + f"session_id={session_id!r}, "
                    + f"expected={expected_head_sequence}, got={instance.head_sequence}"
                )

            prev_hash = instance.head_state_hash
            start_sequence = instance.head_sequence
            results: list[WorkflowAppendResult] = []
            for index, item in enumerate(transitions):
                sequence = start_sequence + index + 1
                state_hash = state_hashes[index]
                snapshot_id = snapshot_ids[index]
                _ = await WorkflowEvent.objects.create(
                    instance=WorkflowEvent(
                        event_id=event_ids[index],
                        company_id=company_id,
                        session_id=session_id,
                        execution_branch_id=execution_branch_id,
                        sequence=sequence,
                        event_type=item.event_type,
                        payload=workflow_event_payload_json(item.payload),
                        state_delta=cls._delta_json(item.state_delta),
                        prev_state_hash=prev_hash,
                        next_state_hash=state_hash,
                        causation_id=item.causation_id,
                        correlation_id=item.correlation_id,
                        created_at=now,
                    )
                )
                if snapshot_id is not None:
                    _ = await WorkflowSnapshot.objects.create(
                        instance=WorkflowSnapshot(
                            snapshot_id=snapshot_id,
                            company_id=company_id,
                            session_id=session_id,
                            execution_branch_id=execution_branch_id,
                            sequence=sequence,
                            state_json=item.state_json,
                            state_hash=state_hash,
                            created_at=now,
                        )
                    )
                results.append(
                    WorkflowAppendResult(
                        event_id=event_ids[index],
                        execution_branch_id=execution_branch_id,
                        sequence=sequence,
                        state_hash=state_hash,
                        snapshot_id=snapshot_id,
                    )
                )
                prev_hash = state_hash

            last = transitions[-1]
            last_snapshot_id = next(
                (
                    snapshot_id
                    for snapshot_id in reversed(snapshot_ids)
                    if snapshot_id is not None
                ),
                None,
            )
            instance.head_sequence = start_sequence + len(transitions)
            instance.head_state_hash = state_hashes[-1]
            if last_snapshot_id is not None:
                instance.latest_snapshot_id = last_snapshot_id
            instance.status = last.status
            instance.flow_id = cls._flow_id_from_session_id(session_id)
            instance.context_id = cls._context_id_from_state(last.state_json, session_id)
            instance.task_id = cls._string_or_none(last.state_json.get("task_id"))
            instance.user_id = cls._string_or_none(last.state_json.get("user_id"))
            instance.flow_branch_id = cls._string_or_none(last.state_json.get("branch_id"))
            instance.last_event_at = now
            instance.updated_at = now
            _ = await instance.save()


        return results

    @classmethod
    async def create_branch_transition(
        cls,
        *,
        company_id: str,
        session_id: str,
        source_execution_branch_id: str | None,
        source_sequence: int,
        reason: ExecutionBranchReason,
        event_type: WorkflowEventType,
        target_state: ExecutionState | None = None,
        activate: bool,
        status: WorkflowStatus = WorkflowStatus.running,
        retry_failed_sequence: int | None = None,
        retry_failed_nodes: list[str] | None = None,
    ) -> WorkflowBranchResult:
        """Create a branch anchored at a historical state and optionally activate it."""
        if source_sequence < 0:
            raise ValueError("source_sequence must be non-negative")

        instance = await cls.any_by_company_and_session(company_id=company_id, session_id=session_id)
        if instance is None:
            raise ValueError(f"Workflow instance not found: {session_id!r}")
        resolved_source_branch_id = source_execution_branch_id or instance.active_execution_branch_id

        base_state = await cls.load_state_at(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=resolved_source_branch_id,
            sequence=source_sequence,
        )
        if base_state is None:
            raise ValueError(
                "Cannot create branch from missing workflow state: "
                + f"session_id={session_id!r}, branch={resolved_source_branch_id!r}, "
                + f"sequence={source_sequence}"
            )
        base_state_json = cls._state_json(base_state)
        base_state_hash = hash_state_json(base_state_json)
        next_state = target_state or base_state
        next_state_json = cls._state_json(next_state)
        next_state_hash = hash_state_json(next_state_json)
        delta = build_state_delta(base_state, next_state)

        branch_id = str(uuid4())
        snapshot_id = str(uuid4())
        event_id = str(uuid4())
        event_sequence = source_sequence + 1
        source_events_after_base = 0
        if event_type == WorkflowEventType.retry_scheduled:
            if retry_failed_sequence is None or retry_failed_nodes is None:
                raise ValueError("Retry branch transition requires retry failure payload")
            event_payload: WorkflowEventPayload = RetryScheduledPayload(
                source_execution_branch_id=resolved_source_branch_id,
                source_sequence=source_sequence,
                reason=reason,
                failed_sequence=retry_failed_sequence,
                recover_sequence=source_sequence,
                failed_nodes=retry_failed_nodes,
            )
        else:
            event_payload = BranchTransitionPayload(
                source_execution_branch_id=resolved_source_branch_id,
                source_sequence=source_sequence,
                reason=reason,
            )

        async with atomic(using="flows"):
            locked_instance = await cls._locked_instance(company_id, session_id)
            if locked_instance is None:
                raise ValueError(f"Workflow instance not found: {session_id!r}")
            source_branch = await ExecutionBranch.objects.filter(
                company_id=company_id,
                session_id=session_id,
                execution_branch_id=resolved_source_branch_id,
            ).first()
            if source_branch is None:
                raise ValueError(
                    "Source execution branch not found: "
                    + f"{resolved_source_branch_id!r}"
                )
            source_events_after_base = await WorkflowEvent.objects.filter(
                company_id=company_id,
                session_id=session_id,
                execution_branch_id=resolved_source_branch_id,
                sequence__gt=source_sequence,
            ).count()
            now = utcnow()
            _ = await ExecutionBranch.objects.create(
                instance=ExecutionBranch(
                    execution_branch_id=branch_id,
                    company_id=company_id,
                    session_id=session_id,
                    parent_execution_branch_id=resolved_source_branch_id,
                    base_sequence=source_sequence,
                    base_state_hash=base_state_hash,
                    reason=reason,
                    created_at=now,
                )
            )
            _ = await WorkflowSnapshot.objects.create(
                instance=WorkflowSnapshot(
                    snapshot_id=snapshot_id,
                    company_id=company_id,
                    session_id=session_id,
                    execution_branch_id=branch_id,
                    sequence=source_sequence,
                    state_json=base_state_json,
                    state_hash=base_state_hash,
                    created_at=now,
                )
            )
            _ = await WorkflowEvent.objects.create(
                instance=WorkflowEvent(
                    event_id=event_id,
                    company_id=company_id,
                    session_id=session_id,
                    execution_branch_id=branch_id,
                    sequence=event_sequence,
                    event_type=event_type,
                    payload=workflow_event_payload_json(event_payload),
                    state_delta=cls._delta_json(delta),
                    prev_state_hash=base_state_hash,
                    next_state_hash=next_state_hash,
                    created_at=now,
                )
            )
            if activate:
                locked_instance.active_execution_branch_id = branch_id
                locked_instance.head_sequence = event_sequence
                locked_instance.head_state_hash = next_state_hash
                locked_instance.latest_snapshot_id = snapshot_id
                locked_instance.status = status
                locked_instance.flow_id = cls._flow_id_from_session_id(session_id)
                locked_instance.context_id = cls._context_id_from_state(
                    next_state_json,
                    session_id,
                )
                locked_instance.task_id = cls._string_or_none(next_state_json.get("task_id"))
                locked_instance.user_id = cls._string_or_none(next_state_json.get("user_id"))
                locked_instance.flow_branch_id = cls._string_or_none(
                    next_state_json.get("branch_id")
                )
                locked_instance.last_event_at = now
                locked_instance.updated_at = now
                _ = await locked_instance.save()

        instance_status = status if activate else instance.status
        return WorkflowBranchResult(
            execution_branch_id=branch_id,
            parent_execution_branch_id=resolved_source_branch_id,
            base_sequence=source_sequence,
            base_state_hash=base_state_hash,
            reason=reason,
            event_id=event_id,
            sequence=event_sequence,
            state_hash=next_state_hash,
            snapshot_id=snapshot_id,
            effect=TimeTravelEffect(
                activates_head=activate,
                source_execution_branch_id=resolved_source_branch_id,
                source_sequence=source_sequence,
                source_events_after_base=source_events_after_base,
                instance_status=instance_status,
                auto_resumes_run=False,
            ),
        )

    @classmethod
    async def load_state_at_head(
        cls,
        *,
        company_id: str,
        session_id: str,
    ) -> tuple[ExecutionState, WorkflowInstance] | None:
        instance = await cls.any_by_company_and_session(company_id=company_id, session_id=session_id)
        if instance is None:
            return None
        state = await cls.load_state_at(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=instance.active_execution_branch_id,
            sequence=instance.head_sequence,
        )
        if state is None:
            return None
        return state, instance

    @classmethod
    async def load_state_at(
        cls,
        *,
        company_id: str,
        session_id: str,
        execution_branch_id: str,
        sequence: int,
    ) -> ExecutionState | None:
        """Rehydrate state from latest snapshot plus events up to sequence."""
        snapshot = await WorkflowSnapshot.latest_at_or_before_sequence_desc(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=execution_branch_id,
            sequence=sequence,
        )
        state: ExecutionState | None = None
        start_sequence = 0
        if snapshot is not None:
            state = ExecutionState.model_validate(snapshot.state_json)
            start_sequence = snapshot.sequence
        events = await WorkflowEvent.list_after_through_sequence_asc(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=execution_branch_id,
            after_sequence=start_sequence,
            through_sequence=sequence,
        )
        for event in events:
            delta = ExecutionStateDelta.model_validate(event.state_delta)
            state = apply_state_delta(state, delta)
            state_hash = hash_state_json(
                cls._state_json(state)
            )
            if state_hash != event.next_state_hash:
                raise WorkflowProjectionMismatchError(
                    session_id=session_id,
                    expected_hash=event.next_state_hash,
                    computed_hash=state_hash,
                )
        return state

    @classmethod
    async def latest_session_id_by_flow_identifier_and_updated_at_desc(
        cls,
        *,
        company_id: str,
        flow_id: str,
        lookup_id: str,
    ) -> str | None:
        """session_id, не строка таблицы. Сначала прямая пара flow_id:lookup_id. Иначе последняя по updated_at DESC среди task_id или context_id. Нет строки — None."""
        direct_session_id = f"{flow_id}:{lookup_id}"
        direct = await cls.any_by_company_and_session(company_id=company_id, session_id=direct_session_id)
        if direct is not None:
            return direct_session_id

        resolved = await (
            WorkflowInstance.objects.filter(company_id=company_id, flow_id=flow_id)
            .filter(Q(task_id=lookup_id) | Q(context_id=lookup_id))
            .order_by("-updated_at")
            .first()
        )
        if resolved is None:
            return None
        return resolved.session_id

    @staticmethod
    def _state_json(state: ExecutionState) -> JsonObject:
        data = require_json_object(
            state.model_dump(mode="json", exclude_none=False),
            "ExecutionState",
        )
        _ = data.pop("flow_config", None)
        return data

    @staticmethod
    def _string_or_none(value: JsonValue) -> str | None:
        if isinstance(value, str) and value:
            return value
        return None

    @classmethod
    def _flow_id_from_session_id(cls, session_id: str) -> str | None:
        if ":" not in session_id:
            return None
        flow_id = session_id.split(":", 1)[0]
        return cls._string_or_none(flow_id)

    @classmethod
    def _context_id_from_state(cls, state_json: JsonObject, session_id: str) -> str | None:
        raw_context_id = state_json.get("context_id")
        if isinstance(raw_context_id, str) and raw_context_id:
            return raw_context_id
        if ":" not in session_id:
            return None
        context_id = session_id.split(":", 1)[1]
        return cls._string_or_none(context_id)
