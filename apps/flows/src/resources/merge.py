"""
Карты ресурсов flow/skill/node и типизированное слияние shared config + patch.

Порядок ключей как в ResourceResolver: последующий слой перекрывает предыдущий
(flow → skill → node).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from apps.flows.src.models import ResourceType
from apps.flows.src.models.resource import (
    LLMResourceConfig,
    parse_typed_resource_config,
)
from apps.flows.src.resources.merge_llm import merge_llm_resource_config_with_patch


def merge_flow_skill_node_resource_maps(
    flow_resources: Optional[Dict[str, Any]],
    skill_resources: Optional[Dict[str, Any]],
    node_resources: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Parity с ResourceResolver.resolve_for_node: объединение словарей по ключам."""
    merged: Dict[str, Any] = {}
    merged.update(flow_resources or {})
    merged.update(skill_resources or {})
    merged.update(node_resources or {})
    return merged


MergeConfigFn = Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]


def _shallow_merge_config(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    return {**base, **patch}


def _llm_merge_config(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    typed_base = LLMResourceConfig.model_validate(base)
    merged = merge_llm_resource_config_with_patch(typed_base, patch)
    return merged.model_dump(mode="json", exclude_none=False)


MERGE_SHARED_CONFIG_BY_TYPE: Dict[ResourceType, MergeConfigFn] = {
    ResourceType.LLM: _llm_merge_config,
}


def merge_shared_definition_config_with_patch(
    resource_type: ResourceType,
    base_config: Dict[str, Any],
    patch: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Сливает shared definition.config с ResourceReference.config (override).

    Для LLM — типизированный patch и deep merge extra_request_body/headers.
    Для прочих типов — shallow {**base, **patch} с последующим parse_typed_resource_config
    (строгая схема целевого типа).
    """
    if not patch:
        return dict(base_config)
    merger = MERGE_SHARED_CONFIG_BY_TYPE.get(resource_type, _shallow_merge_config)
    merged = merger(dict(base_config), patch)
    parse_typed_resource_config(resource_type, merged)
    return merged
