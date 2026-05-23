from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.llm_context import (
    LLMContextBudget,
    LLMContextMemoryEpisode,
    LLMContextMemoryRecallRequest,
    LLMContextMemoryRecord,
    LLMContextMemorySource,
    LLMContextProfile,
    LLMContextRetrievalPolicy,
    LLMContextSourceRequest,
)


class InMemoryStore:
    def __init__(self, records: list[LLMContextMemoryRecord]) -> None:
        self.records = records
        self.requests: list[LLMContextMemoryRecallRequest] = []

    async def write_episode(self, episode: LLMContextMemoryEpisode) -> str:
        return episode.memory_id

    async def recall(
        self,
        request: LLMContextMemoryRecallRequest,
    ) -> list[LLMContextMemoryRecord]:
        self.requests.append(request)
        return list(self.records)


def _policy(
    *,
    memory: str = "session",
    retrieval: str = "hybrid",
    top_k: int = 4,
    min_score: float | None = None,
) -> LLMContextProfile:
    return LLMContextProfile(
        mode="smart",
        budget=LLMContextBudget(),
        memory=memory,
        retrieval=LLMContextRetrievalPolicy(
            mode=retrieval,
            top_k=top_k,
            rerank=False,
            min_score=min_score,
        ),
        compaction="auto",
        cache="auto",
    )


def test_episode_requires_scope_identity() -> None:
    with pytest.raises(ValueError, match="session_id"):
        LLMContextMemoryEpisode(memory_id="m1", content="hello", scope="session")

    with pytest.raises(ValueError, match="flow_id and node_id"):
        LLMContextMemoryEpisode(memory_id="m1", content="hello", scope="node", flow_id="f")

    with pytest.raises(ValueError, match="cannot be 'off'"):
        LLMContextMemoryEpisode(memory_id="m1", content="hello", scope="off")

    with pytest.raises(ValueError, match="flow_id"):
        LLMContextMemoryEpisode(memory_id="m1", content="hello", scope="flow")

    with pytest.raises(ValueError, match="recall scope"):
        LLMContextMemoryRecallRequest(query="hello", scope="off")


@pytest.mark.asyncio
async def test_memory_source_recalls_and_outputs_chronological_memory_blocks() -> None:
    store = InMemoryStore(
        [
            LLMContextMemoryRecord(
                memory_id="new",
                content="newer memory",
                scope="session",
                score=0.99,
                created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
            LLMContextMemoryRecord(
                memory_id="old",
                content="older memory",
                scope="session",
                score=0.70,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        ]
    )
    source = LLMContextMemorySource(
        store=store,
        session_id="flow:ctx",
        flow_id="flow",
        branch_id="default",
        node_id="agent",
        user_id="user",
        top_k=3,
    )

    blocks = await source.collect(
        LLMContextSourceRequest(query="billing", policy=_policy(), metadata={"turn": 1})
    )

    assert [block.stable_key for block in blocks] == [
        "memory:session:2026-01-01T00:00:00+00:00:old",
        "memory:session:2026-01-02T00:00:00+00:00:new",
    ]
    assert blocks[0].kind == "memory"
    assert blocks[0].budget_scope == "memory"
    assert blocks[0].score == 0.70
    assert "older memory" in blocks[0].content
    assert store.requests[0].top_k == 3
    assert store.requests[0].session_id == "flow:ctx"
    assert store.requests[0].search_options == {
        "channels": {"semantic": True, "lexical": True},
        "rerank": False,
    }


@pytest.mark.asyncio
async def test_memory_source_is_disabled_by_memory_or_retrieval_policy() -> None:
    store = InMemoryStore([])
    source = LLMContextMemorySource(store=store, session_id="flow:ctx")

    assert await source.collect(
        LLMContextSourceRequest(query="billing", policy=_policy(memory="off"))
    ) == []
    assert await source.collect(
        LLMContextSourceRequest(query="billing", policy=_policy(retrieval="off"))
    ) == []
    assert store.requests == []


@pytest.mark.asyncio
async def test_memory_source_search_options_cover_single_channel_modes() -> None:
    store = InMemoryStore(
        [
            LLMContextMemoryRecord(
                memory_id="plain",
                content="memory without created timestamp or score",
                scope="flow",
            )
        ]
    )
    source = LLMContextMemorySource(store=store, flow_id="flow")

    lexical_blocks = await source.collect(
        LLMContextSourceRequest(query="billing", policy=_policy(memory="flow", retrieval="lexical"))
    )
    semantic_blocks = await source.collect(
        LLMContextSourceRequest(query="billing", policy=_policy(memory="flow", retrieval="semantic"))
    )

    assert store.requests[0].search_options == {
        "channels": {"semantic": False, "lexical": True},
        "rerank": False,
    }
    assert store.requests[1].search_options == {
        "channels": {"semantic": True, "lexical": False},
        "rerank": False,
    }
    assert "created_at=unknown score=n/a" in lexical_blocks[0].content
    assert semantic_blocks[0].stable_key == "memory:flow:unknown:plain"


@pytest.mark.asyncio
async def test_memory_source_uses_policy_top_k_and_min_score_before_chronological_output() -> None:
    store = InMemoryStore(
        [
            LLMContextMemoryRecord(
                memory_id="relevant-new",
                content="new relevant memory",
                scope="session",
                score=0.94,
                created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
            ),
            LLMContextMemoryRecord(
                memory_id="weak",
                content="weak memory",
                scope="session",
                score=0.42,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            LLMContextMemoryRecord(
                memory_id="relevant-old",
                content="old relevant memory",
                scope="session",
                score=0.91,
                created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
            LLMContextMemoryRecord(
                memory_id="overflow",
                content="third relevant memory beyond top-k",
                scope="session",
                score=0.90,
                created_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
            ),
        ]
    )
    source = LLMContextMemorySource(store=store, session_id="flow:ctx")

    blocks = await source.collect(
        LLMContextSourceRequest(
            query="billing",
            policy=_policy(top_k=2, min_score=0.7),
        )
    )

    assert store.requests[0].top_k == 2
    assert [block.stable_key for block in blocks] == [
        "memory:session:2026-01-02T00:00:00+00:00:relevant-old",
        "memory:session:2026-01-03T00:00:00+00:00:relevant-new",
    ]
    assert [block.score for block in blocks] == [0.91, 0.94]
