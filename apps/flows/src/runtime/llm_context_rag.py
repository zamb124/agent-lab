"""Runtime RAG sources for the generic LLM context layer."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import TYPE_CHECKING

from apps.flows.src.mapping import MappingResolver
from apps.flows.src.models import ResourceType
from apps.flows.src.models.resource import ResourceReference, ResourceReferenceInput
from apps.flows.src.resources.merge import (
    merge_flow_skill_node_resource_maps,
    merge_shared_definition_config_with_patch,
)
from core.llm_context import LLMContextSourceRegistry
from core.rag.llm_context_source import RAGLLMContextSource
from core.rag.rag_resource_bind import RagResourceBindParams
from core.rag.repository import RAGRepository
from core.state import ExecutionState
from core.types import JsonObject, require_json_object

if TYPE_CHECKING:
    from apps.flows.src.db import ResourceRepository


async def resolve_rag_context_source_registry_for_runtime(
    *,
    flow_resources: Mapping[str, ResourceReferenceInput],
    skill_resources: Mapping[str, ResourceReferenceInput] | None,
    node_resources_raw: Mapping[str, ResourceReferenceInput],
    resource_repository: ResourceRepository | None,
    rag_repository: RAGRepository,
    state: ExecutionState | None = None,
) -> LLMContextSourceRegistry | None:
    """Build context sources from every merged ``type: rag`` resource available to the node."""
    binds = await resolve_rag_resource_binds_for_runtime(
        flow_resources=flow_resources,
        skill_resources=skill_resources,
        node_resources_raw=node_resources_raw,
        repository=resource_repository,
        state=state,
    )
    if not binds:
        return None
    return LLMContextSourceRegistry(
        [
            RAGLLMContextSource(
                repository=rag_repository,
                bind=bind,
                name=_source_name_from_resource_key(key),
            )
            for key, bind in binds.items()
        ]
    )


async def resolve_rag_resource_binds_for_runtime(
    *,
    flow_resources: Mapping[str, ResourceReferenceInput],
    skill_resources: Mapping[str, ResourceReferenceInput] | None,
    node_resources_raw: Mapping[str, ResourceReferenceInput],
    repository: ResourceRepository | None,
    state: ExecutionState | None = None,
) -> dict[str, RagResourceBindParams]:
    """Resolve merged flow/skill/node RAG resource references to typed bind params."""
    merged = merge_flow_skill_node_resource_maps(
        flow_resources, skill_resources, node_resources_raw
    )
    binds: dict[str, RagResourceBindParams] = {}
    for key, ref_raw in merged.items():
        ref = ResourceReference.model_validate(ref_raw) if isinstance(ref_raw, dict) else ref_raw
        raw_config = await _resolve_rag_config_for_reference(
            key=key,
            ref=ref,
            repository=repository,
        )
        if raw_config is None:
            continue
        raw_config = _resolve_runtime_templates(raw_config, state)
        binds[key] = RagResourceBindParams.model_validate(raw_config)
    return binds


async def _resolve_rag_config_for_reference(
    *,
    key: str,
    ref: ResourceReference,
    repository: ResourceRepository | None,
) -> JsonObject | None:
    if ref.is_inline:
        if ref.type != ResourceType.RAG:
            return None
        if ref.config is None:
            raise ValueError(f"Ресурс '{key}': inline RAG без config")
        return ref.config

    if repository is None:
        raise ValueError("resource_repository обязателен для shared RAG resources")
    resource_id = ref.resource_id
    if resource_id is None:
        raise ValueError(f"Ресурс '{key}': shared reference без resource_id")
    definition = await repository.get(resource_id)
    if definition is None:
        raise ValueError(f"Shared resource '{resource_id}' не найден в БД")
    if definition.type != ResourceType.RAG:
        return None
    if ref.config:
        return merge_shared_definition_config_with_patch(
            ResourceType.RAG,
            definition.config,
            ref.config,
        )
    return definition.config


def _resolve_runtime_templates(
    config: JsonObject,
    state: ExecutionState | None,
) -> JsonObject:
    config_obj = require_json_object(config, "rag_resource.config")
    if state is None:
        return config_obj
    variables = _state_variables(state)
    resolved = MappingResolver.resolve_json_template_tree(
        config_obj,
        state,
        variables,
    )
    return require_json_object(resolved, "rag_resource.config")


def _state_variables(state: ExecutionState) -> JsonObject:
    return state.variables


def _source_name_from_resource_key(key: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("_", "-", ".") else "_" for ch in key)
    safe = safe.strip("._-") or "resource"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
    return f"rag.{safe}.{digest}"


__all__ = [
    "resolve_rag_context_source_registry_for_runtime",
    "resolve_rag_resource_binds_for_runtime",
]
