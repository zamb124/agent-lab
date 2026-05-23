"""Типизированный merge ресурсов: flow/skill/node карты, shared+patch, LLM deep-merge."""

import pytest
from pydantic import ValidationError

from apps.flows.src.models import ResourceType
from apps.flows.src.models.resource import LLMResourceConfig, LLMResourcePatch
from apps.flows.src.resources.merge import (
    merge_flow_skill_node_resource_maps,
    merge_shared_definition_config_with_patch,
)
from apps.flows.src.resources.merge_llm import (
    merge_llm_resource_config_with_patch,
    merge_llm_resource_patch_dicts,
)


@pytest.mark.parametrize(
    "flow,skill,node,key,expected_resource_id",
    [
        (
            {"a": {"resource_id": "f"}},
            {"a": {"resource_id": "s"}},
            {},
            "a",
            "s",
        ),
        (
            {"a": {"resource_id": "f"}},
            {},
            {"a": {"resource_id": "n"}},
            "a",
            "n",
        ),
        (
            {"a": {"resource_id": "f"}, "b": {"resource_id": "bf"}},
            {"a": {"resource_id": "s"}},
            {"b": {"resource_id": "bn"}},
            "a",
            "s",
        ),
    ],
)
def test_merge_flow_skill_node_resource_maps_last_layer_wins(
    flow: dict,
    skill: dict,
    node: dict,
    key: str,
    expected_resource_id: str,
) -> None:
    merged = merge_flow_skill_node_resource_maps(flow, skill, node)
    assert merged[key]["resource_id"] == expected_resource_id


def test_merge_llm_patch_deep_merges_extra_request_body() -> None:
    base = LLMResourceConfig(
        provider="openrouter",
        model="openai/gpt-4o-mini",
        temperature=0.2,
        extra_request_body={"metadata": {"a": 1}, "top": {"x": 1}},
    )
    out = merge_llm_resource_config_with_patch(
        base,
        {"extra_request_body": {"metadata": {"b": 2}, "other": True}},
    )
    assert out.extra_request_body == {
        "metadata": {"a": 1, "b": 2},
        "top": {"x": 1},
        "other": True,
    }


def test_merge_llm_patch_merges_extra_request_headers() -> None:
    base = LLMResourceConfig(
        provider="openrouter",
        model="m",
        temperature=0.1,
        extra_request_headers={"X-A": "1", "X-B": "old"},
    )
    out = merge_llm_resource_config_with_patch(
        base,
        {"extra_request_headers": {"X-B": "new", "X-C": "3"}},
    )
    assert out.extra_request_headers == {"X-A": "1", "X-B": "new", "X-C": "3"}


def test_llm_resource_patch_accepts_sampling_fields() -> None:
    patch = LLMResourcePatch.model_validate({"top_p": 0.9})
    assert patch.top_p == 0.9


def test_merge_shared_llm_rejects_unknown_patch_field() -> None:
    base = {
        "provider": "openrouter",
        "model": "openai/gpt-4o-mini",
        "temperature": 0.2,
    }
    with pytest.raises(ValidationError):
        merge_shared_definition_config_with_patch(
            ResourceType.LLM,
            base,
            {"unknown_sampling_field": 0.5},
        )


def test_merge_shared_llm_applies_typed_patch() -> None:
    base = {
        "provider": "openrouter",
        "model": "openai/gpt-4o-mini",
        "temperature": 0.2,
        "extra_request_body": {"a": {"x": 1}},
    }
    out = merge_shared_definition_config_with_patch(
        ResourceType.LLM,
        base,
        {"temperature": 0.4, "extra_request_body": {"a": {"y": 2}}},
    )
    assert out["temperature"] == 0.4
    assert out["extra_request_body"] == {"a": {"x": 1, "y": 2}}


def test_merge_llm_resource_patch_dicts_two_partials() -> None:
    first = {"temperature": 0.1, "extra_request_body": {"k": {"a": 1}}}
    second = {"extra_request_body": {"k": {"b": 2}}, "model": "other"}
    out = merge_llm_resource_patch_dicts(first, second)
    assert out["temperature"] == 0.1
    assert out["model"] == "other"
    assert out["extra_request_body"] == {"k": {"a": 1, "b": 2}}


def test_merge_shared_files_shallow_then_validates() -> None:
    base = {
        "bucket": "my-bucket",
        "prefix": "p1",
        "region": "us-east-1",
    }
    out = merge_shared_definition_config_with_patch(
        ResourceType.FILES,
        base,
        {"prefix": "p2"},
    )
    assert out["prefix"] == "p2"
    assert out["bucket"] == "my-bucket"


def test_merge_shared_llm_context_deep_merges_nested_patch() -> None:
    out = merge_shared_definition_config_with_patch(
        ResourceType.LLM_CONTEXT,
        {"profile": "agent", "retrieval": {"top_k": 24, "rerank": True}},
        {"retrieval": {"rerank": False}, "memory": "node"},
    )

    assert out == {
        "profile": "agent",
        "retrieval": {"top_k": 24, "rerank": False},
        "memory": "node",
    }


def test_merge_shared_rag_resource_deep_merges_filters_and_search_options() -> None:
    out = merge_shared_definition_config_with_patch(
        ResourceType.RAG,
        {
            "namespace": "kb",
            "default_top_k": 8,
            "filters": {"tenant": "acme"},
            "search_options": {"channels": {"semantic": True}, "rerank": False},
        },
        {
            "filters": {"collection_id": "support"},
            "search_options": {"rerank": True},
        },
    )

    assert out == {
        "namespace": "kb",
        "provider": "pgvector",
        "default_top_k": 8,
        "filters": {"tenant": "acme", "collection_id": "support"},
        "search_options": {"channels": {"semantic": True}, "rerank": True},
    }
