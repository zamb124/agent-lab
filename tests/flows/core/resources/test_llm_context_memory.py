from __future__ import annotations

import asyncio

import pytest

from apps.flows.src.runtime.a2a_messages import build_assistant_message, build_user_message
from apps.flows.src.runtime.llm_context_memory import (
    prune_state_messages_to_memory_cursor_for_runtime,
    resolve_memory_context_source_for_runtime,
    schedule_state_messages_to_memory_for_runtime,
)
from core.llm_context import (
    LLMContextBudget,
    LLMContextMemoryEpisode,
    LLMContextMemoryRecallRequest,
    LLMContextMemoryRecord,
    LLMContextProfile,
    LLMContextRetrievalPolicy,
)
from core.state import ExecutionState


class RecordingStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.called = asyncio.Event()
        self.episodes: list[LLMContextMemoryEpisode] = []

    async def write_episode(self, episode: LLMContextMemoryEpisode) -> str:
        self.called.set()
        if self.fail:
            raise RuntimeError("memory write failed")
        self.episodes.append(episode)
        return episode.memory_id

    async def recall(self, _request: LLMContextMemoryRecallRequest) -> list[LLMContextMemoryRecord]:
        return []


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

    changed = schedule_state_messages_to_memory_for_runtime(
        store=store,
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=state.messages,
    )
    await asyncio.wait_for(store.called.wait(), timeout=1)
    await asyncio.sleep(0)
    changed_again = schedule_state_messages_to_memory_for_runtime(
        store=store,
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=state.messages,
    )

    assert changed is True
    assert changed_again is False
    assert state.llm_context_memory_cursor == {"session:flow:ctx": 2}
    assert len(store.episodes) == 1
    assert store.episodes[0].session_id == "flow:ctx"
    assert "old alpha beta gamma" in store.episodes[0].content


@pytest.mark.asyncio
async def test_runtime_memory_write_failure_does_not_propagate() -> None:
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

    changed = schedule_state_messages_to_memory_for_runtime(
        store=store,
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=state.messages,
    )
    await asyncio.wait_for(store.called.wait(), timeout=1)
    await asyncio.sleep(0)

    assert changed is True
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

    changed = schedule_state_messages_to_memory_for_runtime(
        store=store,
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=state.messages,
        summarize_episode=summarize,
    )
    await asyncio.wait_for(store.called.wait(), timeout=1)
    await asyncio.sleep(0)

    assert changed is True
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
async def test_runtime_memory_summary_failure_does_not_write_or_advance_cursor() -> None:
    store = RecordingStore()
    called = asyncio.Event()
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
        called.set()
        raise RuntimeError("summary failed")

    changed = schedule_state_messages_to_memory_for_runtime(
        store=store,
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=state.messages,
        summarize_episode=summarize,
    )
    await asyncio.wait_for(called.wait(), timeout=1)
    await asyncio.sleep(0)

    assert changed is True
    assert state.llm_context_memory_cursor == {}
    assert store.episodes == []


@pytest.mark.asyncio
async def test_runtime_memory_schedule_failure_does_not_propagate() -> None:
    store = RecordingStore()
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="flow:ctx",
        branch_id="default",
        messages=[],
    )

    changed = schedule_state_messages_to_memory_for_runtime(
        store=store,
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=[{"content": 123}],
    )

    assert changed is False
    assert state.llm_context_memory_cursor == {}
    assert store.episodes == []
    assert store.called.is_set() is False


@pytest.mark.asyncio
async def test_runtime_memory_cursor_advances_without_empty_episode() -> None:
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

    changed = schedule_state_messages_to_memory_for_runtime(
        store=store,
        state=state,
        node_id="agent",
        policy=_force_policy(),
        messages=state.messages,
    )

    assert changed is True
    assert state.llm_context_memory_cursor == {"session:flow:ctx": 1}
    assert store.episodes == []
    assert store.called.is_set() is False


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

    async def after_write() -> None:
        pruned.append(prune_state_messages_to_memory_cursor_for_runtime(state))

    changed = schedule_state_messages_to_memory_for_runtime(
        store=store,
        state=state,
        node_id="agent",
        policy=_policy(),
        messages=state.messages,
        after_write=after_write,
    )
    await asyncio.wait_for(store.called.wait(), timeout=1)
    await asyncio.sleep(0)

    assert changed is True
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
    assert schedule_state_messages_to_memory_for_runtime(
        store=store,
        state=state,
        node_id="agent",
        policy=None,
        messages=[],
    ) is False
    assert store.episodes == []
