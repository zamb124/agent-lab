from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import cast, override

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.db.models import ActivityAttempts, utc_now
from apps.flows.src.durable_execution import (
    ActivityLifecyclePayload,
    ActivityStatus,
    ChildWorkflowLifecyclePayload,
    DurableWorkflowRepository,
    DurableWorkflowRuntime,
    NodeFailedPayload,
    NonIdempotentActivityReplayBlockedError,
    RunStartedPayload,
    SideEffectPolicy,
    SuperstepCommittedPayload,
    SuperstepStartedPayload,
    UserInputAppliedPayload,
    WorkflowConcurrencyError,
    WorkflowEventRecord,
    WorkflowEventType,
    WorkflowStatus,
    build_state_delta,
    create_initial_state,
    workflow_event_payload_json,
)
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import BaseNode, FlowNode, NodeInputs, NodeRunResult
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.db.storage import Storage
from core.errors import FlowPrematureCompletionError
from core.state import ExecutionState
from core.types import JsonObject, require_json_object

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_taskiq,
    pytest.mark.no_service_client_patch,
]


@dataclass(frozen=True)
class DurableStack:
    repository: DurableWorkflowRepository
    runtime: DurableWorkflowRuntime
    storage: Storage
    redis_client: RedisClient


@dataclass(frozen=True)
class DurableFlowHarness:
    workflow_runtime: DurableWorkflowRuntime
    redis_client: RedisClient


class _StateWriteNode(BaseNode):
    @override
    async def _run_impl(
        self,
        state: ExecutionState,
        inputs: NodeInputs,
    ) -> NodeRunResult:
        _ = inputs
        state.variables[self.node_id] = "done"
        state.response = f"{self.node_id}:done"
        return None


class _FailingNode(BaseNode):
    @override
    async def _run_impl(
        self,
        state: ExecutionState,
        inputs: NodeInputs,
    ) -> NodeRunResult:
        _ = state
        _ = inputs
        raise RuntimeError("boom")


class _ChildInterruptUntilAnswerNode(BaseNode):
    @override
    async def _run_impl(
        self,
        state: ExecutionState,
        inputs: NodeInputs,
    ) -> NodeRunResult:
        _ = inputs
        if state.content != "answer":
            raise FlowInterrupt(question="answer required")
        state.variables["child_answer"] = state.content
        state.response = "child answered"
        return None


class _DurableCountingActivityNode(BaseNode):
    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        container: FlowRuntimeContainer | None = None,
    ) -> None:
        super().__init__(node_id, config, container=container)
        self.side_effect_runs: int = 0

    @override
    async def _run_impl(
        self,
        state: ExecutionState,
        inputs: NodeInputs,
    ) -> NodeRunResult:
        _ = inputs
        current = state.variables.get("count", 0)
        if type(current) is not int:
            raise ValueError("count must be int")
        next_count = current + 1

        async def invoke() -> NodeRunResult:
            self.side_effect_runs += 1
            state.variables["count"] = next_count
            return {"count": next_count}

        return await self._run_durable_activity(
            state,
            activity_type="test_node_side_effect",
            input_payload={
                "node_id": self.node_id,
                "count": current,
            },
            side_effect_policy=SideEffectPolicy.non_idempotent,
            invoke=invoke,
        )


class _FalseCodeConditionRunner:
    def __init__(self) -> None:
        self.calls: int = 0

    async def execute_tool(
        self,
        code: str,
        args: JsonObject,
        state: ExecutionState,
        *,
        entrypoint: str | None = None,
    ) -> bool:
        _ = code, args, state, entrypoint
        self.calls += 1
        return False


class DurableCodeConditionHarness:
    def __init__(
        self,
        *,
        workflow_runtime: DurableWorkflowRuntime,
        redis_client: RedisClient,
        code_runner: _FalseCodeConditionRunner,
    ) -> None:
        self.workflow_runtime: DurableWorkflowRuntime = workflow_runtime
        self.redis_client: RedisClient = redis_client
        self._code_runner: _FalseCodeConditionRunner = code_runner

    def get_code_runner(self, language: str) -> _FalseCodeConditionRunner:
        _ = language
        return self._code_runner


class DurableChildFlowFactory:
    def __init__(self) -> None:
        self._flow: Flow | None = None

    def set_flow(self, flow: Flow) -> None:
        self._flow = flow

    async def get_flow(
        self,
        flow_id: str,
        branch_id: str = "default",
        config_version: str | None = None,
    ) -> Flow | None:
        _ = branch_id, config_version
        if self._flow is None:
            return None
        if self._flow.flow_id != flow_id:
            return None
        return self._flow


@dataclass(frozen=True)
class DurableChildWorkflowHarness:
    workflow_runtime: DurableWorkflowRuntime
    redis_client: RedisClient
    flow_factory: DurableChildFlowFactory


@pytest_asyncio.fixture
async def durable_stack(setup_database_before_tests: object) -> AsyncIterator[DurableStack]:
    _ = setup_database_before_tests
    settings = get_settings()
    if not settings.database.flows_url:
        pytest.skip("DATABASE__FLOWS_URL is required for durable workflow integration tests")

    redis_client = RedisClient(settings.database.redis_url)
    storage = Storage(db_url=settings.database.flows_url)
    repository = DurableWorkflowRepository(storage)
    runtime = DurableWorkflowRuntime(repository=repository, redis_client=redis_client)

    try:
        yield DurableStack(
            repository=repository,
            runtime=runtime,
            storage=storage,
            redis_client=redis_client,
        )
    finally:
        await redis_client.close()


def _session_id(flow_id: str) -> str:
    return f"{flow_id}:{uuid.uuid4().hex}"


def _state_json(state: ExecutionState) -> JsonObject:
    data = require_json_object(
        state.model_dump(mode="json", exclude_none=False),
        "ExecutionState",
    )
    _ = data.pop("flow_config", None)
    return data


def _user_input_payload(state: ExecutionState) -> UserInputAppliedPayload:
    return UserInputAppliedPayload(
        task_id=state.task_id,
        context_id=state.context_id,
        is_resume=False,
    )


def _manual_superstep_payload(step: str) -> SuperstepCommittedPayload:
    return SuperstepCommittedPayload(
        completed_nodes=[step],
        next_nodes=[],
    )


def _event_payload(event: WorkflowEventRecord) -> JsonObject:
    return workflow_event_payload_json(event.payload)


def _activity_payload(value: object, label: str) -> ActivityLifecyclePayload:
    if not isinstance(value, ActivityLifecyclePayload):
        raise AssertionError(f"{label}: expected ActivityLifecyclePayload, got {type(value)!r}")
    return value


def _child_workflow_payload(value: object, label: str) -> ChildWorkflowLifecyclePayload:
    if not isinstance(value, ChildWorkflowLifecyclePayload):
        raise AssertionError(
            f"{label}: expected ChildWorkflowLifecyclePayload, got {type(value)!r}"
        )
    return value


def _json_str(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise AssertionError(f"{label}: expected str, got {type(value)!r}")
    return value


def _json_object_list(value: object, label: str) -> list[JsonObject]:
    if not isinstance(value, list):
        raise AssertionError(f"{label}: expected list, got {type(value)!r}")
    items = cast(list[object], value)
    return [
        require_json_object(item, f"{label}[]")
        for item in items
    ]


def _runtime_container(value: object) -> FlowRuntimeContainer:
    return cast(FlowRuntimeContainer, value)


def _clone_state(state: ExecutionState) -> ExecutionState:
    return ExecutionState.model_validate(
        state.model_dump(mode="json", exclude_none=False)
    )


async def test_event_ledger_rehydrates_after_redis_loss_and_terminal_boundary(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    session_id = _session_id("durable_ledger")
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="first",
        branch_id="main",
    )
    state.variables = {"step": 1}

    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.user_input_applied,
        payload=_user_input_payload(state),
        snapshot=True,
    )

    state.content = "second"
    state.variables = {"step": 2}
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.superstep_committed,
        payload=_manual_superstep_payload("step-2"),
    )

    assert await runtime.delete_state(session_id) is True
    rehydrated = await runtime.get_state(session_id)
    assert rehydrated is not None
    assert rehydrated.content == "second"
    assert rehydrated.variables == {"step": 2}

    _ = await runtime.save_terminal_state(session_id, rehydrated, "completed")
    terminal = await runtime.get_state(session_id)
    history, total = await runtime.get_state_history(session_id)

    assert terminal is not None
    assert terminal.terminal_task_state == "completed"
    assert total == 3
    assert [event.event_type.value for event in history] == [
        WorkflowEventType.user_input_applied.value,
        WorkflowEventType.superstep_committed.value,
        WorkflowEventType.run_terminal.value,
    ]


async def test_branch_time_travel_is_append_only_and_branch_aware(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    session_id = _session_id("durable_branch")
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="one",
    )
    state.variables = {"step": 1}
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.user_input_applied,
        payload=_user_input_payload(state),
        snapshot=True,
    )
    state.content = "two"
    state.variables = {"step": 2}
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.superstep_committed,
        payload=_manual_superstep_payload("step-2"),
    )
    state.content = "three"
    state.variables = {"step": 3}
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.superstep_committed,
        payload=_manual_superstep_payload("step-3"),
    )

    fork = await runtime.fork_state_at_sequence(session_id, 1, activate=False)
    fork_state = await runtime.load_state_at_sequence(
        session_id,
        fork.sequence,
        execution_branch_id=fork.execution_branch_id,
    )
    active_after_fork = await runtime.get_state(session_id)

    assert fork_state is not None
    assert fork_state.content == "one"
    assert active_after_fork is not None
    assert active_after_fork.content == "three"

    rewind = await runtime.rewind_to_sequence(session_id, 2)
    rewound = await runtime.get_state(session_id)
    assert rewound is not None
    assert rewound.content == "two"

    patched = _clone_state(rewound)
    patched.content = "patched"
    patched.variables = {"step": 20, "patched": True}
    patch = await runtime.patch_state_at_sequence(
        session_id,
        rewind.sequence,
        patched,
        activate=True,
    )
    active = await runtime.get_state(session_id)
    branches = await runtime.list_branches(session_id)

    assert active is not None
    assert active.content == "patched"
    assert active.variables == {"step": 20, "patched": True}
    assert patch.reason.value == "manual_patch"
    assert [branch.reason.value for branch in branches] == [
        "start",
        "fork",
        "rewind",
        "manual_patch",
    ]
    assert sum(1 for branch in branches if branch.is_active) == 1


async def test_retry_from_failure_restores_recoverable_node_boundary(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    session_id = _session_id("durable_retry")
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="start",
    )
    state.current_nodes = ["fragile_node"]

    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.superstep_started,
        payload=SuperstepStartedPayload(current_nodes=["fragile_node"]),
        snapshot=True,
    )
    state.terminal_task_state = "failed"
    state.terminal_task_error = "dirty failure marker must not survive retry"
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.node_failed,
        payload=NodeFailedPayload(
            failed_nodes=["fragile_node"],
            current_nodes=["fragile_node"],
            error="boom",
            recover_sequence=1,
            preserved_node_writes=[],
        ),
    )
    _ = await runtime.save_terminal_state(session_id, state, "failed", error="boom")

    retry = await runtime.retry_from_failure(session_id)
    retried = await runtime.get_state(session_id)
    branches = await runtime.list_branches(session_id)

    assert retry.reason.value == "retry"
    assert retried is not None
    assert retried.current_nodes == ["fragile_node"]
    assert retried.terminal_task_state is None
    assert retried.terminal_task_error is None
    assert branches[-1].reason.value == "retry"
    assert branches[-1].is_active is True


async def test_parallel_superstep_retry_preserves_successful_pending_writes(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    flow_id = f"durable_parallel_retry_{uuid.uuid4().hex}"
    session_id = _session_id(flow_id)
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="start",
    )
    state.current_nodes = ["ok", "bad"]
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.run_started,
        payload=RunStartedPayload(),
        snapshot=True,
    )
    flow = Flow(
        flow_id=flow_id,
        name="parallel retry",
        entry="ok",
        nodes={
            "ok": _StateWriteNode("ok", {"type": "function"}),
            "bad": _FailingNode("bad", {"type": "function"}),
        },
        edges=[],
        container=_runtime_container(
            DurableFlowHarness(
                workflow_runtime=runtime,
                redis_client=durable_stack.redis_client,
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="boom"):
        _ = await flow.run(state)

    history, _ = await runtime.get_state_history(session_id)
    event_types = [event.event_type.value for event in history]
    assert WorkflowEventType.node_scheduled.value in event_types
    assert WorkflowEventType.node_write_recorded.value in event_types
    assert WorkflowEventType.node_completed.value in event_types
    assert WorkflowEventType.node_failed.value in event_types

    failed_event = next(
        event
        for event in history
        if event.event_type is WorkflowEventType.node_failed
    )
    failed_payload = _event_payload(failed_event)
    assert failed_payload["failed_nodes"] == ["bad"]
    assert type(failed_payload["recover_sequence"]) is int
    preserved_writes = _json_object_list(
        failed_payload.get("preserved_node_writes"),
        "NodeFailed.payload.preserved_node_writes",
    )
    assert preserved_writes[0]["node_id"] == "ok"

    failed_projection = await runtime.get_state(session_id)
    assert failed_projection is not None
    assert failed_projection.variables == {}

    retry = await runtime.retry_from_failure(session_id)
    retried = await runtime.get_state(session_id)

    assert retry.reason.value == "retry"
    assert retried is not None
    assert retried.variables == {"ok": "done"}
    assert retried.current_nodes == ["bad"]


async def test_node_activity_id_uses_durable_schedule_sequence_for_loop_visits(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    flow_id = f"durable_loop_activity_{uuid.uuid4().hex}"
    session_id = _session_id(flow_id)
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="loop",
    )
    state.variables = {"count": 0}
    state.current_nodes = ["loop"]
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.run_started,
        payload=RunStartedPayload(),
        snapshot=True,
    )
    loop_node = _DurableCountingActivityNode("loop", {"type": "function"})
    done_node = _StateWriteNode("done", {"type": "function"})
    flow = Flow(
        flow_id=flow_id,
        name="durable loop activity ids",
        entry="loop",
        nodes={
            "loop": loop_node,
            "done": done_node,
        },
        edges=[
            {
                "from_node": "loop",
                "to_node": "loop",
                "condition": {
                    "type": "simple",
                    "variable": "variables.count",
                    "operator": "<",
                    "value": 2,
                },
            },
            {
                "from_node": "loop",
                "to_node": "done",
                "condition": {
                    "type": "simple",
                    "variable": "variables.count",
                    "operator": ">=",
                    "value": 2,
                },
            },
        ],
        container=_runtime_container(
            DurableFlowHarness(
                workflow_runtime=runtime,
                redis_client=durable_stack.redis_client,
            ),
        ),
    )

    result = await flow.run(state)

    assert result.variables["count"] == 2
    assert loop_node.side_effect_runs == 2
    history, _ = await runtime.get_state_history(session_id)
    activity_events = [
        event
        for event in history
        if event.event_type is WorkflowEventType.activity_scheduled
        and _event_payload(event).get("activity_type") == "test_node_side_effect"
    ]
    assert len(activity_events) == 2
    activity_ids = [
        _json_str(_event_payload(event).get("activity_id"), "ActivityScheduled.activity_id")
        for event in activity_events
    ]
    assert len(set(activity_ids)) == 2
    for event, activity_id in zip(activity_events, activity_ids):
        execution_branch_id = event.execution_branch_id
        assert f":{execution_branch_id}:node:loop:" in activity_id
        assert ":schedule:" in activity_id


async def test_durable_activity_requires_attached_node_branch_context(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    flow_id = f"durable_activity_scope_{uuid.uuid4().hex}"
    session_id = _session_id(flow_id)
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="scope",
    )
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.run_started,
        payload=RunStartedPayload(),
        snapshot=True,
    )
    node = _DurableCountingActivityNode(
        "unscoped",
        {"type": "function"},
        container=_runtime_container(
            DurableFlowHarness(
                workflow_runtime=runtime,
                redis_client=durable_stack.redis_client,
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="requires execution_branch_id"):
        _ = await node.execute(state)

    history, _ = await runtime.get_state_history(session_id)
    assert all(
        event.event_type is not WorkflowEventType.activity_scheduled
        for event in history
    )
    assert node.side_effect_runs == 0


async def test_activity_schedule_requires_typed_side_effect_policy(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    session_id = _session_id("durable_activity_policy_type")
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="policy",
    )
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.user_input_applied,
        payload=_user_input_payload(state),
        snapshot=True,
    )

    raw_policy = cast(SideEffectPolicy, cast(object, "non_idempotent"))
    with pytest.raises(TypeError, match="SideEffectPolicy"):
        _ = await runtime.record_activity_scheduled(
            session_id=session_id,
            activity_id=f"{session_id}:bad-policy",
            activity_type="tool",
            input_payload={"value": 1},
            idempotency_key=f"{session_id}:bad-policy",
            side_effect_policy=raw_policy,
        )


async def test_code_edge_condition_replays_from_activity_journal_for_same_edge_scope(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    flow_id = f"durable_code_edge_{uuid.uuid4().hex}"
    session_id = _session_id(flow_id)
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="edge",
    )
    state.current_nodes = ["start"]
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.run_started,
        payload=RunStartedPayload(),
        snapshot=True,
    )
    runner = _FalseCodeConditionRunner()
    flow = Flow(
        flow_id=flow_id,
        name="durable code edge condition",
        entry="start",
        nodes={
            "start": _StateWriteNode("start", {"type": "function"}),
            "done": _StateWriteNode("done", {"type": "function"}),
        },
        edges=[
            {
                "from_node": "start",
                "to_node": "done",
                "condition": {
                    "type": "code",
                    "language": "python",
                    "code": "def condition(args, state): return False",
                    "entrypoint": "condition",
                },
            },
        ],
        container=_runtime_container(
            DurableCodeConditionHarness(
                workflow_runtime=runtime,
                redis_client=durable_stack.redis_client,
                code_runner=runner,
            ),
        ),
    )

    with pytest.raises(FlowPrematureCompletionError):
        _ = await flow.run(state)

    assert runner.calls == 1
    history, _ = await runtime.get_state_history(session_id)
    code_condition_events = [
        event
        for event in history
        if event.event_type
        in {
            WorkflowEventType.activity_scheduled,
            WorkflowEventType.activity_completed,
        }
        and _event_payload(event).get("activity_type") == "code_condition"
    ]
    assert [event.event_type for event in code_condition_events] == [
        WorkflowEventType.activity_scheduled,
        WorkflowEventType.activity_completed,
    ]
    first_code_event = code_condition_events[0]
    activity_id = _json_str(
        _event_payload(first_code_event).get("activity_id"),
        "ActivityScheduled.activity_id",
    )
    execution_branch_id = first_code_event.execution_branch_id
    assert f":{execution_branch_id}:edge:0:" in activity_id
    assert ":code_condition:evaluation:" in activity_id


async def test_optimistic_concurrency_rejects_stale_head_append(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    repository = durable_stack.repository
    session_id = _session_id("durable_concurrency")
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="first",
    )
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.user_input_applied,
        payload=_user_input_payload(state),
        snapshot=True,
    )
    stale_base = _clone_state(state)
    state.content = "second"
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.superstep_committed,
        payload=_manual_superstep_payload("second"),
    )

    stale_next = _clone_state(stale_base)
    stale_next.content = "stale"
    instance = await repository.get_instance(company_id="system", session_id=session_id)
    assert instance is not None

    with pytest.raises(WorkflowConcurrencyError):
        _ = await repository.append_state_transition(
            company_id="system",
            session_id=session_id,
            event_type=WorkflowEventType.superstep_committed,
            payload=_manual_superstep_payload("stale"),
            state_delta=build_state_delta(stale_base, stale_next),
            state_json=_state_json(stale_next),
            status=WorkflowStatus.running,
            snapshot=False,
            expected_head_sequence=1,
            expected_execution_branch_id=instance.active_execution_branch_id,
        )


async def test_activity_journal_reuses_completed_result_and_rejects_input_collision(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    session_id = _session_id("durable_activity")
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="activity",
    )
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.user_input_applied,
        payload=_user_input_payload(state),
        snapshot=True,
    )

    input_payload: JsonObject = {"tool_name": "side_effect", "arguments": {"value": 1}}
    activity_id = f"{session_id}:tool-call-1"
    replay_activity_id = f"{session_id}:tool-call-1-replay"
    collision_activity_id = f"{session_id}:tool-call-1-collision"
    idempotency_key = activity_id
    scheduled = await runtime.record_activity_scheduled(
        session_id=session_id,
        activity_id=activity_id,
        activity_type="tool",
        input_payload=input_payload,
        node_id="node-a",
        tool_call_id="tool-call-1",
        idempotency_key=idempotency_key,
        side_effect_policy=SideEffectPolicy.non_idempotent,
    )
    assert scheduled is None
    assert await runtime.record_activity_started(activity_id=activity_id)

    after = _clone_state(state)
    after.variables = {"side_effect_result": "done"}
    delta = build_state_delta(state, after)
    result_json: JsonObject = {
        "result": "done",
        "state_delta": delta.model_dump(mode="json", exclude_none=False),
    }
    assert await runtime.record_activity_completed(
        activity_id=activity_id,
        result_json=result_json,
    )

    completed = await runtime.get_completed_activity_result(
        session_id=session_id,
        activity_id=activity_id,
        idempotency_key=idempotency_key,
        input_payload=input_payload,
    )
    assert completed == result_json

    replayed = await runtime.record_activity_scheduled(
        session_id=session_id,
        activity_id=replay_activity_id,
        activity_type="tool",
        input_payload=input_payload,
        node_id="node-a",
        tool_call_id="tool-call-1-replay",
        idempotency_key=idempotency_key,
        side_effect_policy=SideEffectPolicy.non_idempotent,
    )
    assert replayed == result_json

    with pytest.raises(ValueError, match="different input"):
        _ = await runtime.record_activity_scheduled(
            session_id=session_id,
            activity_id=collision_activity_id,
            activity_type="tool",
            input_payload={"tool_name": "side_effect", "arguments": {"value": 2}},
            node_id="node-a",
            tool_call_id="tool-call-1-collision",
            idempotency_key=idempotency_key,
            side_effect_policy=SideEffectPolicy.non_idempotent,
        )

    history, _ = await runtime.get_state_history(session_id)
    event_types = [event.event_type.value for event in history]
    assert event_types.count(WorkflowEventType.activity_scheduled.value) == 1
    assert event_types.count(WorkflowEventType.activity_started.value) == 1
    assert event_types.count(WorkflowEventType.activity_completed.value) == 1


async def test_non_idempotent_failed_activity_requires_explicit_compensation(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    session_id = _session_id("durable_non_idempotent_gate")
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="activity",
    )
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.user_input_applied,
        payload=_user_input_payload(state),
        snapshot=True,
    )

    input_payload: JsonObject = {"request": {"value": 1}}
    activity_id = f"{session_id}:dangerous-call"
    scheduled = await runtime.record_activity_scheduled(
        session_id=session_id,
        activity_id=activity_id,
        activity_type="external_api",
        input_payload=input_payload,
        node_id="api-node",
        idempotency_key=activity_id,
        side_effect_policy=SideEffectPolicy.non_idempotent,
    )
    assert scheduled is None
    assert await runtime.record_activity_started(activity_id=activity_id)
    assert await runtime.record_activity_completed(
        activity_id=activity_id,
        error="network broke after side effect boundary",
    )

    with pytest.raises(NonIdempotentActivityReplayBlockedError):
        _ = await runtime.record_activity_scheduled(
            session_id=session_id,
            activity_id=activity_id,
            activity_type="external_api",
            input_payload=input_payload,
            node_id="api-node",
            idempotency_key=activity_id,
            side_effect_policy=SideEffectPolicy.non_idempotent,
        )


async def test_idempotent_activity_retry_preserves_append_only_attempt_history(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    session_id = _session_id("durable_idempotent_attempts")
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="activity",
    )
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.user_input_applied,
        payload=_user_input_payload(state),
        snapshot=True,
    )

    input_payload: JsonObject = {"request": {"value": 7}}
    activity_id = f"{session_id}:retryable-call"
    assert await runtime.record_activity_scheduled(
        session_id=session_id,
        activity_id=activity_id,
        activity_type="external_api",
        input_payload=input_payload,
        node_id="api-node",
        idempotency_key=activity_id,
        side_effect_policy=SideEffectPolicy.idempotent,
    ) is None
    assert await runtime.record_activity_started(activity_id=activity_id)
    assert await runtime.record_activity_completed(
        activity_id=activity_id,
        error="transient transport failure",
    )

    assert await runtime.record_activity_scheduled(
        session_id=session_id,
        activity_id=activity_id,
        activity_type="external_api",
        input_payload=input_payload,
        node_id="api-node",
        idempotency_key=activity_id,
        side_effect_policy=SideEffectPolicy.idempotent,
    ) is None
    assert await runtime.record_activity_started(activity_id=activity_id)
    result_json: JsonObject = {"result": "ok", "state_delta": {}}
    assert await runtime.record_activity_completed(
        activity_id=activity_id,
        result_json=result_json,
    )

    async with durable_stack.storage.get_session() as session:
        attempts_result = await session.execute(
            select(ActivityAttempts)
            .where(ActivityAttempts.activity_id == activity_id)
            .order_by(ActivityAttempts.attempt.asc())
        )
        attempts = list(attempts_result.scalars().all())

    assert len(attempts) == 2
    first_attempt, second_attempt = attempts
    assert first_attempt.activity_attempt_id == f"{activity_id}:attempt:1"
    assert first_attempt.attempt == 1
    assert first_attempt.status == ActivityStatus.failed.value
    assert first_attempt.error == "transient transport failure"
    assert first_attempt.result_json is None
    assert first_attempt.started_at is not None
    assert first_attempt.completed_at is not None
    assert second_attempt.activity_attempt_id == f"{activity_id}:attempt:2"
    assert second_attempt.attempt == 2
    assert second_attempt.status == ActivityStatus.completed.value
    assert second_attempt.error is None
    assert require_json_object(second_attempt.result_json, "attempt_2.result_json") == result_json
    assert second_attempt.started_at is not None
    assert second_attempt.completed_at is not None

    history, _ = await runtime.get_state_history(session_id)
    activity_events = [
        event
        for event in history
        if event.event_type
        in {
            WorkflowEventType.activity_scheduled,
            WorkflowEventType.activity_started,
            WorkflowEventType.activity_failed,
            WorkflowEventType.activity_completed,
        }
    ]
    lifecycle = [
        (
            event.event_type,
            _activity_payload(event.payload, "WorkflowEvent.payload").activity_attempt_id,
            _activity_payload(event.payload, "WorkflowEvent.payload").attempt,
            _activity_payload(event.payload, "WorkflowEvent.payload").activity_status,
        )
        for event in activity_events
    ]
    assert lifecycle == [
        (
            WorkflowEventType.activity_scheduled,
            f"{activity_id}:attempt:1",
            1,
            ActivityStatus.scheduled,
        ),
        (
            WorkflowEventType.activity_started,
            f"{activity_id}:attempt:1",
            1,
            ActivityStatus.started,
        ),
        (
            WorkflowEventType.activity_failed,
            f"{activity_id}:attempt:1",
            1,
            ActivityStatus.failed,
        ),
        (
            WorkflowEventType.activity_scheduled,
            f"{activity_id}:attempt:2",
            2,
            ActivityStatus.scheduled,
        ),
        (
            WorkflowEventType.activity_started,
            f"{activity_id}:attempt:2",
            2,
            ActivityStatus.started,
        ),
        (
            WorkflowEventType.activity_completed,
            f"{activity_id}:attempt:2",
            2,
            ActivityStatus.completed,
        ),
    ]


async def test_idempotent_started_activity_retries_only_after_lease_expiry(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    session_id = _session_id("durable_expired_activity_lease")
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="activity",
    )
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.user_input_applied,
        payload=_user_input_payload(state),
        snapshot=True,
    )

    input_payload: JsonObject = {"request": {"value": 11}}
    activity_id = f"{session_id}:leased-call"
    assert await runtime.record_activity_scheduled(
        session_id=session_id,
        activity_id=activity_id,
        activity_type="external_api",
        input_payload=input_payload,
        node_id="api-node",
        idempotency_key=activity_id,
        side_effect_policy=SideEffectPolicy.idempotent,
    ) is None
    assert await runtime.record_activity_started(activity_id=activity_id)

    with pytest.raises(RuntimeError, match="still leased"):
        _ = await runtime.record_activity_scheduled(
            session_id=session_id,
            activity_id=activity_id,
            activity_type="external_api",
            input_payload=input_payload,
            node_id="api-node",
            idempotency_key=activity_id,
            side_effect_policy=SideEffectPolicy.idempotent,
        )

    async with durable_stack.storage.get_session() as session:
        _ = await session.execute(
            update(ActivityAttempts)
            .where(ActivityAttempts.activity_attempt_id == f"{activity_id}:attempt:1")
            .values(lease_until=utc_now() - timedelta(seconds=1))
        )
        await session.commit()

    assert await runtime.record_activity_scheduled(
        session_id=session_id,
        activity_id=activity_id,
        activity_type="external_api",
        input_payload=input_payload,
        node_id="api-node",
        idempotency_key=activity_id,
        side_effect_policy=SideEffectPolicy.idempotent,
    ) is None
    assert await runtime.record_activity_started(activity_id=activity_id)
    result_json: JsonObject = {"result": "ok-after-lease", "state_delta": {}}
    assert await runtime.record_activity_completed(
        activity_id=activity_id,
        result_json=result_json,
    )

    async with durable_stack.storage.get_session() as session:
        attempts_result = await session.execute(
            select(ActivityAttempts)
            .where(ActivityAttempts.activity_id == activity_id)
            .order_by(ActivityAttempts.attempt.asc())
        )
        attempts = list(attempts_result.scalars().all())

    assert len(attempts) == 2
    assert attempts[0].status == ActivityStatus.failed.value
    assert attempts[0].error == "activity lease expired"
    assert attempts[0].lease_until is None
    assert attempts[1].status == ActivityStatus.completed.value
    assert require_json_object(attempts[1].result_json, "attempt_2.result_json") == result_json

    history, _ = await runtime.get_state_history(session_id)
    lifecycle = [
        (
            event.event_type,
            _activity_payload(event.payload, "WorkflowEvent.payload").activity_attempt_id,
            _activity_payload(event.payload, "WorkflowEvent.payload").attempt,
            _activity_payload(event.payload, "WorkflowEvent.payload").activity_status,
        )
        for event in history
        if event.event_type
        in {
            WorkflowEventType.activity_scheduled,
            WorkflowEventType.activity_started,
            WorkflowEventType.activity_failed,
            WorkflowEventType.activity_completed,
        }
    ]
    assert lifecycle == [
        (
            WorkflowEventType.activity_scheduled,
            f"{activity_id}:attempt:1",
            1,
            ActivityStatus.scheduled,
        ),
        (
            WorkflowEventType.activity_started,
            f"{activity_id}:attempt:1",
            1,
            ActivityStatus.started,
        ),
        (
            WorkflowEventType.activity_failed,
            f"{activity_id}:attempt:1",
            1,
            ActivityStatus.failed,
        ),
        (
            WorkflowEventType.activity_scheduled,
            f"{activity_id}:attempt:2",
            2,
            ActivityStatus.scheduled,
        ),
        (
            WorkflowEventType.activity_started,
            f"{activity_id}:attempt:2",
            2,
            ActivityStatus.started,
        ),
        (
            WorkflowEventType.activity_completed,
            f"{activity_id}:attempt:2",
            2,
            ActivityStatus.completed,
        ),
    ]


async def test_activity_journal_is_isolated_by_execution_branch(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    session_id = _session_id("durable_activity_branch")
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="activity",
    )
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.user_input_applied,
        payload=_user_input_payload(state),
        snapshot=True,
    )

    input_payload: JsonObject = {"request": {"value": 1}}
    logical_key = f"{session_id}:logical-side-effect"
    first_activity_id = f"{session_id}:first-branch-call"
    assert await runtime.record_activity_scheduled(
        session_id=session_id,
        activity_id=first_activity_id,
        activity_type="mcp",
        input_payload=input_payload,
        node_id="mcp-node",
        idempotency_key=logical_key,
        side_effect_policy=SideEffectPolicy.non_idempotent,
    ) is None
    assert await runtime.record_activity_started(activity_id=first_activity_id)
    first_result: JsonObject = {"result": "future-branch-result", "state_delta": {}}
    assert await runtime.record_activity_completed(
        activity_id=first_activity_id,
        result_json=first_result,
    )

    fork = await runtime.fork_state_at_sequence(session_id, 1, activate=True)
    second_activity_id = f"{session_id}:fork-branch-call"
    fork_scheduled = await runtime.record_activity_scheduled(
        session_id=session_id,
        activity_id=second_activity_id,
        activity_type="mcp",
        input_payload=input_payload,
        node_id="mcp-node",
        idempotency_key=logical_key,
        side_effect_policy=SideEffectPolicy.non_idempotent,
    )

    assert fork_scheduled is None
    history, _ = await runtime.get_state_history(
        session_id,
        execution_branch_id=fork.execution_branch_id,
    )
    scheduled_events = [
        event
        for event in history
        if event.event_type is WorkflowEventType.activity_scheduled
    ]
    assert len(scheduled_events) == 1
    assert _event_payload(scheduled_events[0]).get("activity_id") == second_activity_id


async def test_flow_node_records_child_workflow_as_separate_durable_history(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    parent_flow_id = f"durable_parent_child_{uuid.uuid4().hex}"
    child_flow_id = f"durable_child_{uuid.uuid4().hex}"
    session_id = _session_id(parent_flow_id)
    factory = DurableChildFlowFactory()
    container = _runtime_container(
        DurableChildWorkflowHarness(
            workflow_runtime=runtime,
            redis_client=durable_stack.redis_client,
            flow_factory=factory,
        )
    )
    child_flow = Flow(
        flow_id=child_flow_id,
        name="child",
        entry="child_write",
        nodes={"child_write": _StateWriteNode("child_write", {"type": "function"})},
        edges=[],
        config={"version": "child-v1"},
        container=container,
    )
    factory.set_flow(child_flow)
    parent_flow = Flow(
        flow_id=parent_flow_id,
        name="parent",
        entry="call_child",
        nodes={
            "call_child": FlowNode(
                "call_child",
                {
                    "type": "flow",
                    "flow_id": child_flow_id,
                    "branch_id": "default",
                },
                container=container,
            )
        },
        edges=[],
        container=container,
    )
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="start",
    )
    state.current_nodes = ["call_child"]
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.run_started,
        payload=RunStartedPayload(),
        snapshot=True,
    )

    result = await parent_flow.run(state)

    link = result.child_workflows["call_child"]
    assert link.status == "completed"
    assert link.child_flow_id == child_flow_id
    assert link.child_flow_branch_id == "default"
    assert result.variables["child_write"] == "done"

    parent_history, _ = await runtime.get_state_history(session_id)
    parent_child_events = [
        event
        for event in parent_history
        if event.event_type
        in {
            WorkflowEventType.child_workflow_started,
            WorkflowEventType.child_workflow_completed,
        }
    ]
    assert [event.event_type for event in parent_child_events] == [
        WorkflowEventType.child_workflow_started,
        WorkflowEventType.child_workflow_completed,
    ]
    for event in parent_child_events:
        payload = _child_workflow_payload(event.payload, "WorkflowEvent.payload")
        assert payload.child_session_id == link.child_session_id
        child_position = payload.child_execution_position
        assert child_position is not None
        assert isinstance(child_position.execution_branch_id, str)

    child_history, _ = await runtime.get_state_history(link.child_session_id)
    child_event_types = [event.event_type.value for event in child_history]
    assert child_event_types[:4] == [
        WorkflowEventType.run_started.value,
        WorkflowEventType.superstep_started.value,
        WorkflowEventType.node_scheduled.value,
        WorkflowEventType.node_write_recorded.value,
    ]
    assert WorkflowEventType.superstep_committed.value in child_event_types


async def test_flow_node_resume_uses_same_child_workflow_session_after_interrupt(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    parent_flow_id = f"durable_parent_child_resume_{uuid.uuid4().hex}"
    child_flow_id = f"durable_child_resume_{uuid.uuid4().hex}"
    session_id = _session_id(parent_flow_id)
    factory = DurableChildFlowFactory()
    container = _runtime_container(
        DurableChildWorkflowHarness(
            workflow_runtime=runtime,
            redis_client=durable_stack.redis_client,
            flow_factory=factory,
        )
    )
    child_flow = Flow(
        flow_id=child_flow_id,
        name="child resume",
        entry="ask",
        nodes={"ask": _ChildInterruptUntilAnswerNode("ask", {"type": "function"})},
        edges=[],
        config={"version": "child-v1"},
        container=container,
    )
    factory.set_flow(child_flow)
    parent_flow = Flow(
        flow_id=parent_flow_id,
        name="parent resume",
        entry="call_child",
        nodes={
            "call_child": FlowNode(
                "call_child",
                {
                    "type": "flow",
                    "flow_id": child_flow_id,
                    "branch_id": "default",
                },
                container=container,
            )
        },
        edges=[],
        container=container,
    )
    state = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_id.split(":", 1)[1],
        user_id="durable-user",
        session_id=session_id,
        content="start",
    )
    state.current_nodes = ["call_child"]
    _ = await runtime.save_state(
        session_id,
        state,
        event_type=WorkflowEventType.run_started,
        payload=RunStartedPayload(),
        snapshot=True,
    )

    interrupted = await parent_flow.run(state)

    assert interrupted.interrupt is not None
    assert interrupted.current_nodes == ["call_child"]
    first_path = interrupted.interrupt_path[0]
    assert first_path.node_type == "flow"
    assert first_path.node_id == "call_child"
    child_session_id = _json_str(first_path.child_session_id, "interrupt_path.child_session_id")

    loaded_parent = await runtime.get_state(session_id)
    assert loaded_parent is not None
    loaded_parent.content = "answer"
    resumed = await parent_flow.run(loaded_parent)

    assert resumed.interrupt is None
    assert resumed.variables["child_answer"] == "answer"
    assert resumed.child_workflows["call_child"].child_session_id == child_session_id
    assert resumed.child_workflows["call_child"].status == "completed"

    child_history, _ = await runtime.get_state_history(child_session_id)
    assert [event.event_type.value for event in child_history].count(
        WorkflowEventType.run_started.value
    ) == 1

    parent_history, _ = await runtime.get_state_history(session_id)
    parent_child_event_types = [
        event.event_type.value
        for event in parent_history
        if event.event_type.value.startswith("ChildWorkflow")
    ]
    assert parent_child_event_types.count(WorkflowEventType.child_workflow_started.value) == 1
    assert WorkflowEventType.child_workflow_suspended.value in parent_child_event_types
    assert WorkflowEventType.child_workflow_completed.value in parent_child_event_types


async def test_session_search_uses_denormalized_instance_metadata(
    durable_stack: DurableStack,
) -> None:
    runtime = durable_stack.runtime
    flow_id = f"durable_search_{uuid.uuid4().hex}"
    session_a = _session_id(flow_id)
    session_b = _session_id(flow_id)

    state_a = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_a.split(":", 1)[1],
        user_id="user-a",
        session_id=session_a,
        content="a",
        branch_id="alpha",
    )
    state_b = create_initial_state(
        task_id=f"task-{uuid.uuid4().hex}",
        context_id=session_b.split(":", 1)[1],
        user_id="user-b",
        session_id=session_b,
        content="b",
        branch_id="beta",
    )

    _ = await runtime.save_state(
        session_a,
        state_a,
        event_type=WorkflowEventType.user_input_applied,
        payload=_user_input_payload(state_a),
        snapshot=True,
    )
    _ = await runtime.save_state(
        session_b,
        state_b,
        event_type=WorkflowEventType.user_input_applied,
        payload=_user_input_payload(state_b),
        snapshot=True,
    )

    sessions, total = await runtime.search_sessions(
        flow_id=flow_id,
        user_id="user-a",
        branch_id="alpha",
        limit=10,
        offset=0,
    )

    assert total == 1
    assert [session.session_id for session in sessions] == [session_a]
