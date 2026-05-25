from __future__ import annotations

from typing import cast

import pytest

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.durable_execution import SideEffectPolicy
from apps.flows.src.models import NodeConfig
from apps.flows.src.models.enums import NodeType
from apps.flows.src.runtime.a2a_messages import build_assistant_message, build_user_message
from apps.flows.src.runtime.llm_context_memory import (
    RuntimeMemoryCloseDecision,
    RuntimeMemoryWriteCommand,
    apply_runtime_memory_cursor_advance,
    apply_runtime_memory_write_result,
    build_state_messages_memory_close_decision,
    prune_state_messages_to_memory_cursor_for_runtime,
    resolve_memory_context_source_for_runtime,
    write_runtime_memory_episode,
)
from apps.flows.src.runtime.runners.llm_runner import LlmNodeRunner
from core.llm_context import (
    LLMContextBudget,
    LLMContextMemoryEpisode,
    LLMContextMemoryRecallRequest,
    LLMContextMemoryRecord,
    LLMContextProfile,
    LLMContextRetrievalPolicy,
)
from core.state import ExecutionState
from core.types import JsonObject


class RecordingStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0
        self.episodes: list[LLMContextMemoryEpisode] = []

    async def write_episode(self, episode: LLMContextMemoryEpisode) -> str:
        self.calls += 1
        if self.fail:
            raise RuntimeError("memory write failed")
        self.episodes.append(episode)
        return episode.memory_id

    async def recall(self, _request: LLMContextMemoryRecallRequest) -> list[LLMContextMemoryRecord]:
        return []


class RecordingWorkflowRuntime:
    def __init__(self) -> None:
        self.completed_result: JsonObject | None = None
        self.scheduled: list[JsonObject] = []
        self.started: list[str] = []
        self.completed: list[JsonObject] = []

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
        self.scheduled.append(
            {
                "session_id": session_id,
                "activity_id": activity_id,
                "activity_type": activity_type,
                "input_payload": input_payload,
                "node_id": node_id,
                "tool_call_id": tool_call_id,
                "idempotency_key": idempotency_key,
                "side_effect_policy": side_effect_policy.value,
            }
        )
        return self.completed_result

    async def record_activity_started(self, *, activity_id: str) -> bool:
        self.started.append(activity_id)
        return True

    async def record_activity_completed(
        self,
        *,
        activity_id: str,
        result_json: JsonObject | None = None,
        error: str | None = None,
    ) -> bool:
        self.completed.append(
            {
                "activity_id": activity_id,
                "result_json": result_json,
                "error": error,
            }
        )
        if result_json is not None:
            self.completed_result = result_json
        return True


class MemoryRuntimeContainer:
    def __init__(
        self,
        *,
        store: RecordingStore,
        workflow_runtime: RecordingWorkflowRuntime,
    ) -> None:
        self.llm_context_memory_store = store
        self.workflow_runtime = workflow_runtime


def _command_from_decision(
    state: ExecutionState,
    decision: RuntimeMemoryCloseDecision | None,
    *,
    node_id: str = "agent",
) -> RuntimeMemoryWriteCommand:
    assert decision is not None
    assert decision.episode is not None
    return RuntimeMemoryWriteCommand(
        session_id=state.session_id,
        execution_branch_id="branch-exec",
        node_schedule_sequence=12,
        node_id=node_id,
        cursor_key=decision.cursor_key,
        cursor=decision.cursor,
        next_cursor=decision.next_cursor,
        episode=decision.episode,
        compaction=decision.compaction,
    )


def _runner(
    *,
    store: RecordingStore,
    workflow_runtime: RecordingWorkflowRuntime,
    policy: LLMContextProfile | None = None,
) -> LlmNodeRunner:
    return LlmNodeRunner(
        node_config=NodeConfig(
            node_id="agent",
            type=NodeType.LLM_NODE,
            name="Agent",
            prompt="You are a memory writer.",
        ),
        tools=[],
        llm=None,
        prompt="You are a memory writer.",
        container=cast(
            FlowRuntimeContainer,
            MemoryRuntimeContainer(store=store, workflow_runtime=workflow_runtime),
        ),
        llm_context_policy=policy,
    )


def test_resolves_memory_context_source_from_runtime_state() -> None:
    store = RecordingStore()
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
        branch_id="default",
    )
    source = resolve_memory_context_source_for_runtime(
        store=store,
        state=state,
        node_id="agent",
    )

    assert source is not None
    assert source.store is store
    assert source.session_id == "flow:ctx"
    assert source.flow_id == "flow"
    assert source.branch_id == "default"
    assert source.node_id == "agent"
    assert source.user_id == "user"


def test_memory_context_source_is_absent_without_state() -> None:
    assert resolve_memory_context_source_for_runtime(
        store=RecordingStore(),
        state=None,
        node_id="agent",
    ) is None


def _policy() -> LLMContextProfile:
    return LLMContextProfile(
        mode="smart",
        budget=LLMContextBudget(
            max_input_tokens=1_000,
            output_reserve_tokens=10,
            reasoning_reserve_tokens=0,
            safety_buffer_tokens=10,
            active_window_tokens=4,
            memory_tokens=100,
            rag_tokens=100,
            tool_result_tokens=100,
        ),
        memory="session",
        retrieval=LLMContextRetrievalPolicy(mode="hybrid", top_k=4, rerank=False),
        compaction="auto",
        cache="auto",
    )


def _force_policy() -> LLMContextProfile:
    return _policy().model_copy(update={"compaction": "force"})


@pytest.mark.asyncio
async def test_closes_runtime_state_messages_and_updates_cursor() -> None:
    store = RecordingStore()
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
        branch_id="default",
        messages=[
            build_user_message("old alpha beta gamma", "agent", context_id="ctx", task_id="task"),
            build_assistant_message("old reply delta epsilon", "agent", context_id="ctx", task_id="task"),
            build_user_message("current question", "agent", context_id="ctx", task_id="task"),
        ],
    )

    decision = build_state_messages_memory_close_decision(
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=state.messages,
        compaction="raw",
    )
    assert decision is not None
    assert decision.episode is not None
    assert store.calls == 0

    result = await write_runtime_memory_episode(
        store=store,
        command=_command_from_decision(state, decision),
        summarize_episode=None,
    )
    apply_runtime_memory_write_result(state, result)
    changed_again = build_state_messages_memory_close_decision(
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=state.messages,
        compaction="raw",
    )

    assert changed_again is None
    assert state.llm_context_memory_cursor == {"session:flow:ctx": 2}
    assert len(store.episodes) == 1
    assert store.episodes[0].session_id == "flow:ctx"
    assert "old alpha beta gamma" in store.episodes[0].content


@pytest.mark.asyncio
async def test_runtime_memory_write_failure_propagates_without_cursor_advance() -> None:
    store = RecordingStore(fail=True)
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
        branch_id="default",
        messages=[
            build_user_message("old alpha beta gamma", "agent", context_id="ctx", task_id="task"),
            build_assistant_message("old reply delta epsilon", "agent", context_id="ctx", task_id="task"),
            build_user_message("current question", "agent", context_id="ctx", task_id="task"),
        ],
    )

    decision = build_state_messages_memory_close_decision(
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=state.messages,
        compaction="raw",
    )
    with pytest.raises(RuntimeError, match="memory write failed"):
        await write_runtime_memory_episode(
            store=store,
            command=_command_from_decision(state, decision),
            summarize_episode=None,
        )

    assert state.llm_context_memory_cursor == {}
    assert store.episodes == []


@pytest.mark.asyncio
async def test_runtime_memory_write_summarizes_episode_before_persisting() -> None:
    store = RecordingStore()
    raw_inputs: list[str] = []
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
        branch_id="default",
        messages=[
            build_user_message("old alpha beta gamma", "agent", context_id="ctx", task_id="task"),
            build_assistant_message("old reply delta epsilon", "agent", context_id="ctx", task_id="task"),
            build_user_message("current question", "agent", context_id="ctx", task_id="task"),
        ],
    )

    async def summarize(raw: str) -> str:
        raw_inputs.append(raw)
        return "Remembered compact alpha preference."

    decision = build_state_messages_memory_close_decision(
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=state.messages,
    )
    assert decision is not None
    result = await write_runtime_memory_episode(
        store=store,
        command=_command_from_decision(state, decision),
        summarize_episode=summarize,
    )
    apply_runtime_memory_write_result(state, result)

    assert "old alpha beta gamma" in raw_inputs[0]
    assert state.llm_context_memory_cursor == {"session:flow:ctx": 2}
    assert len(store.episodes) == 1
    assert store.episodes[0].content == (
        "[Compacted conversation memory]\n"
        "Remembered compact alpha preference.\n\n"
        "[Original closed conversation segment]\n"
        "[user]\nold alpha beta gamma\n\n[assistant]\nold reply delta epsilon"
    )
    assert store.episodes[0].metadata["llm_context_recall_content"] == (
        "[Compacted conversation memory]\nRemembered compact alpha preference."
    )
    assert "old alpha beta gamma" not in store.episodes[0].metadata["llm_context_recall_content"]
    assert store.episodes[0].metadata["compaction"] == "llm_summary"


@pytest.mark.asyncio
async def test_runtime_memory_summary_failure_propagates_without_cursor_advance() -> None:
    store = RecordingStore()
    called: list[bool] = []
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
        branch_id="default",
        messages=[
            build_user_message("old alpha beta gamma", "agent", context_id="ctx", task_id="task"),
            build_assistant_message("old reply delta epsilon", "agent", context_id="ctx", task_id="task"),
            build_user_message("current question", "agent", context_id="ctx", task_id="task"),
        ],
    )

    async def summarize(_: str) -> str:
        called.append(True)
        raise RuntimeError("summary failed")

    decision = build_state_messages_memory_close_decision(
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=state.messages,
    )
    with pytest.raises(RuntimeError, match="summary failed"):
        await write_runtime_memory_episode(
            store=store,
            command=_command_from_decision(state, decision),
            summarize_episode=summarize,
        )

    assert called == [True]
    assert state.llm_context_memory_cursor == {}
    assert store.episodes == []


def test_runtime_memory_build_failure_propagates() -> None:
    store = RecordingStore()
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
        branch_id="default",
        messages=[],
    )
    _ = store

    with pytest.raises(ValueError):
        _ = build_state_messages_memory_close_decision(
            state=state,
            node_id="agent",
            policy=_policy(),
            messages=[{"content": 123}],
        )
    assert state.llm_context_memory_cursor == {}
    assert store.episodes == []
    assert store.calls == 0


def test_runtime_memory_cursor_advances_without_empty_episode() -> None:
    store = RecordingStore()
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
        branch_id="default",
        messages=[
            build_user_message("", "agent", context_id="ctx", task_id="task"),
            build_user_message("current question", "agent", context_id="ctx", task_id="task"),
        ],
    )

    decision = build_state_messages_memory_close_decision(
        state=state,
        node_id="agent",
        policy=_force_policy(),
        messages=state.messages,
    )
    assert decision is not None
    assert decision.episode is None
    apply_runtime_memory_cursor_advance(state, decision)

    assert state.llm_context_memory_cursor == {"session:flow:ctx": 1}
    assert store.episodes == []
    assert store.calls == 0


def test_runtime_memory_close_decision_is_deterministic_activity_input() -> None:
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
        branch_id="default",
        messages=[
            build_user_message("old alpha beta gamma", "agent", context_id="ctx", task_id="task"),
            build_assistant_message("old reply delta epsilon", "agent", context_id="ctx", task_id="task"),
            build_user_message("current question", "agent", context_id="ctx", task_id="task"),
        ],
    )

    first = build_state_messages_memory_close_decision(
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=state.messages,
    )
    second = build_state_messages_memory_close_decision(
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=state.messages,
    )

    assert first is not None
    assert second is not None
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert "created_at" not in first.model_dump_json()


@pytest.mark.asyncio
async def test_runtime_memory_prunes_state_messages_and_rebases_cursors() -> None:
    store = RecordingStore()
    pruned: list[int] = []
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
        branch_id="default",
        messages=[
            build_user_message("old alpha beta gamma", "agent", context_id="ctx", task_id="task"),
            build_assistant_message("old reply delta epsilon", "agent", context_id="ctx", task_id="task"),
            build_user_message("current question", "agent", context_id="ctx", task_id="task"),
        ],
    )

    decision = build_state_messages_memory_close_decision(
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=state.messages,
        compaction="raw",
    )
    result = await write_runtime_memory_episode(
        store=store,
        command=_command_from_decision(state, decision),
        summarize_episode=None,
    )
    apply_runtime_memory_write_result(state, result)
    pruned.append(prune_state_messages_to_memory_cursor_for_runtime(state))

    assert pruned == [2]
    assert state.llm_context_memory_cursor == {"session:flow:ctx": 0}
    assert len(state.messages) == 1
    assert state.messages[0].parts[0].root.text == "current question"
    assert "old alpha beta gamma" in store.episodes[0].content


def test_runtime_memory_prune_uses_min_cursor_and_keeps_last_message() -> None:
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
        branch_id="default",
        messages=[
            build_user_message("m0", "agent", context_id="ctx", task_id="task"),
            build_user_message("m1", "agent", context_id="ctx", task_id="task"),
            build_user_message("m2", "agent", context_id="ctx", task_id="task"),
            build_user_message("m3", "agent", context_id="ctx", task_id="task"),
        ],
        llm_context_memory_cursor={
            "session:flow:ctx": 3,
            "node:flow:agent": 2,
        },
    )

    pruned = prune_state_messages_to_memory_cursor_for_runtime(state)

    assert pruned == 2
    assert [message.parts[0].root.text for message in state.messages] == ["m2", "m3"]
    assert state.llm_context_memory_cursor == {
        "session:flow:ctx": 1,
        "node:flow:agent": 0,
    }


def test_runtime_memory_prune_is_noop_without_cursor_or_tail() -> None:
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
        messages=[
            build_user_message("only", "agent", context_id="ctx", task_id="task"),
        ],
        llm_context_memory_cursor={"session:flow:ctx": 1},
    )

    assert prune_state_messages_to_memory_cursor_for_runtime(state) == 0

    state.messages.append(build_user_message("second", "agent", context_id="ctx", task_id="task"))
    state.llm_context_memory_cursor = {}
    assert prune_state_messages_to_memory_cursor_for_runtime(state) == 0

    state.llm_context_memory_cursor = {"session:flow:ctx": 0}
    assert prune_state_messages_to_memory_cursor_for_runtime(state) == 0


@pytest.mark.asyncio
async def test_runtime_memory_close_is_absent_without_policy() -> None:
    store = RecordingStore()
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
    )
    assert build_state_messages_memory_close_decision(
        state=state,
        node_id="agent",
        policy=None,
        messages=[],
    ) is None
    assert store.episodes == []


@pytest.mark.asyncio
async def test_runtime_memory_close_requires_durable_node_context() -> None:
    store = RecordingStore()
    workflow_runtime = RecordingWorkflowRuntime()
    runner = _runner(store=store, workflow_runtime=workflow_runtime, policy=_policy())
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
        branch_id="default",
        messages=[
            build_user_message("old alpha beta gamma", "agent", context_id="ctx", task_id="task"),
            build_assistant_message("old reply delta epsilon", "agent", context_id="ctx", task_id="task"),
            build_user_message("current question", "agent", context_id="ctx", task_id="task"),
        ],
    )

    with pytest.raises(RuntimeError, match="durable execution_branch_id"):
        await runner._close_context_memory_window(state)

    assert store.calls == 0
    assert workflow_runtime.scheduled == []
    assert state.llm_context_memory_cursor == {}


@pytest.mark.asyncio
async def test_runtime_memory_activity_replays_without_second_store_write() -> None:
    store = RecordingStore()
    workflow_runtime = RecordingWorkflowRuntime()
    runner = _runner(store=store, workflow_runtime=workflow_runtime, policy=_policy())
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
        branch_id="default",
        messages=[
            build_user_message("old alpha beta gamma", "agent", context_id="ctx", task_id="task"),
            build_assistant_message("old reply delta epsilon", "agent", context_id="ctx", task_id="task"),
            build_user_message("current question", "agent", context_id="ctx", task_id="task"),
        ],
    )
    decision = build_state_messages_memory_close_decision(
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=state.messages,
        compaction="raw",
    )
    command = _command_from_decision(state, decision)

    result = await runner._run_context_memory_write_activity(state, command)

    assert result.written is True
    assert store.calls == 1
    assert state.llm_context_memory_cursor == {"session:flow:ctx": 2}
    assert len(workflow_runtime.scheduled) == 1
    scheduled = workflow_runtime.scheduled[0]
    assert scheduled["activity_type"] == "memory_write"
    assert scheduled["idempotency_key"] == scheduled["activity_id"]
    assert scheduled["side_effect_policy"] == SideEffectPolicy.idempotent.value
    assert workflow_runtime.started == [scheduled["activity_id"]]
    assert len(workflow_runtime.completed) == 1

    replay_state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
        branch_id="default",
        messages=list(state.messages),
    )
    replayed = await runner._run_context_memory_write_activity(replay_state, command)

    assert replayed == result
    assert store.calls == 1
    assert replay_state.llm_context_memory_cursor == {"session:flow:ctx": 2}
    assert len(workflow_runtime.scheduled) == 2
    assert len(workflow_runtime.started) == 1
    assert len(workflow_runtime.completed) == 1
