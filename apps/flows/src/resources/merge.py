"""Карты LLM-ресурсов flow/skill/node и типизированное слияние shared config + patch."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apps.flows.src.models import ResourceType
from apps.flows.src.models.resource import (
    LLMResourceConfig,
    parse_typed_resource_config,
)
from apps.flows.src.resources.merge_llm import merge_llm_resource_config_with_patch


def merge_flow_skill_node_resource_maps(
    flow_resources: dict[str, Any] | None,
    skill_resources: dict[str, Any] | None,
    node_resources: dict[str, Any] | None,
) -> dict[str, Any]:
    """Parity с ResourceResolver.resolve_for_node: объединение словарей по ключам."""
    merged: dict[str, Any] = {}
    merged.update(flow_resources or {})
    merged.update(skill_resources or {})
    merged.update(node_resources or {})
    return merged


MergeConfigFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def _llm_merge_config(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    typed_base = LLMResourceConfig.model_validate(base)
    merged = merge_llm_resource_config_with_patch(typed_base, patch)
    return merged.model_dump(mode="json", exclude_none=False)


MERGE_SHARED_CONFIG_BY_TYPE: dict[ResourceType, MergeConfigFn] = {
    ResourceType.LLM: _llm_merge_config,
}


def merge_shared_definition_config_with_patch(
    resource_type: ResourceType,
    base_config: dict[str, Any],
    patch: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Сливает shared definition.config с ResourceReference.config (override).

    LLM — единственный runtime resource type. Code/files доступны sandbox-коду
    через capability-gateway/tools, а не через resources namespace.
    """
    if not patch:
        return dict(base_config)
    merger = MERGE_SHARED_CONFIG_BY_TYPE.get(resource_type)
    if merger is None:
        raise ValueError(f"Unsupported resource type: {resource_type}")
    merged = merger(dict(base_config), patch)
    parse_typed_resource_config(resource_type, merged)
    return merged
