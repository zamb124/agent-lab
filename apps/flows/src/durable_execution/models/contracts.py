"""Типизированные контракты durable execution для flows."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import ClassVar, Literal, TypeAlias

from pydantic import ConfigDict, Field

from core.models import StrictBaseModel
from core.state import ChildWorkflowStatus, ExecutionState, ExecutionTaskState
from core.state.interrupt import HandoffMode
from core.types import JsonArray, JsonObject, JsonValue, require_json_object


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


def _json_map(value: JsonValue, field_name: str) -> JsonObject:
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
    validated = payload_model.model_validate(payload)
    if not isinstance(validated, WorkflowEventPayload):
        raise TypeError(f"workflow event {event_type} payload is not a known payload model")
    return validated


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
