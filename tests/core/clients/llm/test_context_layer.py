from __future__ import annotations

import pytest

from core.clients.llm.context_layer import (
    llm_context_trace_metadata,
    merge_provider_cache_hints,
    openai_messages_to_a2a_messages,
    prepare_messages_for_context_layer,
)
from core.clients.llm.messages import messages_to_openai, normalize_messages
from core.company_ai import METADATA_KEY
from core.context import Company, Context, User, clear_context, set_context
from core.llm_context import (
    LLM_CONTEXT_PROFILE_METADATA_KEY,
    LLMContextBlock,
    LLMContextBudget,
    LLMContextCompiler,
    LLMContextProfile,
    LLMContextRetrievalPolicy,
    LLMContextSourceRegistry,
    LLMContextSourceRequest,
    SimpleTokenCounter,
)


def _compiler() -> LLMContextCompiler:
    return LLMContextCompiler(token_counter=SimpleTokenCounter())


def _profile(*, active_window_tokens: int = 10) -> LLMContextProfile:
    return LLMContextProfile(
        mode="window",
        budget=LLMContextBudget(
            max_input_tokens=40,
            output_reserve_tokens=2,
            reasoning_reserve_tokens=0,
            safety_buffer_tokens=1,
            active_window_tokens=active_window_tokens,
            memory_tokens=10,
            rag_tokens=10,
            tool_result_tokens=4,
        ),
        memory="session",
        retrieval=LLMContextRetrievalPolicy(mode="off", rerank=False),
        compaction="auto",
        cache="auto",
    )


class QueryEchoContextSource:
    name = "query.echo"

    async def collect(self, request: LLMContextSourceRequest) -> list[LLMContextBlock]:
        return [
            LLMContextBlock(
                kind="custom",
                budget_scope="custom",
                content=f"query:{request.query}",
                stable_key="query",
            )
        ]


@pytest.mark.asyncio
async def test_context_layer_preserves_system_prefix_and_trims_active_window() -> None:
    messages = normalize_messages(
        [
            {"role": "system", "content": "keep rules"},
            {"role": "user", "content": "old one two"},
            {"role": "assistant", "content": "old reply"},
            {"role": "user", "content": "now"},
        ]
    )

    prepared = await prepare_messages_for_context_layer(
        messages,
        llm_context=_profile(active_window_tokens=3),
        compiler=_compiler(),
    )

    assert prepared.compiled_context is not None
    assert prepared.openai_messages == [
        {"role": "system", "content": "keep rules"},
        {"role": "user", "content": "now"},
    ]
    assert messages_to_openai(prepared.messages) == prepared.openai_messages


@pytest.mark.asyncio
async def test_context_layer_accepts_pre_retrieved_blocks_without_extra_tools() -> None:
    messages = normalize_messages([{"role": "user", "content": "current"}])

    prepared = await prepare_messages_for_context_layer(
        messages,
        llm_context=_profile(),
        llm_context_blocks=[
            LLMContextBlock(
                kind="memory",
                budget_scope="memory",
                content="remembered fact",
                stable_key="memory:1",
            )
        ],
        compiler=_compiler(),
    )

    assert [message["content"] for message in prepared.openai_messages] == [
        "remembered fact",
        "current",
    ]


@pytest.mark.asyncio
async def test_context_layer_collects_blocks_from_source_registry() -> None:
    messages = normalize_messages([{"role": "user", "content": "current question"}])

    prepared = await prepare_messages_for_context_layer(
        messages,
        llm_context=_profile(),
        llm_context_source_registry=LLMContextSourceRegistry([QueryEchoContextSource()]),
        compiler=_compiler(),
    )

    assert [message["content"] for message in prepared.openai_messages] == [
        "query:current question",
        "current question",
    ]


@pytest.mark.asyncio
async def test_context_layer_clamps_to_model_context_length() -> None:
    messages = normalize_messages(
        [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "old one two three four five six seven"},
            {"role": "user", "content": "current"},
        ]
    )

    prepared = await prepare_messages_for_context_layer(
        messages,
        llm_context=_profile(active_window_tokens=100),
        model_context_length=12,
        compiler=_compiler(),
    )

    assert prepared.compiled_context is not None
    assert prepared.compiled_context.usage.max_input_tokens == 12
    assert prepared.compiled_context.usage.model_context_length == 12
    assert prepared.openai_messages == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "current"},
    ]


@pytest.mark.asyncio
async def test_context_layer_trace_metadata_is_content_free() -> None:
    messages = normalize_messages([{"role": "user", "content": "current"}])

    prepared = await prepare_messages_for_context_layer(
        messages,
        llm_context=_profile(),
        llm_context_blocks=[
            LLMContextBlock(
                kind="memory",
                budget_scope="memory",
                content="secret remembered fact",
                stable_key="memory:1",
                score=0.9,
                provenance={"session_id": "s1"},
            )
        ],
        compiler=_compiler(),
    )

    metadata = llm_context_trace_metadata(prepared.compiled_context)

    assert metadata is not None
    assert metadata["usage"]["total_input_tokens"] > 0
    assert metadata["selected_blocks"] == [
        {
            "kind": "memory",
            "budget_scope": "memory",
            "stable_key": "memory:1",
            "priority": 100,
            "score": 0.9,
            "token_count": 4,
            "required": False,
            "provenance": {"session_id": "s1"},
        }
    ]
    assert "secret remembered fact" not in str(metadata)


@pytest.mark.asyncio
async def test_context_layer_uses_company_patch_without_call_level_context() -> None:
    clear_context()
    try:
        company = Company(
            company_id="c1",
            name="Company",
            metadata={
                METADATA_KEY: {
                    "llm_context": {
                        "profile": "compact",
                        "budget": {
                            "max_input_tokens": 40,
                            "output_reserve_tokens": 2,
                            "reasoning_reserve_tokens": 0,
                            "safety_buffer_tokens": 1,
                            "active_window_tokens": 3,
                        },
                    }
                }
            },
        )
        user = User(user_id="u1", name="User", active_company_id="c1")
        set_context(Context(user=user, active_company=company, channel="test"))
        messages = normalize_messages(
            [
                {"role": "system", "content": "keep rules"},
                {"role": "user", "content": "old one two"},
                {"role": "assistant", "content": "old reply"},
                {"role": "user", "content": "now"},
            ]
        )

        prepared = await prepare_messages_for_context_layer(messages, compiler=_compiler())

        assert prepared.compiled_context is not None
        assert prepared.openai_messages == [
            {"role": "system", "content": "keep rules"},
            {"role": "user", "content": "now"},
        ]
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_context_layer_injects_identity_profile_block_from_context() -> None:
    clear_context()
    try:
        user = User(
            user_id="u1",
            name="User",
            bio="Always answer in concise Russian.",
            active_company_id="c1",
        )
        company = Company(
            company_id="c1",
            name="Company",
            metadata={LLM_CONTEXT_PROFILE_METADATA_KEY: "Company profile for agent."},
        )
        set_context(Context(user=user, active_company=company, channel="test"))

        prepared = await prepare_messages_for_context_layer(
            normalize_messages([{"role": "user", "content": "now"}]),
            llm_context=_profile(active_window_tokens=20),
            compiler=_compiler(),
        )
    finally:
        clear_context()

    assert prepared.compiled_context is not None
    assert prepared.openai_messages == [
        {
            "role": "system",
            "content": (
                "[Profile]\nUser bio:\nAlways answer in concise Russian.\n\n"
                "Company profile:\nCompany profile for agent."
            ),
        },
        {"role": "user", "content": "now"},
    ]
    assert prepared.compiled_context.selected_blocks[0].kind == "profile"


def test_openai_message_roundtrip_preserves_system_tool_and_tool_calls() -> None:
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "lookup", "arguments": "{}"},
        }
    ]
    openai_messages = [
        {"role": "system", "content": "rules"},
        {"role": "assistant", "content": "", "tool_calls": tool_calls},
        {"role": "tool", "content": "42", "tool_call_id": "call_1"},
    ]

    converted = openai_messages_to_a2a_messages(openai_messages)

    assert messages_to_openai(converted) == openai_messages


def test_normalize_messages_preserves_openai_roles() -> None:
    normalized = normalize_messages(
        [
            {"role": "system", "content": "rules"},
            {"role": "assistant", "content": "answer"},
            {"role": "tool", "content": "done", "tool_call_id": "call_1"},
        ]
    )

    assert messages_to_openai(normalized) == [
        {"role": "system", "content": "rules"},
        {"role": "assistant", "content": "answer"},
        {"role": "tool", "content": "done", "tool_call_id": "call_1"},
    ]


def test_provider_cache_hints_add_openai_prompt_cache_key() -> None:
    body = merge_provider_cache_hints(
        provider="openai",
        extra_body={"store": False},
        provider_hints={"stable_prefix_hash": "abc123"},
    )

    assert body == {"store": False, "prompt_cache_key": "abc123"}


def test_provider_cache_hints_keep_explicit_prompt_cache_key() -> None:
    body = merge_provider_cache_hints(
        provider="openai",
        extra_body={"prompt_cache_key": "manual"},
        provider_hints={"stable_prefix_hash": "abc123"},
    )

    assert body == {"prompt_cache_key": "manual"}


def test_provider_cache_hints_do_not_modify_non_openai_provider() -> None:
    body = merge_provider_cache_hints(
        provider="openrouter",
        model="openai/gpt-5.1",
        extra_body={"custom": True},
        provider_hints={"stable_prefix_hash": "abc123"},
    )

    assert body == {"custom": True}


def test_provider_cache_hints_add_openrouter_anthropic_cache_control() -> None:
    body = merge_provider_cache_hints(
        provider="openrouter",
        model="anthropic/claude-sonnet-4.5",
        extra_body={"custom": True},
        provider_hints={"stable_prefix_hash": "abc123"},
    )

    assert body == {"custom": True, "cache_control": {"type": "ephemeral"}}


def test_provider_cache_hints_keep_explicit_anthropic_cache_control() -> None:
    body = merge_provider_cache_hints(
        provider="openrouter",
        model="anthropic/claude-sonnet-4.5",
        extra_body={"cache_control": {"type": "ephemeral", "ttl": "1h"}},
        provider_hints={"stable_prefix_hash": "abc123"},
    )

    assert body == {"cache_control": {"type": "ephemeral", "ttl": "1h"}}


def test_provider_cache_hints_ignore_missing_hash() -> None:
    assert (
        merge_provider_cache_hints(
            provider="openai",
            extra_body=None,
            provider_hints={},
        )
        is None
    )
