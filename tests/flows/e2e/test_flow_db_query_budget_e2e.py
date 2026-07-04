"""
E2E-бюджет durable ledger при выполнении flow.

Инфраструктура настоящая: FastAPI A2A API, TaskIQ worker, PostgreSQL, Redis.
Единственный допустимый мок — MockLLM через Redis. Monkeypatch не используется:
маркер real_taskiq отключает autouse sync_tools.

Бюджет считается строго в разрезе собственного session_id (workflow_events
ledger), а не глобально по pg_stat_statements: при параллельном прогоне
глобальный счёт SQL включает чужие тесты и бессмыслен.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from apps.flows.config import get_settings
from apps.flows.src.durable_execution import WorkflowEventType

pytestmark = [pytest.mark.e2e, pytest.mark.real_taskiq, pytest.mark.timeout(120, func_only=True)]


def _msg(text_value: str, context_id: str) -> dict[str, Any]:
    return {
        "messageId": str(uuid.uuid4()),
        "contextId": context_id,
        "role": "user",
        "parts": [{"kind": "text", "text": text_value}],
    }


def _task_from_json_rpc(data: dict[str, Any]) -> dict[str, Any]:
    assert "error" not in data, data.get("error")
    task = data.get("result")
    assert isinstance(task, dict)
    return task


async def _count_session_workflow_events(db_url: str, session_id: str) -> int:
    engine = create_async_engine(db_url)
    try:
        async with engine.connect() as conn:
            row = await conn.execute(
                text("SELECT COUNT(*) FROM workflow_events WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
            first = row.first()
            assert first is not None
            return int(first[0])
    finally:
        await engine.dispose()


async def _create_parallel_llm_flow(client, flow_id: str) -> None:
    response = await client.post(
        "/flows/api/v1/flows/",
        json={
            "flow_id": flow_id,
            "name": "DB Query Budget E2E",
            "entry": "entry_llm",
            "nodes": {
                "entry_llm": {
                    "type": "llm_node",
                    "prompt": "Return entry result.",
                    "llm": {"provider": "mock", "model": "mock-gpt-4"},
                },
                "left_llm": {
                    "type": "llm_node",
                    "prompt": "Return left result.",
                    "llm": {"provider": "mock", "model": "mock-gpt-4"},
                },
                "right_llm": {
                    "type": "llm_node",
                    "prompt": "Return right result.",
                    "llm": {"provider": "mock", "model": "mock-gpt-4"},
                },
            },
            "edges": [
                {"from_node": "entry_llm", "to_node": "left_llm"},
                {"from_node": "entry_llm", "to_node": "right_llm"},
                {"from_node": "left_llm", "to_node": None},
                {"from_node": "right_llm", "to_node": None},
            ],
        },
    )
    assert response.status_code == 200, response.text


async def _execute_flow_once(client, flow_id: str, context_id: str) -> dict[str, Any]:
    response = await client.post(
        f"/flows/api/v1/{flow_id}",
        json={
            "jsonrpc": "2.0",
            "id": f"db-budget-{uuid.uuid4().hex}",
            "method": "message/send",
            "params": {"message": _msg("run parallel llm flow", context_id)},
        },
    )
    assert response.status_code == 200, response.text
    return _task_from_json_rpc(response.json())


@pytest.mark.asyncio
async def test_parallel_llm_flow_db_query_budget(client, container, mock_llm_redis, unique_id):
    """
    Проверяет ledger budget выполнения flow с параллельной волной LLM-нод.

    Цель регрессионная: выполнение пишет append-only ledger в workflow_events,
    Redis остаётся только cache projection, история восстановима через
    workflow runtime, а число событий на один прогон ограничено сверху.
    """
    settings = get_settings()
    flows_db_url = str(settings.database.flows_url)
    flow_id = f"e2e_db_budget_{unique_id}"
    context_id = f"ctx-{unique_id}"
    session_id = f"{flow_id}:{context_id}"
    await _create_parallel_llm_flow(client, flow_id)
    await mock_llm_redis(
        [
            {"type": "text", "content": "entry result"},
            {"type": "text", "content": "left result"},
            {"type": "text", "content": "right result"},
        ]
    )
    try:
        task = await _execute_flow_once(client, flow_id, context_id)
        assert task["status"]["state"] == "completed"

        persisted_state = await container.workflow_runtime.get_state(session_id)
        assert persisted_state is not None
        assert persisted_state.terminal_task_state == "completed"

        (history, total_history) = await container.workflow_runtime.get_state_history(session_id)
        assert total_history >= 1
        assert history[-1].event_type is WorkflowEventType.run_terminal

        session_event_count = await _count_session_workflow_events(flows_db_url, session_id)
        assert session_event_count >= 1, (
            "Flow execution должен писать durable workflow_events для своего session_id"
        )
        assert session_event_count <= 60, (
            f"Слишком много workflow_events для одного прогона flow "
            f"(3 llm-ноды): {session_event_count}"
        )
    finally:
        await container.workflow_runtime.delete_state(session_id)
        await client.delete(f"/flows/api/v1/flows/{flow_id}")
