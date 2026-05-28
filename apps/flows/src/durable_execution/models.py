"""Типизированные контракты durable execution для flows."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar, TypeAlias, cast

from pydantic import ConfigDict, Field

from core.models import StrictBaseModel
from core.state import ChildWorkflowStatus, ExecutionTaskState
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
    operator_task_id: str = Field(..., min_length=1)
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
    operator_task_id: str = Field(..., min_length=1)
    operator_user_id: str = Field(..., min_length=1)
    handoff_mode: HandoffMode
    resolution_preview: str = Field(..., min_length=1)
    file_count: int = Field(..., ge=0)


class HandoffRejectedPayload(DurableStrictBaseModel):
    handoff_command_id: str = Field(..., min_length=1)
    correlation_id: str = Field(..., min_length=1)
    operator_task_id: str = Field(..., min_length=1)
    operator_user_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class HandoffResumedPayload(DurableStrictBaseModel):
    current_nodes: list[str] = Field(..., min_length=1)
    node_id: str = Field(..., min_length=1)
    handoff_command_id: str = Field(..., min_length=1)
    correlation_id: str = Field(..., min_length=1)
    operator_task_id: str = Field(..., min_length=1)
    response_preview: str = Field(..., min_length=1)


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


WorkflowEventPayload: TypeAlias = (
    EmptyWorkflowEventPayload
    | RunStartedPayload
    | UserInputAppliedPayload
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
)

_PAYLOAD_BY_EVENT_TYPE: dict[WorkflowEventType, type[DurableStrictBaseModel]] = {
    WorkflowEventType.run_started: RunStartedPayload,
    WorkflowEventType.user_input_applied: UserInputAppliedPayload,
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
