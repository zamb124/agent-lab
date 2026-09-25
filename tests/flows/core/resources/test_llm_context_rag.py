from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.flows.src.models.resource import ResourceDefinition, ResourceReference, ResourceType
from apps.flows.src.runtime.llm_context_rag import (
    _resolve_rag_config_for_reference,
    _resolve_runtime_templates,
    _source_name_from_resource_key,
    resolve_rag_context_source_registry_for_runtime,
    resolve_rag_resource_binds_for_runtime,
)
from core.authz.company_sync import sync_company_member_roles
from core.authz.group_sync import sync_user_groups
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.state import ExecutionState
from core.types import JsonObject


async def _company_visible_rag_state(di, unique_id: str) -> ExecutionState:
    """Company member + context для RAG permission=[] (company-visible)."""
    user_id = f"user-rag-{unique_id}"
    company_id = f"co-rag-{unique_id}"
    await sync_company_member_roles(
        di.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=["member"],
    )
    set_context(
        Context(
            user=User(user_id=user_id, name="U", groups=[]),
            active_company=Company(company_id=company_id, name="Co"),
            channel="api",
        )
    )
    return ExecutionState.create(
        task_id=f"task-rag-{unique_id}",
        context_id=f"ctx-rag-{unique_id}",
        user_id=user_id,
        session_id=f"flow-rag-{unique_id}:ctx-rag-{unique_id}",
        variables={},
        user_groups=[],
    )


async def _shared_resource(
    resource_id: str,
    config: JsonObject,
    *,
    resource_type: ResourceType = ResourceType.RAG,
    permission: list[str] | None = None,
) -> str:
    _ = await ResourceDefinition.set(
        ResourceDefinition(
            resource_id=resource_id,
            type=resource_type,
            config=config,
            permission=permission if permission is not None else [],
        )
    )
    return resource_id


@pytest.mark.asyncio
async def test_resolves_inline_rag_resource_with_state_templates(
    di,
    unique_id,
) -> None:
    base = await _company_visible_rag_state(di, unique_id)
    state = ExecutionState.create(
        task_id=base.task_id,
        context_id=base.context_id,
        user_id=base.user_id,
        session_id=base.session_id,
        variables={},
        user_groups=[],
        rag_namespace_id="session-kb",
        collection_id="support",
    )

    binds = await resolve_rag_resource_binds_for_runtime(
        flow_resources={
            "kb": {
                "type": "rag",
                "config": {
                    "namespace": "@state:rag_namespace_id",
                    "default_top_k": 8,
                    "filters": {"collection_id": "@state:collection_id"},
                },
            }
        },
        skill_resources=None,
        node_resources_raw={},
        authz=di.authz_service,
        state=state,
    )

    assert binds["kb"].namespace == "session-kb"
    assert binds["kb"].filters == {"collection_id": "support"}
    assert binds["kb"].default_top_k == 8


@pytest.mark.asyncio
async def test_non_rag_resources_are_ignored_and_empty_registry_is_none(di) -> None:
    binds = await resolve_rag_resource_binds_for_runtime(
        flow_resources={
            "ctx": {"type": "llm_context", "config": {"profile": "agent"}},
        },
        skill_resources=None,
        node_resources_raw={},
        authz=di.authz_service,
    )
    registry = await resolve_rag_context_source_registry_for_runtime(
        flow_resources={},
        skill_resources=None,
        node_resources_raw={},
        authz=di.authz_service,
    )

    assert binds == {}
    assert registry is None


@pytest.mark.asyncio
async def test_resolves_shared_rag_resource_with_deep_reference_patch(
    di,
    unique_id,
) -> None:
    state = await _company_visible_rag_state(di, unique_id)
    resource_id = await _shared_resource(
        f"shared_kb_{unique_id}",
        {
            "namespace": "company-kb",
            "default_top_k": 12,
            "filters": {"tenant": "acme"},
            "search_options": {
                "channels": {"semantic": True, "lexical": False},
                "rerank": False,
            },
        },
    )

    binds = await resolve_rag_resource_binds_for_runtime(
        flow_resources={
            "kb": {
                "resource_id": resource_id,
                "config": {
                    "filters": {"collection_id": "legal"},
                    "search_options": {"rerank": True},
                },
            }
        },
        skill_resources=None,
        node_resources_raw={},
        state=state,
        authz=di.authz_service,
    )

    assert binds["kb"].namespace == "company-kb"
    assert binds["kb"].filters == {"tenant": "acme", "collection_id": "legal"}
    assert binds["kb"].search_options is not None
    assert binds["kb"].search_options.model_dump(mode="json", exclude_none=True) == {
        "channels": {"semantic": True, "lexical": False},
        "rerank": True,
    }


@pytest.mark.asyncio
async def test_shared_rag_resource_without_patch_uses_definition_config(
    di,
    unique_id,
) -> None:
    state = await _company_visible_rag_state(di, unique_id)
    resource_id = await _shared_resource(f"shared_kb_{unique_id}", {"namespace": "company-kb"})

    binds = await resolve_rag_resource_binds_for_runtime(
        flow_resources={"kb": {"resource_id": resource_id}},
        skill_resources=None,
        node_resources_raw={},
        state=state,
        authz=di.authz_service,
    )

    assert binds["kb"].namespace == "company-kb"


@pytest.mark.asyncio
async def test_missing_shared_rag_resource_is_rejected(di, unique_id) -> None:
    with pytest.raises(ValueError, match="not found"):
        await resolve_rag_resource_binds_for_runtime(
            flow_resources={"kb": {"resource_id": f"missing_{unique_id}"}},
            skill_resources=None,
            node_resources_raw={},
            authz=di.authz_service,
        )


@pytest.mark.asyncio
async def test_shared_non_rag_resource_is_ignored(di, unique_id) -> None:
    resource_id = await _shared_resource(
        f"ctx_{unique_id}", {"profile": "agent"}, resource_type=ResourceType.LLM_CONTEXT
    )

    binds = await resolve_rag_resource_binds_for_runtime(
        flow_resources={"ctx": {"resource_id": resource_id}},
        skill_resources=None,
        node_resources_raw={},
        authz=di.authz_service,
    )

    assert binds == {}


@pytest.mark.asyncio
async def test_inline_rag_resource_without_config_is_rejected() -> None:
    bad_ref = ResourceReference.model_construct(
        type=ResourceType.RAG,
        resource_id=None,
        config=None,
        name=None,
        description=None,
    )

    with pytest.raises(ValueError, match="inline RAG"):
        await _resolve_rag_config_for_reference(key="kb", ref=bad_ref)


def test_runtime_template_helpers_cover_object_state_and_invalid_variables() -> None:
    state = ExecutionState.create(
        task_id="task-rag-template",
        context_id="ctx-rag-template",
        user_id="user-rag-template",
        session_id="flow-rag-template:ctx-rag-template",
        variables={"namespace": "object-kb"},
    )

    assert _resolve_runtime_templates(
        {"namespace": "@var:namespace"},
        state,
    ) == {"namespace": "object-kb"}

    with pytest.raises(ValidationError, match="variables"):
        ExecutionState.create(
            task_id="task-rag-template-bad",
            context_id="ctx-rag-template-bad",
            user_id="user-rag-template",
            session_id="flow-rag-template:ctx-rag-template-bad",
            variables=["bad"],
        )


def test_runtime_template_helpers_reject_non_object_result_and_empty_source_key() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        _resolve_runtime_templates(
            ["not", "object"],
            None,
        )

    assert _source_name_from_resource_key("!!!").startswith("rag.resource.")


@pytest.mark.asyncio
async def test_rag_context_registry_uses_all_merged_rag_resources(
    di,
    unique_id,
) -> None:
    state = await _company_visible_rag_state(di, unique_id)
    merged = {
        "flow_resources": {"kb": {"type": "rag", "config": {"namespace": "flow-kb"}}},
        "skill_resources": {"skill_kb": {"type": "rag", "config": {"namespace": "skill-kb"}}},
        "node_resources_raw": {"node_kb": {"type": "rag", "config": {"namespace": "node-kb"}}},
    }

    binds = await resolve_rag_resource_binds_for_runtime(
        **merged, state=state, authz=di.authz_service
    )
    registry = await resolve_rag_context_source_registry_for_runtime(
        **merged, state=state, authz=di.authz_service
    )

    assert [(key, bind.namespace) for key, bind in binds.items()] == [
        ("kb", "flow-kb"),
        ("skill_kb", "skill-kb"),
        ("node_kb", "node-kb"),
    ]
    assert registry is not None
    assert registry.has_sources is True


@pytest.mark.asyncio
async def test_resolve_ensures_namespace_via_namespace_service(
    di,
    unique_id,
) -> None:
    state = await _company_visible_rag_state(di, unique_id)
    namespace = f"kb-support-{unique_id}"
    binds = await resolve_rag_resource_binds_for_runtime(
        flow_resources={
            "kb": {
                "type": "rag",
                "config": {
                    "namespace": namespace,
                    "namespace_description": "Support docs",
                },
            }
        },
        skill_resources=None,
        node_resources_raw={},
        authz=di.authz_service,
        namespace_service=di.namespace_service,
        state=state,
    )
    assert binds["kb"].namespace == namespace
    created = await di.namespace_service.get(namespace)
    assert created is not None
    assert created.description == "Support docs"


@pytest.mark.asyncio
async def test_inline_rag_permission_denied_when_groups_missing(
    di,
    unique_id,
) -> None:
    user_id = f"user-rag-{unique_id}"
    company_id = f"co-rag-{unique_id}"
    await sync_user_groups(
        di.authz_service,
        user_id=user_id,
        groups=["users"],
        company_ids=[company_id],
        previous_groups=[],
    )
    set_context(
        Context(
            user=User(user_id=user_id, name="U", groups=["users"]),
            active_company=Company(company_id=company_id, name="Co"),
            channel="api",
        )
    )
    state = ExecutionState.create(
        task_id="task-rag-perm",
        context_id="ctx-rag-perm",
        user_id=user_id,
        session_id="flow-rag-perm:ctx-rag-perm",
        variables={},
        user_groups=["users"],
    )
    try:
        with pytest.raises(PermissionError, match="no access to RAG resource"):
            await resolve_rag_resource_binds_for_runtime(
                flow_resources={
                    "kb": {
                        "type": "rag",
                        "permission": ["managers"],
                        "config": {"namespace": "kb-private"},
                    }
                },
                skill_resources=None,
                node_resources_raw={},
        authz=di.authz_service,
                state=state,
            )
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_shared_rag_permission_allows_matching_group(
    di,
    unique_id,
) -> None:
    user_id = f"user-rag-{unique_id}"
    company_id = f"co-rag-{unique_id}"
    await sync_user_groups(
        di.authz_service,
        user_id=user_id,
        groups=["managers"],
        company_ids=[company_id],
        previous_groups=[],
    )
    set_context(
        Context(
            user=User(user_id=user_id, name="U", groups=["managers"]),
            active_company=Company(company_id=company_id, name="Co"),
            channel="api",
        )
    )
    state = ExecutionState.create(
        task_id="task-rag-perm-ok",
        context_id="ctx-rag-perm-ok",
        user_id=user_id,
        session_id="flow-rag-perm:ctx-rag-perm-ok",
        variables={},
        user_groups=["managers"],
    )
    try:
        resource_id = await _shared_resource(
            f"shared_kb_{unique_id}", {"namespace": "company-kb"}, permission=["managers"]
        )
        binds = await resolve_rag_resource_binds_for_runtime(
            flow_resources={"kb": {"resource_id": resource_id}},
            skill_resources=None,
            node_resources_raw={},
            state=state,
            authz=di.authz_service,
        )
    finally:
        clear_context()
    assert binds["kb"].namespace == "company-kb"


@pytest.mark.asyncio
async def test_empty_permission_requires_company_member(
    di,
    unique_id,
) -> None:
    user_id = f"user-rag-{unique_id}"
    company_id = f"co-rag-{unique_id}"
    await sync_company_member_roles(
        di.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=["member"],
    )
    set_context(
        Context(
            user=User(user_id=user_id, name="U", groups=[]),
            active_company=Company(company_id=company_id, name="Co"),
            channel="api",
        )
    )
    state = ExecutionState.create(
        task_id="task-rag-perm-empty",
        context_id="ctx-rag-perm-empty",
        user_id=user_id,
        session_id="flow-rag-perm:ctx-rag-perm-empty",
        variables={},
        user_groups=[],
    )
    binds = await resolve_rag_resource_binds_for_runtime(
        flow_resources={
            "kb": {
                "type": "rag",
                "permission": [],
                "config": {"namespace": "kb-open"},
            }
        },
        skill_resources=None,
        node_resources_raw={},
        authz=di.authz_service,
        state=state,
    )
    assert binds["kb"].namespace == "kb-open"
