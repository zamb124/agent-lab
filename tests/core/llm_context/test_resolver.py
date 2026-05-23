from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.company_ai import METADATA_KEY, CompanyAIProviders, LLMContextPatch
from core.context import Company, Context, User, clear_context, set_context
from core.llm_context import (
    LLMContextBudget,
    LLMContextConfig,
    LLMContextProfile,
    LLMContextRetrievalPatch,
    LLMContextRetrievalPolicy,
    SimpleTokenCounter,
    TiktokenTokenCounter,
)
from core.llm_context.merge import merge_dict_layers
from core.llm_context.resolver import (
    resolve_company_llm_context_patch,
    resolve_llm_context_policy,
)


def _config() -> LLMContextConfig:
    small = LLMContextBudget(
        max_input_tokens=1_000,
        output_reserve_tokens=100,
        reasoning_reserve_tokens=0,
        safety_buffer_tokens=50,
        active_window_tokens=100,
        memory_tokens=100,
        rag_tokens=100,
        tool_result_tokens=50,
    )
    large = LLMContextBudget(
        max_input_tokens=10_000,
        output_reserve_tokens=500,
        reasoning_reserve_tokens=500,
        safety_buffer_tokens=100,
        active_window_tokens=1_000,
        memory_tokens=2_000,
        rag_tokens=2_000,
        tool_result_tokens=500,
    )
    return LLMContextConfig(
        default_profile="compact",
        budgets={"small": small, "large": large},
        profiles={
            "compact": LLMContextProfile(
                mode="window",
                budget=small,
                memory="off",
                retrieval=LLMContextRetrievalPolicy(mode="off", rerank=False),
                compaction="auto",
                cache="auto",
            ),
            "agent": LLMContextProfile(
                mode="agent",
                budget=large,
                memory="session",
                retrieval=LLMContextRetrievalPolicy(mode="hybrid", top_k=32, rerank=True),
                compaction="auto",
                cache="provider_hints",
            ),
        },
    )


def test_resolver_applies_layers_in_platform_company_resource_node_call_order() -> None:
    policy = resolve_llm_context_policy(
        config=_config(),
        company={"budget": "large", "retrieval": "semantic"},
        resource={"memory": "flow"},
        node={"profile": "agent", "memory": "node"},
        call={"retrieval": {"top_k": 7, "rerank": False}, "cache": "off"},
    )

    assert policy.mode == "agent"
    assert policy.budget.max_input_tokens == 10_000
    assert policy.memory == "node"
    assert policy.retrieval.mode == "hybrid"
    assert policy.retrieval.top_k == 7
    assert policy.retrieval.rerank is False
    assert policy.cache == "off"


def test_resolver_rejects_unknown_profile_and_budget() -> None:
    with pytest.raises(ValueError, match="profile"):
        resolve_llm_context_policy(config=_config(), node={"profile": "missing"})

    with pytest.raises(ValueError, match="budget"):
        resolve_llm_context_policy(config=_config(), node={"budget": "max"})


def test_strict_patch_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        LLMContextPatch.model_validate({"unknown": True})


def test_model_validators_reject_invalid_profiles_budgets_and_retrieval() -> None:
    with pytest.raises(ValidationError, match="reserves"):
        LLMContextBudget(
            max_input_tokens=100,
            output_reserve_tokens=80,
            reasoning_reserve_tokens=20,
            safety_buffer_tokens=0,
        )

    with pytest.raises(ValidationError, match="rerank"):
        LLMContextRetrievalPolicy(mode="off", rerank=True)

    with pytest.raises(ValidationError, match="profile"):
        LLMContextPatch(profile="bad profile")

    with pytest.raises(ValidationError, match="default_profile"):
        LLMContextConfig(default_profile="bad profile")

    with pytest.raises(ValidationError, match="slug"):
        LLMContextConfig(profiles={"bad key": LLMContextProfile()})

    with pytest.raises(ValidationError, match="absent"):
        LLMContextConfig(default_profile="missing")

    patch = LLMContextRetrievalPatch(top_k=3)
    assert patch.top_k == 3


def test_merge_layers_and_token_counters_are_concrete_implementations() -> None:
    assert merge_dict_layers(
        {"a": {"x": 1}, "b": 1},
        None,
        {"a": {"y": 2}},
    ) == {"a": {"x": 1, "y": 2}, "b": 1}

    simple = SimpleTokenCounter()
    assert simple.count_text("") == 0
    assert simple.count_message({"role": "user", "content": {"text": "hello"}}) >= 2

    tiktoken_counter = TiktokenTokenCounter()
    assert tiktoken_counter.count_text("") == 0
    assert tiktoken_counter.count_text("hello world") >= 1


def test_company_metadata_can_store_context_patch_without_affecting_llm_capabilities() -> None:
    providers = CompanyAIProviders(llm_context=LLMContextPatch(profile="agent", memory="company"))
    metadata = {METADATA_KEY: providers.to_metadata_dict()}

    restored = CompanyAIProviders.from_metadata(metadata)

    assert restored.llm_context is not None
    assert restored.llm_context.profile == "agent"
    assert restored.llm_context.memory == "company"
    assert restored.llm_chat is None


def test_active_company_context_patch_reader() -> None:
    clear_context()
    try:
        providers = CompanyAIProviders(
            llm_context=LLMContextPatch(profile="compact", retrieval="semantic")
        )
        company = Company(
            company_id="c1",
            name="Company",
            metadata={METADATA_KEY: providers.to_metadata_dict()},
        )
        user = User(user_id="u1", name="User", active_company_id="c1")
        set_context(Context(user=user, active_company=company, channel="test"))

        patch = resolve_company_llm_context_patch()

        assert patch is not None
        assert patch.profile == "compact"
        assert patch.retrieval == "semantic"
    finally:
        clear_context()


def test_company_context_patch_reader_handles_absent_and_invalid_metadata() -> None:
    clear_context()
    try:
        assert resolve_company_llm_context_patch() is None

        company = Company(company_id="c1", name="Company", metadata={})
        user = User(user_id="u1", name="User", active_company_id="c1")
        set_context(Context(user=user, active_company=company, channel="test"))
        assert resolve_company_llm_context_patch() is None

        company.metadata = {METADATA_KEY: {}}
        assert resolve_company_llm_context_patch() is None

        company.metadata = "invalid"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="metadata"):
            resolve_company_llm_context_patch()

        company.metadata = {METADATA_KEY: "invalid"}
        with pytest.raises(ValueError, match=METADATA_KEY):
            resolve_company_llm_context_patch()
    finally:
        clear_context()
