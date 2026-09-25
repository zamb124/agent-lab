"""Lara Documents E2E: MockLLM loads skills and exercises Documents employee tools via run_flow."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest
from pydantic import TypeAdapter

from apps.flows.di import FlowsDi
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
from tests.flows.agent_skills_harness import ensure_lara_flow
from tests.flows.durable_runtime_harness import run_flow
from tests.sync.api._helpers import seed_namespace_via_repo

pytestmark = [pytest.mark.usefixtures("app"), pytest.mark.timeout(180, func_only=True)]

MockLLMQueue = Callable[[list[MockLLMQueuedResponse]], MockLLM]
_JSON_OBJECT_ADAPTER: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)
_BRANCH = "documents"


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
        trace_id="lara-documents-skills-runtime",
        session_id="lara-documents-skills",
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
    context_id = f"lara-docs-{unique_id}{suffix}"
    return ExecutionState(
        task_id=f"task-docs-{unique_id}{suffix}",
        context_id=context_id,
        user_id=user_id,
        session_id=f"lara:{context_id}",
        branch_id=_BRANCH,
        content=f"documents runtime {unique_id}{suffix}",
    )


async def _seed_lara_skills(di: FlowsDi) -> None:
    seeded = await seed_platform_assistant_skills(
        di.files_service,
        "system",
    )
    assert seeded == len(PLATFORM_ASSISTANT_SEED_SKILL_IDS)


async def _require_lara(di: FlowsDi) -> Flow:
    _ = await ensure_lara_flow(di)
    flow = await di.flow_factory.get_flow("lara", branch_id=_BRANCH, tool_registry=di.tool_registry)
    assert flow is not None
    return flow


async def _run_lara(di: FlowsDi, *, state: ExecutionState) -> ExecutionState:
    flow = await _require_lara(di)
    main_node = flow.nodes["main"]
    assert getattr(main_node, "agent_skill_ids", None) == list(LARA_PLATFORM_SKILL_ROOTS)
    tool_names = {tool.name for tool in await main_node.get_tools(state)}
    assert "load_agent_skill" in tool_names
    assert "documents_list_catalog" not in tool_names
    return await run_flow(
        di=di,
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
    frontend_di,
    unique_id: str,
    flow_suffix: str,
) -> tuple[User, Company, str, str]:
    flow_id = f"lara_docs_{flow_suffix}_{unique_id}"
    company = await Company.get("system")
    assert company is not None
    employee = await ensure_flow_employee(
        frontend_di,
        flow_id=flow_id,
        company_id="system",
        name=f"Lara Docs {flow_suffix}",
        roles=["member"],
        curator_user_ids=["system"],
    )
    employee_user_id = flow_employee_user_id(flow_id)
    namespace = f"lara_docs_{flow_suffix}_{unique_id}"
    await seed_namespace_via_repo(frontend_di, "system", namespace)
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
async def test_lara_documents_unlock_skills(
    di: FlowsDi,
    flows_service,
    frontend_di,
    mock_llm_with_queue: MockLLMQueue,
    mock_llm_capture,
    unique_id: str,
) -> None:
    _ = flows_service
    employee, company, employee_user_id, namespace = await _prepare_employee(
        frontend_di=frontend_di,
        unique_id=unique_id,
        flow_suffix="unlock",
    )
    _ = mock_llm_with_queue(
        [
            *_load(
                "documents-platform",
                "documents-catalog",
                "document-workspace",
                "diagrams-viz",
                "knowledge-rag",
            ),
            _text("documents skills ready"),
        ]
    )
    state = _lara_state(unique_id=unique_id, user_id=employee_user_id)
    with _employee_context(employee, company, namespace=namespace):
        await _seed_lara_skills(di)
        result = await _run_lara(di, state=state)

    assert result.interrupt is None
    calls = await mock_llm_capture()
    assert "documents_list_catalog" not in _captured_tool_names(calls[0])
    unlocked = set().union(*(_captured_tool_names(call) for call in calls))
    for tool_name in (
        "documents_list_catalog",
        "documents_create_empty",
        "documents_create_catalog",
        "documents_rotate_public_link",
        "create_viz",
        "rag_search",
    ):
        assert tool_name in unlocked


@pytest.mark.asyncio
async def test_lara_documents_lifecycle(
    di: FlowsDi,
    flows_service,
    frontend_di,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = flows_service
    employee, company, employee_user_id, namespace = await _prepare_employee(
        frontend_di=frontend_di,
        unique_id=unique_id,
        flow_suffix="life",
    )
    folder_a = f"folder-a-{unique_id}"
    folder_b = f"folder-b-{unique_id}"
    _ = mock_llm_with_queue(
        [
            *_load("documents-platform", "documents-catalog", "document-workspace"),
            _call(
                "documents_create_catalog",
                title=folder_a,
                is_public=False,
            ),
            _call(
                "documents_create_catalog",
                title=folder_b,
                is_public=False,
            ),
            _text("catalogs ready"),
        ]
    )
    state1 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-c")
    with _employee_context(employee, company, namespace=namespace):
        await _seed_lara_skills(di)
        result1 = await _run_lara(di, state=state1)

    assert result1.interrupt is None
    # last create overwrites tool_results key — list catalogs to get both
    _ = mock_llm_with_queue(
        [
            *_load("documents-platform", "documents-catalog"),
            _call("documents_list_catalog"),
            _text("listed"),
        ]
    )
    state_list = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-list")
    with _employee_context(employee, company, namespace=namespace):
        listed = await _run_lara(di, state=state_list)

    assert listed.interrupt is None
    roots = _tool_json(listed.tool_results["documents_list_catalog"])
    catalogs = roots["catalogs"]
    assert isinstance(catalogs, list)
    by_title = {
        item["title"]: item["catalog_id"]
        for item in catalogs
        if isinstance(item, dict) and isinstance(item.get("title"), str)
    }
    catalog_a = by_title[folder_a]
    catalog_b = by_title[folder_b]
    assert isinstance(catalog_a, str) and isinstance(catalog_b, str)

    _ = mock_llm_with_queue(
        [
            *_load("documents-platform", "document-workspace", "documents-catalog"),
            _call(
                "documents_create_empty",
                title=f"doc-{unique_id}",
                document_type="word",
                catalog_id=catalog_a,
            ),
            _text("created"),
        ]
    )
    state2 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-e")
    with _employee_context(employee, company, namespace=namespace):
        result2 = await _run_lara(di, state=state2)

    assert result2.interrupt is None
    created = _tool_json(result2.tool_results["documents_create_empty"])
    file_id = created["file_id"]
    assert isinstance(file_id, str)

    _ = mock_llm_with_queue(
        [
            *_load("documents-platform", "document-workspace", "documents-catalog"),
            _call("documents_rename", file_id=file_id, title=f"renamed-{unique_id}"),
            _call("documents_move", file_id=file_id, catalog_id=catalog_b),
            _call(
                "documents_copy",
                file_id=file_id,
                catalog_id=catalog_a,
                title=f"copy-{unique_id}",
            ),
            _call("documents_get_link", file_id=file_id, kind="editor"),
            _text("lifecycle mid"),
        ]
    )
    state3 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-m")
    with _employee_context(employee, company, namespace=namespace):
        result3 = await _run_lara(di, state=state3)

    assert result3.interrupt is None
    renamed = _tool_json(result3.tool_results["documents_rename"])
    assert renamed.get("title") == f"renamed-{unique_id}"
    moved = _tool_json(result3.tool_results["documents_move"])
    assert moved.get("catalog_id") == catalog_b
    copied = _tool_json(result3.tool_results["documents_copy"])
    copy_id = copied["file_id"]
    assert isinstance(copy_id, str) and copy_id != file_id
    link = _tool_json(result3.tool_results["documents_get_link"])
    assert link.get("kind") == "editor"
    assert isinstance(link.get("url"), str) and "/documents/edit/" in str(link["url"])

    _ = mock_llm_with_queue(
        [
            *_load("documents-platform", "document-workspace"),
            _call("documents_delete", file_id=copy_id),
            _call("documents_list_deleted"),
            _call("documents_restore", file_id=copy_id),
            _call("documents_delete", file_id=copy_id),
            _call("documents_permanent_delete", file_id=copy_id),
            _text("trash done"),
        ]
    )
    state4 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-t")
    with _employee_context(employee, company, namespace=namespace):
        result4 = await _run_lara(di, state=state4)

    assert result4.interrupt is None
    permanent = _tool_json(result4.tool_results["documents_permanent_delete"])
    assert permanent.get("permanently_deleted") is True


@pytest.mark.asyncio
async def test_lara_documents_catalog_access_and_rag_status(
    di: FlowsDi,
    flows_service,
    frontend_di,
    system_user_id: str,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = flows_service
    employee, company, employee_user_id, namespace = await _prepare_employee(
        frontend_di=frontend_di,
        unique_id=unique_id,
        flow_suffix="acl",
    )
    _ = mock_llm_with_queue(
        [
            *_load("documents-platform", "documents-catalog", "team-directory"),
            _call(
                "documents_create_catalog",
                title=f"acl-{unique_id}",
                is_public=False,
            ),
            _text("catalog"),
        ]
    )
    state1 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-a1")
    with _employee_context(employee, company, namespace=namespace):
        await _seed_lara_skills(di)
        result1 = await _run_lara(di, state=state1)

    assert result1.interrupt is None
    catalog = _tool_json(result1.tool_results["documents_create_catalog"])
    catalog_id = catalog["catalog_id"]
    assert isinstance(catalog_id, str)

    _ = mock_llm_with_queue(
        [
            *_load("documents-platform", "documents-catalog", "team-directory"),
            _call(
                "documents_update_catalog",
                catalog_id=catalog_id,
                title=f"acl-renamed-{unique_id}",
            ),
            _call(
                "documents_add_catalog_member",
                catalog_id=catalog_id,
                user_id=system_user_id,
            ),
            _call("documents_list_catalog_members", catalog_id=catalog_id),
            _call(
                "documents_get_access",
                resource_kind="catalog",
                resource_id=catalog_id,
            ),
            _text("members done"),
        ]
    )
    state2 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-a2")
    with _employee_context(employee, company, namespace=namespace):
        result2 = await _run_lara(di, state=state2)

    assert result2.interrupt is None
    updated = _tool_json(result2.tool_results["documents_update_catalog"])
    assert updated.get("title") == f"acl-renamed-{unique_id}"
    members = _tool_json(result2.tool_results["documents_list_catalog_members"])
    member_ids = {
        item.get("user_id")
        for item in members["items"]
        if isinstance(item, dict)
    }
    assert system_user_id in member_ids
    _ = _tool_json(result2.tool_results["documents_get_access"])

    _ = mock_llm_with_queue(
        [
            *_load("documents-platform", "documents-catalog"),
            _call(
                "documents_patch_access",
                resource_kind="catalog",
                resource_id=catalog_id,
                link_enabled=True,
                link_permission="viewer",
            ),
            _call(
                "documents_rotate_public_link",
                resource_kind="catalog",
                resource_id=catalog_id,
            ),
            _call("documents_catalog_rag_status", catalog_id=catalog_id),
            _text("acl done"),
        ]
    )
    state3 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-a3")
    with _employee_context(employee, company, namespace=namespace):
        result3 = await _run_lara(di, state=state3)

    assert result3.interrupt is None
    rotated = _tool_json(result3.tool_results["documents_rotate_public_link"])
    public_url = rotated.get("public_url")
    assert isinstance(public_url, str) and "/documents/p/" in public_url
    rag_status = _tool_json(result3.tool_results["documents_catalog_rag_status"])
    assert rag_status.get("enabled") is False
