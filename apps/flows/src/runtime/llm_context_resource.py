"""Разрешение LLM context resources в runtime."""

from __future__ import annotations

from collections.abc import Mapping

from apps.flows.src.models import ResourceType
from apps.flows.src.models.resource import (
    ResourceDefinition,
    ResourceReference,
    ResourceReferenceInput,
)
from apps.flows.src.resources.merge import (
    merge_flow_skill_node_resource_maps,
    merge_shared_definition_config_with_patch,
)
from core.llm_context import (
    LLMContextConfig,
    LLMContextPatch,
    LLMContextProfile,
)
from core.llm_context.resolver import (
    resolve_company_llm_context_patch,
    resolve_llm_context_policy,
)
from core.types import JsonObject


async def infer_unique_llm_context_resource_key_from_merged_maps(
    *,
    flow_resources: Mapping[str, ResourceReferenceInput],
    skill_resources: Mapping[str, ResourceReferenceInput] | None,
    node_resources_raw: Mapping[str, ResourceReferenceInput],
) -> str | None:
    """
    Выводит context resource только если в объединённой карте flow/skill/node ровно один.

    Аналогично выводу LLM resource: ноль или несколько context resources — «нет неявного
    выбора»; авторы уточняют через ``llm_context_resource_key``.
    """
    merged = merge_flow_skill_node_resource_maps(
        flow_resources, skill_resources, node_resources_raw
    )
    context_keys: list[str] = []
    for key, ref_raw in merged.items():
        ref = ResourceReference.model_validate(ref_raw) if isinstance(ref_raw, dict) else ref_raw
        if ref.is_inline:
            if ref.type == ResourceType.LLM_CONTEXT:
                context_keys.append(key)
            continue
        resource_id = ref.resource_id
        if resource_id is None:
            raise ValueError(f"Resource '{key}': shared reference without resource_id")
        definition = await ResourceDefinition.get(
            ResourceDefinition.row_id(resource_id)
        )
        if definition is not None and definition.type == ResourceType.LLM_CONTEXT:
            context_keys.append(key)
    if len(context_keys) != 1:
        return None
    return context_keys[0]


async def resolve_llm_context_resource_patch(
    *,
    llm_context_resource_key: str | None,
    flow_resources: Mapping[str, ResourceReferenceInput],
    skill_resources: Mapping[str, ResourceReferenceInput] | None,
    node_resources_raw: Mapping[str, ResourceReferenceInput],
) -> LLMContextPatch | None:
    """Разрешает patch слоя resource для иерархии platform context."""
    key = str(llm_context_resource_key or "").strip()
    if not key:
        inferred = await infer_unique_llm_context_resource_key_from_merged_maps(
            flow_resources=flow_resources,
            skill_resources=skill_resources,
            node_resources_raw=node_resources_raw,
        )
        if inferred is None:
            return None
        key = inferred

    merged = merge_flow_skill_node_resource_maps(
        flow_resources, skill_resources, node_resources_raw
    )
    if key not in merged:
        raise ValueError(f"llm_context_resource_key '{key}' is missing from flow/skill/node resources")

    ref_raw = merged[key]
    ref = ResourceReference.model_validate(ref_raw) if isinstance(ref_raw, dict) else ref_raw

    if ref.is_inline:
        if ref.type != ResourceType.LLM_CONTEXT:
            raise ValueError(f"Resource '{key}': expected type llm_context, got {ref.type!r}")
        if ref.config is None:
            raise ValueError(f"Resource '{key}': inline LLM context without config")
        return LLMContextPatch.model_validate(ref.config)

    resource_id = ref.resource_id
    if resource_id is None:
        raise ValueError(f"Resource '{key}': shared reference without resource_id")
    definition = await ResourceDefinition.get(
        ResourceDefinition.row_id(resource_id)
    )
    if definition is None:
        raise ValueError(f"Shared resource '{resource_id}' not found in the database")
    if definition.type != ResourceType.LLM_CONTEXT:
        raise ValueError(
            f"Resource '{key}': shared '{resource_id}' is not LLM context, got {definition.type!r}"
        )
    merged_config = definition.config
    if ref.config:
        merged_config = merge_shared_definition_config_with_patch(
            ResourceType.LLM_CONTEXT,
            definition.config,
            ref.config,
        )
    return LLMContextPatch.model_validate(merged_config)


async def resolve_llm_context_policy_for_runtime(
    *,
    llm_context_resource_key: str | None,
    flow_resources: Mapping[str, ResourceReferenceInput],
    skill_resources: Mapping[str, ResourceReferenceInput] | None,
    node_resources_raw: Mapping[str, ResourceReferenceInput],
    node: LLMContextPatch | JsonObject | None = None,
    call: LLMContextPatch | JsonObject | None = None,
    company: LLMContextPatch | JsonObject | None = None,
    config: LLMContextConfig | None = None,
) -> LLMContextProfile:
    """Разрешает platform -> company -> resource -> node -> inline call для flow runtime."""
    resource = await resolve_llm_context_resource_patch(
        llm_context_resource_key=llm_context_resource_key,
        flow_resources=flow_resources,
        skill_resources=skill_resources,
        node_resources_raw=node_resources_raw,
    )
    company_patch = company if company is not None else resolve_company_llm_context_patch()
    return resolve_llm_context_policy(
        config=config,
        company=company_patch,
        resource=resource,
        node=node,
        call=call,
    )


__all__ = [
    "infer_unique_llm_context_resource_key_from_merged_maps",
    "resolve_llm_context_policy_for_runtime",
    "resolve_llm_context_resource_patch",
]
