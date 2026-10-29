"""Lara runtime: MockLLM chooses skills/tools, platform services stay real."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest
from httpx2 import AsyncClient
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
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.state import ExecutionState
from core.types import JsonObject, JsonValue
from tests.fixtures.auth import service_client_asgi_auth_context
from tests.fixtures.crm_test_setup import wait_for_crm_semantic_search_hit
from tests.flows.agent_skills_harness import ensure_lara_flow
from tests.flows.durable_runtime_harness import run_flow
from tests.sync.api._helpers import seed_namespace_via_repo

pytestmark = [pytest.mark.usefixtures("app"), pytest.mark.timeout(180, func_only=True)]

MockLLMQueue = Callable[[list[MockLLMQueuedResponse]], MockLLM]
_JSON_OBJECT_ADAPTER: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)
_SYNC_BASE = "http://127.0.0.1:9005"


@contextmanager
def _system_context(
    *,
    auth_token: str,
    system_user_id: str,
) -> Iterator[None]:
    previous = get_context()
    set_context(
        Context(
            user=User(user_id=system_user_id, name="Lara runtime test"),
            active_company=Company(company_id="system", name="System"),
            auth_token=auth_token,
            channel="test",
            active_namespace="default",
            metadata={"user_id": system_user_id, "email": "test@example.com", "grps": []},
        )
    )
    try:
        yield
    finally:
        if previous is None:
            clear_context()
        else:
            set_context(previous)


@contextmanager
def _employee_context(employee_user: User, company: Company) -> Iterator[None]:
    previous = get_context()
    set_context(
        build_job_context(
            company=company,
            user=employee_user,
            host="",
            trace_id="lara-sync-runtime-test",
            session_id="lara-sync-runtime",
            channel="a2a",
        )
    )
    try:
        yield
    finally:
        if previous is None:
            clear_context()
        else:
            set_context(previous)


def _lara_state(*, unique_id: str, branch_id: str, user_id: str = "system") -> ExecutionState:
    context_id = f"lara-runtime-{branch_id}-{unique_id}"
    return ExecutionState(
        task_id=f"task-{branch_id}-{unique_id}",
        context_id=context_id,
        user_id=user_id,
        session_id=f"lara:{context_id}",
        branch_id=branch_id,
        content=f"runtime check {branch_id} {unique_id}",
    )


async def _require_lara_flow(
    di: FlowsDi,
    *,
    branch_id: str,
) -> Flow:
    _ = await ensure_lara_flow(di)
    flow = await di.flow_factory.get_flow("lara", branch_id=branch_id, tool_registry=di.tool_registry)
    assert flow is not None
    return flow


async def _seed_lara_skills(di: FlowsDi) -> None:
    seeded = await seed_platform_assistant_skills(
        di.files_service,
        "system",
    )
    assert seeded == len(PLATFORM_ASSISTANT_SEED_SKILL_IDS)


async def _run_lara(
    di: FlowsDi,
    *,
    state: ExecutionState,
    branch_id: str,
) -> ExecutionState:
    flow = await _require_lara_flow(di, branch_id=branch_id)
    main_node = flow.nodes["main"]
    assert getattr(main_node, "agent_skill_ids", None) == list(LARA_PLATFORM_SKILL_ROOTS)
    tool_names = {tool.name for tool in await main_node.get_tools(state)}
    assert "load_agent_skill" in tool_names
    assert "crm_search_entities" not in tool_names
    return await run_flow(
        di=di,
        flow=flow,
        state=state,
    )


def _tool_result_json_object(value: JsonValue) -> JsonObject:
    if isinstance(value, str):
        return _JSON_OBJECT_ADAPTER.validate_json(value)
    return _JSON_OBJECT_ADAPTER.validate_python(value)


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
async def test_lara_crm_branch_load_then_search_entities(
    di: FlowsDi,
    crm_service,
    crm_client,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user_id: str,
    mock_llm_with_queue: MockLLMQueue,
    mock_llm_capture,
    unique_id: str,
) -> None:
    _ = crm_service
    marker = f"lara_runtime_crm_marker_{unique_id}"
    create = await crm_client.post(
        "/crm/api/v1/entities",
        json={
            "entity_type": "organization",
            "name": f"Lara Runtime Org {unique_id}",
            "description": f"Runtime CRM semantic marker {marker} " + ("context " * 40),
            "namespace": "default",
        },
        headers=auth_headers_system,
    )
    assert create.status_code in (200, 201), create.text
    await wait_for_crm_semantic_search_hit(
        crm_client,
        auth_headers_system,
        query=marker,
        entity_type="organization",
        namespace="default",
    )
    _ = mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "load_agent_skill", "args": {"agent_skill_id": "networkle"}},
            {"type": "tool_call", "tool": "load_agent_skill", "args": {"agent_skill_id": "crm-entities"}},
            {
                "type": "tool_call",
                "tool": "crm_search_entities",
                "args": {
                    "query": marker,
                    "entity_type": "organization",
                    "namespace": "default",
                    "limit": 5,
                },
            },
            {"type": "text", "content": f"Found CRM marker {marker}"},
        ]
    )
    state = _lara_state(unique_id=unique_id, branch_id="crm", user_id=system_user_id)
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            await _seed_lara_skills(di)
            result = await _run_lara(di, state=state, branch_id="crm")

    assert result.interrupt is None
    search_body = _tool_result_json_object(result.tool_results["crm_search_entities"])
    hits = search_body.get("hits")
    assert isinstance(hits, list) and hits
    calls = await mock_llm_capture()
    assert "crm_search_entities" not in _captured_tool_names(calls[0])
    assert any("crm_search_entities" in _captured_tool_names(call) for call in calls[2:])


@pytest.mark.asyncio
async def test_lara_documents_branch_load_then_knowledge_search(
    di: FlowsDi,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user_id: str,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    namespace_id = f"lara_rt_docs_kb_{unique_id}"
    marker = f"lara-docs-kb-marker-{unique_id}"
    _ = mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": "load_agent_skill",
                "args": {"agent_skill_id": "documents-platform"},
            },
            {"type": "tool_call", "tool": "load_agent_skill", "args": {"agent_skill_id": "knowledge-rag"}},
            {
                "type": "tool_call",
                "tool": "rag_create_namespace",
                "args": {"name": namespace_id, "description": "Lara runtime Documents knowledge test"},
            },
            {
                "type": "tool_call",
                "tool": "rag_add_text",
                "args": {
                    "namespace_id": namespace_id,
                    "collection_id": "lara_runtime",
                    "text": f"Grounded Lara runtime knowledge {marker}",
                    "document_name": "lara-runtime.txt",
                },
            },
            {
                "type": "tool_call",
                "tool": "rag_search",
                "args": {
                    "namespace_id": namespace_id,
                    "collection_id": "lara_runtime",
                    "query": marker,
                    "limit": 5,
                },
            },
            {"type": "text", "content": f"Found Documents knowledge marker {marker}"},
        ]
    )
    state = _lara_state(unique_id=unique_id, branch_id="documents", user_id=system_user_id)
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            await _seed_lara_skills(di)
            result = await _run_lara(di, state=state, branch_id="documents")

    assert result.interrupt is None
    search_body = _tool_result_json_object(result.tool_results["rag_search"])
    results = search_body.get("results")
    assert isinstance(results, list) and results
    assert marker in json.dumps(results, ensure_ascii=False)


@pytest.mark.asyncio
async def test_lara_flows_branch_load_then_read_context(
    di: FlowsDi,
    flows_service,
    flows_client,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user_id: str,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = flows_service
    target_flow_id = f"lara_runtime_flow_{unique_id}"
    create = await flows_client.post(
        "/flows/api/v1/flows/",
        json={
            "flow_id": target_flow_id,
            "name": f"Lara Runtime Flow {unique_id}",
            "description": "Flow for Lara runtime tool checks",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "name": "Main",
                    "prompt": f"Initial prompt {unique_id}",
                    "tools": ["ask_user"],
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
            "variables": {},
            "tags": ["test", "lara"],
            "branches": {},
            "triggers": {},
            "resources": {},
        },
        headers=auth_headers_system,
    )
    assert create.status_code == 200, create.text
    _ = mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "load_agent_skill", "args": {"agent_skill_id": "flows-platform"}},
            {"type": "tool_call", "tool": "load_agent_skill", "args": {"agent_skill_id": "flows-editor"}},
            {
                "type": "tool_call",
                "tool": "flows_read_context",
                "args": {"flow_id": target_flow_id, "branch_id": "base", "node_id": "main"},
            },
            {"type": "text", "content": "Read flow context"},
        ]
    )
    state = _lara_state(unique_id=unique_id, branch_id="flows", user_id=system_user_id)
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            await _seed_lara_skills(di)
            result = await _run_lara(di, state=state, branch_id="flows")

    assert result.interrupt is None
    read_body = _tool_result_json_object(result.tool_results["flows_read_context"])
    assert read_body.get("success") is True
    assert read_body.get("flow_id") == target_flow_id
    flow_summary = read_body.get("flow")
    assert isinstance(flow_summary, dict)
    assert "nodes" not in flow_summary
    assert "edges" not in flow_summary
    nodes_index = read_body.get("nodes_index")
    assert isinstance(nodes_index, list)
    assert any(isinstance(item, dict) and item.get("node_id") == "main" for item in nodes_index)
    node = read_body.get("node")
    assert isinstance(node, dict)
    assert node.get("prompt") == f"Initial prompt {unique_id}"


@pytest.mark.asyncio
async def test_lara_sync_branch_load_then_send_message(
    di: FlowsDi,
    flows_service,
    sync_service,
    frontend_di,
    auth_token_system: str,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = flows_service, sync_service
    flow_id = f"lara_sync_runtime_{unique_id}"
    company = await Company.get("system")
    assert company is not None
    employee = await ensure_flow_employee(
        frontend_di,
        flow_id=flow_id,
        company_id="system",
        name="Lara Sync Runtime",
        roles=["member"],
        curator_user_ids=["system"],
    )
    employee_user_id = flow_employee_user_id(flow_id)
    assert employee.user_id == employee_user_id
    namespace = f"lara_sync_rt_{unique_id}"
    await seed_namespace_via_repo(frontend_di, "system", namespace)
    headers = {"Authorization": f"Bearer {auth_token_system}"}
    async with AsyncClient(base_url=_SYNC_BASE, timeout=60.0) as http:
        created = await http.post(
            "/sync/api/v1/channels/",
            headers=headers,
            json={"namespace": namespace, "type": "topic", "name": "lara runtime", "is_private": False},
        )
        assert created.status_code == 201, created.text
        channel_id = created.json()["channel_id"]
        member_added = await http.post(
            f"/sync/api/v1/channels/{channel_id}/members",
            headers=headers,
            json={"user_id": employee_user_id, "role": "member"},
        )
        assert member_added.status_code in (200, 201), member_added.text

    text = f"Lara Sync runtime message {unique_id}"
    _ = mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "load_agent_skill", "args": {"agent_skill_id": "sync-platform"}},
            {"type": "tool_call", "tool": "load_agent_skill", "args": {"agent_skill_id": "sync-messaging"}},
            {
                "type": "tool_call",
                "tool": "sync_send_message",
                "args": {"channel_id": channel_id, "text": text},
            },
            {"type": "tool_call", "tool": "sync_list_messages", "args": {"channel_id": channel_id, "limit": 20}},
            {"type": "text", "content": "Sent sync message"},
        ]
    )
    state = _lara_state(unique_id=unique_id, branch_id="sync", user_id=employee_user_id)
    with _employee_context(employee, company):
        await _seed_lara_skills(di)
        result = await _run_lara(di, state=state, branch_id="sync")

    assert result.interrupt is None
    send_body = _tool_result_json_object(result.tool_results["sync_send_message"])
    assert send_body.get("channel_id") == channel_id
    assert isinstance(send_body.get("message_id"), str) and send_body["message_id"]
    list_body = _tool_result_json_object(result.tool_results["sync_list_messages"])
    assert list_body.get("channel_id") == channel_id
    assert int(list_body.get("count", 0)) >= 1


@pytest.mark.parametrize(
    "branch_id",
    ["console", "crm", "flows", "sync", "documents", "worktracker", "litserve"],
)
@pytest.mark.asyncio
async def test_lara_any_entry_can_load_cross_service_skill(
    di: FlowsDi,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user_id: str,
    mock_llm_with_queue: MockLLMQueue,
    mock_llm_capture,
    unique_id: str,
    branch_id: str,
) -> None:
    _ = mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "load_agent_skill", "args": {"agent_skill_id": "networkle"}},
            {"type": "tool_call", "tool": "load_agent_skill", "args": {"agent_skill_id": "crm-entities"}},
            {"type": "text", "content": f"{branch_id} loaded CRM skills"},
        ]
    )
    state = _lara_state(unique_id=unique_id, branch_id=branch_id, user_id=system_user_id)
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            await _seed_lara_skills(di)
            result = await _run_lara(di, state=state, branch_id=branch_id)

    assert result.interrupt is None
    calls = await mock_llm_capture()
    assert len(calls) >= 2
    assert "crm_search_entities" not in _captured_tool_names(calls[0])
    assert "crm_search_entities" in _captured_tool_names(calls[-1])


@pytest.mark.asyncio
async def test_lara_console_branch_ask_user_interrupts(
    di: FlowsDi,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user_id: str,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": "ask_user",
                "args": {"question": "Какой раздел консоли открыть?"},
            }
        ]
    )
    state = _lara_state(unique_id=unique_id, branch_id="console", user_id=system_user_id)
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            await _seed_lara_skills(di)
            result = await _run_lara(di, state=state, branch_id="console")

    assert result.interrupt is not None
    assert "консоли" in result.interrupt.question.lower()
