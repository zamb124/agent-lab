"""Runtime RAG-источники для generic LLM context layer."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, NamedTuple

from apps.flows.config import get_settings
from apps.flows.src.mapping import MappingResolver
from apps.flows.src.models import ResourceType
from apps.flows.src.models.resource import ResourceReference, ResourceReferenceInput
from apps.flows.src.resources.merge import (
    merge_flow_skill_node_resource_maps,
    merge_shared_definition_config_with_patch,
)
from core.auth import permission_checker
from core.llm_context import LLMContextSourceRegistry
from core.namespace import NamespaceService
from core.rag.llm_context_source import RAGLLMContextSource
from core.rag.rag_resource_bind import RagResourceBindParams
from core.rag.repository import RAGRepository
from core.state import ExecutionState
from core.types import JsonObject, require_json_object

if TYPE_CHECKING:
    from apps.flows.src.db import ResourceRepository


class _ResolvedRagConfig(NamedTuple):
    config: JsonObject
    permission: list[str]


async def resolve_rag_context_source_registry_for_runtime(
    *,
    flow_resources: Mapping[str, ResourceReferenceInput],
    skill_resources: Mapping[str, ResourceReferenceInput] | None,
    node_resources_raw: Mapping[str, ResourceReferenceInput],
    resource_repository: ResourceRepository | None,
    rag_repository: RAGRepository,
    namespace_service: NamespaceService | None = None,
    state: ExecutionState | None = None,
) -> LLMContextSourceRegistry | None:
    """Собирает context sources из каждого merged ``type: rag`` resource, доступного ноде."""
    binds = await resolve_rag_resource_binds_for_runtime(
        flow_resources=flow_resources,
        skill_resources=skill_resources,
        node_resources_raw=node_resources_raw,
        repository=resource_repository,
        namespace_service=namespace_service,
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
    namespace_service: NamespaceService | None = None,
    state: ExecutionState | None = None,
) -> dict[str, RagResourceBindParams]:
    """Разрешает merged flow/skill/node RAG resource references в typed bind params."""
    merged = merge_flow_skill_node_resource_maps(
        flow_resources, skill_resources, node_resources_raw
    )
    binds: dict[str, RagResourceBindParams] = {}
    for key, ref_raw in merged.items():
        ref = ResourceReference.model_validate(ref_raw) if isinstance(ref_raw, dict) else ref_raw
        resolved = await _resolve_rag_config_for_reference(
            key=key,
            ref=ref,
            repository=repository,
        )
        if resolved is None:
            continue
        _assert_rag_resource_permission(
            key=key,
            permission=resolved.permission,
            state=state,
        )
        raw_config = _resolve_runtime_templates(resolved.config, state)
        bind = RagResourceBindParams.model_validate(raw_config)
        if namespace_service is not None:
            await _ensure_rag_namespace(namespace_service, bind)
        binds[key] = bind
    return binds


async def _resolve_rag_config_for_reference(
    *,
    key: str,
    ref: ResourceReference,
    repository: ResourceRepository | None,
) -> _ResolvedRagConfig | None:
    if ref.is_inline:
        if ref.type != ResourceType.RAG:
            return None
        if ref.config is None:
            raise ValueError(f"Ресурс '{key}': inline RAG без config")
        return _ResolvedRagConfig(config=ref.config, permission=list(ref.permission))

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
        config = merge_shared_definition_config_with_patch(
            ResourceType.RAG,
            definition.config,
            ref.config,
        )
    else:
        config = definition.config
    return _ResolvedRagConfig(config=config, permission=list(definition.permission))


def _assert_rag_resource_permission(
    *,
    key: str,
    permission: list[str],
    state: ExecutionState | None,
) -> None:
    settings = get_settings()
    if not settings.auth.permissions_enabled:
        return
    if permission == []:
        return
    user_groups = _user_groups_from_state(state)
    if permission_checker.check_tool_permission(user_groups, permission):
        return
    required = permission_checker.normalize(permission)
    groups = ", ".join(required)
    raise PermissionError(
        f"У пользователя нет прав на RAG-ресурс '{key}'. Требуется одна из групп: {groups}"
    )


def _user_groups_from_state(state: ExecutionState | None) -> list[str]:
    if state is None:
        return []
    if state.user_groups:
        return list(state.user_groups)
    extra = state.json_extra()
    raw_user = extra.get("user")
    if isinstance(raw_user, Mapping):
        user = require_json_object(raw_user, "state.user")
        raw_groups = user.get("grps")
        if isinstance(raw_groups, list) and all(isinstance(group, str) for group in raw_groups):
            return [group for group in raw_groups if isinstance(group, str)]
    return []


async def _ensure_rag_namespace(
    namespace_service: NamespaceService,
    bind: RagResourceBindParams,
) -> None:
    namespace_id = bind.namespace.strip()
    if not namespace_id:
        raise ValueError("RAG resource: namespace обязателен")
    _ = await namespace_service.get_or_create(
        namespace_id,
        description=bind.namespace_description,
    )


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
