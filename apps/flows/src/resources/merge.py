"""Карты LLM-ресурсов flow/skill/node и типизированное слияние shared config + patch."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from apps.flows.src.models import ResourceType
from apps.flows.src.models.resource import (
    LLMResourceConfig,
    ResourceMapInput,
    ResourceReferenceInput,
    parse_typed_resource_config,
)
from apps.flows.src.resources.merge_llm import merge_llm_resource_config_with_patch
from core.llm_context import LLMContextPatch
from core.llm_context.merge import deep_merge_dict
from core.rag.rag_resource_bind import RagResourceBindParams, RagResourceBindPatch
from core.types import JsonObject, require_json_object


def merge_flow_skill_node_resource_maps(
    flow_resources: Mapping[str, ResourceReferenceInput] | None,
    skill_resources: Mapping[str, ResourceReferenceInput] | None,
    node_resources: Mapping[str, ResourceReferenceInput] | None,
) -> ResourceMapInput:
    """Parity с ResourceResolver.resolve_for_node: объединение словарей по ключам."""
    merged: ResourceMapInput = {}
    merged.update(flow_resources or {})
    merged.update(skill_resources or {})
    merged.update(node_resources or {})
    return merged


MergeConfigFn = Callable[[JsonObject, JsonObject], JsonObject]


def _llm_merge_config(base: JsonObject, patch: JsonObject) -> JsonObject:
    typed_base = LLMResourceConfig.model_validate(base)
    merged = merge_llm_resource_config_with_patch(typed_base, patch)
    return require_json_object(
        merged.model_dump(mode="json", exclude_none=False),
        "llm_resource.merge",
    )


def _llm_context_merge_config(base: JsonObject, patch: JsonObject) -> JsonObject:
    _ = LLMContextPatch.model_validate(base)
    _ = LLMContextPatch.model_validate(patch)
    merged = require_json_object(deep_merge_dict(base, patch), "llm_context_resource.merge")
    typed = LLMContextPatch.model_validate(merged)
    return require_json_object(
        typed.model_dump(mode="json", exclude_none=True),
        "llm_context_resource.typed_merge",
    )


def _rag_merge_config(base: JsonObject, patch: JsonObject) -> JsonObject:
    _ = RagResourceBindParams.model_validate(base)
    _ = RagResourceBindPatch.model_validate(patch)
    merged = require_json_object(deep_merge_dict(base, patch), "rag_resource.merge")
    typed = RagResourceBindParams.model_validate(merged)
    return require_json_object(
        typed.model_dump(mode="json", exclude_none=True),
        "rag_resource.typed_merge",
    )


MERGE_SHARED_CONFIG_BY_TYPE: dict[ResourceType, MergeConfigFn] = {
    ResourceType.LLM: _llm_merge_config,
    ResourceType.LLM_CONTEXT: _llm_context_merge_config,
    ResourceType.RAG: _rag_merge_config,
}


def merge_shared_definition_config_with_patch(
    resource_type: ResourceType,
    base_config: JsonObject,
    patch: JsonObject | None,
) -> JsonObject:
    """
    Сливает shared definition.config с ResourceReference.config (override).

    LLM — единственный runtime resource type. Code/files доступны sandbox-коду
    через capability-gateway/tools, а не через resources namespace.
    """
    if not patch:
        return dict(base_config)
    merger = MERGE_SHARED_CONFIG_BY_TYPE.get(resource_type)
    if merger is None:
        merged: JsonObject = {**base_config, **patch}
        _ = parse_typed_resource_config(resource_type, merged)
        return merged
    merged = merger(base_config, patch)
    _ = parse_typed_resource_config(resource_type, merged)
    return merged
