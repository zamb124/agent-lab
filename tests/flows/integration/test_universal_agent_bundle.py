"""
Интеграционные тесты bundle «Универсальный агент» (universal_agent).

Покрытие: реальный запуск flow из БД, реальные тулы (calculator, ask_user, sandbox_codegen,
rag_create_namespace, rag_add_text, rag_search). Очередь ответов — только MockLLM
(`mock_llm_with_queue` / `setup_mock_responses`).

Инфраструктура pytest (autouse для всего репозитория): sync_tools (TaskIQ in-process),
patch ServiceClient на ASGI-приложения. В этом модуле нет собственных monkeypatch и
нет подмены тулов вне MockLLM.
"""

from __future__ import annotations

import json

import pytest

from apps.flows.src.container import get_container
from core.state import ExecutionState
from tests.fixtures.auth import service_client_asgi_auth_context

FLOW_ID = "universal_agent"


def _tool_ids_from_main_node_tools(tools: object) -> list[str]:
    if not isinstance(tools, list):
        return []
    out: list[str] = []
    for item in tools:
        if isinstance(item, dict):
            tid = item.get("tool_id")
            if isinstance(tid, str) and tid:
                out.append(tid)
        elif isinstance(item, str) and item:
            out.append(item)
    return out


@pytest.mark.asyncio
async def test_universal_agent_loaded_in_database(app):
    container = get_container()
    config = await container.flow_repository.get(FLOW_ID)
    assert config is not None
    assert config.flow_id == FLOW_ID
    assert "code_focus" in config.branches
    assert "with_rag" in config.branches


@pytest.mark.asyncio
async def test_universal_agent_with_rag_skill_merges_rag_tools(app):
    container = get_container()
    nodes = await container.flow_factory.get_effective_nodes_map(FLOW_ID, "with_rag")
    main = nodes["main"]
    tool_ids = _tool_ids_from_main_node_tools(main.get("tools"))
    for name in (
        "ask_user",
        "calculator",
        "sandbox_codegen",
        "rag_create_namespace",
        "rag_add_text",
        "rag_search",
    ):
        assert name in tool_ids


@pytest.mark.asyncio
async def test_universal_agent_code_focus_skill_merges_prompt(app):
    container = get_container()
    nodes = await container.flow_factory.get_effective_nodes_map(FLOW_ID, "code_focus")
    prompt = nodes["main"].get("prompt", "")
    assert isinstance(prompt, str)
    assert "песочница кода" in prompt


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="universal_agent_llm")
async def test_universal_agent_calculator_tool(app, mock_llm_with_queue, unique_id):
    mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "19 + 23"}},
            "Сумма 19 и 23 равна 42.",
        ]
    )
    container = get_container()
    flow = await container.flow_factory.get_flow(FLOW_ID)
    context_id = f"ua-calc-{unique_id}"
    state = ExecutionState(
        task_id=f"task-{unique_id}",
        context_id=context_id,
        user_id=f"user-{unique_id}",
        session_id=f"{FLOW_ID}:{context_id}",
        content="Сколько будет 19 плюс 23?",
    )
    result = await flow.run(state)
    assert result.interrupt is None
    assert "calculator" in result.tool_results
    calc_out = result.tool_results["calculator"]
    assert "42" in str(calc_out)
    assert "42" in (result.response or "")


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="universal_agent_llm")
async def test_universal_agent_sandbox_codegen_tool(app, mock_llm_with_queue, unique_id):
    gen_code = "async def run(state):\n    return {'k': 99}\n"
    mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": "sandbox_codegen",
                "args": {
                    "task": "Верни dict с ключом k и значением 99",
                    "max_iterations": 2,
                },
            },
            {"type": "structured_output", "data": {"code_lines": gen_code.splitlines()}},
            "Готово: k=99 по результату мета-тула.",
        ]
    )
    container = get_container()
    flow = await container.flow_factory.get_flow(FLOW_ID)
    context_id = f"ua-eval-{unique_id}"
    state = ExecutionState(
        task_id=f"task-{unique_id}",
        context_id=context_id,
        user_id=f"user-{unique_id}",
        session_id=f"{FLOW_ID}:{context_id}",
        content="Запусти вычисление через sandbox_codegen",
    )
    result = await flow.run(state)
    assert result.interrupt is None
    assert "sandbox_codegen" in result.tool_results
    raw = result.tool_results["sandbox_codegen"]
    payload = json.loads(raw) if isinstance(raw, str) else raw
    assert payload["success"] is True
    assert payload["result"] == {"k": 99}


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="universal_agent_llm")
async def test_universal_agent_ask_user_interrupt(app, mock_llm_with_queue, unique_id):
    mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": "ask_user",
                "args": {"question": "Уточните, пожалуйста, город доставки?"},
            },
        ]
    )
    container = get_container()
    flow = await container.flow_factory.get_flow(FLOW_ID)
    context_id = f"ua-ask-{unique_id}"
    state = ExecutionState(
        task_id=f"task-{unique_id}",
        context_id=context_id,
        user_id=f"user-{unique_id}",
        session_id=f"{FLOW_ID}:{context_id}",
        content="Нужна доставка, но адрес неясен",
    )
    result = await flow.run(state)
    assert result.interrupt is not None
    assert "город" in result.interrupt.question.lower()


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="universal_agent_llm")
async def test_universal_agent_code_focus_skill_runs_calculator(
    app, mock_llm_with_queue, unique_id
):
    mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "6 * 7"}},
            "Произведение 6 и 7: 42.",
        ]
    )
    container = get_container()
    flow = await container.flow_factory.get_flow(FLOW_ID, branch_id="code_focus")
    context_id = f"ua-cf-{unique_id}"
    state = ExecutionState(
        task_id=f"task-{unique_id}",
        context_id=context_id,
        user_id=f"user-{unique_id}",
        session_id=f"{FLOW_ID}:{context_id}",
        content="Сколько 6 умножить на 7?",
    )
    result = await flow.run(state)
    assert result.interrupt is None
    assert "calculator" in result.tool_results
    assert "42" in str(result.tool_results["calculator"])


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="universal_agent_llm")
async def test_universal_agent_with_rag_create_namespace(
    app, mock_llm_with_queue, unique_id, auth_headers_system
):
    ns = f"ua_ns_{unique_id}"
    mock_llm_with_queue(
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
    flow = await container.flow_factory.get_flow(FLOW_ID, branch_id="with_rag")
    context_id = f"ua-ragc-{unique_id}"
    state = ExecutionState(
        task_id=f"task-{unique_id}",
        context_id=context_id,
        user_id=f"user-{unique_id}",
        session_id=f"{FLOW_ID}:{context_id}",
        content=f"Создай RAG namespace с именем {ns}",
    )
    with service_client_asgi_auth_context(auth_headers_system):
        result = await flow.run(state)
    assert result.interrupt is None
    out = result.tool_results["rag_create_namespace"]
    body = out if isinstance(out, dict) else json.loads(out)
    assert body.get("success") is True
    assert body.get("name") == ns


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="universal_agent_llm")
async def test_universal_agent_with_rag_ingest_and_search(
    app, mock_llm_with_queue, unique_id, auth_headers_system
):
    ns = f"ua_ing_{unique_id}"
    chunk = "Humanitec universal_agent RAG marker zeta-9 for semantic retrieval."
    mock_llm_with_queue(
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
    flow = await container.flow_factory.get_flow(FLOW_ID, branch_id="with_rag")
    context_id = f"ua-ragf-{unique_id}"
    state = ExecutionState(
        task_id=f"task-{unique_id}",
        context_id=context_id,
        user_id=f"user-{unique_id}",
        session_id=f"{FLOW_ID}:{context_id}",
        content="Создай namespace, добавь текст про zeta-9 и найди его поиском.",
    )
    with service_client_asgi_auth_context(auth_headers_system):
        result = await flow.run(state)
    assert result.interrupt is None
    add_out = result.tool_results.get("rag_add_text")
    assert add_out is not None
    if isinstance(add_out, dict):
        add_body = add_out
    else:
        add_body = json.loads(add_out)
    assert add_body.get("success") is True

    search_out = result.tool_results.get("rag_search")
    assert search_out is not None
    if isinstance(search_out, dict):
        search_body = search_out
    else:
        search_body = json.loads(search_out)
    assert search_body.get("success") is True
    results = search_body.get("results")
    assert isinstance(results, list)
    assert len(results) >= 1
    first = results[0]
    content = first.get("content", "")
    assert "zeta-9" in content or "Humanitec" in content
