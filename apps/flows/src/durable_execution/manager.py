"""Runtime-фасад для проекции состояния durable workflow."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from a2a.types import Message, TextPart

from apps.flows.src.durable_execution.hashing import hash_state_json
from apps.flows.src.durable_execution.models import (
    ActivityLifecyclePayload,
    ActivityRecord,
    ActivityStatus,
    EmptyWorkflowEventPayload,
    ExecutionBranchReason,
    ExecutionStateDelta,
    NodeFailedPayload,
    RunTerminalPayload,
    SideEffectPolicy,
    WorkflowAppendResult,
    WorkflowBranchRecord,
    WorkflowBranchResult,
    WorkflowEventPayload,
    WorkflowEventRecord,
    WorkflowEventType,
    WorkflowExecutionPosition,
    WorkflowStatus,
)
from apps.flows.src.durable_execution.repository import (
    DurableWorkflowRepository,
    NonIdempotentActivityReplayBlockedError,
    WorkflowConcurrencyError,
    WorkflowStateTransitionWrite,
)
from apps.flows.src.durable_execution.state_delta import apply_state_delta, build_state_delta
from apps.flows.src.models import SessionConfig
from apps.flows.src.models.enums import SessionStatus
from core.clients.redis_client import RedisClient
from core.context import get_context
from core.state import TERMINAL_TASK_STATES, ExecutionState, ExecutionTaskState
from core.types import JsonObject, parse_json_object, require_json_object


def create_initial_state(
    task_id: str,
    context_id: str,
    user_id: str,
    session_id: str,
    content: str | None = None,
    branch_id: str = "default",
) -> ExecutionState:
    """Создаёт новую проекцию ExecutionState для сессии workflow."""
    return ExecutionState(
        task_id=task_id,
        context_id=context_id,
        user_id=user_id,
        session_id=session_id,
        content=content,
        branch_id=branch_id,
    )


@dataclass(frozen=True)
class WorkflowStateEventSpec:
    state: ExecutionState | JsonObject
    event_type: WorkflowEventType
    payload: WorkflowEventPayload | None = None
    snapshot: bool = False


@dataclass(frozen=True)
class _CachedWorkflowHead:
    state: ExecutionState
    head_sequence: int
    head_state_hash: str
    execution_branch_id: str
    status: WorkflowStatus


class DurableWorkflowRuntime:
    """Runtime проекции состояния на append-only workflow events."""

    def __init__(
        self,
        *,
        repository: DurableWorkflowRepository,
        redis_client: RedisClient,
    ) -> None:
        self._repository: DurableWorkflowRepository = repository
        self._redis: RedisClient = redis_client

    def _company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("DurableWorkflowRuntime requires active company context")
        return context.active_company.company_id

    def _cache_key(self, company_id: str, session_id: str) -> str:
        return f"flows:workflow_projection:{company_id}:{session_id}"

    async def _get_cached_head(
        self,
        *,
        company_id: str,
        session_id: str,
    ) -> _CachedWorkflowHead | None:
        raw = await self._redis.get(self._cache_key(company_id, session_id))
        if not raw:
            return None
        payload = parse_json_object(raw, "workflow_projection_cache")
        head_sequence_raw = payload.get("head_sequence")
        head_state_hash = payload.get("head_state_hash")
        execution_branch_id = payload.get("execution_branch_id")
        status_raw = payload.get("status")
        if (
            not isinstance(head_sequence_raw, int)
            or not isinstance(head_state_hash, str)
            or not isinstance(execution_branch_id, str)
        ):
            return None
        if isinstance(status_raw, str):
            try:
                status = self._workflow_status_from_value(status_raw)
            except ValueError:
                return None
        else:
            status = WorkflowStatus.running
        state_json = require_json_object(payload.get("state_json"), "cached_state")
        return _CachedWorkflowHead(
            state=ExecutionState.model_validate(state_json),
            head_sequence=head_sequence_raw,
            head_state_hash=head_state_hash,
            execution_branch_id=execution_branch_id,
            status=status,
        )

    async def _load_head_for_append(
        self,
        *,
        company_id: str,
        session_id: str,
    ) -> tuple[ExecutionState | None, int | None, str | None, WorkflowStatus | None]:
        cached = await self._get_cached_head(company_id=company_id, session_id=session_id)
        if cached is not None:
            return (
                cached.state,
                cached.head_sequence,
                cached.execution_branch_id,
                cached.status,
            )
        loaded = await self._repository.load_state_at_head(
            company_id=company_id,
            session_id=session_id,
        )
        if loaded is None:
            return None, None, None, None
        state, instance = loaded
        return (
            state,
            int(instance.head_sequence),
            instance.active_execution_branch_id,
            self._workflow_status_from_value(instance.status),
        )

    @staticmethod
    def _require_side_effect_policy(value: object) -> SideEffectPolicy:
        if type(value) is not SideEffectPolicy:
            raise TypeError("side_effect_policy must be SideEffectPolicy")
        return value

    @staticmethod
    def _dump_state(state: ExecutionState) -> JsonObject:
        payload = state.model_dump(mode="json", exclude_none=False)
        payload.pop("flow_config", None)
        return require_json_object(payload, "ExecutionState")

    async def get_state(self, session_id: str) -> ExecutionState | None:
        company_id = self._company_id()
        cached = await self._get_cached_head(company_id=company_id, session_id=session_id)
        if cached is not None:
            return cached.state

        instance = await self._repository.get_instance(
            company_id=company_id,
            session_id=session_id,
        )
        if instance is None:
            return None

        cache_key = self._cache_key(company_id, session_id)
        raw = await self._redis.get(cache_key)
        if raw:
            payload = parse_json_object(raw, "workflow_projection_cache")
            if (
                payload.get("head_sequence") == instance.head_sequence
                and payload.get("head_state_hash") == instance.head_state_hash
            ):
                data = require_json_object(payload.get("state_json"), "cached_state")
                return ExecutionState.model_validate(data)

        loaded = await self._repository.load_state_at_head(
            company_id=company_id,
            session_id=session_id,
        )
        if loaded is None:
            return None
        state, refreshed_instance = loaded
        head_state_hash = refreshed_instance.head_state_hash
        if head_state_hash is None:
            raise RuntimeError(f"Workflow instance has no head_state_hash: {session_id!r}")
        await self._cache_projection(
            company_id=company_id,
            session_id=session_id,
            state=state,
            head_sequence=int(refreshed_instance.head_sequence),
            head_state_hash=head_state_hash,
            execution_branch_id=refreshed_instance.active_execution_branch_id,
            status=self._workflow_status_from_value(refreshed_instance.status),
        )
        return state

    async def get_active_execution_position(
        self, session_id: str
    ) -> WorkflowExecutionPosition | None:
        """Возвращает метаданные активной ветки/head для durable command keys."""
        company_id = self._company_id()
        cached = await self._get_cached_head(company_id=company_id, session_id=session_id)
        if cached is not None:
            return WorkflowExecutionPosition(
                execution_branch_id=cached.execution_branch_id,
                head_sequence=cached.head_sequence,
                head_state_hash=cached.head_state_hash,
            )
        instance = await self._repository.get_instance(
            company_id=company_id,
            session_id=session_id,
        )
        if instance is None:
            return None
        return WorkflowExecutionPosition(
            execution_branch_id=instance.active_execution_branch_id,
            head_sequence=int(instance.head_sequence),
            head_state_hash=instance.head_state_hash,
        )

    async def record_lifecycle_event(
        self,
        session_id: str,
        *,
        event_type: WorkflowEventType,
        payload: WorkflowEventPayload,
    ) -> WorkflowAppendResult:
        """
        Добавляет факт lifecycle workflow без изменения текущей проекции.

        Используется для command/history-событий, например lifecycle дочернего workflow.
        Событие продвигает durable sequence, но state_delta остаётся пустым.
        """
        company_id = self._company_id()
        for attempt_index in range(5):
            state, expected_head_sequence, expected_execution_branch_id, status = (
                await self._load_head_for_append(
                    company_id=company_id,
                    session_id=session_id,
                )
            )
            if state is None or expected_head_sequence is None or status is None:
                raise ValueError(f"Workflow instance not found: {session_id!r}")
            state_json = self._dump_state(state)
            try:
                result = await self._repository.append_state_transition(
                    company_id=company_id,
                    session_id=session_id,
                    event_type=event_type,
                    payload=payload,
                    state_delta=build_state_delta(state, state),
                    state_json=state_json,
                    status=status,
                    snapshot=False,
                    expected_head_sequence=expected_head_sequence,
                    expected_execution_branch_id=expected_execution_branch_id,
                )
            except WorkflowConcurrencyError:
                if attempt_index == 4:
                    raise
                continue
            await self._cache_projection(
                company_id=company_id,
                session_id=session_id,
                state=state,
                head_sequence=result.sequence,
                head_state_hash=result.state_hash,
                execution_branch_id=result.execution_branch_id,
                status=status,
            )
            return result
        raise WorkflowConcurrencyError(
            f"Failed to append lifecycle event for workflow {session_id!r}"
        )

    async def save_state(
        self,
        session_id: str,
        state: ExecutionState | JsonObject,
        *,
        event_type: WorkflowEventType = WorkflowEventType.state_projection_committed,
        payload: WorkflowEventPayload | None = None,
        snapshot: bool = False,
    ) -> bool:
        _ = await self.record_state_event(
            session_id,
            state,
            event_type=event_type,
            payload=payload,
            snapshot=snapshot,
        )
        return True

    async def record_state_event(
        self,
        session_id: str,
        state: ExecutionState | JsonObject,
        *,
        event_type: WorkflowEventType,
        payload: WorkflowEventPayload | None = None,
        snapshot: bool = False,
    ) -> WorkflowAppendResult:
        st = ExecutionState.model_validate(state) if isinstance(state, dict) else state
        company_id = self._company_id()
        before, expected_head_sequence, expected_execution_branch_id, _status = (
            await self._load_head_for_append(
                company_id=company_id,
                session_id=session_id,
            )
        )
        state_json = self._dump_state(st)
        delta = build_state_delta(before, st)
        result = await self._repository.append_state_transition(
            company_id=company_id,
            session_id=session_id,
            event_type=event_type,
            payload=self._resolve_event_payload(event_type, payload),
            state_delta=delta,
            state_json=state_json,
            status=WorkflowStatus.running,
            snapshot=self._should_snapshot(
                requested=snapshot,
                event_type=event_type,
                delta=delta,
                expected_head_sequence=expected_head_sequence,
            ),
            expected_head_sequence=expected_head_sequence,
            expected_execution_branch_id=expected_execution_branch_id,
        )
        await self._cache_projection(
            company_id=company_id,
            session_id=session_id,
            state=st,
            head_sequence=result.sequence,
            head_state_hash=result.state_hash,
            execution_branch_id=result.execution_branch_id,
            status=WorkflowStatus.running,
        )
        return result

    async def record_state_events(
        self,
        session_id: str,
        events: Sequence[WorkflowStateEventSpec],
    ) -> list[WorkflowAppendResult]:
        if not events:
            return []

        states = [
            ExecutionState.model_validate(event.state)
            if isinstance(event.state, dict)
            else event.state
            for event in events
        ]
        company_id = self._company_id()
        before, expected_head_sequence, expected_execution_branch_id, _status = (
            await self._load_head_for_append(
                company_id=company_id,
                session_id=session_id,
            )
        )

        transitions: list[WorkflowStateTransitionWrite] = []
        snapshot_head_sequence = expected_head_sequence
        previous = before
        for event, state in zip(events, states, strict=True):
            state_json = self._dump_state(state)
            delta = build_state_delta(previous, state)
            transitions.append(
                WorkflowStateTransitionWrite(
                    event_type=event.event_type,
                    payload=self._resolve_event_payload(event.event_type, event.payload),
                    state_delta=delta,
                    state_json=state_json,
                    status=WorkflowStatus.running,
                    snapshot=self._should_snapshot(
                        requested=event.snapshot,
                        event_type=event.event_type,
                        delta=delta,
                        expected_head_sequence=snapshot_head_sequence,
                    ),
                )
            )
            previous = state
            snapshot_head_sequence = (
                1 if snapshot_head_sequence is None else snapshot_head_sequence + 1
            )

        results = await self._repository.append_state_transitions(
            company_id=company_id,
            session_id=session_id,
            transitions=transitions,
            expected_head_sequence=expected_head_sequence,
            expected_execution_branch_id=expected_execution_branch_id,
        )
        last_state = states[-1]
        last_result = results[-1]
        await self._cache_projection(
            company_id=company_id,
            session_id=session_id,
            state=last_state,
            head_sequence=last_result.sequence,
            head_state_hash=last_result.state_hash,
            execution_branch_id=last_result.execution_branch_id,
        )
        return results

    @staticmethod
    def _resolve_event_payload(
        event_type: WorkflowEventType,
        payload: WorkflowEventPayload | None,
    ) -> WorkflowEventPayload:
        if payload is not None:
            return payload
        if event_type is WorkflowEventType.state_projection_committed:
            return EmptyWorkflowEventPayload()
        raise ValueError(f"{event_type.value} requires an explicit typed payload")

    async def save_terminal_state(
        self,
        session_id: str,
        state: ExecutionState | JsonObject,
        terminal_task_state: ExecutionTaskState,
        *,
        error: str | None = None,
    ) -> bool:
        if terminal_task_state not in TERMINAL_TASK_STATES:
            raise ValueError(f"Unknown terminal task state: {terminal_task_state!r}")
        st = ExecutionState.model_validate(state) if isinstance(state, dict) else state
        st.terminal_task_state = terminal_task_state
        st.terminal_task_error = error

        status = self._workflow_status_for_terminal(terminal_task_state)
        company_id = self._company_id()
        before, expected_head_sequence, expected_execution_branch_id, _current_status = (
            await self._load_head_for_append(
                company_id=company_id,
                session_id=session_id,
            )
        )
        state_json = self._dump_state(st)
        delta = build_state_delta(before, st)
        result = await self._repository.append_state_transition(
            company_id=company_id,
            session_id=session_id,
            event_type=WorkflowEventType.run_terminal,
            payload=RunTerminalPayload(
                terminal_task_state=terminal_task_state,
                terminal_task_error=error,
            ),
            state_delta=delta,
            state_json=state_json,
            status=status,
            snapshot=True,
            expected_head_sequence=expected_head_sequence,
            expected_execution_branch_id=expected_execution_branch_id,
        )
        await self._cache_projection(
            company_id=company_id,
            session_id=session_id,
            state=st,
            head_sequence=result.sequence,
            head_state_hash=result.state_hash,
            execution_branch_id=result.execution_branch_id,
            status=status,
        )
        return True

    async def delete_state(self, session_id: str) -> bool:
        company_id = self._company_id()
        instance = await self._repository.get_instance(
            company_id=company_id,
            session_id=session_id,
        )
        if instance is None:
            return False
        _ = await self._redis.delete(self._cache_key(company_id, session_id))
        return True

    async def search_sessions(
        self,
        *,
        user_id: str | None = None,
        flow_id: str | None = None,
        branch_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SessionConfig], int]:
        company_id = self._company_id()
        instances, total = await self._repository.list_instances(
            company_id=company_id,
            flow_id=flow_id,
            user_id=user_id,
            flow_branch_id=branch_id,
            updated_from=date_from,
            updated_to=date_to,
            limit=limit,
            offset=offset,
        )
        sessions: list[SessionConfig] = []
        for instance in instances:
            state = await self.get_state(instance.session_id)
            if state is None:
                continue
            resolved_flow_id, context_id = instance.session_id.split(":", 1)
            first_message = None
            if state.messages:
                first_message = self._message_text(state.messages[0])
            sessions.append(
                SessionConfig(
                    session_id=instance.session_id,
                    channel="a2a",
                    user_id=state.user_id,
                    flow_id=resolved_flow_id,
                    context_id=context_id,
                    status=SessionStatus.ACTIVE,
                    metadata={
                        "workflow_status": instance.status,
                        "head_sequence": instance.head_sequence,
                        "head_state_hash": instance.head_state_hash,
                    },
                    message_count=len(state.messages),
                    first_message=first_message,
                    created_at=instance.created_at,
                    last_activity=instance.updated_at,
                )
            )
        return sessions, total

    @staticmethod
    def _message_text(message: Message) -> str | None:
        text_parts: list[str] = []
        for part in message.parts:
            if isinstance(part.root, TextPart):
                text_parts.append(part.root.text)
        combined = "".join(text_parts).strip()
        return combined or None

    async def get_state_history(
        self,
        session_id: str,
        *,
        execution_branch_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[WorkflowEventRecord], int]:
        company_id = self._company_id()
        resolved_branch_id = execution_branch_id
        if resolved_branch_id is None:
            instance = await self._repository.get_instance(
                company_id=company_id,
                session_id=session_id,
            )
            if instance is None:
                return [], 0
            resolved_branch_id = instance.active_execution_branch_id
        records, total = await self._repository.list_events(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=resolved_branch_id,
            limit=limit,
            offset=offset,
        )
        return records, total

    async def load_state_at_sequence(
        self,
        session_id: str,
        sequence: int,
        *,
        execution_branch_id: str | None = None,
    ) -> ExecutionState | None:
        company_id = self._company_id()
        instance = await self._repository.get_instance(
            company_id=company_id,
            session_id=session_id,
        )
        if instance is None:
            return None
        return await self._repository.load_state_at(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=execution_branch_id or instance.active_execution_branch_id,
            sequence=sequence,
        )

    async def list_branches(self, session_id: str) -> list[WorkflowBranchRecord]:
        company_id = self._company_id()
        records = await self._repository.list_branches(
            company_id=company_id,
            session_id=session_id,
        )
        return records

    async def fork_state_at_sequence(
        self,
        session_id: str,
        sequence: int,
        *,
        execution_branch_id: str | None = None,
        activate: bool = False,
    ) -> WorkflowBranchResult:
        company_id = self._company_id()
        result = await self._repository.create_branch_transition(
            company_id=company_id,
            session_id=session_id,
            source_execution_branch_id=execution_branch_id,
            source_sequence=sequence,
            reason=ExecutionBranchReason.fork,
            event_type=WorkflowEventType.fork_created,
            target_state=None,
            activate=activate,
        )
        if activate:
            state = await self._repository.load_state_at(
                company_id=company_id,
                session_id=session_id,
                execution_branch_id=result.execution_branch_id,
                sequence=result.sequence,
            )
            if state is not None:
                await self._cache_projection(
                    company_id=company_id,
                    session_id=session_id,
                    state=state,
                    head_sequence=result.sequence,
                    head_state_hash=result.state_hash,
                    execution_branch_id=result.execution_branch_id,
                )
        return result

    async def rewind_to_sequence(
        self,
        session_id: str,
        sequence: int,
        *,
        execution_branch_id: str | None = None,
    ) -> WorkflowBranchResult:
        company_id = self._company_id()
        result = await self._repository.create_branch_transition(
            company_id=company_id,
            session_id=session_id,
            source_execution_branch_id=execution_branch_id,
            source_sequence=sequence,
            reason=ExecutionBranchReason.rewind,
            event_type=WorkflowEventType.rewind_committed,
            target_state=None,
            activate=True,
        )
        state = await self._repository.load_state_at(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=result.execution_branch_id,
            sequence=result.sequence,
        )
        if state is None:
            raise RuntimeError("Failed to load rewound workflow state")
        await self._cache_projection(
            company_id=company_id,
            session_id=session_id,
            state=state,
            head_sequence=result.sequence,
            head_state_hash=result.state_hash,
            execution_branch_id=result.execution_branch_id,
        )
        return result

    async def patch_state_at_sequence(
        self,
        session_id: str,
        sequence: int,
        patched_state: ExecutionState | JsonObject,
        *,
        execution_branch_id: str | None = None,
        activate: bool = True,
    ) -> WorkflowBranchResult:
        company_id = self._company_id()
        target = (
            ExecutionState.model_validate(patched_state)
            if isinstance(patched_state, dict)
            else patched_state
        )
        result = await self._repository.create_branch_transition(
            company_id=company_id,
            session_id=session_id,
            source_execution_branch_id=execution_branch_id,
            source_sequence=sequence,
            reason=ExecutionBranchReason.manual_patch,
            event_type=WorkflowEventType.manual_state_patch_applied,
            target_state=target,
            activate=activate,
        )
        if activate:
            await self._cache_projection(
                company_id=company_id,
                session_id=session_id,
                state=target,
                head_sequence=result.sequence,
                head_state_hash=result.state_hash,
                execution_branch_id=result.execution_branch_id,
            )
        return result

    async def retry_from_failure(
        self,
        session_id: str,
        *,
        failed_sequence: int | None = None,
        execution_branch_id: str | None = None,
    ) -> WorkflowBranchResult:
        company_id = self._company_id()
        instance = await self._repository.get_instance(
            company_id=company_id,
            session_id=session_id,
        )
        if instance is None:
            raise ValueError(f"Workflow instance not found: {session_id!r}")
        resolved_branch_id = execution_branch_id or instance.active_execution_branch_id
        failed_event = await self._repository.get_event_by_type(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=resolved_branch_id,
            event_type=WorkflowEventType.node_failed,
            sequence=failed_sequence,
        )
        if failed_event is None:
            raise ValueError("No NodeFailed event found for retry")
        failed_event_sequence = failed_event.sequence
        payload = failed_event.payload
        if not isinstance(payload, NodeFailedPayload):
            raise TypeError("NodeFailed event must have NodeFailedPayload")
        recover_sequence = payload.recover_sequence
        failed_nodes = payload.failed_nodes
        events, _ = await self._repository.list_events(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=resolved_branch_id,
            limit=10000,
        )
        blocked_activity_ids: list[str] = []
        failed_node_set = set(failed_nodes)
        for event in events:
            if event.sequence <= recover_sequence or event.sequence > failed_event_sequence:
                continue
            if event.event_type != WorkflowEventType.activity_failed:
                continue
            activity_payload = event.payload
            if not isinstance(activity_payload, ActivityLifecyclePayload):
                raise TypeError("ActivityFailed event must have ActivityLifecyclePayload")
            if activity_payload.side_effect_policy is not SideEffectPolicy.non_idempotent:
                continue
            if failed_node_set and activity_payload.node_id not in failed_node_set:
                continue
            blocked_activity_ids.append(activity_payload.activity_id)
        if blocked_activity_ids:
            raise ValueError(
                "Cannot retry failed workflow automatically because non-idempotent "
                + "activity failed after the recovery boundary: "
                + ", ".join(blocked_activity_ids)
            )
        retry_state = await self.load_state_at_sequence(
            session_id,
            recover_sequence,
            execution_branch_id=execution_branch_id,
        )
        if retry_state is None:
            raise ValueError("Failed retry recovery state not found")
        for write in payload.preserved_node_writes:
            retry_state = apply_state_delta(
                retry_state,
                write.state_delta,
            )
        if failed_nodes:
            retry_state.current_nodes = failed_nodes
        retry_state.terminal_task_state = None
        retry_state.terminal_task_error = None

        result = await self._repository.create_branch_transition(
            company_id=company_id,
            session_id=session_id,
            source_execution_branch_id=execution_branch_id,
            source_sequence=recover_sequence,
            reason=ExecutionBranchReason.retry,
            event_type=WorkflowEventType.retry_scheduled,
            target_state=retry_state,
            activate=True,
            retry_failed_sequence=failed_event_sequence,
            retry_failed_nodes=failed_nodes,
        )
        await self._cache_projection(
            company_id=company_id,
            session_id=session_id,
            state=retry_state,
            head_sequence=result.sequence,
            head_state_hash=result.state_hash,
            execution_branch_id=result.execution_branch_id,
        )
        return result

    async def record_activity_scheduled(
        self,
        *,
        session_id: str,
        activity_id: str,
        activity_type: str,
        input_payload: JsonObject,
        node_id: str | None = None,
        tool_call_id: str | None = None,
        idempotency_key: str | None = None,
        side_effect_policy: SideEffectPolicy,
    ) -> JsonObject | None:
        resolved_side_effect_policy = self._require_side_effect_policy(side_effect_policy)
        company_id = self._company_id()
        instance = await self._repository.get_instance(
            company_id=company_id,
            session_id=session_id,
        )
        if instance is None:
            raise ValueError(f"Workflow instance not found before activity schedule: {session_id!r}")
        record = await self._repository.cache_activity(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=instance.active_execution_branch_id,
            activity_id=activity_id,
            activity_type=activity_type,
            input_hash=hash_state_json(input_payload),
            node_id=node_id,
            tool_call_id=tool_call_id,
            idempotency_key=idempotency_key,
            side_effect_policy=resolved_side_effect_policy,
        )
        if record.was_created:
            await self._record_activity_lifecycle_event(
                record,
                WorkflowEventType.activity_scheduled,
            )
        if record.status is ActivityStatus.completed:
            return record.result_json
        if record.was_created:
            return None
        if record.side_effect_policy is SideEffectPolicy.non_idempotent:
            raise NonIdempotentActivityReplayBlockedError(
                "Non-idempotent activity cannot be repeated without an explicit "
                + f"retry/compensation command: activity_id={record.activity_id!r}, "
                + f"status={record.status!r}"
            )
        if record.status in {ActivityStatus.failed, ActivityStatus.started}:
            reschedule = await self._repository.reschedule_activity_attempt(
                activity_id=record.activity_id,
            )
            if reschedule is None:
                raise RuntimeError(
                    "Failed to reschedule idempotent activity attempt. "
                    + "The latest attempt is either still leased or not retryable: "
                    + f"{record.activity_id!r}"
                )
            if reschedule.expired_attempt is not None:
                await self._record_activity_lifecycle_event(
                    reschedule.expired_attempt,
                    WorkflowEventType.activity_failed,
                )
            await self._record_activity_lifecycle_event(
                reschedule.scheduled_attempt,
                WorkflowEventType.activity_scheduled,
            )
            return None
        if record.status is not ActivityStatus.scheduled:
            raise RuntimeError(
                f"Activity cannot be scheduled from status {record.status!r}: "
                + f"activity_id={record.activity_id!r}"
            )
        return None

    async def get_completed_activity_result(
        self,
        *,
        session_id: str,
        activity_id: str | None = None,
        idempotency_key: str | None = None,
        input_payload: JsonObject,
    ) -> JsonObject | None:
        company_id = self._company_id()
        instance = await self._repository.get_instance(
            company_id=company_id,
            session_id=session_id,
        )
        if instance is None:
            raise ValueError(f"Workflow instance not found: {session_id!r}")
        return await self._repository.get_completed_activity_result(
            company_id=company_id,
            session_id=session_id,
            execution_branch_id=instance.active_execution_branch_id,
            activity_id=activity_id,
            idempotency_key=idempotency_key,
            input_hash=hash_state_json(input_payload),
        )

    async def record_activity_completed(
        self,
        *,
        activity_id: str,
        result_json: JsonObject | None = None,
        error: str | None = None,
    ) -> bool:
        record = await self._repository.complete_activity(
            activity_id=activity_id,
            result_json=result_json,
            error=error,
        )
        if record is None:
            return False
        await self._record_activity_lifecycle_event(
            record,
            WorkflowEventType.activity_failed if error else WorkflowEventType.activity_completed,
        )
        return True

    async def record_activity_started(self, *, activity_id: str) -> bool:
        record = await self._repository.start_activity(activity_id=activity_id)
        if record is None:
            return False
        await self._record_activity_lifecycle_event(
            record,
            WorkflowEventType.activity_started,
        )
        return True

    async def resolve_session_id_by_flow_and_identifier(
        self,
        flow_id: str,
        lookup_id: str,
    ) -> str | None:
        company_id = self._company_id()
        return await self._repository.resolve_session_id_by_flow_and_identifier(
            company_id=company_id,
            flow_id=flow_id,
            lookup_id=lookup_id,
        )

    async def _record_activity_lifecycle_event(
        self,
        record: ActivityRecord,
        event_type: WorkflowEventType,
    ) -> None:
        for attempt_index in range(5):
            state, expected_head_sequence, expected_execution_branch_id, status = (
                await self._load_head_for_append(
                    company_id=record.company_id,
                    session_id=record.session_id,
                )
            )
            if state is None or expected_head_sequence is None:
                return
            state_json = self._dump_state(state)
            try:
                result = await self._repository.append_state_transition(
                    company_id=record.company_id,
                    session_id=record.session_id,
                    event_type=event_type,
                    payload=ActivityLifecyclePayload(
                        activity_id=record.activity_id,
                        activity_attempt_id=record.activity_attempt_id,
                        activity_type=record.activity_type,
                        activity_status=record.status,
                        node_id=record.node_id,
                        tool_call_id=record.tool_call_id,
                        input_hash=record.input_hash,
                        idempotency_key=record.idempotency_key,
                        side_effect_policy=record.side_effect_policy,
                        attempt=record.attempt,
                        lease_until=(
                            record.lease_until.isoformat() if record.lease_until else None
                        ),
                        error=record.error,
                    ),
                    state_delta=build_state_delta(state, state),
                    state_json=state_json,
                    status=status or WorkflowStatus.running,
                    snapshot=False,
                    expected_head_sequence=expected_head_sequence,
                    expected_execution_branch_id=expected_execution_branch_id,
                )
            except WorkflowConcurrencyError:
                if attempt_index == 4:
                    raise
                continue
            await self._cache_projection(
                company_id=record.company_id,
                session_id=record.session_id,
                state=state,
                head_sequence=result.sequence,
                head_state_hash=result.state_hash,
                execution_branch_id=result.execution_branch_id,
                status=status or WorkflowStatus.running,
            )
            return

    async def _cache_projection(
        self,
        *,
        company_id: str,
        session_id: str,
        state: ExecutionState,
        head_sequence: int,
        head_state_hash: str,
        execution_branch_id: str,
        status: WorkflowStatus = WorkflowStatus.running,
    ) -> None:
        state_json = self._dump_state(state)
        computed_hash = hash_state_json(state_json)
        if computed_hash != head_state_hash:
            raise ValueError(
                f"Projection hash mismatch for {session_id}: "
                + f"expected {head_state_hash}, got {computed_hash}"
            )
        _ = await self._redis.set(
            self._cache_key(company_id, session_id),
            json.dumps(
                {
                    "session_id": session_id,
                    "execution_branch_id": execution_branch_id,
                    "head_sequence": head_sequence,
                    "head_state_hash": head_state_hash,
                    "status": status.value,
                    "state_json": state_json,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )

    @staticmethod
    def _should_snapshot(
        *,
        requested: bool,
        event_type: WorkflowEventType,
        delta: ExecutionStateDelta,
        expected_head_sequence: int | None,
    ) -> bool:
        if requested:
            return True
        if expected_head_sequence is None:
            return True
        if event_type in {
            WorkflowEventType.run_started,
            WorkflowEventType.breakpoint_hit,
            WorkflowEventType.interrupt_raised,
            WorkflowEventType.handoff_requested,
        }:
            return True
        if (expected_head_sequence + 1) % 25 == 0:
            return True
        encoded = json.dumps(
            delta.model_dump(mode="json", exclude_none=False),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return len(encoded.encode("utf-8")) > 32768

    @staticmethod
    def _workflow_status_for_terminal(
        terminal_task_state: ExecutionTaskState,
    ) -> WorkflowStatus:
        if terminal_task_state == "completed":
            return WorkflowStatus.completed
        if terminal_task_state == "failed":
            return WorkflowStatus.failed
        if terminal_task_state == "canceled":
            return WorkflowStatus.canceled
        return WorkflowStatus.suspended

    @staticmethod
    def _workflow_status_from_value(value: str) -> WorkflowStatus:
        return WorkflowStatus(value)
