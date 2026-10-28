"""Runtime RAG-источники для generic LLM context layer."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import NamedTuple

from apps.flows.src.mapping import MappingResolver
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
from core.authz.errors import AuthzDenied
from core.authz.ids import PLATFORM_ADMIN_GROUP
from core.authz.models import AuthzObject, AuthzSubject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation
from core.clients.rag_client import RagClient
from core.context import require_active_company
from core.llm_context import LLMContextSourceRegistry
from core.namespace import NamespaceService
from core.rag.llm_context_source import RAGLLMContextSource
from core.rag.rag_resource_bind import RagResourceBindParams
from core.state import ExecutionState
from core.types import JsonObject, require_json_object


class _ResolvedRagConfig(NamedTuple):
    config: JsonObject
    permission: list[str]


async def resolve_rag_context_source_registry_for_runtime(
    *,
    flow_resources: Mapping[str, ResourceReferenceInput],
    skill_resources: Mapping[str, ResourceReferenceInput] | None,
    node_resources_raw: Mapping[str, ResourceReferenceInput],
    namespace_service: NamespaceService | None = None,
    state: ExecutionState | None = None,
    rag_client: RagClient | None = None,
    authz: AuthzService,
) -> LLMContextSourceRegistry | None:
    """Собирает context sources из каждого merged ``type: rag`` resource, доступного ноде."""
    binds = await resolve_rag_resource_binds_for_runtime(
        flow_resources=flow_resources,
        skill_resources=skill_resources,
        node_resources_raw=node_resources_raw,
        namespace_service=namespace_service,
        state=state,
        authz=authz,
    )
    if not binds:
        return None
    return LLMContextSourceRegistry(
        [
            RAGLLMContextSource(
                bind=bind,
                rag_client=rag_client,
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
    namespace_service: NamespaceService | None = None,
    state: ExecutionState | None = None,
    authz: AuthzService,
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
        )
        if resolved is None:
            continue
        await _assert_rag_resource_permission(
            key=key,
            permission=resolved.permission,
            state=state,
            authz=authz,
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
) -> _ResolvedRagConfig | None:
    if ref.is_inline:
        if ref.type != ResourceType.RAG:
            return None
        if ref.config is None:
            raise ValueError(f"Resource '{key}': inline RAG without config")
        return _ResolvedRagConfig(config=ref.config, permission=list(ref.permission))

    resource_id = ref.resource_id
    if resource_id is None:
        raise ValueError(f"Resource '{key}': shared reference without resource_id")
    definition = await ResourceDefinition.get(
        ResourceDefinition.resource_row_id_for_active_company(resource_id)
    )
    if definition is None:
        raise ValueError(f"Shared resource '{resource_id}' not found in the database")
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


async def _assert_rag_resource_permission(
    *,
    key: str,
    permission: list[str],
    state: ExecutionState | None,
    authz: AuthzService,
) -> None:
    if state is None:
        raise PermissionError(f"User has no access to RAG resource '{key}'")
    user_id = state.user_id
    try:
        if not permission:
            company = require_active_company()
            await authz.require_can_view(
                AuthzObject.company(company.company_id), user_id=user_id
            )
            return
        company = require_active_company()
        for group_name in permission:
            clean = group_name.strip()
            if not clean:
                continue
            group_obj = (
                AuthzObject.group(PLATFORM_ADMIN_GROUP)
                if clean == PLATFORM_ADMIN_GROUP
                else AuthzObject.group(clean, company_id=company.company_id)
            )
            if await authz.check(
                AuthzSubject.user(user_id),
                AuthzRelation.MEMBER,
                group_obj,
            ):
                return
    except AuthzDenied as exc:
        groups = ", ".join(permission)
        raise PermissionError(
            f"User has no access to RAG resource '{key}'. One of these groups is required: {groups}"
        ) from exc
    groups = ", ".join(permission)
    raise PermissionError(
        f"User has no access to RAG resource '{key}'. One of these groups is required: {groups}"
    )


async def _ensure_rag_namespace(
    namespace_service: NamespaceService,
    bind: RagResourceBindParams,
) -> None:
    namespace_id = bind.namespace.strip()
    if not namespace_id:
        raise ValueError("RAG resource: namespace is required")
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
