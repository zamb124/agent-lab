"""PostgreSQL repository for flows durable execution ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import desc, or_, select, update
from sqlalchemy import func as sa_func
from sqlalchemy.dialects.postgresql import insert

from apps.flows.src.db.models import (
    ActivityAttempts,
    ActivityTasks,
    ExecutionBranches,
    WorkflowEvents,
    WorkflowInstances,
    WorkflowSnapshots,
    utc_now,
)
from apps.flows.src.durable_execution.hashing import hash_state_json
from apps.flows.src.durable_execution.models import (
    ActivityRecord,
    ActivityRescheduleResult,
    ActivityStatus,
    BranchTransitionPayload,
    ExecutionBranchReason,
    ExecutionStateDelta,
    RetryScheduledPayload,
    SideEffectPolicy,
    WorkflowAppendResult,
    WorkflowBranchRecord,
    WorkflowBranchResult,
    WorkflowEventPayload,
    WorkflowEventRecord,
    WorkflowEventType,
    WorkflowStatus,
    parse_workflow_event_payload,
    workflow_event_payload_json,
)
from apps.flows.src.durable_execution.state_delta import apply_state_delta, build_state_delta
from core.db.storage import Storage
from core.state import ExecutionState
from core.types import JsonObject, require_json_object


class WorkflowConcurrencyError(RuntimeError):
    """Raised when a workflow append races with a newer committed head."""


class NonIdempotentActivityReplayBlockedError(RuntimeError):
    """Raised when non-idempotent work would be repeated without an explicit command."""


ACTIVITY_LEASE_SECONDS = 900


@dataclass(frozen=True)
class WorkflowStateTransitionWrite:
    event_type: WorkflowEventType
    payload: WorkflowEventPayload
    state_delta: ExecutionStateDelta
    state_json: JsonObject
    status: WorkflowStatus
    snapshot: bool
    causation_id: str | None = None
    correlation_id: str | None = None


class DurableWorkflowRepository:
    """Repository for canonical workflow events and projection anchors."""

    def __init__(self, storage: Storage) -> None:
        self._storage: Storage = storage

    @staticmethod
    def _require_side_effect_policy(value: object) -> SideEffectPolicy:
        if type(value) is not SideEffectPolicy:
            raise TypeError("side_effect_policy must be SideEffectPolicy")
        return value

    @staticmethod
    def _attempt_id(activity_id: str, attempt: int) -> str:
        return f"{activity_id}:attempt:{attempt}"

    @staticmethod
    def _activity_record(
        task: ActivityTasks,
        attempt: ActivityAttempts,
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
            status=ActivityStatus(attempt.status),
            attempt=int(attempt.attempt),
            input_hash=task.input_hash,
            idempotency_key=task.idempotency_key,
            side_effect_policy=SideEffectPolicy(task.side_effect_policy),
            result_json=attempt.result_json,
            error=attempt.error,
            lease_until=attempt.lease_until,
            was_created=was_created,
        )

    @staticmethod
    def _workflow_event_record(row: WorkflowEvents) -> WorkflowEventRecord:
        event_type = WorkflowEventType(row.event_type)
        payload = parse_workflow_event_payload(
            event_type,
            require_json_object(row.payload, "WorkflowEvent.payload"),
        )
        return WorkflowEventRecord(
            event_id=row.event_id,
            session_id=row.session_id,
            execution_branch_id=row.execution_branch_id,
            sequence=int(row.sequence),
            event_type=event_type,
            payload=payload,
            state_delta=ExecutionStateDelta.model_validate(row.state_delta),
            prev_state_hash=row.prev_state_hash,
            next_state_hash=row.next_state_hash,
            created_at=row.created_at.isoformat(),
        )

    async def get_instance(
        self,
        *,
        company_id: str,
        session_id: str,
    ) -> WorkflowInstances | None:
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(WorkflowInstances).where(
                    WorkflowInstances.company_id == company_id,
                    WorkflowInstances.session_id == session_id,
                )
            )
            return result.scalar_one_or_none()

    async def list_instances(
        self,
        *,
        company_id: str,
        flow_id: str | None = None,
        user_id: str | None = None,
        flow_branch_id: str | None = None,
        updated_from: datetime | None = None,
        updated_to: datetime | None = None,
        limit: int | None = 50,
        offset: int = 0,
    ) -> tuple[list[WorkflowInstances], int]:
        filters = [WorkflowInstances.company_id == company_id]
        if flow_id:
            filters.append(WorkflowInstances.flow_id == flow_id)
        if user_id:
            filters.append(WorkflowInstances.user_id == user_id)
        if flow_branch_id:
            filters.append(WorkflowInstances.flow_branch_id == flow_branch_id)
        if updated_from is not None:
            filters.append(WorkflowInstances.updated_at >= updated_from)
        if updated_to is not None:
            filters.append(WorkflowInstances.updated_at <= updated_to)

        async with self._storage.get_session() as session:
            count_result = await session.execute(
                select(sa_func.count()).select_from(WorkflowInstances).where(*filters)
            )
            total = int(count_result.scalar_one())
            stmt = (
                select(WorkflowInstances)
                .where(*filters)
                .order_by(desc(WorkflowInstances.updated_at))
            )
            if limit is not None:
                stmt = stmt.limit(limit).offset(offset)
            rows_result = await session.execute(stmt)
            return list(rows_result.scalars().all()), total

    async def list_events(
        self,
        *,
        company_id: str,
        session_id: str,
        execution_branch_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[WorkflowEventRecord], int]:
        filters = [
            WorkflowEvents.company_id == company_id,
            WorkflowEvents.session_id == session_id,
        ]
        if execution_branch_id is not None:
            filters.append(WorkflowEvents.execution_branch_id == execution_branch_id)
        async with self._storage.get_session() as session:
            count_result = await session.execute(
                select(sa_func.count()).select_from(WorkflowEvents).where(*filters)
            )
            total = int(count_result.scalar_one())
            rows_result = await session.execute(
                select(WorkflowEvents)
                .where(*filters)
                .order_by(WorkflowEvents.sequence.asc())
                .limit(limit)
                .offset(offset)
            )
            rows = rows_result.scalars().all()
            return [self._workflow_event_record(row) for row in rows], total

    async def get_event_by_type(
        self,
        *,
        company_id: str,
        session_id: str,
        execution_branch_id: str,
        event_type: WorkflowEventType,
        sequence: int | None = None,
    ) -> WorkflowEventRecord | None:
        filters = [
            WorkflowEvents.company_id == company_id,
            WorkflowEvents.session_id == session_id,
            WorkflowEvents.execution_branch_id == execution_branch_id,
            WorkflowEvents.event_type == event_type.value,
        ]
        if sequence is not None:
            filters.append(WorkflowEvents.sequence == sequence)
            order_by = WorkflowEvents.sequence.asc()
        else:
            order_by = desc(WorkflowEvents.sequence)
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(WorkflowEvents)
                .where(*filters)
                .order_by(order_by)
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return self._workflow_event_record(row)

    async def list_branches(
        self,
        *,
        company_id: str,
        session_id: str,
    ) -> list[WorkflowBranchRecord]:
        instance = await self.get_instance(company_id=company_id, session_id=session_id)
        active_branch_id = instance.active_execution_branch_id if instance is not None else None
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(ExecutionBranches)
                .where(
                    ExecutionBranches.company_id == company_id,
                    ExecutionBranches.session_id == session_id,
                )
                .order_by(ExecutionBranches.created_at.asc())
            )
            rows = result.scalars().all()
            return [
                WorkflowBranchRecord(
                    execution_branch_id=row.execution_branch_id,
                    parent_execution_branch_id=row.parent_execution_branch_id,
                    base_sequence=int(row.base_sequence),
                    base_state_hash=row.base_state_hash,
                    reason=ExecutionBranchReason(row.reason),
                    created_at=row.created_at.isoformat(),
                    is_active=row.execution_branch_id == active_branch_id,
                )
                for row in rows
            ]

    async def append_state_transition(
        self,
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

        async with self._storage.get_session() as session:
            async with session.begin():
                result = await session.execute(
                    select(WorkflowInstances)
                    .where(
                        WorkflowInstances.company_id == company_id,
                        WorkflowInstances.session_id == session_id,
                    )
                    .with_for_update()
                )
                instance = result.scalar_one_or_none()

                now = utc_now()
                if instance is None:
                    if expected_head_sequence is not None or expected_execution_branch_id is not None:
                        raise WorkflowConcurrencyError(
                            f"Workflow {session_id!r} does not exist for expected append"
                        )
                    execution_branch_id = str(uuid4())
                    instance_id = str(uuid4())
                    branch = ExecutionBranches(
                        execution_branch_id=execution_branch_id,
                        company_id=company_id,
                        session_id=session_id,
                        parent_execution_branch_id=None,
                        base_sequence=0,
                        base_state_hash=None,
                        reason=ExecutionBranchReason.start.value,
                        created_at=now,
                    )
                    session.add(branch)
                    instance = WorkflowInstances(
                        workflow_instance_id=instance_id,
                        company_id=company_id,
                        session_id=session_id,
                        flow_id=self._flow_id_from_session_id(session_id),
                        context_id=self._context_id_from_state(state_json, session_id),
                        task_id=self._string_or_none(state_json.get("task_id")),
                        user_id=self._string_or_none(state_json.get("user_id")),
                        flow_branch_id=self._string_or_none(state_json.get("branch_id")),
                        active_execution_branch_id=execution_branch_id,
                        head_sequence=0,
                        head_state_hash=None,
                        latest_snapshot_id=None,
                        status=WorkflowStatus.running.value,
                        last_event_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(instance)
                    await session.flush()

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
                    and int(instance.head_sequence) != expected_head_sequence
                ):
                    raise WorkflowConcurrencyError(
                        "Workflow head sequence changed during append: "
                        + f"session_id={session_id!r}, "
                        + f"expected={expected_head_sequence}, got={instance.head_sequence}"
                    )
                prev_hash = instance.head_state_hash
                sequence = int(instance.head_sequence) + 1

                event = WorkflowEvents(
                    event_id=event_id,
                    company_id=company_id,
                    session_id=session_id,
                    execution_branch_id=execution_branch_id,
                    sequence=sequence,
                    event_type=event_type.value,
                    payload=workflow_event_payload_json(payload),
                    state_delta=state_delta.model_dump(mode="json", exclude_none=False),
                    prev_state_hash=prev_hash,
                    next_state_hash=state_hash,
                    causation_id=causation_id,
                    correlation_id=correlation_id,
                    schema_version=1,
                    created_at=now,
                )
                session.add(event)

                if snapshot_id is not None:
                    snapshot_row = WorkflowSnapshots(
                        snapshot_id=snapshot_id,
                        company_id=company_id,
                        session_id=session_id,
                        execution_branch_id=execution_branch_id,
                        sequence=sequence,
                        state_json=state_json,
                        state_hash=state_hash,
                        schema_version=1,
                        created_at=now,
                    )
                    session.add(snapshot_row)

                instance.head_sequence = sequence
                instance.head_state_hash = state_hash
                instance.latest_snapshot_id = snapshot_id or instance.latest_snapshot_id
                instance.status = status.value
                instance.flow_id = self._flow_id_from_session_id(session_id)
                instance.context_id = self._context_id_from_state(state_json, session_id)
                instance.task_id = self._string_or_none(state_json.get("task_id"))
                instance.user_id = self._string_or_none(state_json.get("user_id"))
                instance.flow_branch_id = self._string_or_none(state_json.get("branch_id"))
                instance.last_event_at = now
                instance.updated_at = now

        return WorkflowAppendResult(
            event_id=event_id,
            execution_branch_id=execution_branch_id,
            sequence=sequence,
            state_hash=state_hash,
            snapshot_id=snapshot_id,
        )

    async def append_state_transitions(
        self,
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

        async with self._storage.get_session() as session:
            async with session.begin():
                result = await session.execute(
                    select(WorkflowInstances)
                    .where(
                        WorkflowInstances.company_id == company_id,
                        WorkflowInstances.session_id == session_id,
                    )
                    .with_for_update()
                )
                instance = result.scalar_one_or_none()

                now = utc_now()
                if instance is None:
                    if expected_head_sequence is not None or expected_execution_branch_id is not None:
                        raise WorkflowConcurrencyError(
                            f"Workflow {session_id!r} does not exist for expected append"
                        )
                    execution_branch_id = str(uuid4())
                    instance_id = str(uuid4())
                    first_state_json = transitions[0].state_json
                    branch = ExecutionBranches(
                        execution_branch_id=execution_branch_id,
                        company_id=company_id,
                        session_id=session_id,
                        parent_execution_branch_id=None,
                        base_sequence=0,
                        base_state_hash=None,
                        reason=ExecutionBranchReason.start.value,
                        created_at=now,
                    )
                    session.add(branch)
                    instance = WorkflowInstances(
                        workflow_instance_id=instance_id,
                        company_id=company_id,
                        session_id=session_id,
                        flow_id=self._flow_id_from_session_id(session_id),
                        context_id=self._context_id_from_state(first_state_json, session_id),
                        task_id=self._string_or_none(first_state_json.get("task_id")),
                        user_id=self._string_or_none(first_state_json.get("user_id")),
                        flow_branch_id=self._string_or_none(first_state_json.get("branch_id")),
                        active_execution_branch_id=execution_branch_id,
                        head_sequence=0,
                        head_state_hash=None,
                        latest_snapshot_id=None,
                        status=WorkflowStatus.running.value,
                        last_event_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(instance)
                    await session.flush()

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
                    and int(instance.head_sequence) != expected_head_sequence
                ):
                    raise WorkflowConcurrencyError(
                        "Workflow head sequence changed during append: "
                        + f"session_id={session_id!r}, "
                        + f"expected={expected_head_sequence}, got={instance.head_sequence}"
                    )

                prev_hash = instance.head_state_hash
                start_sequence = int(instance.head_sequence)
                event_rows: list[dict[str, object | None]] = []
                snapshot_rows: list[dict[str, object | None]] = []
                results: list[WorkflowAppendResult] = []

                for index, item in enumerate(transitions):
                    sequence = start_sequence + index + 1
                    state_hash = state_hashes[index]
                    snapshot_id = snapshot_ids[index]
                    event_rows.append(
                        {
                            "event_id": event_ids[index],
                            "company_id": company_id,
                            "session_id": session_id,
                            "execution_branch_id": execution_branch_id,
                            "sequence": sequence,
                            "event_type": item.event_type.value,
                            "payload": workflow_event_payload_json(item.payload),
                            "state_delta": item.state_delta.model_dump(
                                mode="json",
                                exclude_none=False,
                            ),
                            "prev_state_hash": prev_hash,
                            "next_state_hash": state_hash,
                            "causation_id": item.causation_id,
                            "correlation_id": item.correlation_id,
                            "schema_version": 1,
                            "created_at": now,
                        }
                    )
                    if snapshot_id is not None:
                        snapshot_rows.append(
                            {
                                "snapshot_id": snapshot_id,
                                "company_id": company_id,
                                "session_id": session_id,
                                "execution_branch_id": execution_branch_id,
                                "sequence": sequence,
                                "state_json": item.state_json,
                                "state_hash": state_hash,
                                "schema_version": 1,
                                "created_at": now,
                            }
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

                if event_rows:
                    _ = await session.execute(insert(WorkflowEvents).values(event_rows))
                if snapshot_rows:
                    _ = await session.execute(insert(WorkflowSnapshots).values(snapshot_rows))

                last = transitions[-1]
                last_sequence = start_sequence + len(transitions)
                last_snapshot_id = next(
                    (snapshot_id for snapshot_id in reversed(snapshot_ids) if snapshot_id is not None),
                    None,
                )
                instance.head_sequence = last_sequence
                instance.head_state_hash = state_hashes[-1]
                instance.latest_snapshot_id = last_snapshot_id or instance.latest_snapshot_id
                instance.status = last.status.value
                instance.flow_id = self._flow_id_from_session_id(session_id)
                instance.context_id = self._context_id_from_state(last.state_json, session_id)
                instance.task_id = self._string_or_none(last.state_json.get("task_id"))
                instance.user_id = self._string_or_none(last.state_json.get("user_id"))
                instance.flow_branch_id = self._string_or_none(last.state_json.get("branch_id"))
                instance.last_event_at = now
                instance.updated_at = now

        return results

    async def create_branch_transition(
        self,
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

        instance = await self.get_instance(company_id=company_id, session_id=session_id)
        if instance is None:
            raise ValueError(f"Workflow instance not found: {session_id!r}")
        resolved_source_branch_id = source_execution_branch_id or instance.active_execution_branch_id

        base_state = await self.load_state_at(
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
        base_state_json = self._state_json(base_state)
        base_state_hash = hash_state_json(base_state_json)
        next_state = target_state or base_state
        next_state_json = self._state_json(next_state)
        next_state_hash = hash_state_json(next_state_json)
        delta = build_state_delta(base_state, next_state)

        branch_id = str(uuid4())
        snapshot_id = str(uuid4())
        event_id = str(uuid4())
        event_sequence = source_sequence + 1
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

        async with self._storage.get_session() as session:
            async with session.begin():
                locked_result = await session.execute(
                    select(WorkflowInstances)
                    .where(
                        WorkflowInstances.company_id == company_id,
                        WorkflowInstances.session_id == session_id,
                    )
                    .with_for_update()
                )
                locked_instance = locked_result.scalar_one_or_none()
                if locked_instance is None:
                    raise ValueError(f"Workflow instance not found: {session_id!r}")

                branch_result = await session.execute(
                    select(ExecutionBranches).where(
                        ExecutionBranches.company_id == company_id,
                        ExecutionBranches.session_id == session_id,
                        ExecutionBranches.execution_branch_id == resolved_source_branch_id,
                    )
                )
                source_branch = branch_result.scalar_one_or_none()
                if source_branch is None:
                    raise ValueError(
                        "Source execution branch not found: "
                        + f"{resolved_source_branch_id!r}"
                    )

                now = utc_now()
                session.add(
                    ExecutionBranches(
                        execution_branch_id=branch_id,
                        company_id=company_id,
                        session_id=session_id,
                        parent_execution_branch_id=resolved_source_branch_id,
                        base_sequence=source_sequence,
                        base_state_hash=base_state_hash,
                        reason=reason.value,
                        created_at=now,
                    )
                )
                session.add(
                    WorkflowSnapshots(
                        snapshot_id=snapshot_id,
                        company_id=company_id,
                        session_id=session_id,
                        execution_branch_id=branch_id,
                        sequence=source_sequence,
                        state_json=base_state_json,
                        state_hash=base_state_hash,
                        schema_version=1,
                        created_at=now,
                    )
                )
                session.add(
                    WorkflowEvents(
                        event_id=event_id,
                        company_id=company_id,
                        session_id=session_id,
                        execution_branch_id=branch_id,
                        sequence=event_sequence,
                        event_type=event_type.value,
                        payload=workflow_event_payload_json(event_payload),
                        state_delta=delta.model_dump(mode="json", exclude_none=False),
                        prev_state_hash=base_state_hash,
                        next_state_hash=next_state_hash,
                        causation_id=None,
                        correlation_id=None,
                        schema_version=1,
                        created_at=now,
                    )
                )

                if activate:
                    locked_instance.active_execution_branch_id = branch_id
                    locked_instance.head_sequence = event_sequence
                    locked_instance.head_state_hash = next_state_hash
                    locked_instance.latest_snapshot_id = snapshot_id
                    locked_instance.status = status.value
                    locked_instance.flow_id = self._flow_id_from_session_id(session_id)
                    locked_instance.context_id = self._context_id_from_state(
                        next_state_json,
                        session_id,
                    )
                    locked_instance.task_id = self._string_or_none(next_state_json.get("task_id"))
                    locked_instance.user_id = self._string_or_none(next_state_json.get("user_id"))
                    locked_instance.flow_branch_id = self._string_or_none(
                        next_state_json.get("branch_id")
                    )
                    locked_instance.last_event_at = now
                    locked_instance.updated_at = now

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
        )

    async def load_state_at_head(
        self,
        *,
        company_id: str,
        session_id: str,
    ) -> tuple[ExecutionState, WorkflowInstances] | None:
        instance = await self.get_instance(company_id=company_id, session_id=session_id)
        if instance is None:
            return None
        state = await self.load_state_at(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=instance.active_execution_branch_id,
            sequence=int(instance.head_sequence),
        )
        if state is None:
            return None
        return state, instance

    async def load_state_at(
        self,
        *,
        company_id: str,
        session_id: str,
        execution_branch_id: str,
        sequence: int,
    ) -> ExecutionState | None:
        """Rehydrate state from latest snapshot plus events up to sequence."""
        async with self._storage.get_session() as session:
            snapshot_result = await session.execute(
                select(WorkflowSnapshots)
                .where(
                    WorkflowSnapshots.company_id == company_id,
                    WorkflowSnapshots.session_id == session_id,
                    WorkflowSnapshots.execution_branch_id == execution_branch_id,
                    WorkflowSnapshots.sequence <= sequence,
                )
                .order_by(desc(WorkflowSnapshots.sequence))
                .limit(1)
            )
            snapshot = snapshot_result.scalar_one_or_none()

            state: ExecutionState | None = None
            start_sequence = 0
            if snapshot is not None:
                state = ExecutionState.model_validate(snapshot.state_json)
                start_sequence = int(snapshot.sequence)

            events_result = await session.execute(
                select(WorkflowEvents)
                .where(
                    WorkflowEvents.company_id == company_id,
                    WorkflowEvents.session_id == session_id,
                    WorkflowEvents.execution_branch_id == execution_branch_id,
                    WorkflowEvents.sequence > start_sequence,
                    WorkflowEvents.sequence <= sequence,
                )
                .order_by(WorkflowEvents.sequence.asc())
            )
            events = list(events_result.scalars().all())

        for event in events:
            delta = ExecutionStateDelta.model_validate(event.state_delta)
            state = apply_state_delta(state, delta)
            state_hash = hash_state_json(
                self._state_json(state)
            )
            if state_hash != event.next_state_hash:
                raise ValueError(
                    "Workflow event hash mismatch: "
                    + f"session_id={session_id!r}, sequence={event.sequence}, "
                    + f"expected={event.next_state_hash}, got={state_hash}"
                )
        return state

    async def cache_activity(
        self,
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
        resolved_side_effect_policy = self._require_side_effect_policy(side_effect_policy)
        now = utc_now()
        async with self._storage.get_session() as session:
            stmt = (
                insert(ActivityTasks)
                .values(
                    activity_id=activity_id,
                    company_id=company_id,
                    session_id=session_id,
                    execution_branch_id=execution_branch_id,
                    node_id=node_id,
                    tool_call_id=tool_call_id,
                    activity_type=activity_type,
                    input_hash=input_hash,
                    idempotency_key=idempotency_key,
                    side_effect_policy=resolved_side_effect_policy.value,
                    created_at=now,
                )
                .on_conflict_do_nothing()
                .returning(ActivityTasks)
            )
            inserted_result = await session.execute(stmt)
            inserted_row = inserted_result.scalar_one_or_none()
            inserted_attempt_row: ActivityAttempts | None = None
            if inserted_row is not None:
                attempt_stmt = (
                    insert(ActivityAttempts)
                    .values(
                        activity_attempt_id=self._attempt_id(activity_id, 1),
                        activity_id=activity_id,
                        company_id=company_id,
                        session_id=session_id,
                        execution_branch_id=execution_branch_id,
                        attempt=1,
                        status=ActivityStatus.scheduled.value,
                        scheduled_at=now,
                    )
                    .returning(ActivityAttempts)
                )
                attempt_result = await session.execute(attempt_stmt)
                inserted_attempt_row = attempt_result.scalar_one()
            await session.commit()
            if inserted_row is not None and inserted_attempt_row is not None:
                return self._activity_record(
                    inserted_row,
                    inserted_attempt_row,
                    was_created=True,
                )
        record = await self.get_activity(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=execution_branch_id,
            activity_id=activity_id,
            idempotency_key=idempotency_key,
        )
        if record is None:
            raise RuntimeError(f"Activity was not persisted: {activity_id!r}")
        if record.input_hash != input_hash:
            raise ValueError(
                "Activity idempotency collision with different input: "
                + f"activity_id={activity_id!r}, idempotency_key={idempotency_key!r}"
            )
        return record

    async def get_activity(
        self,
        *,
        company_id: str,
        session_id: str,
        execution_branch_id: str,
        activity_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ActivityRecord | None:
        if activity_id is None and idempotency_key is None:
            raise ValueError("activity_id or idempotency_key is required")
        filters = [
            ActivityTasks.company_id == company_id,
            ActivityTasks.session_id == session_id,
            ActivityTasks.execution_branch_id == execution_branch_id,
        ]
        if idempotency_key is not None:
            filters.append(ActivityTasks.idempotency_key == idempotency_key)
        elif activity_id is not None:
            filters.append(ActivityTasks.activity_id == activity_id)
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(ActivityTasks)
                .where(*filters)
                .limit(1)
            )
            task = result.scalar_one_or_none()
            if task is None:
                return None
            attempt_result = await session.execute(
                select(ActivityAttempts)
                .where(ActivityAttempts.activity_id == task.activity_id)
                .order_by(desc(ActivityAttempts.attempt))
                .limit(1)
            )
            attempt = attempt_result.scalar_one_or_none()
            if attempt is None:
                raise RuntimeError(f"Activity has no attempts: {task.activity_id!r}")
            return self._activity_record(task, attempt)

    async def get_completed_activity_result(
        self,
        *,
        company_id: str,
        session_id: str,
        execution_branch_id: str,
        activity_id: str | None = None,
        idempotency_key: str | None = None,
        input_hash: str,
    ) -> JsonObject | None:
        record = await self.get_activity(
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

    async def complete_activity(
        self,
        *,
        activity_id: str,
        result_json: JsonObject | None = None,
        error: str | None = None,
    ) -> ActivityRecord | None:
        status = ActivityStatus.failed.value if error else ActivityStatus.completed.value
        now = utc_now()
        async with self._storage.get_session() as session:
            task_result = await session.execute(
                select(ActivityTasks).where(ActivityTasks.activity_id == activity_id)
            )
            task = task_result.scalar_one_or_none()
            if task is None:
                return None
            latest_result = await session.execute(
                select(ActivityAttempts)
                .where(ActivityAttempts.activity_id == activity_id)
                .order_by(desc(ActivityAttempts.attempt))
                .limit(1)
            )
            latest = latest_result.scalar_one_or_none()
            if latest is None or latest.status != ActivityStatus.started.value:
                return None
            result = await session.execute(
                update(ActivityAttempts)
                .where(ActivityAttempts.activity_attempt_id == latest.activity_attempt_id)
                .where(ActivityAttempts.status == ActivityStatus.started.value)
                .values(
                    status=status,
                    result_json=result_json,
                    error=error,
                    completed_at=now,
                    lease_until=None,
                )
                .returning(ActivityAttempts)
            )
            await session.commit()
            attempt = result.scalar_one_or_none()
            if attempt is None:
                return None
            return self._activity_record(task, attempt)

    async def start_activity(
        self,
        *,
        activity_id: str,
    ) -> ActivityRecord | None:
        now = utc_now()
        lease_until = now + timedelta(seconds=ACTIVITY_LEASE_SECONDS)
        async with self._storage.get_session() as session:
            task_result = await session.execute(
                select(ActivityTasks).where(ActivityTasks.activity_id == activity_id)
            )
            task = task_result.scalar_one_or_none()
            if task is None:
                return None
            latest_result = await session.execute(
                select(ActivityAttempts)
                .where(ActivityAttempts.activity_id == activity_id)
                .order_by(desc(ActivityAttempts.attempt))
                .limit(1)
            )
            latest = latest_result.scalar_one_or_none()
            if latest is None or latest.status != ActivityStatus.scheduled.value:
                return None
            result = await session.execute(
                update(ActivityAttempts)
                .where(ActivityAttempts.activity_attempt_id == latest.activity_attempt_id)
                .where(ActivityAttempts.status == ActivityStatus.scheduled.value)
                .values(
                    status=ActivityStatus.started.value,
                    lease_until=lease_until,
                    started_at=now,
                )
                .returning(ActivityAttempts)
            )
            await session.commit()
            attempt = result.scalar_one_or_none()
            if attempt is None:
                return None
            return self._activity_record(task, attempt)

    async def reschedule_activity_attempt(
        self,
        *,
        activity_id: str,
    ) -> ActivityRescheduleResult | None:
        now = utc_now()
        async with self._storage.get_session() as session:
            task_result = await session.execute(
                select(ActivityTasks).where(ActivityTasks.activity_id == activity_id)
            )
            task = task_result.scalar_one_or_none()
            if task is None or task.side_effect_policy == SideEffectPolicy.non_idempotent.value:
                return None
            latest_result = await session.execute(
                select(ActivityAttempts)
                .where(ActivityAttempts.activity_id == activity_id)
                .order_by(desc(ActivityAttempts.attempt))
                .limit(1)
            )
            latest = latest_result.scalar_one_or_none()
            if latest is None:
                return None
            can_reschedule_failed = latest.status == ActivityStatus.failed.value
            can_reschedule_expired_started = (
                latest.status == ActivityStatus.started.value
                and latest.lease_until is not None
                and latest.lease_until <= now
            )
            if not can_reschedule_failed and not can_reschedule_expired_started:
                return None
            expired_attempt_row: ActivityAttempts | None = None
            if can_reschedule_expired_started:
                expired_result = await session.execute(
                    update(ActivityAttempts)
                    .where(ActivityAttempts.activity_attempt_id == latest.activity_attempt_id)
                    .where(ActivityAttempts.status == ActivityStatus.started.value)
                    .where(ActivityAttempts.lease_until <= now)
                    .values(
                        status=ActivityStatus.failed.value,
                        error="activity lease expired",
                        completed_at=now,
                        lease_until=None,
                    )
                    .returning(ActivityAttempts)
                )
                expired_attempt_row = expired_result.scalar_one_or_none()
                if expired_attempt_row is None:
                    return None
            next_attempt = int(latest.attempt) + 1
            result = await session.execute(
                insert(ActivityAttempts)
                .values(
                    activity_attempt_id=self._attempt_id(activity_id, next_attempt),
                    activity_id=activity_id,
                    company_id=task.company_id,
                    session_id=task.session_id,
                    execution_branch_id=task.execution_branch_id,
                    attempt=next_attempt,
                    status=ActivityStatus.scheduled.value,
                    scheduled_at=now,
                )
                .returning(ActivityAttempts)
            )
            await session.commit()
            attempt = result.scalar_one_or_none()
            if attempt is None:
                return None
            return ActivityRescheduleResult(
                expired_attempt=(
                    self._activity_record(task, expired_attempt_row)
                    if expired_attempt_row is not None
                    else None
                ),
                scheduled_attempt=self._activity_record(task, attempt),
            )

    async def resolve_session_id_by_flow_and_identifier(
        self,
        *,
        company_id: str,
        flow_id: str,
        lookup_id: str,
    ) -> str | None:
        direct_session_id = f"{flow_id}:{lookup_id}"
        direct = await self.get_instance(company_id=company_id, session_id=direct_session_id)
        if direct is not None:
            return direct_session_id

        async with self._storage.get_session() as session:
            result = await session.execute(
                select(WorkflowInstances.session_id)
                .where(
                    WorkflowInstances.company_id == company_id,
                    WorkflowInstances.flow_id == flow_id,
                    or_(
                        WorkflowInstances.task_id == lookup_id,
                        WorkflowInstances.context_id == lookup_id,
                    ),
                )
                .order_by(desc(WorkflowInstances.updated_at))
                .limit(1)
            )
            resolved = result.scalar_one_or_none()
            if resolved is not None:
                return str(resolved)
        return None

    @staticmethod
    def _state_json(state: ExecutionState) -> JsonObject:
        data = require_json_object(
            state.model_dump(mode="json", exclude_none=False),
            "ExecutionState",
        )
        _ = data.pop("flow_config", None)
        return data

    @staticmethod
    def _string_or_none(value: object) -> str | None:
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
