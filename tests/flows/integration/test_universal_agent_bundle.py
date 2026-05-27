"""
Интеграционные тесты bundle «Универсальный агент» (universal_agent).

Покрытие: реальный запуск flow из БД, реальные тулы (calculator, ask_user,
rag_create_namespace, rag_add_text, rag_search). Очередь ответов — только MockLLM
(`mock_llm_with_queue` / `setup_mock_responses`).

Инфраструктура pytest (autouse для всего репозитория): sync_tools (TaskIQ in-process),
patch ServiceClient на ASGI-приложения. В этом модуле нет собственных monkeypatch и
нет подмены тулов вне MockLLM.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import TypeAdapter

from apps.flows.src.container import FlowContainer, get_container
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.runtime.flow import Flow
from core.clients.llm.mock import MockLLM, MockLLMQueuedResponse
from core.state import ExecutionState
from core.types import JsonObject, JsonValue
from tests.fixtures.auth import service_client_asgi_auth_context
from tests.flows.durable_runtime_harness import run_flow

FLOW_ID = "universal_agent"
pytestmark = pytest.mark.usefixtures("app")
MockLLMQueue = Callable[[list[MockLLMQueuedResponse]], MockLLM]
_JSON_OBJECT_ADAPTER: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)
_JSON_ARRAY_ADAPTER: TypeAdapter[list[JsonValue]] = TypeAdapter(list[JsonValue])


def _tool_ids_from_main_node_tools(tools: JsonValue) -> list[str]:
    if not isinstance(tools, list):
        return []
    out: list[str] = []
    for item in _JSON_ARRAY_ADAPTER.validate_python(tools):
        if isinstance(item, dict):
            if "tool_id" not in item:
                continue
            tid = item["tool_id"]
            if isinstance(tid, str) and tid:
                out.append(tid)
        elif isinstance(item, str) and item:
            out.append(item)
    return out


async def _require_universal_agent_flow(
    container: FlowContainer,
    *,
    branch_id: str = "default",
) -> Flow:
    flow = await container.flow_factory.get_flow(FLOW_ID, branch_id=branch_id)
    assert flow is not None
    return flow


async def _run_universal_agent_flow(
    container: FlowContainer,
    state: ExecutionState,
    *,
    branch_id: str = "default",
) -> ExecutionState:
    flow = await _require_universal_agent_flow(container, branch_id=branch_id)
    return await run_flow(
        container=as_flow_runtime_container(container),
        flow=flow,
        state=state,
    )


def _tool_result_json_object(value: JsonValue) -> JsonObject:
    if isinstance(value, str):
        return _JSON_OBJECT_ADAPTER.validate_json(value)
    return _JSON_OBJECT_ADAPTER.validate_python(value)


def _required_json_array(body: JsonObject, key: str) -> list[JsonValue]:
    if key not in body:
        raise AssertionError(f"Expected JSON object key {key!r}")
    return _JSON_ARRAY_ADAPTER.validate_python(body[key])


def _required_str(body: JsonObject, key: str) -> str:
    if key not in body:
        raise AssertionError(f"Expected JSON object key {key!r}")
    value = body[key]
    if not isinstance(value, str):
        raise AssertionError(f"Expected JSON object key {key!r} to be a string")
    return value


@pytest.mark.asyncio
async def test_universal_agent_loaded_in_database() -> None:
    container = get_container()
    config = await container.flow_repository.get(FLOW_ID)
    assert config is not None
    assert config.flow_id == FLOW_ID
    assert "code_focus" in config.branches
    assert "with_rag" in config.branches


@pytest.mark.asyncio
async def test_universal_agent_with_rag_skill_merges_rag_tools() -> None:
    container = get_container()
    nodes = await container.flow_factory.get_effective_nodes_map(FLOW_ID, "with_rag")
    main = nodes["main"]
    tool_ids = _tool_ids_from_main_node_tools(main.get("tools"))
    for name in (
        "ask_user",
        "calculator",
        "rag_create_namespace",
        "rag_add_text",
        "rag_search",
    ):
        assert name in tool_ids


@pytest.mark.asyncio
async def test_universal_agent_code_focus_skill_merges_prompt() -> None:
    container = get_container()
    nodes = await container.flow_factory.get_effective_nodes_map(FLOW_ID, "code_focus")
    prompt = nodes["main"].get("prompt", "")
    assert isinstance(prompt, str)
    assert "песочница кода" in prompt


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="universal_agent_llm")
async def test_universal_agent_calculator_tool(
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "19 + 23"}},
            "Сумма 19 и 23 равна 42.",
        ]
    )
    container = get_container()
    context_id = f"ua-calc-{unique_id}"
    state = ExecutionState(
        task_id=f"task-{unique_id}",
        context_id=context_id,
        user_id=f"user-{unique_id}",
        session_id=f"{FLOW_ID}:{context_id}",
        content="Сколько будет 19 плюс 23?",
    )
    result = await _run_universal_agent_flow(container, state)
    assert result.interrupt is None
    assert "calculator" in result.tool_results
    calc_out = result.tool_results["calculator"]
    assert "42" in str(calc_out)
    assert "42" in (result.response or "")


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="universal_agent_llm")
async def test_universal_agent_ask_user_interrupt(
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": "ask_user",
                "args": {"question": "Уточните, пожалуйста, город доставки?"},
            },
        ]
    )
    container = get_container()
    context_id = f"ua-ask-{unique_id}"
    state = ExecutionState(
        task_id=f"task-{unique_id}",
        context_id=context_id,
        user_id=f"user-{unique_id}",
        session_id=f"{FLOW_ID}:{context_id}",
        content="Нужна доставка, но адрес неясен",
    )
    result = await _run_universal_agent_flow(container, state)
    assert result.interrupt is not None
    assert "город" in result.interrupt.question.lower()


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="universal_agent_llm")
async def test_universal_agent_code_focus_skill_runs_calculator(
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "6 * 7"}},
            "Произведение 6 и 7: 42.",
        ]
    )
    container = get_container()
    context_id = f"ua-cf-{unique_id}"
    state = ExecutionState(
        task_id=f"task-{unique_id}",
        context_id=context_id,
        user_id=f"user-{unique_id}",
        session_id=f"{FLOW_ID}:{context_id}",
        branch_id="code_focus",
        content="Сколько 6 умножить на 7?",
    )
    result = await _run_universal_agent_flow(container, state, branch_id="code_focus")
    assert result.interrupt is None
    assert "calculator" in result.tool_results
    assert "42" in str(result.tool_results["calculator"])


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="universal_agent_llm")
async def test_universal_agent_with_rag_create_namespace(
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    ns = f"ua_ns_{unique_id}"
    _ = mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": "rag_create_namespace",
                "args": {"name": ns, "description": "universal_agent test"},
            },
            f"Создан namespace {ns}.",
        ]
    )
    container = get_container()
    context_id = f"ua-ragc-{unique_id}"
    state = ExecutionState(
        task_id=f"task-{unique_id}",
        context_id=context_id,
        user_id=f"user-{unique_id}",
        session_id=f"{FLOW_ID}:{context_id}",
        branch_id="with_rag",
        content=f"Создай RAG namespace с именем {ns}",
    )
    with service_client_asgi_auth_context(auth_headers_system):
        result = await _run_universal_agent_flow(container, state, branch_id="with_rag")
    assert result.interrupt is None
    out = result.tool_results["rag_create_namespace"]
    body = _tool_result_json_object(out)
    assert body.get("success") is True
    assert body.get("name") == ns


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="universal_agent_llm")
async def test_universal_agent_with_rag_ingest_and_search(
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    ns = f"ua_ing_{unique_id}"
    chunk = "Humanitec universal_agent RAG marker zeta-9 for semantic retrieval."
    _ = mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": "rag_create_namespace",
                "args": {"name": ns, "description": "ingest test"},
            },
            {
                "type": "tool_call",
                "tool": "rag_add_text",
                "args": {
                    "namespace_id": ns,
                    "collection_id": "universal_agent_test",
                    "text": chunk,
                    "document_name": "ua_marker.txt",
                },
            },
            {
                "type": "tool_call",
                "tool": "rag_search",
                "args": {
                    "namespace_id": ns,
                    "collection_id": "universal_agent_test",
                    "query": "zeta-9 marker Humanitec",
                    "limit": 5,
                },
            },
            "Найден фрагмент в базе знаний.",
        ]
    )
    container = get_container()
    context_id = f"ua-ragf-{unique_id}"
    state = ExecutionState(
        task_id=f"task-{unique_id}",
        context_id=context_id,
        user_id=f"user-{unique_id}",
        session_id=f"{FLOW_ID}:{context_id}",
        branch_id="with_rag",
        content="Создай namespace, добавь текст про zeta-9 и найди его поиском.",
    )
    with service_client_asgi_auth_context(auth_headers_system):
        result = await _run_universal_agent_flow(container, state, branch_id="with_rag")
    assert result.interrupt is None
    assert "rag_add_text" in result.tool_results
    add_body = _tool_result_json_object(result.tool_results["rag_add_text"])
    assert add_body.get("success") is True

    assert "rag_search" in result.tool_results
    search_body = _tool_result_json_object(result.tool_results["rag_search"])
    assert search_body.get("success") is True
    results = _required_json_array(search_body, "results")
    assert len(results) >= 1
    first = _JSON_OBJECT_ADAPTER.validate_python(results[0])
    content = _required_str(first, "content")
    assert "zeta-9" in content or "Humanitec" in content
