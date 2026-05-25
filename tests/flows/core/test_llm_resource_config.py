"""Слияние NodeLLMConfig с LLM-ресурсом по llm_resource_key."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.flows.src.models import ResourceType
from apps.flows.src.models.node_config import NodeLLMConfig
from apps.flows.src.runtime.llm_resource_config import (
    infer_unique_llm_resource_key_from_merged_maps,
    resolve_llm_config_with_resource_key,
)


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
        repository=MagicMock(),
    )
    assert merged is not None
    assert merged.llm_resource_key is None
    assert merged.model == "openai/gpt-4o"
    assert merged.provider == "openrouter"
    assert merged.temperature == 0.9


@pytest.mark.asyncio
async def test_resolve_shared_resource_from_repository() -> None:
    repo = AsyncMock()
    repo.get = AsyncMock(
        return_value=MagicMock(
            type=ResourceType.LLM,
            config={
                "provider": "openai",
                "model": "gpt-4o-mini",
                "temperature": 0.5,
            },
        )
    )

    flow_resources = {
        "shared": {"resource_id": "rid-1"},
    }
    ov = NodeLLMConfig(llm_resource_key="shared", model="should-not-apply")
    merged = await resolve_llm_config_with_resource_key(
        llm_config=ov,
        flow_resources=flow_resources,
        skill_resources=None,
        node_resources_raw={},
        repository=repo,
    )
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
        repository=MagicMock(),
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
        repository=MagicMock(),
    )
    assert key is None


@pytest.mark.asyncio
async def test_infer_unique_llm_key_shared_from_repository() -> None:
    repo = AsyncMock()
    repo.get = AsyncMock(
        return_value=MagicMock(
            type=ResourceType.LLM,
            config={"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.5},
        )
    )
    flow_resources = {"ref": {"resource_id": "rid-1"}}
    key = await infer_unique_llm_resource_key_from_merged_maps(
        flow_resources=flow_resources,
        skill_resources=None,
        node_resources_raw={},
        repository=repo,
    )
    assert key == "ref"


@pytest.mark.asyncio
async def test_infer_unique_llm_key_two_shared_one_llm_counts_one() -> None:
    repo = AsyncMock()

    async def _get(rid: str):
        if rid == "llm-1":
            return MagicMock(
                type=ResourceType.LLM,
                config={"provider": "openai", "model": "m", "temperature": 0.1},
            )
        if rid == "files-1":
            return MagicMock(
                type=ResourceType.FILES,
                config={"bucket": "b", "prefix": "", "region": "us-east-1"},
            )
        raise AssertionError(f"unexpected resource_id {rid!r}")

    repo.get = AsyncMock(side_effect=_get)
    flow_resources = {
        "f": {"resource_id": "files-1"},
        "l": {"resource_id": "llm-1"},
    }
    key = await infer_unique_llm_resource_key_from_merged_maps(
        flow_resources=flow_resources,
        skill_resources=None,
        node_resources_raw={},
        repository=repo,
    )
    assert key == "l"
