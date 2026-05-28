from __future__ import annotations

import pytest

from core.llm_context import (
    LLMContextBlock,
    LLMContextBudget,
    LLMContextBudgetError,
    LLMContextCompiler,
    LLMContextCompileRequest,
    LLMContextMode,
    LLMContextProfile,
    LLMContextRetrievalPolicy,
    SimpleTokenCounter,
)
from core.types import JsonObject, require_json_object


def _compiler() -> LLMContextCompiler:
    return LLMContextCompiler(token_counter=SimpleTokenCounter())


def _policy(
    *,
    mode: LLMContextMode = "smart",
    max_input_tokens: int = 40,
    active_window_tokens: int = 10,
    memory_tokens: int = 6,
    rag_tokens: int = 6,
    tool_result_tokens: int = 4,
) -> LLMContextProfile:
    return LLMContextProfile(
        mode=mode,
        budget=LLMContextBudget(
            max_input_tokens=max_input_tokens,
            output_reserve_tokens=4,
            reasoning_reserve_tokens=0,
            safety_buffer_tokens=1,
            active_window_tokens=active_window_tokens,
            memory_tokens=memory_tokens,
            rag_tokens=rag_tokens,
            tool_result_tokens=tool_result_tokens,
        ),
        memory="session",
        retrieval=LLMContextRetrievalPolicy(mode="hybrid", top_k=8, rerank=True),
        compaction="auto",
        cache="provider_hints",
    )


def test_mode_off_returns_messages_without_context_blocks() -> None:
    messages: list[JsonObject] = [
        require_json_object({"role": "system", "content": "static instruction"}),
        require_json_object({"role": "user", "content": "hello"}),
    ]
    compiled = _compiler().compile(
        LLMContextCompileRequest(
            messages=messages,
            candidate_blocks=[
                LLMContextBlock(
                    kind="memory",
                    budget_scope="memory",
                    content="old memory",
                    stable_key="memory:1",
                )
            ],
            policy=_policy(mode="off"),
        )
    )

    assert compiled.messages == messages
    assert compiled.selected_blocks == []
    assert compiled.dropped_blocks == []
    assert compiled.provider_hints == {}


def test_mode_off_raises_when_messages_exceed_budget() -> None:
    with pytest.raises(LLMContextBudgetError, match="mode=off"):
        _compiler().compile(
            LLMContextCompileRequest(
                messages=[{"role": "user", "content": "one two three four five six"}],
                policy=_policy(mode="off", max_input_tokens=10),
            )
        )


def test_tools_schema_can_exhaust_available_budget() -> None:
    with pytest.raises(LLMContextBudgetError, match="reserves"):
        _compiler().compile(
            LLMContextCompileRequest(
                messages=[{"role": "user", "content": "current"}],
                policy=_policy(max_input_tokens=40),
                tools_schema_tokens=36,
            )
        )


def test_empty_messages_compile_to_empty_prompt() -> None:
    compiled = _compiler().compile(LLMContextCompileRequest(messages=[], policy=_policy()))

    assert compiled.messages == []
    assert compiled.usage.active_message_tokens == 0


def test_active_window_keeps_last_message_when_tail_exceeds_window() -> None:
    compiled = _compiler().compile(
        LLMContextCompileRequest(
            messages=[
                {"role": "user", "content": "one two"},
                {"role": "assistant", "content": "three four"},
                {"role": "user", "content": "five six"},
            ],
            policy=_policy(active_window_tokens=5),
        )
    )

    assert compiled.messages == [{"role": "user", "content": "five six"}]
    assert compiled.usage.active_message_tokens == 3


def test_system_prefix_is_kept_outside_active_window() -> None:
    compiled = _compiler().compile(
        LLMContextCompileRequest(
            messages=[
                {"role": "system", "content": "rules stay"},
                {"role": "user", "content": "one two"},
                {"role": "assistant", "content": "three four"},
                {"role": "user", "content": "five"},
            ],
            policy=_policy(active_window_tokens=3),
        )
    )

    assert compiled.messages == [
        {"role": "system", "content": "rules stay"},
        {"role": "user", "content": "five"},
    ]


def test_system_prefix_over_budget_raises() -> None:
    with pytest.raises(LLMContextBudgetError, match="System LLM context prefix"):
        _compiler().compile(
            LLMContextCompileRequest(
                messages=[
                    {"role": "system", "content": "one two three"},
                    {"role": "user", "content": "current"},
                ],
                policy=_policy(max_input_tokens=8, active_window_tokens=10),
            )
        )


def test_active_window_also_stops_at_global_available_budget() -> None:
    compiled = _compiler().compile(
        LLMContextCompileRequest(
            messages=[
                {"role": "user", "content": "one two"},
                {"role": "assistant", "content": "three four"},
                {"role": "user", "content": "five"},
            ],
            policy=_policy(max_input_tokens=12, active_window_tokens=100),
        )
    )

    assert compiled.messages == [
        {"role": "assistant", "content": "three four"},
        {"role": "user", "content": "five"},
    ]
    assert compiled.usage.active_message_tokens == 5


def test_compiler_dedupes_blocks_orders_sections_and_respects_scope_budgets() -> None:
    blocks = [
        LLMContextBlock(
            kind="memory",
            budget_scope="memory",
            content="low memory",
            stable_key="memory:same",
            priority=10,
            score=0.3,
        ),
        LLMContextBlock(
            kind="memory",
            budget_scope="memory",
            content="better memory",
            stable_key="memory:same",
            priority=20,
            score=0.9,
        ),
        LLMContextBlock(
            kind="memory",
            budget_scope="memory",
            content="second memory",
            stable_key="memory:2",
            priority=19,
            score=0.8,
        ),
        LLMContextBlock(
            kind="rag",
            budget_scope="rag",
            content="rag hit",
            stable_key="rag:1",
            priority=30,
            score=0.95,
        ),
        LLMContextBlock(
            kind="profile",
            budget_scope="profile",
            content="profile facts",
            stable_key="profile:1",
            priority=5,
        ),
    ]

    compiled = _compiler().compile(
        LLMContextCompileRequest(
            messages=[{"role": "user", "content": "current"}],
            candidate_blocks=blocks,
            policy=_policy(memory_tokens=3, rag_tokens=3),
        )
    )

    assert [block.stable_key for block in compiled.selected_blocks] == [
        "profile:1",
        "memory:same",
        "rag:1",
    ]
    assert [message["content"] for message in compiled.messages] == [
        "profile facts",
        "better memory",
        "rag hit",
        "current",
    ]
    assert [block.stable_key for block in compiled.dropped_blocks] == ["memory:2"]
    assert compiled.provider_hints["stable_prefix_block_keys"] == [
        "profile:1",
        "memory:same",
        "rag:1",
    ]


def test_compiler_outputs_selected_memory_blocks_chronologically() -> None:
    compiled = _compiler().compile(
        LLMContextCompileRequest(
            messages=[{"role": "user", "content": "current"}],
            candidate_blocks=[
                LLMContextBlock(
                    kind="memory",
                    budget_scope="memory",
                    content="new high score",
                    stable_key="memory:session:2026-01-03T00:00:00+00:00:new",
                    priority=80,
                    score=0.99,
                    provenance={"created_at": "2026-01-03T00:00:00+00:00"},
                ),
                LLMContextBlock(
                    kind="memory",
                    budget_scope="memory",
                    content="old lower score",
                    stable_key="memory:session:2026-01-01T00:00:00+00:00:old",
                    priority=80,
                    score=0.71,
                    provenance={"created_at": "2026-01-01T00:00:00+00:00"},
                ),
                LLMContextBlock(
                    kind="rag",
                    budget_scope="rag",
                    content="rag hit",
                    stable_key="rag:1",
                    priority=90,
                    score=0.95,
                ),
            ],
            policy=_policy(memory_tokens=20, rag_tokens=5),
        )
    )

    assert [block.stable_key for block in compiled.selected_blocks] == [
        "memory:session:2026-01-01T00:00:00+00:00:old",
        "memory:session:2026-01-03T00:00:00+00:00:new",
        "rag:1",
    ]
    assert [message["content"] for message in compiled.messages] == [
        "old lower score",
        "new high score",
        "rag hit",
        "current",
    ]


def test_compiler_packs_memory_budget_chronologically_after_retrieval() -> None:
    compiled = _compiler().compile(
        LLMContextCompileRequest(
            messages=[{"role": "user", "content": "current"}],
            candidate_blocks=[
                LLMContextBlock(
                    kind="memory",
                    budget_scope="memory",
                    content="new high score",
                    stable_key="memory:session:2026-01-03T00:00:00+00:00:new",
                    priority=80,
                    score=0.99,
                    token_count=3,
                    provenance={"created_at": "2026-01-03T00:00:00+00:00"},
                ),
                LLMContextBlock(
                    kind="memory",
                    budget_scope="memory",
                    content="old lower score",
                    stable_key="memory:session:2026-01-01T00:00:00+00:00:old",
                    priority=80,
                    score=0.71,
                    token_count=3,
                    provenance={"created_at": "2026-01-01T00:00:00+00:00"},
                ),
            ],
            policy=_policy(memory_tokens=3),
        )
    )

    assert [block.stable_key for block in compiled.selected_blocks] == [
        "memory:session:2026-01-01T00:00:00+00:00:old",
    ]
    assert [block.stable_key for block in compiled.dropped_blocks] == [
        "memory:session:2026-01-03T00:00:00+00:00:new",
    ]


def test_block_explicit_token_count_is_authoritative() -> None:
    compiled = _compiler().compile(
        LLMContextCompileRequest(
            messages=[{"role": "user", "content": "current"}],
            candidate_blocks=[
                LLMContextBlock(
                    kind="memory",
                    budget_scope="memory",
                    content="one two three four five six seven eight nine",
                    stable_key="memory:counted",
                    token_count=3,
                )
            ],
            policy=_policy(memory_tokens=3),
        )
    )

    assert [block.token_count for block in compiled.selected_blocks] == [3]
    assert compiled.usage.selected_block_tokens == 3


def test_cache_provider_hints_ignore_non_system_blocks() -> None:
    compiled = _compiler().compile(
        LLMContextCompileRequest(
            messages=[{"role": "user", "content": "current"}],
            candidate_blocks=[
                LLMContextBlock(
                    kind="custom",
                    budget_scope="custom",
                    role="user",
                    content="user side context",
                    stable_key="custom:user",
                )
            ],
            policy=_policy(),
        )
    )

    assert compiled.selected_blocks[0].stable_key == "custom:user"
    assert compiled.provider_hints == {}


def test_cache_provider_hints_include_system_prefix_in_hash() -> None:
    block = LLMContextBlock(
        kind="memory",
        budget_scope="memory",
        content="stable memory",
        stable_key="memory:stable",
    )
    first = _compiler().compile(
        LLMContextCompileRequest(
            messages=[
                {"role": "system", "content": "first rules"},
                {"role": "user", "content": "current"},
            ],
            candidate_blocks=[block],
            policy=_policy(),
        )
    )
    second = _compiler().compile(
        LLMContextCompileRequest(
            messages=[
                {"role": "system", "content": "second rules"},
                {"role": "user", "content": "current"},
            ],
            candidate_blocks=[block],
            policy=_policy(),
        )
    )

    assert first.provider_hints["stable_prefix_block_keys"] == ["memory:stable"]
    assert second.provider_hints["stable_prefix_block_keys"] == ["memory:stable"]
    assert (
        first.provider_hints["stable_prefix_hash"]
        != second.provider_hints["stable_prefix_hash"]
    )


def test_cache_provider_hints_work_with_system_prefix_only() -> None:
    compiled = _compiler().compile(
        LLMContextCompileRequest(
            messages=[
                {"role": "system", "content": "stable rules"},
                {"role": "user", "content": "current"},
            ],
            policy=_policy(),
        )
    )

    assert compiled.provider_hints["stable_prefix_block_keys"] == []
    assert compiled.provider_hints["stable_prefix_hash"]


def test_cache_provider_hints_disabled_by_policy() -> None:
    policy = _policy().model_copy(update={"cache": "off"})
    compiled = _compiler().compile(
        LLMContextCompileRequest(
            messages=[
                {"role": "system", "content": "stable rules"},
                {"role": "user", "content": "current"},
            ],
            candidate_blocks=[
                LLMContextBlock(
                    kind="memory",
                    budget_scope="memory",
                    content="stable memory",
                    stable_key="memory:stable",
                )
            ],
            policy=policy,
        )
    )

    assert compiled.provider_hints == {}


def test_compiler_filters_disabled_sources_unless_required() -> None:
    policy = _policy()
    policy = policy.model_copy(
        update={
            "memory": "off",
            "retrieval": LLMContextRetrievalPolicy(mode="off", rerank=False),
            "compaction": "off",
        }
    )

    compiled = _compiler().compile(
        LLMContextCompileRequest(
            messages=[{"role": "user", "content": "current"}],
            candidate_blocks=[
                LLMContextBlock(
                    kind="memory",
                    budget_scope="memory",
                    content="optional memory",
                    stable_key="memory:optional",
                ),
                LLMContextBlock(
                    kind="rag",
                    budget_scope="rag",
                    content="required rag",
                    stable_key="rag:required",
                    required=True,
                ),
                LLMContextBlock(
                    kind="tool_summary",
                    budget_scope="tool_result",
                    content="optional tool",
                    stable_key="tool:optional",
                ),
            ],
            policy=policy,
        )
    )

    assert [block.stable_key for block in compiled.selected_blocks] == ["rag:required"]
    assert [block.stable_key for block in compiled.dropped_blocks] == [
        "memory:optional",
        "tool:optional",
    ]


def test_required_block_over_budget_raises() -> None:
    with pytest.raises(LLMContextBudgetError, match="Required"):
        _compiler().compile(
            LLMContextCompileRequest(
                messages=[{"role": "user", "content": "current"}],
                candidate_blocks=[
                    LLMContextBlock(
                        kind="memory",
                        budget_scope="memory",
                        content="one two three four five six seven",
                        stable_key="memory:required",
                        required=True,
                    )
                ],
                policy=_policy(max_input_tokens=14, active_window_tokens=10, memory_tokens=4),
            )
        )


def test_last_message_over_budget_raises() -> None:
    with pytest.raises(LLMContextBudgetError, match="Last LLM message"):
        _compiler().compile(
            LLMContextCompileRequest(
                messages=[{"role": "user", "content": "one two three four five six seven"}],
                policy=_policy(max_input_tokens=10, active_window_tokens=10),
            )
        )


def test_model_context_length_clamps_policy_budget() -> None:
    compiled = _compiler().compile(
        LLMContextCompileRequest(
            messages=[
                {"role": "user", "content": "old one two three four five six seven"},
                {"role": "user", "content": "current"},
            ],
            policy=_policy(max_input_tokens=100, active_window_tokens=100),
            model_context_length=12,
        )
    )

    assert compiled.usage.max_input_tokens == 12
    assert compiled.usage.policy_max_input_tokens == 100
    assert compiled.usage.model_context_length == 12
    assert compiled.messages == [{"role": "user", "content": "current"}]


def test_tool_result_compaction_keeps_large_tool_result_inside_budget() -> None:
    compiled = _compiler().compile(
        LLMContextCompileRequest(
            messages=[
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "lookup", "arguments": "{}"},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call-1",
                    "content": " ".join(f"result{i}" for i in range(80)),
                },
            ],
            policy=_policy(
                max_input_tokens=40,
                active_window_tokens=100,
                tool_result_tokens=8,
            ),
        )
    )

    assert compiled.messages[-1]["role"] == "tool"
    tool_content = compiled.messages[-1]["content"]
    assert isinstance(tool_content, str)
    assert "tool result compacted" in tool_content
    assert compiled.messages[-1]["tool_call_id"] == "call-1"
    assert compiled.usage.tool_result_original_tokens > compiled.usage.tool_result_compacted_tokens
    assert compiled.usage.tool_result_saved_tokens > 0
    assert compiled.usage.tool_result_compacted_messages == 1


def test_min_score_drops_low_memory_and_rag_results() -> None:
    policy = _policy()
    policy = policy.model_copy(
        update={"retrieval": LLMContextRetrievalPolicy(mode="semantic", min_score=0.7)}
    )

    compiled = _compiler().compile(
        LLMContextCompileRequest(
            messages=[{"role": "user", "content": "current"}],
            candidate_blocks=[
                LLMContextBlock(
                    kind="memory",
                    budget_scope="memory",
                    content="weak memory",
                    stable_key="memory:weak",
                    score=0.2,
                ),
                LLMContextBlock(
                    kind="memory",
                    budget_scope="memory",
                    content="strong memory",
                    stable_key="memory:strong",
                    score=0.8,
                ),
                LLMContextBlock(
                    kind="rag",
                    budget_scope="rag",
                    content="weak hit",
                    stable_key="rag:weak",
                    score=0.3,
                ),
                LLMContextBlock(
                    kind="rag",
                    budget_scope="rag",
                    content="strong hit",
                    stable_key="rag:strong",
                    score=0.9,
                ),
            ],
            policy=policy,
        )
    )

    assert [block.stable_key for block in compiled.selected_blocks] == [
        "memory:strong",
        "rag:strong",
    ]
    assert [block.stable_key for block in compiled.dropped_blocks] == [
        "memory:weak",
        "rag:weak",
    ]
