from __future__ import annotations

import pytest

from core.llm_context import (
    LLM_CONTEXT_MEMORY_RECALL_CONTENT_METADATA_KEY,
    LLMContextBudget,
    LLMContextMemoryEpisode,
    LLMContextProfile,
    LLMContextRetrievalPolicy,
    SimpleTokenCounter,
    close_llm_context_memory_window,
    compact_llm_context_memory_episode,
    llm_context_memory_cursor_key,
)


class RecordingStore:
    def __init__(self) -> None:
        self.episodes: list[LLMContextMemoryEpisode] = []

    async def write_episode(self, episode: LLMContextMemoryEpisode) -> str:
        self.episodes.append(episode)
        return episode.memory_id


def _policy(
    *,
    active_window_tokens: int = 5,
    memory: str = "session",
    compaction: str = "auto",
    mode: str = "smart",
) -> LLMContextProfile:
    return LLMContextProfile(
        mode=mode,
        budget=LLMContextBudget(
            max_input_tokens=1_000,
            output_reserve_tokens=10,
            reasoning_reserve_tokens=0,
            safety_buffer_tokens=10,
            active_window_tokens=active_window_tokens,
            memory_tokens=100,
            rag_tokens=100,
            tool_result_tokens=100,
        ),
        memory=memory,
        retrieval=LLMContextRetrievalPolicy(mode="hybrid", top_k=4, rerank=False),
        compaction=compaction,
        cache="auto",
    )


@pytest.mark.asyncio
async def test_closes_prefix_outside_active_window_and_advances_cursor() -> None:
    store = RecordingStore()
    messages = [
        {"role": "user", "content": "old account preference alpha beta"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call-1", "name": "lookup", "arguments": {"q": "alpha"}}],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "tool result gamma"},
        {"role": "user", "content": "current question"},
    ]

    cursor = await close_llm_context_memory_window(
        store,
        messages=messages,
        policy=_policy(active_window_tokens=4),
        cursor=0,
        session_id="flow:ctx",
        flow_id="flow",
        branch_id="default",
        node_id="agent",
        user_id="user",
        token_counter=SimpleTokenCounter(),
    )
    same_cursor = await close_llm_context_memory_window(
        store,
        messages=messages,
        policy=_policy(active_window_tokens=4),
        cursor=cursor,
        session_id="flow:ctx",
        flow_id="flow",
        node_id="agent",
        token_counter=SimpleTokenCounter(),
    )

    assert cursor == 3
    assert same_cursor == 3
    assert len(store.episodes) == 1
    episode = store.episodes[0]
    assert episode.scope == "session"
    assert episode.session_id == "flow:ctx"
    assert episode.flow_id == "flow"
    assert episode.branch_id == "default"
    assert episode.node_id == "agent"
    assert episode.user_id == "user"
    assert episode.source == "llm_context_compaction"
    assert episode.metadata["cursor_start"] == 0
    assert episode.metadata["cursor_end"] == 3
    assert "[user]\nold account preference" in episode.content
    assert "tool_calls=" in episode.content
    assert "tool_call_id=call-1" in episode.content


@pytest.mark.asyncio
async def test_compaction_respects_disabled_policy_and_empty_content() -> None:
    store = RecordingStore()
    messages = [
        {"role": "assistant", "content": ""},
        {"role": "user", "content": "current"},
    ]

    assert await close_llm_context_memory_window(
        store,
        messages=messages,
        policy=_policy(memory="off"),
        cursor=0,
        token_counter=SimpleTokenCounter(),
    ) == 0
    assert await close_llm_context_memory_window(
        store,
        messages=messages,
        policy=_policy(compaction="off"),
        cursor=0,
        session_id="flow:ctx",
        token_counter=SimpleTokenCounter(),
    ) == 0
    assert await close_llm_context_memory_window(
        store,
        messages=messages,
        policy=_policy(mode="off"),
        cursor=0,
        session_id="flow:ctx",
        token_counter=SimpleTokenCounter(),
    ) == 0
    assert await close_llm_context_memory_window(
        store,
        messages=messages,
        policy=_policy(compaction="force"),
        cursor=0,
        session_id="flow:ctx",
        token_counter=SimpleTokenCounter(),
    ) == 1
    assert store.episodes == []


@pytest.mark.asyncio
async def test_force_compaction_writes_all_but_last_message() -> None:
    store = RecordingStore()
    cursor = await close_llm_context_memory_window(
        store,
        messages=[
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "last"},
        ],
        policy=_policy(compaction="force"),
        cursor=0,
        session_id="flow:ctx",
        token_counter=SimpleTokenCounter(),
    )

    assert cursor == 2
    assert len(store.episodes) == 1
    assert "[user]\nfirst" in store.episodes[0].content
    assert "[assistant]\nsecond" in store.episodes[0].content
    assert "last" not in store.episodes[0].content


@pytest.mark.asyncio
async def test_compaction_does_not_write_when_messages_fit_active_window() -> None:
    store = RecordingStore()
    cursor = await close_llm_context_memory_window(
        store,
        messages=[
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
        ],
        policy=_policy(active_window_tokens=100),
        cursor=0,
        session_id="flow:ctx",
        token_counter=SimpleTokenCounter(),
    )
    single_cursor = await close_llm_context_memory_window(
        store,
        messages=[{"role": "user", "content": "only"}],
        policy=_policy(compaction="force"),
        cursor=0,
        session_id="flow:ctx",
        token_counter=SimpleTokenCounter(),
    )

    assert cursor == 0
    assert single_cursor == 0
    assert store.episodes == []


@pytest.mark.asyncio
async def test_compaction_renders_non_string_message_content() -> None:
    store = RecordingStore()
    cursor = await close_llm_context_memory_window(
        store,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "list text"},
                    {"type": "image_url", "image_url": {"url": "ignored"}},
                ],
            },
            {"role": "assistant", "content": {"json": 1}},
            {"role": "tool", "content": None, "tool_call_id": "call-1"},
            {"role": "user", "content": "last"},
        ],
        policy=_policy(compaction="force"),
        cursor=0,
        session_id="flow:ctx",
        token_counter=SimpleTokenCounter(),
    )

    assert cursor == 3
    assert len(store.episodes) == 1
    content = store.episodes[0].content
    assert "[user]\nlist text" in content
    assert '[assistant]\n{"json": 1}' in content
    assert "[tool]\ntool_call_id=call-1" in content


def test_memory_cursor_keys_are_scoped() -> None:
    assert llm_context_memory_cursor_key(scope="session", session_id="flow:ctx") == (
        "session:flow:ctx"
    )
    assert llm_context_memory_cursor_key(scope="node", flow_id="flow", node_id="agent") == (
        "node:flow:agent"
    )
    assert llm_context_memory_cursor_key(scope="flow", flow_id="flow") == "flow:flow"
    assert llm_context_memory_cursor_key(scope="company", flow_id="flow", node_id="agent") == (
        "company:flow:agent"
    )
    assert llm_context_memory_cursor_key(scope="off") == "off"


def test_compacts_raw_episode_into_summary_memory() -> None:
    episode = LLMContextMemoryEpisode(
        memory_id="m1",
        content="[user]\nraw preference alpha beta\n\n[assistant]\nraw reply",
        scope="session",
        session_id="flow:ctx",
        metadata={"cursor_start": 0, "cursor_end": 2, "content_hash": "raw-hash"},
    )

    compacted = compact_llm_context_memory_episode(
        episode,
        summary="User prefers alpha for billing reports.",
        token_counter=SimpleTokenCounter(),
    )

    assert compacted.content == (
        "[Compacted conversation memory]\n"
        "User prefers alpha for billing reports.\n\n"
        "[Original closed conversation segment]\n"
        "[user]\nraw preference alpha beta\n\n[assistant]\nraw reply"
    )
    assert compacted.metadata[LLM_CONTEXT_MEMORY_RECALL_CONTENT_METADATA_KEY] == (
        "[Compacted conversation memory]\nUser prefers alpha for billing reports."
    )
    assert "raw preference alpha beta" not in compacted.metadata[
        LLM_CONTEXT_MEMORY_RECALL_CONTENT_METADATA_KEY
    ]
    assert compacted.metadata["cursor_start"] == 0
    assert compacted.metadata["compaction"] == "llm_summary"
    assert compacted.metadata["raw_content_hash"]
    assert compacted.metadata["content_hash"] != "raw-hash"
    assert compacted.metadata["summary_token_count"] > 0

    with pytest.raises(ValueError, match="summary"):
        compact_llm_context_memory_episode(episode, summary=" ")
