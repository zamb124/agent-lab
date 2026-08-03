"""Lara Networkle (CRM) E2E: MockLLM loads skills and exercises CRM employee tools via run_flow."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date

import pytest
from pydantic import TypeAdapter

from apps.flows.src.container import FlowContainer
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.services.platform_assistant_skills import (
    LARA_PLATFORM_SKILL_ROOTS,
    PLATFORM_ASSISTANT_SEED_SKILL_IDS,
    seed_platform_assistant_skills,
)
from core.clients.llm.mock import MockLLM, MockLLMQueuedResponse
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.identity.flow_employee import ensure_flow_employee, flow_employee_user_id
from core.models.identity_models import Company, User
from core.state import ExecutionState
from core.types import JsonObject, JsonValue
from tests.fixtures.crm_test_setup import ensure_crm_namespace, ensure_entity_type_in_namespace
from tests.flows.agent_skills_harness import ensure_lara_flow
from tests.flows.durable_runtime_harness import run_flow

pytestmark = [
    pytest.mark.usefixtures("app", "crm_service"),
    pytest.mark.timeout(180, func_only=True),
]

MockLLMQueue = Callable[[list[MockLLMQueuedResponse]], MockLLM]
_JSON_OBJECT_ADAPTER: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)
_BRANCH = "crm"


@contextmanager
def _employee_context(
    employee_user: User,
    company: Company,
    *,
    namespace: str,
) -> Iterator[None]:
    previous = get_context()
    ctx = build_job_context(
        company=company,
        user=employee_user,
        host="",
        trace_id="lara-networkle-skills-runtime",
        session_id="lara-networkle-skills",
        channel="a2a",
    )
    set_context(ctx.model_copy(update={"active_namespace": namespace}))
    try:
        yield
    finally:
        if previous is None:
            clear_context()
        else:
            set_context(previous)


def _lara_state(*, unique_id: str, user_id: str, suffix: str = "") -> ExecutionState:
    context_id = f"lara-crm-{unique_id}{suffix}"
    return ExecutionState(
        task_id=f"task-crm-{unique_id}{suffix}",
        context_id=context_id,
        user_id=user_id,
        session_id=f"lara:{context_id}",
        branch_id=_BRANCH,
        content=f"networkle runtime {unique_id}{suffix}",
    )


async def _seed_lara_skills(container: FlowContainer) -> None:
    seeded = await seed_platform_assistant_skills(
        container.agent_skill_service,
        container.files_service,
        "system",
    )
    assert seeded == len(PLATFORM_ASSISTANT_SEED_SKILL_IDS)


async def _require_lara(container: FlowContainer) -> Flow:
    _ = await ensure_lara_flow(container)
    flow = await container.flow_factory.get_flow("lara", branch_id=_BRANCH)
    assert flow is not None
    return flow


async def _run_lara(container: FlowContainer, *, state: ExecutionState) -> ExecutionState:
    flow = await _require_lara(container)
    main_node = flow.nodes["main"]
    assert getattr(main_node, "agent_skill_ids", None) == list(LARA_PLATFORM_SKILL_ROOTS)
    tool_names = {tool.name for tool in await main_node.get_tools(state)}
    assert "load_agent_skill" in tool_names
    assert "crm_search_entities" not in tool_names
    return await run_flow(
        container=as_flow_runtime_container(container),
        flow=flow,
        state=state,
    )


def _tool_json(value: JsonValue) -> JsonObject:
    if isinstance(value, str):
        return _JSON_OBJECT_ADAPTER.validate_json(value)
    return _JSON_OBJECT_ADAPTER.validate_python(value)


def _load(*skill_ids: str) -> list[MockLLMQueuedResponse]:
    return [
        {
            "type": "tool_call",
            "tool": "load_agent_skill",
            "args": {"agent_skill_id": skill_id},
        }
        for skill_id in skill_ids
    ]


def _text(content: str) -> MockLLMQueuedResponse:
    return {"type": "text", "content": content}


def _call(tool: str, **args: object) -> MockLLMQueuedResponse:
    return {"type": "tool_call", "tool": tool, "args": dict(args)}


async def _prepare_employee(
    *,
    frontend_container,
    crm_client,
    auth_headers_system: dict[str, str],
    unique_id: str,
    flow_suffix: str,
) -> tuple[User, Company, str, str]:
    flow_id = f"lara_crm_{flow_suffix}_{unique_id}"
    company = await frontend_container.company_repository.get("system")
    assert company is not None
    employee = await ensure_flow_employee(
        frontend_container,
        flow_id=flow_id,
        company_id="system",
        name=f"Lara CRM {flow_suffix}",
        roles=["member"],
        curator_user_ids=["system"],
    )
    employee_user_id = flow_employee_user_id(flow_id)
    namespace = f"lara_crm_{flow_suffix}_{unique_id}"
    await ensure_crm_namespace(crm_client, auth_headers_system, namespace)
    for type_id, type_name in (
        ("organization", "Организация"),
        ("note", "Заметка"),
        ("task", "Задача"),
    ):
        await ensure_entity_type_in_namespace(
            crm_client,
            auth_headers_system,
            type_id,
            type_name,
            namespace,
        )
    return employee, company, employee_user_id, namespace


def _captured_tool_names(call: JsonObject) -> set[str]:
    raw_tools = call.get("tools")
    names: set[str] = set()
    if not isinstance(raw_tools, list):
        return names
    for tool in raw_tools:
        if not isinstance(tool, dict):
            continue
        direct_name = tool.get("name")
        if isinstance(direct_name, str) and direct_name.strip():
            names.add(direct_name)
            continue
        function = tool.get("function")
        if isinstance(function, dict):
            function_name = function.get("name")
            if isinstance(function_name, str) and function_name.strip():
                names.add(function_name)
    return names


@pytest.mark.asyncio
async def test_lara_networkle_unlock_skills(
    container: FlowContainer,
    flows_service,
    frontend_container,
    crm_client,
    auth_headers_system: dict[str, str],
    mock_llm_with_queue: MockLLMQueue,
    mock_llm_capture,
    unique_id: str,
) -> None:
    _ = flows_service
    employee, company, employee_user_id, namespace = await _prepare_employee(
        frontend_container=frontend_container,
        crm_client=crm_client,
        auth_headers_system=auth_headers_system,
        unique_id=unique_id,
        flow_suffix="unlock",
    )
    _ = mock_llm_with_queue(
        [
            *_load(
                "networkle",
                "crm-entities",
                "crm-notes",
                "crm-graph",
                "crm-ops",
                "work-items",
                "team-directory",
            ),
            _text("networkle skills ready"),
        ]
    )
    state = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-unlock")
    with _employee_context(employee, company, namespace=namespace):
        await _seed_lara_skills(container)
        result = await _run_lara(container, state=state)

    assert result.interrupt is None
    calls = await mock_llm_capture()
    assert "crm_search_entities" not in _captured_tool_names(calls[0])
    unlocked = set().union(*(_captured_tool_names(call) for call in calls))
    for tool_name in (
        "crm_search_entities",
        "crm_update_entity",
        "crm_list_notes",
        "crm_apply_analysis_draft",
        "crm_list_relationships",
        "crm_list_suggests",
        "crm_create_activity_task",
        "work_item_get",
        "team_resolve_user",
    ):
        assert tool_name in unlocked


@pytest.mark.asyncio
async def test_lara_networkle_entity_update_delete(
    container: FlowContainer,
    flows_service,
    frontend_container,
    crm_client,
    auth_headers_system: dict[str, str],
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = flows_service
    employee, company, employee_user_id, namespace = await _prepare_employee(
        frontend_container=frontend_container,
        crm_client=crm_client,
        auth_headers_system=auth_headers_system,
        unique_id=unique_id,
        flow_suffix="entity",
    )
    org_name = f"Org {unique_id}"
    _ = mock_llm_with_queue(
        [
            *_load("networkle", "crm-entities"),
            _call(
                "crm_create_entity",
                entity_type="organization",
                name=org_name,
                description=f"desc {unique_id}",
            ),
            _text("created"),
        ]
    )
    state1 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-e1")
    with _employee_context(employee, company, namespace=namespace):
        await _seed_lara_skills(container)
        result1 = await _run_lara(container, state=state1)

    assert result1.interrupt is None
    created = _tool_json(result1.tool_results["crm_create_entity"])
    entity_id = created["entity"]["entity_id"]
    assert isinstance(entity_id, str) and entity_id

    updated_name = f"Org updated {unique_id}"
    _ = mock_llm_with_queue(
        [
            *_load("networkle", "crm-entities"),
            _call("crm_get_entity", entity_id=entity_id),
            _call("crm_update_entity", entity_id=entity_id, name=updated_name),
            _call("crm_delete_entity", entity_id=entity_id),
            _text("entity lifecycle done"),
        ]
    )
    state2 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-e2")
    with _employee_context(employee, company, namespace=namespace):
        result2 = await _run_lara(container, state=state2)

    assert result2.interrupt is None
    got = _tool_json(result2.tool_results["crm_get_entity"])
    assert isinstance(got.get("entity"), dict)
    updated = _tool_json(result2.tool_results["crm_update_entity"])
    assert updated["entity"]["name"] == updated_name
    deleted = _tool_json(result2.tool_results["crm_delete_entity"])
    assert deleted.get("entity_id") == entity_id


@pytest.mark.asyncio
async def test_lara_networkle_note_list_and_discard_draft_path(
    container: FlowContainer,
    flows_service,
    frontend_container,
    crm_client,
    auth_headers_system: dict[str, str],
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    """Create note via entity API path (confirm-first skipped) + list_notes + discard empty draft."""
    _ = flows_service
    employee, company, employee_user_id, namespace = await _prepare_employee(
        frontend_container=frontend_container,
        crm_client=crm_client,
        auth_headers_system=auth_headers_system,
        unique_id=unique_id,
        flow_suffix="notes",
    )
    today = date.today().isoformat()
    note_name = f"Note {unique_id}"
    _ = mock_llm_with_queue(
        [
            *_load("networkle", "crm-notes", "crm-entities"),
            _call(
                "crm_create_entity",
                entity_type="note",
                name=note_name,
                description=f"body {unique_id}",
            ),
            _call("crm_list_notes", date_from=today, date_to=today),
            _text("notes listed"),
        ]
    )
    state = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-n1")
    with _employee_context(employee, company, namespace=namespace):
        await _seed_lara_skills(container)
        result = await _run_lara(container, state=state)

    assert result.interrupt is None
    created = _tool_json(result.tool_results["crm_create_entity"])
    note_id = created["entity"]["entity_id"]
    listed = _tool_json(result.tool_results["crm_list_notes"])
    assert listed["count"] >= 1
    assert any(
        isinstance(row, dict) and row.get("entity_id") == note_id for row in listed["items"]
    )

    _ = mock_llm_with_queue(
        [
            *_load("networkle", "crm-notes"),
            _call("crm_discard_analysis_draft", note_id=note_id),
            _text("discard attempted"),
        ]
    )
    state2 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-n2")
    with _employee_context(employee, company, namespace=namespace):
        result2 = await _run_lara(container, state=state2)

    assert result2.interrupt is None
    discarded = _tool_json(result2.tool_results["crm_discard_analysis_draft"])
    assert discarded.get("note_id") == note_id
    assert discarded.get("status") == "draft_discarded"


@pytest.mark.asyncio
async def test_lara_networkle_graph_relationships(
    container: FlowContainer,
    flows_service,
    frontend_container,
    crm_client,
    auth_headers_system: dict[str, str],
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = flows_service
    employee, company, employee_user_id, namespace = await _prepare_employee(
        frontend_container=frontend_container,
        crm_client=crm_client,
        auth_headers_system=auth_headers_system,
        unique_id=unique_id,
        flow_suffix="graph",
    )
    _ = mock_llm_with_queue(
        [
            *_load("networkle", "crm-entities", "crm-graph"),
            _call("crm_list_relationship_types"),
            _call("crm_create_entity", entity_type="organization", name=f"LinkSrc {unique_id}"),
            _text("src"),
        ]
    )
    state1 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-g1")
    with _employee_context(employee, company, namespace=namespace):
        await _seed_lara_skills(container)
        result1 = await _run_lara(container, state=state1)

    assert result1.interrupt is None
    types = _tool_json(result1.tool_results["crm_list_relationship_types"])
    assert types["count"] >= 1
    type_id = types["items"][0]["type_id"]
    assert isinstance(type_id, str)
    src_id = _tool_json(result1.tool_results["crm_create_entity"])["entity"]["entity_id"]

    _ = mock_llm_with_queue(
        [
            *_load("networkle", "crm-entities", "crm-graph"),
            _call("crm_create_entity", entity_type="organization", name=f"LinkDst {unique_id}"),
            _text("dst"),
        ]
    )
    state2 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-g2")
    with _employee_context(employee, company, namespace=namespace):
        result2 = await _run_lara(container, state=state2)
    dst_id = _tool_json(result2.tool_results["crm_create_entity"])["entity"]["entity_id"]

    _ = mock_llm_with_queue(
        [
            *_load("networkle", "crm-entities", "crm-graph"),
            _call(
                "crm_create_relationship",
                source_entity_id=src_id,
                target_entity_id=dst_id,
                relationship_type=type_id,
            ),
            _call("crm_list_relationships", entity_id=src_id),
            _call("crm_entity_related", entity_id=src_id, direction="both"),
            _call("crm_shortest_path", from_entity_id=src_id, to_entity_id=dst_id),
            _text("graph ok"),
        ]
    )
    state3 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-g3")
    with _employee_context(employee, company, namespace=namespace):
        result3 = await _run_lara(container, state=state3)

    assert result3.interrupt is None
    rel = _tool_json(result3.tool_results["crm_create_relationship"])
    relationship_id = rel["relationship"]["relationship_id"]
    assert isinstance(_tool_json(result3.tool_results["crm_list_relationships"]).get("items"), list)
    assert isinstance(_tool_json(result3.tool_results["crm_entity_related"]).get("related"), dict)
    assert isinstance(_tool_json(result3.tool_results["crm_shortest_path"]).get("path"), dict)

    _ = mock_llm_with_queue(
        [
            *_load("networkle", "crm-graph"),
            _call("crm_delete_relationship", relationship_id=relationship_id),
            _text("deleted"),
        ]
    )
    state4 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-g4")
    with _employee_context(employee, company, namespace=namespace):
        result4 = await _run_lara(container, state=state4)
    assert result4.interrupt is None
    deleted_rel = _tool_json(result4.tool_results["crm_delete_relationship"])
    assert deleted_rel.get("relationship_id") == relationship_id
    assert deleted_rel.get("status") == "deleted"


@pytest.mark.asyncio
async def test_lara_networkle_activity_and_ops(
    container: FlowContainer,
    flows_service,
    frontend_container,
    crm_client,
    auth_headers_system: dict[str, str],
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = flows_service
    employee, company, employee_user_id, namespace = await _prepare_employee(
        frontend_container=frontend_container,
        crm_client=crm_client,
        auth_headers_system=auth_headers_system,
        unique_id=unique_id,
        flow_suffix="ops",
    )
    _ = mock_llm_with_queue(
        [
            *_load("networkle", "crm-entities", "crm-ops"),
            _call(
                "crm_create_activity_task",
                title=f"Activity {unique_id}",
                description="from lara e2e",
            ),
            _call("crm_list_activity_tasks"),
            _call("crm_list_suggests"),
            _call("crm_knowledge_import_status"),
            _text("ops ok"),
        ]
    )
    state = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-ops")
    with _employee_context(employee, company, namespace=namespace):
        await _seed_lara_skills(container)
        result = await _run_lara(container, state=state)

    assert result.interrupt is None
    activity = _tool_json(result.tool_results["crm_create_activity_task"])
    assert isinstance(activity["work_item_id"], str) and activity["work_item_id"]
    assert isinstance(_tool_json(result.tool_results["crm_list_activity_tasks"]).get("items"), list)
    assert isinstance(_tool_json(result.tool_results["crm_list_suggests"]).get("items"), list)
    assert isinstance(
        _tool_json(result.tool_results["crm_knowledge_import_status"]).get("items"), list
    )
