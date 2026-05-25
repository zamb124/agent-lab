"""Тесты durable workflow projection для ExecutionState."""

from __future__ import annotations

import uuid

import pytest
from a2a.types import Message, Part, Role, TextPart

from apps.flows.src.container import get_container
from apps.flows.src.durable_execution import (
    NodeFailedPayload,
    RunStartedPayload,
    SuperstepCommittedPayload,
    SuperstepStartedPayload,
    UserInputAppliedPayload,
    WorkflowEventType,
    create_initial_state,
)
from apps.flows.src.durable_execution.manager import DurableWorkflowRuntime
from core.state import ExecutionState


def _msg(text: str, role: Role = Role.user) -> Message:
    return Message(
        message_id=str(uuid.uuid4()),
        role=role,
        parts=[Part(root=TextPart(text=text))],
    )


def _user_input_payload(state: ExecutionState) -> UserInputAppliedPayload:
    return UserInputAppliedPayload(
        task_id=state.task_id,
        context_id=state.context_id,
        is_resume=False,
    )


def _manual_superstep_payload(step: str) -> SuperstepCommittedPayload:
    return SuperstepCommittedPayload(completed_nodes=[step], next_nodes=[])


@pytest.fixture
def workflow_runtime(app: object) -> DurableWorkflowRuntime:
    _ = app
    return get_container().workflow_runtime


class TestDurableWorkflowProjection:
    def test_execution_state_rejects_forbidden_terminal_field_names(self):
        with pytest.raises(ValueError, match="system field names"):
            _ = ExecutionState.model_validate(
                {
                    "task_id": "test-task",
                    "context_id": "test-context",
                    "user_id": "test-user",
                    "session_id": "test-flow:test-context",
                    "terminal_status": "completed",
                }
            )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-flow:test-context",
        )
        with pytest.raises(ValueError, match="system field name"):
            state.terminal_error = "failed"

    @pytest.mark.asyncio
    async def test_get_state_returns_none_for_new_session(
        self,
        workflow_runtime: DurableWorkflowRuntime,
    ):
        state = await workflow_runtime.get_state(f"new_session:{uuid.uuid4().hex}")
        assert state is None

    @pytest.mark.asyncio
    async def test_save_and_get_projection_with_a2a_messages(
        self,
        workflow_runtime: DurableWorkflowRuntime,
    ):
        session_id = f"test_save_get_state:{uuid.uuid4().hex}"
        state = create_initial_state(
            task_id=f"task-{uuid.uuid4().hex}",
            context_id=session_id.split(":", 1)[1],
            user_id="test-user",
            session_id=session_id,
        )
        state.messages = [_msg("Hello", Role.user)]
        state.variables = {"key": "value"}

        _ = await workflow_runtime.save_state(
            session_id,
            state,
            event_type=WorkflowEventType.user_input_applied,
            payload=_user_input_payload(state),
            snapshot=True,
        )
        loaded = await workflow_runtime.get_state(session_id)

        assert loaded is not None
        assert len(loaded.messages) == 1
        assert isinstance(loaded.messages[0], Message)
        assert loaded.messages[0].role == Role.user
        root = loaded.messages[0].parts[0].root
        assert isinstance(root, TextPart)
        assert root.text == "Hello"
        assert loaded.variables == {"key": "value"}

    @pytest.mark.asyncio
    async def test_history_and_load_state_at_sequence(
        self,
        workflow_runtime: DurableWorkflowRuntime,
    ):
        session_id = f"history_flow:{uuid.uuid4().hex}"
        state = create_initial_state(
            task_id=f"task-{uuid.uuid4().hex}",
            context_id=session_id.split(":", 1)[1],
            user_id="test-user",
            session_id=session_id,
            content="first",
        )
        state.variables = {"step": 1}

        _ = await workflow_runtime.save_state(
            session_id,
            state,
            event_type=WorkflowEventType.user_input_applied,
            payload=_user_input_payload(state),
            snapshot=True,
        )
        state.content = "second"
        state.variables["step"] = 2
        _ = await workflow_runtime.save_state(
            session_id,
            state,
            event_type=WorkflowEventType.superstep_committed,
            payload=_manual_superstep_payload("step-2"),
        )

        history, total = await workflow_runtime.get_state_history(session_id)
        state_at_first = await workflow_runtime.load_state_at_sequence(session_id, 1)
        state_at_second = await workflow_runtime.load_state_at_sequence(session_id, 2)

        assert total == 2
        assert [event.sequence for event in history] == [1, 2]
        assert state_at_first is not None
        assert state_at_first.content == "first"
        assert state_at_first.variables == {"step": 1}
        assert state_at_second is not None
        assert state_at_second.content == "second"
        assert state_at_second.variables == {"step": 2}

    @pytest.mark.asyncio
    async def test_fork_rewind_and_manual_patch_are_branch_based(
        self,
        workflow_runtime: DurableWorkflowRuntime,
    ):
        session_id = f"time_travel_flow:{uuid.uuid4().hex}"
        state = create_initial_state(
            task_id=f"task-{uuid.uuid4().hex}",
            context_id=session_id.split(":", 1)[1],
            user_id="test-user",
            session_id=session_id,
            content="first",
        )
        state.variables = {"step": 1}

        _ = await workflow_runtime.save_state(
            session_id,
            state,
            event_type=WorkflowEventType.user_input_applied,
            payload=_user_input_payload(state),
            snapshot=True,
        )
        state.content = "second"
        state.variables = {"step": 2}
        _ = await workflow_runtime.save_state(
            session_id,
            state,
            event_type=WorkflowEventType.superstep_committed,
            payload=_manual_superstep_payload("step-2"),
        )

        fork = await workflow_runtime.fork_state_at_sequence(session_id, 1)
        fork_state = await workflow_runtime.load_state_at_sequence(
            session_id,
            fork.sequence,
            execution_branch_id=fork.execution_branch_id,
        )
        active_before_rewind = await workflow_runtime.get_state(session_id)

        assert fork_state is not None
        assert fork_state.content == "first"
        assert active_before_rewind is not None
        assert active_before_rewind.content == "second"

        rewind = await workflow_runtime.rewind_to_sequence(session_id, 1)
        rewound = await workflow_runtime.get_state(session_id)
        assert rewound is not None
        assert rewound.content == "first"

        patched = ExecutionState.model_validate(
            rewound.model_dump(mode="json", exclude_none=False)
        )
        patched.content = "patched"
        patch = await workflow_runtime.patch_state_at_sequence(
            session_id,
            rewind.sequence,
            patched,
        )
        patched_loaded = await workflow_runtime.get_state(session_id)
        branches = await workflow_runtime.list_branches(session_id)

        assert patched_loaded is not None
        assert patched_loaded.content == "patched"
        assert patch.reason.value == "manual_patch"
        assert len(branches) == 4
        assert sum(1 for branch in branches if branch.is_active) == 1

    @pytest.mark.asyncio
    async def test_retry_from_failure_restores_failed_node_boundary(
        self,
        workflow_runtime: DurableWorkflowRuntime,
    ):
        session_id = f"retry_flow:{uuid.uuid4().hex}"
        state = create_initial_state(
            task_id=f"task-{uuid.uuid4().hex}",
            context_id=session_id.split(":", 1)[1],
            user_id="test-user",
            session_id=session_id,
            content="start",
        )
        state.current_nodes = ["n1"]

        _ = await workflow_runtime.save_state(
            session_id,
            state,
            event_type=WorkflowEventType.superstep_started,
            payload=SuperstepStartedPayload(current_nodes=["n1"]),
            snapshot=True,
        )
        _ = await workflow_runtime.save_state(
            session_id,
            state,
            event_type=WorkflowEventType.node_failed,
            payload=NodeFailedPayload(
                failed_nodes=["n1"],
                current_nodes=["n1"],
                error="boom",
                recover_sequence=1,
                preserved_node_writes=[],
            ),
        )

        retry = await workflow_runtime.retry_from_failure(session_id)
        retried = await workflow_runtime.get_state(session_id)
        history, _ = await workflow_runtime.get_state_history(session_id)

        assert retry.reason.value == "retry"
        assert retried is not None
        assert retried.current_nodes == ["n1"]
        assert history[-1].event_type is WorkflowEventType.retry_scheduled

    @pytest.mark.asyncio
    async def test_projection_rehydrates_after_cache_delete(
        self,
        workflow_runtime: DurableWorkflowRuntime,
    ):
        session_id = f"rehydrate_flow:{uuid.uuid4().hex}"
        state = create_initial_state(
            task_id=f"task-{uuid.uuid4().hex}",
            context_id=session_id.split(":", 1)[1],
            user_id="test-user",
            session_id=session_id,
            content="cached",
        )

        _ = await workflow_runtime.save_state(
            session_id,
            state,
            event_type=WorkflowEventType.state_projection_committed,
            snapshot=True,
        )
        assert await workflow_runtime.delete_state(session_id) is True

        loaded = await workflow_runtime.get_state(session_id)
        assert loaded is not None
        assert loaded.content == "cached"

    @pytest.mark.asyncio
    async def test_terminal_event_updates_projection(
        self,
        workflow_runtime: DurableWorkflowRuntime,
    ):
        session_id = f"terminal_flow:{uuid.uuid4().hex}"
        state = create_initial_state(
            task_id=f"task-{uuid.uuid4().hex}",
            context_id=session_id.split(":", 1)[1],
            user_id="test-user",
            session_id=session_id,
        )
        state.response = "done"

        _ = await workflow_runtime.save_state(
            session_id,
            state,
            event_type=WorkflowEventType.run_started,
            payload=RunStartedPayload(),
            snapshot=True,
        )
        _ = await workflow_runtime.save_terminal_state(session_id, state, "completed")

        loaded = await workflow_runtime.get_state(session_id)
        history, total = await workflow_runtime.get_state_history(session_id)

        assert loaded is not None
        assert loaded.terminal_task_state == "completed"
        assert loaded.response == "done"
        assert total == 2
        assert history[-1].event_type is WorkflowEventType.run_terminal

    @pytest.mark.asyncio
    async def test_resolve_session_by_task_or_context(
        self,
        workflow_runtime: DurableWorkflowRuntime,
    ):
        session_id = f"resolve_flow:{uuid.uuid4().hex}"
        context_id = session_id.split(":", 1)[1]
        task_id = f"task-{uuid.uuid4().hex}"
        state = create_initial_state(
            task_id=task_id,
            context_id=context_id,
            user_id="test-user",
            session_id=session_id,
        )

        _ = await workflow_runtime.save_state(
            session_id,
            state,
            event_type=WorkflowEventType.user_input_applied,
            payload=_user_input_payload(state),
            snapshot=True,
        )

        assert (
            await workflow_runtime.resolve_session_id_by_flow_and_identifier(
                "resolve_flow",
                task_id,
            )
            == session_id
        )
        assert (
            await workflow_runtime.resolve_session_id_by_flow_and_identifier(
                "resolve_flow",
                context_id,
            )
            == session_id
        )
