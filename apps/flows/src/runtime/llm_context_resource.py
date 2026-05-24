"""Runtime resolution for LLM context resources."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from apps.flows.src.models import ResourceType
from apps.flows.src.models.resource import ResourceReference, ResourceReferenceInput
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

if TYPE_CHECKING:
    from apps.flows.src.db import ResourceRepository


async def infer_unique_llm_context_resource_key_from_merged_maps(
    *,
    flow_resources: Mapping[str, ResourceReferenceInput],
    skill_resources: Mapping[str, ResourceReferenceInput] | None,
    node_resources_raw: Mapping[str, ResourceReferenceInput],
    repository: ResourceRepository | None,
) -> str | None:
    """
    Infer a context resource only when the merged flow/skill/node map has exactly one.

    This mirrors LLM resource inference: zero or multiple context resources means "no implicit
    choice"; authors can disambiguate with ``llm_context_resource_key``.
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
        if repository is None:
            raise ValueError("resource_repository обязателен для shared LLM context resources")
        resource_id = ref.resource_id
        if resource_id is None:
            raise ValueError(f"Ресурс '{key}': shared reference без resource_id")
        definition = await repository.get(resource_id)
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
    repository: ResourceRepository | None,
) -> LLMContextPatch | None:
    """Resolve the resource layer patch for the platform context hierarchy."""
    key = str(llm_context_resource_key or "").strip()
    if not key:
        inferred = await infer_unique_llm_context_resource_key_from_merged_maps(
            flow_resources=flow_resources,
            skill_resources=skill_resources,
            node_resources_raw=node_resources_raw,
            repository=repository,
        )
        if inferred is None:
            return None
        key = inferred

    merged = merge_flow_skill_node_resource_maps(
        flow_resources, skill_resources, node_resources_raw
    )
    if key not in merged:
        raise ValueError(f"llm_context_resource_key '{key}' отсутствует в ресурсах flow/skill/node")

    ref_raw = merged[key]
    ref = ResourceReference.model_validate(ref_raw) if isinstance(ref_raw, dict) else ref_raw

    if ref.is_inline:
        if ref.type != ResourceType.LLM_CONTEXT:
            raise ValueError(f"Ресурс '{key}': ожидается type llm_context, получено {ref.type!r}")
        if ref.config is None:
            raise ValueError(f"Ресурс '{key}': inline LLM context без config")
        return LLMContextPatch.model_validate(ref.config)

    if repository is None:
        raise ValueError("resource_repository обязателен для shared LLM context resources")
    resource_id = ref.resource_id
    if resource_id is None:
        raise ValueError(f"Ресурс '{key}': shared reference без resource_id")
    definition = await repository.get(resource_id)
    if definition is None:
        raise ValueError(f"Shared resource '{resource_id}' не найден в БД")
    if definition.type != ResourceType.LLM_CONTEXT:
        raise ValueError(
            f"Ресурс '{key}': shared '{resource_id}' не LLM context, а {definition.type!r}"
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
    repository: ResourceRepository | None,
    node: LLMContextPatch | JsonObject | None = None,
    call: LLMContextPatch | JsonObject | None = None,
    company: LLMContextPatch | JsonObject | None = None,
    config: LLMContextConfig | None = None,
) -> LLMContextProfile:
    """Resolve platform -> company -> resource -> node -> inline call for flow runtime."""
    resource = await resolve_llm_context_resource_patch(
        llm_context_resource_key=llm_context_resource_key,
        flow_resources=flow_resources,
        skill_resources=skill_resources,
        node_resources_raw=node_resources_raw,
        repository=repository,
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
