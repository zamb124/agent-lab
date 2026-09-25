from __future__ import annotations

import pytest

from apps.flows.src.models.resource import ResourceDefinition, ResourceReference, ResourceType
from apps.flows.src.runtime.llm_context_resource import (
    infer_unique_llm_context_resource_key_from_merged_maps,
    resolve_llm_context_policy_for_runtime,
    resolve_llm_context_resource_patch,
)
from core.llm_context import (
    LLMContextBudget,
    LLMContextConfig,
    LLMContextPatch,
    LLMContextProfile,
    LLMContextRetrievalPolicy,
)
from core.types import JsonObject


async def _shared_resource(resource_id: str, resource_type: ResourceType, config: JsonObject) -> str:
    _ = await ResourceDefinition.set(
        ResourceDefinition(resource_id=resource_id, type=resource_type, config=config)
    )
    return resource_id


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


@pytest.mark.asyncio
async def test_infers_unique_inline_llm_context_resource() -> None:
    key = await infer_unique_llm_context_resource_key_from_merged_maps(
        flow_resources={
            "ctx": {"type": "llm_context", "config": {"profile": "agent"}},
            "llm": {"type": "llm", "config": {"provider": "openrouter", "model": "m"}},
        },
        skill_resources=None,
        node_resources_raw={},
    )

    assert key == "ctx"


@pytest.mark.asyncio
async def test_multiple_context_resources_are_not_inferred() -> None:
    key = await infer_unique_llm_context_resource_key_from_merged_maps(
        flow_resources={
            "ctx_a": {"type": "llm_context", "config": {"profile": "agent"}},
            "ctx_b": {"type": "llm_context", "config": {"profile": "compact"}},
        },
        skill_resources=None,
        node_resources_raw={},
    )

    assert key is None


@pytest.mark.asyncio
async def test_infers_unique_shared_llm_context_resource(unique_id: str) -> None:
    resource_id = await _shared_resource(
        f"shared_ctx_{unique_id}", ResourceType.LLM_CONTEXT, {"profile": "agent"}
    )
    key = await infer_unique_llm_context_resource_key_from_merged_maps(
        flow_resources={"ctx": {"resource_id": resource_id}},
        skill_resources=None,
        node_resources_raw={},
    )

    assert key == "ctx"


@pytest.mark.asyncio
async def test_resolves_shared_context_resource_with_reference_patch(unique_id: str) -> None:
    resource_id = await _shared_resource(
        f"shared_ctx_{unique_id}",
        ResourceType.LLM_CONTEXT,
        {"profile": "agent", "retrieval": {"top_k": 24, "rerank": True}},
    )

    patch = await resolve_llm_context_resource_patch(
        llm_context_resource_key="ctx",
        flow_resources={
            "ctx": {
                "resource_id": resource_id,
                "config": {"retrieval": {"rerank": False}, "memory": "flow"},
            }
        },
        skill_resources=None,
        node_resources_raw={},
    )

    assert patch is not None
    assert patch.profile == "agent"
    assert patch.memory == "flow"
    assert patch.retrieval is not None
    assert patch.retrieval.top_k == 24
    assert patch.retrieval.rerank is False


@pytest.mark.asyncio
async def test_resolves_inferred_context_resource_patch() -> None:
    patch = await resolve_llm_context_resource_patch(
        llm_context_resource_key=None,
        flow_resources={"ctx": {"type": "llm_context", "config": {"profile": "agent"}}},
        skill_resources=None,
        node_resources_raw={},
    )

    assert patch is not None
    assert patch.profile == "agent"


@pytest.mark.asyncio
async def test_inline_context_resource_allows_empty_patch() -> None:
    patch = await resolve_llm_context_resource_patch(
        llm_context_resource_key="ctx",
        flow_resources={"ctx": {"type": "llm_context", "config": {}}},
        skill_resources=None,
        node_resources_raw={},
    )

    assert patch == LLMContextPatch()


@pytest.mark.asyncio
async def test_runtime_policy_applies_company_resource_node_call_order() -> None:
    policy = await resolve_llm_context_policy_for_runtime(
        llm_context_resource_key="ctx",
        flow_resources={
            "ctx": {"type": "llm_context", "config": {"profile": "agent", "memory": "flow"}},
        },
        skill_resources=None,
        node_resources_raw={},
        company=LLMContextPatch(profile="compact", memory="company"),
        node=LLMContextPatch(memory="node", retrieval={"top_k": 7}),
        call=LLMContextPatch(cache="off"),
        config=_config(),
    )

    assert policy.mode == "agent"
    assert policy.memory == "node"
    assert policy.retrieval.mode == "hybrid"
    assert policy.retrieval.top_k == 7
    assert policy.cache == "off"


@pytest.mark.asyncio
async def test_explicit_context_resource_key_rejects_wrong_type() -> None:
    with pytest.raises(ValueError, match="llm_context"):
        await resolve_llm_context_resource_patch(
            llm_context_resource_key="llm",
            flow_resources={
                "llm": {"type": "llm", "config": {"provider": "openrouter", "model": "m"}},
            },
            skill_resources=None,
            node_resources_raw={},
        )


@pytest.mark.asyncio
async def test_context_resource_resolution_errors_are_strict(unique_id: str) -> None:
    assert await resolve_llm_context_resource_patch(
        llm_context_resource_key=None,
        flow_resources={},
        skill_resources=None,
        node_resources_raw={},
    ) is None

    with pytest.raises(ValueError, match="is missing"):
        await resolve_llm_context_resource_patch(
            llm_context_resource_key="missing",
            flow_resources={"ctx": {"type": "llm_context", "config": {}}},
            skill_resources=None,
            node_resources_raw={},
        )

    with pytest.raises(ValueError, match="inline LLM context without config"):
        await resolve_llm_context_resource_patch(
            llm_context_resource_key="ctx",
            flow_resources={
                "ctx": ResourceReference.model_construct(
                    type=ResourceType.LLM_CONTEXT,
                    config=None,
                    resource_id=None,
                )
            },
            skill_resources=None,
            node_resources_raw={},
        )

    with pytest.raises(ValueError, match="not found"):
        await resolve_llm_context_resource_patch(
            llm_context_resource_key="ctx",
            flow_resources={"ctx": {"resource_id": f"missing_ctx_{unique_id}"}},
            skill_resources=None,
            node_resources_raw={},
        )

    shared_llm_id = await _shared_resource(
        f"shared_llm_{unique_id}",
        ResourceType.LLM,
        {"provider": "openrouter", "model": "m"},
    )
    with pytest.raises(ValueError, match="is not LLM context"):
        await resolve_llm_context_resource_patch(
            llm_context_resource_key="ctx",
            flow_resources={"ctx": {"resource_id": shared_llm_id}},
            skill_resources=None,
            node_resources_raw={},
        )
