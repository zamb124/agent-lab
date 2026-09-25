"""Слияние NodeLLMConfig с LLM-ресурсом по llm_resource_key."""

import pytest

from apps.flows.src.models import ResourceType
from apps.flows.src.models.node_config import NodeLLMConfig
from apps.flows.src.models.resource import ResourceDefinition
from apps.flows.src.runtime.llm_resource_config import (
    infer_unique_llm_resource_key_from_merged_maps,
    resolve_llm_config_with_resource_key,
)
from core.types import JsonObject


async def _shared_resource(resource_id: str, resource_type: ResourceType, config: JsonObject) -> str:
    _ = await ResourceDefinition.set(
        ResourceDefinition(resource_id=resource_id, type=resource_type, config=config)
    )
    return resource_id


@pytest.mark.asyncio
async def test_resolve_merges_inline_llm_resource() -> None:
    flow_resources = {
        "gpt": {
            "type": "llm",
            "config": {
                "provider": "openrouter",
                "model": "openai/gpt-4o",
                "temperature": 0.2,
            },
        }
    }
    ov = NodeLLMConfig(llm_resource_key="gpt", temperature=0.9)
    merged = await resolve_llm_config_with_resource_key(
        llm_config=ov,
        flow_resources=flow_resources,
        skill_resources=None,
        node_resources_raw={},
    )
    assert merged is not None
    assert merged.llm_resource_key is None
    assert merged.model == "openai/gpt-4o"
    assert merged.provider == "openrouter"
    assert merged.temperature == 0.9


@pytest.mark.asyncio
async def test_resolve_shared_resource_from_catalog(unique_id: str) -> None:
    resource_id = await _shared_resource(
        f"llm-{unique_id}",
        ResourceType.LLM,
        {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.5},
    )
    flow_resources = {"shared": {"resource_id": resource_id}}
    ov = NodeLLMConfig(llm_resource_key="shared", model="should-not-apply")
    merged = await resolve_llm_config_with_resource_key(
        llm_config=ov,
        flow_resources=flow_resources,
        skill_resources=None,
        node_resources_raw={},
    )
    assert merged is not None
    assert merged.model == "should-not-apply"
    assert merged.provider == "openai"
    assert merged.temperature == 0.5


@pytest.mark.asyncio
async def test_infer_unique_llm_key_single_inline() -> None:
    flow_resources = {
        "only": {
            "type": "llm",
            "config": {"provider": "openrouter", "model": "x", "temperature": 0.1},
        }
    }
    key = await infer_unique_llm_resource_key_from_merged_maps(
        flow_resources=flow_resources,
        skill_resources=None,
        node_resources_raw={},
    )
    assert key == "only"


@pytest.mark.asyncio
async def test_infer_unique_llm_key_none_when_multiple() -> None:
    flow_resources = {
        "a": {"type": "llm", "config": {"provider": "openrouter", "model": "a", "temperature": 0.1}},
        "b": {"type": "llm", "config": {"provider": "openrouter", "model": "b", "temperature": 0.2}},
    }
    key = await infer_unique_llm_resource_key_from_merged_maps(
        flow_resources=flow_resources,
        skill_resources=None,
        node_resources_raw={},
    )
    assert key is None


@pytest.mark.asyncio
async def test_infer_unique_llm_key_shared_from_catalog(unique_id: str) -> None:
    resource_id = await _shared_resource(
        f"llm-{unique_id}",
        ResourceType.LLM,
        {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.5},
    )
    key = await infer_unique_llm_resource_key_from_merged_maps(
        flow_resources={"ref": {"resource_id": resource_id}},
        skill_resources=None,
        node_resources_raw={},
    )
    assert key == "ref"


@pytest.mark.asyncio
async def test_infer_unique_llm_key_two_shared_one_llm_counts_one(unique_id: str) -> None:
    llm_id = await _shared_resource(
        f"llm-{unique_id}",
        ResourceType.LLM,
        {"provider": "openai", "model": "m", "temperature": 0.1},
    )
    files_id = await _shared_resource(
        f"files-{unique_id}",
        ResourceType.FILES,
        {"bucket": "b", "prefix": "", "region": "us-east-1"},
    )
    key = await infer_unique_llm_resource_key_from_merged_maps(
        flow_resources={"f": {"resource_id": files_id}, "l": {"resource_id": llm_id}},
        skill_resources=None,
        node_resources_raw={},
    )
    assert key == "l"
