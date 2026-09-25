"""Типизированные контракты durable execution для flows."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import ClassVar, Literal, TypeAlias, cast
from uuid import uuid4

from oxyde import Field as DbField
from oxyde import Index, Q, atomic
from oxyde.exceptions import IntegrityError
from pydantic import ConfigDict, Field

from apps.flows.src.durable_execution.hashing import hash_state_json
from core.models import StrictBaseModel
from core.models.platform_model import PlatformModel
from core.state import ChildWorkflowStatus, ExecutionState, ExecutionTaskState
from core.state.interrupt import HandoffMode
from core.types import JsonArray, JsonObject, JsonValue, require_json_object
from core.utils.time import utcnow


class DurableStrictBaseModel(StrictBaseModel):
    """Строгий durable-контракт с типизированными enum внутри Python."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=False,
        str_strip_whitespace=False,
        validate_default=True,
    )


class WorkflowStatus(StrEnum):
    running = "running"
    suspended = "suspended"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


class ExecutionBranchReason(StrEnum):
    start = "start"
    fork = "fork"
    rewind = "rewind"
    retry = "retry"
    manual_patch = "manual_patch"


class WorkflowEventType(StrEnum):
    run_started = "RunStarted"
    user_input_applied = "UserInputApplied"
    variables_resolved = "VariablesResolved"
    state_projection_committed = "StateProjectionCommitted"
    superstep_started = "SuperstepStarted"
    node_scheduled = "NodeScheduled"
    child_workflow_started = "ChildWorkflowStarted"
    child_workflow_suspended = "ChildWorkflowSuspended"
    child_workflow_completed = "ChildWorkflowCompleted"
    child_workflow_failed = "ChildWorkflowFailed"
    activity_scheduled = "ActivityScheduled"
    activity_started = "ActivityStarted"
    activity_completed = "ActivityCompleted"
    activity_failed = "ActivityFailed"
    node_write_recorded = "NodeWriteRecorded"
    node_completed = "NodeCompleted"
    node_failed = "NodeFailed"
    superstep_committed = "SuperstepCommitted"
    edge_activated = "EdgeActivated"
    interrupt_raised = "InterruptRaised"
    handoff_requested = "HandoffRequested"
    handoff_completed = "HandoffCompleted"
    handoff_rejected = "HandoffRejected"
    handoff_resumed = "HandoffResumed"
    breakpoint_hit = "BreakpointHit"
    run_terminal = "RunTerminal"
    fork_created = "ForkCreated"
    rewind_committed = "RewindCommitted"
    manual_state_patch_applied = "ManualStatePatchApplied"
    retry_scheduled = "RetryScheduled"
    handoff_initiated = "HandoffInitiated"
    handoff_accepted = "HandoffAccepted"
    handback_requested = "HandbackRequested"
    handback_completed = "HandbackCompleted"
    conversation_message_appended = "ConversationMessageAppended"
    a2a_task_opened = "A2ATaskOpened"
    a2a_message_appended = "A2AMessageAppended"
    a2a_artifact_updated = "A2AArtifactUpdated"
    a2a_task_status_changed = "A2ATaskStatusChanged"


class ActivityStatus(StrEnum):
    scheduled = "scheduled"
    started = "started"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


class SideEffectPolicy(StrEnum):
    pure = "pure"
    idempotent = "idempotent"
    non_idempotent = "non_idempotent"


class ExecutionStateDelta(DurableStrictBaseModel):
    """Доменная delta для проекции ExecutionState."""

    messages_append: JsonArray = Field(default_factory=list)
    variables_set: JsonObject = Field(default_factory=dict)
    variables_delete: list[str] = Field(default_factory=list)
    tool_results_set: JsonObject = Field(default_factory=dict)
    tool_results_delete: list[str] = Field(default_factory=list)
    nested_states_set: JsonObject = Field(default_factory=dict)
    nested_states_delete: list[str] = Field(default_factory=list)
    child_workflows_set: JsonObject = Field(default_factory=dict)
    child_workflows_delete: list[str] = Field(default_factory=list)
    fields_set: dict[str, JsonValue] = Field(default_factory=dict)
    fields_unset: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return (
            not self.messages_append
            and not self.variables_set
            and not self.variables_delete
            and not self.tool_results_set
            and not self.tool_results_delete
            and not self.nested_states_set
            and not self.nested_states_delete
            and not self.child_workflows_set
            and not self.child_workflows_delete
            and not self.fields_set
            and not self.fields_unset
        )



_MAP_FIELDS = {
    "variables",
    "tool_results",
    "nested_states",
    "child_workflows",
}
_SPECIAL_FIELDS = {"messages", *_MAP_FIELDS}


def _state_json(state: ExecutionState) -> JsonObject:
    raw = state.model_dump(mode="json", exclude_none=False)
    raw.pop("flow_config", None)
    return require_json_object(raw, "ExecutionState")


def _json_map(value: object, field_name: str) -> JsonObject:
    if value is None:
        return {}
    return require_json_object(value, field_name)


def _build_map_delta(
    before: JsonObject,
    after: JsonObject,
) -> tuple[JsonObject, list[str]]:
    set_values: JsonObject = {}
    delete_keys: list[str] = []

    for key, after_value in after.items():
        if key not in before or before[key] != after_value:
            set_values[key] = after_value
    for key in before:
        if key not in after:
            delete_keys.append(key)
    return set_values, sorted(delete_keys)


def build_state_delta(
    before: ExecutionState | None,
    after: ExecutionState,
) -> ExecutionStateDelta:
    """Возвращает компактную семантическую delta от before к after."""
    after_json = _state_json(after)
    if before is None:
        fields_set = {
            key: value
            for key, value in after_json.items()
            if key not in _SPECIAL_FIELDS
        }
        variables_set = _json_map(after_json.get("variables"), "variables")
        tool_results_set = _json_map(after_json.get("tool_results"), "tool_results")
        nested_states_set = _json_map(after_json.get("nested_states"), "nested_states")
        child_workflows_set = _json_map(after_json.get("child_workflows"), "child_workflows")
        messages_raw = after_json.get("messages") or []
        if not isinstance(messages_raw, list):
            raise ValueError("ExecutionState.messages must be a list")
        return ExecutionStateDelta(
            messages_append=messages_raw,
            variables_set=variables_set,
            tool_results_set=tool_results_set,
            nested_states_set=nested_states_set,
            child_workflows_set=child_workflows_set,
            fields_set=fields_set,
        )

    before_json = _state_json(before)
    before_messages = before_json.get("messages") or []
    after_messages = after_json.get("messages") or []
    if not isinstance(before_messages, list) or not isinstance(after_messages, list):
        raise ValueError("ExecutionState.messages must be a list")

    messages_append: list[JsonValue]
    if after_messages[: len(before_messages)] == before_messages:
        messages_append = after_messages[len(before_messages):]
    elif before_messages != after_messages:
        messages_append = []
        after_json["messages"] = after_messages
    else:
        messages_append = []

    variables_set, variables_delete = _build_map_delta(
        _json_map(before_json.get("variables"), "before.variables"),
        _json_map(after_json.get("variables"), "after.variables"),
    )
    tool_results_set, tool_results_delete = _build_map_delta(
        _json_map(before_json.get("tool_results"), "before.tool_results"),
        _json_map(after_json.get("tool_results"), "after.tool_results"),
    )
    nested_states_set, nested_states_delete = _build_map_delta(
        _json_map(before_json.get("nested_states"), "before.nested_states"),
        _json_map(after_json.get("nested_states"), "after.nested_states"),
    )
    child_workflows_set, child_workflows_delete = _build_map_delta(
        _json_map(before_json.get("child_workflows"), "before.child_workflows"),
        _json_map(after_json.get("child_workflows"), "after.child_workflows"),
    )

    fields_set: dict[str, JsonValue] = {}
    fields_unset: list[str] = []
    keys = sorted(set(before_json) | set(after_json))
    for key in keys:
        if key in _SPECIAL_FIELDS:
            continue
        before_value = before_json.get(key)
        after_has_key = key in after_json
        after_value = after_json.get(key)
        if not after_has_key:
            fields_unset.append(key)
            continue
        if before_value != after_value:
            if after_value is None and key in ExecutionState.model_fields:
                fields_unset.append(key)
            else:
                fields_set[key] = after_value

    if "messages" in after_json and before_messages != after_messages and not messages_append:
        fields_set["messages"] = after_json["messages"]

    return ExecutionStateDelta(
        messages_append=messages_append,
        variables_set=variables_set,
        variables_delete=variables_delete,
        tool_results_set=tool_results_set,
        tool_results_delete=tool_results_delete,
        nested_states_set=nested_states_set,
        nested_states_delete=nested_states_delete,
        child_workflows_set=child_workflows_set,
        child_workflows_delete=child_workflows_delete,
        fields_set=fields_set,
        fields_unset=fields_unset,
    )


def apply_state_delta(
    state: ExecutionState | None,
    delta: ExecutionStateDelta,
) -> ExecutionState:
    """Применяет delta и возвращает валидированную проекцию ExecutionState."""
    if state is None:
        data: JsonObject = {}
    else:
        data = _state_json(state)

    if delta.messages_append:
        messages = deepcopy(data.get("messages") or [])
        if not isinstance(messages, list):
            raise ValueError("ExecutionState.messages must be a list")
        messages.extend(deepcopy(delta.messages_append))
        data["messages"] = messages

    for field_name, set_values, delete_keys in (
        ("variables", delta.variables_set, delta.variables_delete),
        ("tool_results", delta.tool_results_set, delta.tool_results_delete),
        ("nested_states", delta.nested_states_set, delta.nested_states_delete),
        ("child_workflows", delta.child_workflows_set, delta.child_workflows_delete),
    ):
        current = _json_map(data.get(field_name), field_name)
        for key in delete_keys:
            _ = current.pop(key, None)
        current.update(deepcopy(set_values))
        data[field_name] = current

    for key in delta.fields_unset:
        if key in ExecutionState.model_fields:
            data[key] = None
        else:
            _ = data.pop(key, None)
    for key, value in delta.fields_set.items():
        data[key] = deepcopy(value)

    return ExecutionState.model_validate(data)

class WorkflowConcurrencyError(RuntimeError):
    """Raised when a workflow append races with a newer committed head."""


class WorkflowProjectionMismatchError(RuntimeError):
    """Canonical state_json hash does not match persisted head_state_hash."""

    session_id: str
    expected_hash: str
    computed_hash: str

    def __init__(
        self,
        *,
        session_id: str,
        expected_hash: str,
        computed_hash: str,
    ) -> None:
        self.session_id = session_id
        self.expected_hash = expected_hash
        self.computed_hash = computed_hash
        super().__init__(
            f"Projection hash mismatch for {session_id}: "
            + f"expected {expected_hash}, got {computed_hash}"
        )


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


class WorkflowExecutionPosition(DurableStrictBaseModel):
    """Активный durable head для детерминированных command keys."""

    execution_branch_id: str = Field(..., min_length=1)
    head_sequence: int = Field(..., ge=0)
    head_state_hash: str | None = None


class EmptyWorkflowEventPayload(DurableStrictBaseModel):
    """Payload для событий, факт которых полностью описан event_type."""


class RunStartedPayload(DurableStrictBaseModel):
    flow_id: str | None = None
    branch_id: str | None = None
    task_id: str | None = None
    flow_config_version: str | None = None
    parent_session_id: str | None = None
    parent_node_id: str | None = None
    parent_execution_branch_id: str | None = None
    parent_node_schedule_sequence: int | None = Field(default=None, ge=1)
    child_flow_id: str | None = None
    child_flow_branch_id: str | None = None


class UserInputAppliedPayload(DurableStrictBaseModel):
    task_id: str = Field(..., min_length=1)
    context_id: str = Field(..., min_length=1)
    is_resume: bool


class A2ATaskOpenedPayload(DurableStrictBaseModel):
    task_id: str = Field(..., min_length=1)
    context_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    revision: int = Field(..., ge=1)
    action_id: str = Field(..., min_length=1)
    previous_task_id: str | None = Field(default=None, min_length=1)


class A2AMessageAppendedPayload(DurableStrictBaseModel):
    task_id: str = Field(..., min_length=1)
    context_id: str = Field(..., min_length=1)
    message_id: str = Field(..., min_length=1)
    role: Literal["user", "agent"]
    ordinal: int = Field(..., ge=0)


class A2AArtifactUpdatedPayload(DurableStrictBaseModel):
    task_id: str = Field(..., min_length=1)
    context_id: str = Field(..., min_length=1)
    artifact_id: str = Field(..., min_length=1)
    sequence: int = Field(..., ge=1)
    payload_hash: str = Field(..., min_length=1)
    event_identity: str = Field(..., min_length=1)
    event_json: JsonObject


class A2ATaskStatusChangedPayload(DurableStrictBaseModel):
    task_id: str = Field(..., min_length=1)
    context_id: str = Field(..., min_length=1)
    status_state: str = Field(..., min_length=1)
    sequence: int = Field(..., ge=1)
    event_identity: str = Field(..., min_length=1)
    terminal: bool
    event_json: JsonObject


class VariablesResolvedPayload(DurableStrictBaseModel):
    """Материализация переменных компании/flow на старте.

    Значения попадают в `ExecutionState.variables` через `state_delta` (как все
    переменные), здесь — только аудит ключей; секреты в payload не дублируются.
    """

    variable_keys: list[str] = Field(default_factory=list)
    secret_keys: list[str] = Field(default_factory=list)


class SuperstepStartedPayload(DurableStrictBaseModel):
    current_nodes: list[str] = Field(..., min_length=1)


class NodeScheduledPayload(DurableStrictBaseModel):
    node_id: str = Field(..., min_length=1)
    node_type: str = Field(..., min_length=1)
    current_nodes: list[str] = Field(..., min_length=1)


class NodeWriteRecordedPayload(DurableStrictBaseModel):
    node_id: str = Field(..., min_length=1)
    node_type: str = Field(..., min_length=1)
    state_delta: ExecutionStateDelta


class NodeCompletedPayload(DurableStrictBaseModel):
    node_id: str = Field(..., min_length=1)
    node_type: str = Field(..., min_length=1)


class InterruptRaisedPayload(DurableStrictBaseModel):
    current_nodes: list[str] = Field(..., min_length=1)
    node_id: str | None = Field(default=None, min_length=1)
    preserved_node_writes: list[NodeWriteRecordedPayload] = Field(default_factory=list)


class HandoffRequestedPayload(DurableStrictBaseModel):
    current_nodes: list[str] = Field(..., min_length=1)
    node_id: str = Field(..., min_length=1)
    handoff_command_id: str = Field(..., min_length=1)
    correlation_id: str = Field(..., min_length=1)
    work_item_id: str = Field(..., min_length=1)
    task_title: str = Field(..., min_length=1)
    assignee_queue: str = Field(..., min_length=1)
    handoff_mode: HandoffMode
    execution_branch_id: str = Field(..., min_length=1)
    node_schedule_sequence: int = Field(..., ge=1)
    tool_call_id: str | None = Field(default=None, min_length=1)
    preserved_node_writes: list[NodeWriteRecordedPayload] = Field(default_factory=list)


class HandoffCompletedPayload(DurableStrictBaseModel):
    handoff_command_id: str = Field(..., min_length=1)
    correlation_id: str = Field(..., min_length=1)
    work_item_id: str = Field(..., min_length=1)
    operator_user_id: str = Field(..., min_length=1)
    handoff_mode: HandoffMode
    resolution_preview: str = Field(..., min_length=1)
    file_count: int = Field(..., ge=0)


class HandoffRejectedPayload(DurableStrictBaseModel):
    handoff_command_id: str = Field(..., min_length=1)
    correlation_id: str = Field(..., min_length=1)
    work_item_id: str = Field(..., min_length=1)
    operator_user_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class HandoffResumedPayload(DurableStrictBaseModel):
    current_nodes: list[str] = Field(..., min_length=1)
    node_id: str = Field(..., min_length=1)
    handoff_command_id: str = Field(..., min_length=1)
    correlation_id: str = Field(..., min_length=1)
    work_item_id: str = Field(..., min_length=1)
    response_preview: str = Field(..., min_length=1)


class ConversationMessageAppendedPayload(DurableStrictBaseModel):
    """Внешний turn (оператор/пользователь), дописанный в лог сессии HITL.

    `message_id` детерминирован для идемпотентности повторной доставки.
    """

    author_role: Literal["operator", "user"]
    author_user_id: str = Field(..., min_length=1)
    work_item_id: str = Field(..., min_length=1)
    message_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)


class NodeFailedPayload(DurableStrictBaseModel):
    failed_nodes: list[str] = Field(..., min_length=1)
    current_nodes: list[str] = Field(..., min_length=1)
    error: str = Field(..., min_length=1)
    recover_sequence: int = Field(..., ge=0)
    preserved_node_writes: list[NodeWriteRecordedPayload] = Field(default_factory=list)


class EdgeActivatedPayload(DurableStrictBaseModel):
    edge_index: int = Field(..., ge=0)
    from_node: str = Field(..., min_length=1)
    to_node: str = Field(..., min_length=1)


class SuperstepCommittedPayload(DurableStrictBaseModel):
    completed_nodes: list[str] = Field(..., min_length=1)
    next_nodes: list[str]
    edge_activations: list[EdgeActivatedPayload] = Field(default_factory=list)


class BreakpointHitPayload(DurableStrictBaseModel):
    node_id: str = Field(..., min_length=1)
    node_type: str = Field(..., min_length=1)


class RunTerminalPayload(DurableStrictBaseModel):
    terminal_task_state: ExecutionTaskState
    terminal_task_error: str | None = None


class BranchTransitionPayload(DurableStrictBaseModel):
    source_execution_branch_id: str = Field(..., min_length=1)
    source_sequence: int = Field(..., ge=0)
    reason: ExecutionBranchReason


class RetryScheduledPayload(BranchTransitionPayload):
    failed_sequence: int = Field(..., ge=1)
    recover_sequence: int = Field(..., ge=0)
    failed_nodes: list[str] = Field(..., min_length=1)


class ActivityLifecyclePayload(DurableStrictBaseModel):
    activity_id: str = Field(..., min_length=1)
    activity_attempt_id: str = Field(..., min_length=1)
    activity_type: str = Field(..., min_length=1)
    activity_status: ActivityStatus
    node_id: str | None = Field(default=None, min_length=1)
    tool_call_id: str | None = Field(default=None, min_length=1)
    input_hash: str = Field(..., min_length=1)
    idempotency_key: str | None = Field(default=None, min_length=1)
    side_effect_policy: SideEffectPolicy
    attempt: int = Field(..., ge=1)
    lease_until: str | None = None
    error: str | None = None


class ChildWorkflowLifecyclePayload(DurableStrictBaseModel):
    node_id: str = Field(..., min_length=1)
    child_session_id: str = Field(..., min_length=3)
    child_flow_id: str = Field(..., min_length=1)
    child_flow_branch_id: str = Field(..., min_length=1)
    child_execution_branch_id: str = Field(..., min_length=1)
    parent_execution_branch_id: str = Field(..., min_length=1)
    parent_node_schedule_sequence: int = Field(..., ge=1)
    child_execution_position: WorkflowExecutionPosition
    status: ChildWorkflowStatus
    error: str | None = None


class FlowHandoffInitiatedPayload(DurableStrictBaseModel):
    parent_session_id: str = Field(..., min_length=3)
    child_session_id: str = Field(..., min_length=3)
    target_flow_id: str = Field(..., min_length=1)
    target_branch_id: str = Field(..., min_length=1)
    variables: JsonObject = Field(default_factory=dict)
    handoff_depth: int = Field(..., ge=1)
    trace_id: str | None = Field(
        default=None,
        min_length=1,
        description="OTEL trace_id цепочки handoff для jump в trace viewer",
    )
    span_id: str | None = Field(
        default=None,
        min_length=1,
        description="Span handoff.initiated для корреляции",
    )


class FlowHandbackCompletedPayload(DurableStrictBaseModel):
    parent_session_id: str = Field(..., min_length=3)
    child_session_id: str = Field(..., min_length=3)
    child_flow_id: str = Field(..., min_length=1)
    response: str = Field(..., min_length=1)
    variables: JsonObject = Field(default_factory=dict)
    handoff_depth: int = Field(..., ge=0)
    trace_id: str | None = Field(
        default=None,
        min_length=1,
        description="OTEL trace_id цепочки handoff",
    )
    span_id: str | None = Field(
        default=None,
        min_length=1,
        description="Span handback.completed",
    )


WorkflowEventPayload: TypeAlias = (
    EmptyWorkflowEventPayload
    | RunStartedPayload
    | UserInputAppliedPayload
    | VariablesResolvedPayload
    | SuperstepStartedPayload
    | NodeScheduledPayload
    | NodeWriteRecordedPayload
    | NodeCompletedPayload
    | InterruptRaisedPayload
    | HandoffRequestedPayload
    | HandoffCompletedPayload
    | HandoffRejectedPayload
    | HandoffResumedPayload
    | NodeFailedPayload
    | EdgeActivatedPayload
    | SuperstepCommittedPayload
    | BreakpointHitPayload
    | RunTerminalPayload
    | BranchTransitionPayload
    | RetryScheduledPayload
    | ActivityLifecyclePayload
    | ChildWorkflowLifecyclePayload
    | FlowHandoffInitiatedPayload
    | FlowHandbackCompletedPayload
    | ConversationMessageAppendedPayload
    | A2ATaskOpenedPayload
    | A2AMessageAppendedPayload
    | A2AArtifactUpdatedPayload
    | A2ATaskStatusChangedPayload
)

_PAYLOAD_BY_EVENT_TYPE: dict[WorkflowEventType, type[DurableStrictBaseModel]] = {
    WorkflowEventType.run_started: RunStartedPayload,
    WorkflowEventType.user_input_applied: UserInputAppliedPayload,
    WorkflowEventType.variables_resolved: VariablesResolvedPayload,
    WorkflowEventType.state_projection_committed: EmptyWorkflowEventPayload,
    WorkflowEventType.superstep_started: SuperstepStartedPayload,
    WorkflowEventType.node_scheduled: NodeScheduledPayload,
    WorkflowEventType.child_workflow_started: ChildWorkflowLifecyclePayload,
    WorkflowEventType.child_workflow_suspended: ChildWorkflowLifecyclePayload,
    WorkflowEventType.child_workflow_completed: ChildWorkflowLifecyclePayload,
    WorkflowEventType.child_workflow_failed: ChildWorkflowLifecyclePayload,
    WorkflowEventType.activity_scheduled: ActivityLifecyclePayload,
    WorkflowEventType.activity_started: ActivityLifecyclePayload,
    WorkflowEventType.activity_completed: ActivityLifecyclePayload,
    WorkflowEventType.activity_failed: ActivityLifecyclePayload,
    WorkflowEventType.node_write_recorded: NodeWriteRecordedPayload,
    WorkflowEventType.node_completed: NodeCompletedPayload,
    WorkflowEventType.node_failed: NodeFailedPayload,
    WorkflowEventType.superstep_committed: SuperstepCommittedPayload,
    WorkflowEventType.edge_activated: EdgeActivatedPayload,
    WorkflowEventType.interrupt_raised: InterruptRaisedPayload,
    WorkflowEventType.handoff_requested: HandoffRequestedPayload,
    WorkflowEventType.handoff_completed: HandoffCompletedPayload,
    WorkflowEventType.handoff_rejected: HandoffRejectedPayload,
    WorkflowEventType.handoff_resumed: HandoffResumedPayload,
    WorkflowEventType.breakpoint_hit: BreakpointHitPayload,
    WorkflowEventType.run_terminal: RunTerminalPayload,
    WorkflowEventType.fork_created: BranchTransitionPayload,
    WorkflowEventType.rewind_committed: BranchTransitionPayload,
    WorkflowEventType.manual_state_patch_applied: BranchTransitionPayload,
    WorkflowEventType.retry_scheduled: RetryScheduledPayload,
    WorkflowEventType.handoff_initiated: FlowHandoffInitiatedPayload,
    WorkflowEventType.handback_completed: FlowHandbackCompletedPayload,
    WorkflowEventType.conversation_message_appended: ConversationMessageAppendedPayload,
    WorkflowEventType.a2a_task_opened: A2ATaskOpenedPayload,
    WorkflowEventType.a2a_message_appended: A2AMessageAppendedPayload,
    WorkflowEventType.a2a_artifact_updated: A2AArtifactUpdatedPayload,
    WorkflowEventType.a2a_task_status_changed: A2ATaskStatusChangedPayload,
}


def parse_workflow_event_payload(
    event_type: WorkflowEventType,
    payload: JsonObject,
) -> WorkflowEventPayload:
    payload_model = _PAYLOAD_BY_EVENT_TYPE[event_type]
    return cast(WorkflowEventPayload, payload_model.model_validate(payload))


def workflow_event_payload_json(payload: WorkflowEventPayload) -> JsonObject:
    return require_json_object(
        payload.model_dump(mode="json", exclude_none=False),
        "WorkflowEvent.payload",
    )


class WorkflowAppendResult(DurableStrictBaseModel):
    event_id: str
    execution_branch_id: str
    sequence: int
    state_hash: str
    snapshot_id: str | None


class TimeTravelEffect(DurableStrictBaseModel):
    """Структурированный итог fork/rewind/retry/manual-patch для UX Outcome."""

    activates_head: bool
    source_execution_branch_id: str
    source_sequence: int
    source_events_after_base: int = Field(..., ge=0)
    instance_status: WorkflowStatus
    auto_resumes_run: bool = False


class WorkflowBranchResult(DurableStrictBaseModel):
    execution_branch_id: str
    parent_execution_branch_id: str | None
    base_sequence: int
    base_state_hash: str | None
    reason: ExecutionBranchReason
    event_id: str | None
    sequence: int
    state_hash: str
    snapshot_id: str
    effect: TimeTravelEffect


class WorkflowBranchRecord(DurableStrictBaseModel):
    execution_branch_id: str
    parent_execution_branch_id: str | None
    base_sequence: int
    base_state_hash: str | None
    reason: ExecutionBranchReason
    created_at: str
    is_active: bool


class WorkflowEventRecord(DurableStrictBaseModel):
    event_id: str
    session_id: str
    execution_branch_id: str
    sequence: int
    event_type: WorkflowEventType
    payload: WorkflowEventPayload
    state_delta: ExecutionStateDelta
    prev_state_hash: str | None
    next_state_hash: str
    created_at: str


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
    async def get_instance(
        cls,
        *,
        company_id: str,
        session_id: str,
    ) -> WorkflowInstance | None:
        return await WorkflowInstance.objects.filter(
            company_id=company_id,
            session_id=session_id,
        ).first()

    @classmethod
    async def list_instances(
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
    async def list_events(
        cls,
        *,
        company_id: str,
        session_id: str,
        execution_branch_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[WorkflowEventRecord], int]:
        query = WorkflowEvent.objects.filter(company_id=company_id, session_id=session_id)
        if execution_branch_id is not None:
            query = query.filter(execution_branch_id=execution_branch_id)
        total = await query.count()
        rows = await query.order_by("sequence").limit(limit).offset(offset).all()
        return [cls._workflow_event_record(row) for row in rows], total

    @classmethod
    async def get_event_by_type(
        cls,
        *,
        company_id: str,
        session_id: str,
        execution_branch_id: str,
        event_type: WorkflowEventType,
        sequence: int | None = None,
    ) -> WorkflowEventRecord | None:
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
    async def list_branches(
        cls,
        *,
        company_id: str,
        session_id: str,
    ) -> list[WorkflowBranchRecord]:
        instance = await cls.get_instance(company_id=company_id, session_id=session_id)
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

        instance = await cls.get_instance(company_id=company_id, session_id=session_id)
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
        instance = await cls.get_instance(company_id=company_id, session_id=session_id)
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
        snapshot = await (
            WorkflowSnapshot.objects.filter(
                company_id=company_id,
                session_id=session_id,
                execution_branch_id=execution_branch_id,
                sequence__lte=sequence,
            )
            .order_by("-sequence")
            .first()
        )
        state: ExecutionState | None = None
        start_sequence = 0
        if snapshot is not None:
            state = ExecutionState.model_validate(snapshot.state_json)
            start_sequence = snapshot.sequence
        events = await (
            WorkflowEvent.objects.filter(
                company_id=company_id,
                session_id=session_id,
                execution_branch_id=execution_branch_id,
                sequence__gt=start_sequence,
                sequence__lte=sequence,
            )
            .order_by("sequence")
            .all()
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
    async def resolve_session_id_by_flow_and_identifier(
        cls,
        *,
        company_id: str,
        flow_id: str,
        lookup_id: str,
    ) -> str | None:
        direct_session_id = f"{flow_id}:{lookup_id}"
        direct = await cls.get_instance(company_id=company_id, session_id=direct_session_id)
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


class ExecutionBranch(PlatformModel):
    """Линия fork/rewind/retry. Таблица ``execution_branches``."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "execution_branches"
        indexes: list[Index] = [
            Index(["company_id", "session_id"]),
            Index(["parent_execution_branch_id"]),
        ]

    execution_branch_id: str = DbField(db_pk=True)
    company_id: str = DbField()
    session_id: str = DbField()
    reason: ExecutionBranchReason = DbField()
    created_at: datetime = DbField()
    base_sequence: int = DbField(default=0, ge=0)
    parent_execution_branch_id: str | None = DbField(default=None)
    base_state_hash: str | None = DbField(default=None)


class WorkflowEvent(PlatformModel):
    """Событие истории выполнения. Таблица ``workflow_events``."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "workflow_events"
        unique_together: list[tuple[str, str, str, str]] = [
            ("company_id", "session_id", "execution_branch_id", "sequence"),
        ]
        indexes: list[Index] = [
            Index(["company_id", "session_id", "sequence"]),
            Index(["execution_branch_id", "sequence"]),
            Index(["event_type"]),
        ]

    event_id: str = DbField(db_pk=True)
    company_id: str = DbField()
    session_id: str = DbField()
    execution_branch_id: str = DbField()
    sequence: int = DbField(ge=1)
    event_type: WorkflowEventType = DbField()
    payload: JsonObject = DbField(db_type="JSONB")
    state_delta: JsonObject = DbField(db_type="JSONB")
    next_state_hash: str = DbField()
    created_at: datetime = DbField()
    schema_version: int = DbField(default=1)
    prev_state_hash: str | None = DbField(default=None)
    causation_id: str | None = DbField(default=None)
    correlation_id: str | None = DbField(default=None)


class WorkflowSnapshot(PlatformModel):
    """Якорь проекции. Таблица ``workflow_snapshots``."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "workflow_snapshots"
        unique_together: list[tuple[str, str, str, str]] = [
            ("company_id", "session_id", "execution_branch_id", "sequence"),
        ]
        indexes: list[Index] = [
            Index(["company_id", "session_id", "sequence"]),
            Index(["execution_branch_id", "sequence"]),
        ]

    snapshot_id: str = DbField(db_pk=True)
    company_id: str = DbField()
    session_id: str = DbField()
    execution_branch_id: str = DbField()
    sequence: int = DbField(ge=0)
    state_json: JsonObject = DbField(db_type="JSONB")
    state_hash: str = DbField()
    created_at: datetime = DbField()
    schema_version: int = DbField(default=1)


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
    def _require_side_effect_policy(value: object) -> SideEffectPolicy:
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


class ActivityAttempt(PlatformModel):
    """Попытка команды. Таблица ``activity_attempts``."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "activity_attempts"
        unique_together: list[tuple[str, str]] = [("activity_id", "attempt")]
        indexes: list[Index] = [
            Index(["activity_id"]),
            Index(["execution_branch_id", "status"]),
            Index(["company_id", "session_id"]),
        ]

    activity_attempt_id: str = DbField(db_pk=True, db_type="TEXT")
    activity_id: str = DbField(db_type="TEXT")
    company_id: str = DbField()
    session_id: str = DbField()
    execution_branch_id: str = DbField()
    attempt: int = DbField(ge=1)
    status: ActivityStatus = DbField()
    scheduled_at: datetime = DbField()
    result_json: JsonObject | None = DbField(default=None, db_type="JSONB")
    error: str | None = DbField(default=None, db_type="TEXT")
    lease_until: datetime | None = DbField(default=None)
    started_at: datetime | None = DbField(default=None)
    completed_at: datetime | None = DbField(default=None)


class ActivityRecord(DurableStrictBaseModel):
    activity_id: str
    activity_attempt_id: str
    company_id: str
    session_id: str
    execution_branch_id: str
    node_id: str | None
    tool_call_id: str | None
    activity_type: str
    status: ActivityStatus
    attempt: int
    input_hash: str
    idempotency_key: str | None
    side_effect_policy: SideEffectPolicy
    result_json: JsonObject | None
    error: str | None
    lease_until: datetime | None
    was_created: bool = False


class ActivityRescheduleResult(DurableStrictBaseModel):
    expired_attempt: ActivityRecord | None
    scheduled_attempt: ActivityRecord
