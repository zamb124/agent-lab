"""
E2E-бюджет SQL-запросов при выполнении flow.

Инфраструктура настоящая: FastAPI A2A API, TaskIQ worker, PostgreSQL, Redis.
Единственный допустимый мок — MockLLM через Redis. Monkeypatch не используется:
маркер real_taskiq отключает autouse sync_tools.
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass
from typing import Any
import pytest
from filelock import FileLock
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from apps.flows.config import get_settings

pytestmark = [pytest.mark.e2e, pytest.mark.real_taskiq, pytest.mark.timeout(120, func_only=True)]
_PG_STAT_LOCK = "/tmp/platform_pg_stat_statements_flow_budget.lock"


@dataclass(frozen=True)
class StatementStat:
    database: str
    query: str
    calls: int
    rows: int
    total_exec_time_ms: float


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


async def _ensure_pg_stat_statements(db_url: str) -> None:
    engine = create_async_engine(db_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_stat_statements"))
            try:
                await conn.execute(text("SELECT 1 FROM pg_stat_statements LIMIT 1"))
            except Exception as exc:
                raise AssertionError(
                    f"pg_stat_statements is not loaded in test PostgreSQL. Restart postgres-test after docker-compose-test.yaml update; this E2E must not be skipped. (original error: {exc})"
                ) from exc
    finally:
        await engine.dispose()


async def _reset_pg_stat_statements(db_url: str) -> None:
    engine = create_async_engine(db_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT pg_stat_statements_reset()"))
    finally:
        await engine.dispose()


async def _collect_statement_stats(db_url: str, database: str) -> list[StatementStat]:
    engine = create_async_engine(db_url)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "\n                        SELECT query, calls, rows, total_exec_time\n                        FROM pg_stat_statements\n                        WHERE dbid = (\n                            SELECT oid FROM pg_database WHERE datname = current_database()\n                        )\n                        ORDER BY calls DESC, total_exec_time DESC\n                        "
                    )
                )
            ).mappings()
            stats = [
                StatementStat(
                    database=database,
                    query=str(row["query"]),
                    calls=int(row["calls"]),
                    rows=int(row["rows"]),
                    total_exec_time_ms=float(row["total_exec_time"]),
                )
                for row in rows
            ]
            return [
                stat
                for stat in stats
                if "pg_stat_statements" not in stat.query and "CREATE EXTENSION" not in stat.query
            ]
    finally:
        await engine.dispose()


def _calls_matching(stats: list[StatementStat], *needles: str) -> int:
    return sum(
        (
            stat.calls
            for stat in stats
            if all((needle.lower() in stat.query.lower() for needle in needles))
        )
    )


def _workflow_event_write_calls(stats: list[StatementStat]) -> int:
    total = 0
    for stat in stats:
        normalized = " ".join(stat.query.split()).lower()
        if "insert into workflow_events" in normalized:
            total += stat.calls
    return total


def _is_control_statement(query: str) -> bool:
    normalized = " ".join(query.split()).lower()
    return normalized in {
        "begin",
        "commit",
        "rollback",
        "show transaction isolation level",
        "show standard_conforming_strings",
        "select pg_catalog.version()",
        "select current_schema()",
    }


def _application_stats(stats: list[StatementStat]) -> list[StatementStat]:
    return [stat for stat in stats if not _is_control_statement(stat.query)]


def _format_top(stats: list[StatementStat], limit: int = 15) -> str:
    lines = []
    for stat in sorted(stats, key=lambda s: (s.calls, s.total_exec_time_ms), reverse=True)[:limit]:
        query = " ".join(stat.query.split())
        if len(query) > 220:
            query = query[:217] + "..."
        lines.append(
            f"{stat.database}: calls={stat.calls}, rows={stat.rows}, time_ms={stat.total_exec_time_ms:.2f}, query={query}"
        )
    return "\n".join(lines)


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
    Проверяет SQL budget выполнения flow с параллельной волной LLM-нод.

    Цель регрессионная: выполнение пишет append-only ledger, а Redis остаётся
    только cache projection. История должна быть восстановима через workflow runtime.
    """
    settings = get_settings()
    db_urls = {
        "platform_agents": settings.database.flows_url,
        "platform_shared": settings.database.shared_url,
    }
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
        with FileLock(_PG_STAT_LOCK, timeout=420):
            for db_url in db_urls.values():
                await _ensure_pg_stat_statements(str(db_url))
            await _reset_pg_stat_statements(str(db_urls["platform_agents"]))
            task = await _execute_flow_once(client, flow_id, context_id)
            stats: list[StatementStat] = []
            for database, db_url in db_urls.items():
                stats.extend(await _collect_statement_stats(str(db_url), database))
        assert task["status"]["state"] == "completed"
        persisted_state = await container.workflow_runtime.get_state(session_id)
        assert persisted_state is not None
        assert persisted_state.terminal_task_state == "completed"
        (history, total_history) = await container.workflow_runtime.get_state_history(session_id)
        assert total_history >= 1
        assert history[-1]["event_type"] == "RunTerminal"
        app_stats = _application_stats(stats)
        agents_stats = [stat for stat in app_stats if stat.database == "platform_agents"]
        shared_stats = [stat for stat in app_stats if stat.database == "platform_shared"]
        top = _format_top(stats)
        agents_total_calls = sum((stat.calls for stat in agents_stats))
        shared_total_calls = sum((stat.calls for stat in shared_stats))
        workflow_event_writes = _workflow_event_write_calls(agents_stats)
        shared_storage_calls = _calls_matching(shared_stats, "select", "storage")
        assert workflow_event_writes >= 1, (
            f"Flow execution должен писать durable workflow_events.\n{top}"
        )
        assert agents_total_calls <= 40, (
            f"Слишком много прикладных SQL в platform_agents: {agents_total_calls}.\n{top}"
        )
        assert shared_storage_calls <= 2, (
            f"Слишком много shared storage SELECT во время A2A flow execution: {shared_storage_calls}.\n{top}"
        )
        assert shared_total_calls <= 4, (
            f"Слишком много прикладных SQL в platform_shared: {shared_total_calls}.\n{top}"
        )
    finally:
        await container.workflow_runtime.delete_state(session_id)
        await client.delete(f"/flows/api/v1/flows/{flow_id}")
