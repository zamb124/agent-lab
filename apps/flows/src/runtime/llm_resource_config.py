"""Слияние NodeLLMConfig с LLM-ресурсом по ключу из flow/skill/node resources."""

from __future__ import annotations

from collections.abc import Mapping

from apps.flows.src.models import ResourceType
from apps.flows.src.models.node_config import NodeLLMConfig
from apps.flows.src.models.resource import (
    LLMResourceConfig,
    ResourceDefinition,
    ResourceReference,
    ResourceReferenceInput,
)
from apps.flows.src.resources.merge import (
    merge_flow_skill_node_resource_maps,
    merge_shared_definition_config_with_patch,
)
from apps.flows.src.resources.merge_llm import merge_llm_resource_into_node_config


async def infer_unique_llm_resource_key_from_merged_maps(
    *,
    flow_resources: Mapping[str, ResourceReferenceInput],
    skill_resources: Mapping[str, ResourceReferenceInput] | None,
    node_resources_raw: Mapping[str, ResourceReferenceInput],
) -> str | None:
    """
    Если в merge (flow → skill → node) ровно один ключ с типом LLM — возвращает его идентификатор.
    Иначе None (0 или несколько LLM).

    Inline: ResourceReference.type == llm. Reference: тип shared из ResourceDefinition.get.
    """
    merged = merge_flow_skill_node_resource_maps(
        flow_resources, skill_resources, node_resources_raw
    )
    llm_keys: list[str] = []
    for key, ref_raw in merged.items():
        ref = ResourceReference.model_validate(ref_raw) if isinstance(ref_raw, dict) else ref_raw
        if ref.is_inline:
            if ref.type == ResourceType.LLM:
                llm_keys.append(key)
            continue
        resource_id = ref.resource_id
        if resource_id is None:
            raise ValueError(f"Resource '{key}': shared reference without resource_id")
        definition = await ResourceDefinition.get(
            ResourceDefinition.resource_row_id_for_active_company(resource_id)
        )
        if definition is not None and definition.type == ResourceType.LLM:
            llm_keys.append(key)
    if len(llm_keys) != 1:
        return None
    return llm_keys[0]


async def resolve_llm_config_with_resource_key(
    *,
    llm_config: NodeLLMConfig | None,
    flow_resources: Mapping[str, ResourceReferenceInput],
    skill_resources: Mapping[str, ResourceReferenceInput] | None,
    node_resources_raw: Mapping[str, ResourceReferenceInput],
) -> NodeLLMConfig | None:
    """
    Если в config задан llm_resource_key — подмешивает LLMResourceConfig из мержи ресурсов.
    Ключи flow → skill → node (как в ResourceResolver).
    Результат без llm_resource_key, чтобы не применять дважды.
    """
    if not llm_config or not llm_config.llm_resource_key:
        return llm_config
    key = str(llm_config.llm_resource_key).strip()
    if not key:
        raise ValueError("llm_resource_key is empty")

    merged = merge_flow_skill_node_resource_maps(
        flow_resources, skill_resources, node_resources_raw
    )
    if key not in merged:
        raise ValueError(f"llm_resource_key '{key}' is missing from flow/skill/node resources")

    ref_raw = merged[key]
    ref = ResourceReference.model_validate(ref_raw) if isinstance(ref_raw, dict) else ref_raw

    if ref.is_inline:
        if ref.type != ResourceType.LLM:
            raise ValueError(f"Resource '{key}': expected type llm, got {ref.type!r}")
        if ref.config is None:
            raise ValueError(f"Resource '{key}': inline LLM without config")
        base_cfg = LLMResourceConfig.model_validate(ref.config)
    else:
        resource_id = ref.resource_id
        if resource_id is None:
            raise ValueError(f"Resource '{key}': shared reference without resource_id")
        definition = await ResourceDefinition.get(
            ResourceDefinition.resource_row_id_for_active_company(resource_id)
        )
        if definition is None:
            raise ValueError(f"Shared resource '{resource_id}' not found in the database")
        if definition.type != ResourceType.LLM:
            raise ValueError(
                f"Resource '{key}': shared '{resource_id}' is not LLM, got {definition.type!r}"
            )
        merged_dict = definition.config
        if ref.config:
            merged_dict = merge_shared_definition_config_with_patch(
                ResourceType.LLM,
                definition.config,
                ref.config,
            )
        base_cfg = LLMResourceConfig.model_validate(merged_dict)

    merged_config = merge_llm_resource_into_node_config(base_cfg, llm_config)
    return merged_config.model_copy(update={"llm_resource_key": None})
