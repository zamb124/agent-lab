"""
Сбор server-side статистики Postgres во время make test (DB_PROFILE default-on).

Subcommands:
  reset   — pg_stat_statements_reset() на всех test-БД
  collect — snapshot pg_stat_* views → reports/db_test_profile/<run_id>/raw/
  report  — summary.json + report.html + terminal summary (KPI, tops, delta)

Scope: stats снимаются после pytest phase 1 (`-m "not integration and not network"`).
Integration/retry/agent E2E в этот snapshot не входят.

Guard: только localhost:54322 (как db_test_reset.py).
Opt-out: DB_PROFILE=0 make test.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import importlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, TypedDict
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST_PATH = _REPO_ROOT / "migrations" / "services.json"
_REPORTS_ROOT = _REPO_ROOT / "reports" / "db_test_profile"
_POSTGRES_LOG_DIR = _REPO_ROOT / "reports" / "postgres-test-logs"

_TEST_POSTGRES_PORT = 54322
_TEST_POSTGRES_HOSTS = {"localhost", "127.0.0.1"}
_DEFAULT_DSN = "postgresql://platform_user:admin@localhost:54322"

_SLOW_MEAN_MS = float(os.environ.get("DB_PROFILE_SLOW_MS", "50"))
_SLOW_TOTAL_MS = float(os.environ.get("DB_PROFILE_SLOW_TOTAL_MS", "5000"))
_HEAVY_ROWS = int(os.environ.get("DB_PROFILE_HEAVY_ROWS", "10000"))
_SEQ_SCAN_TABLE_MIN_ROWS = int(os.environ.get("DB_PROFILE_SEQ_SCAN_MIN_ROWS", "1000"))
_MIN_CALLS_FOR_CHATTY = int(os.environ.get("DB_PROFILE_CHATTY_MIN_CALLS", "100"))
_TOP_N = int(os.environ.get("DB_PROFILE_TOP_N", "50"))
_TERMINAL_TOP_N = int(os.environ.get("DB_PROFILE_TERMINAL_TOP_N", "10"))
_UNCONDITIONAL_TOP_N = int(os.environ.get("DB_PROFILE_UNCONDITIONAL_TOP_N", "10"))
_EMPTY_TOTAL_EXEC_MS = 1000.0
_EMPTY_TOTAL_CALLS = 100


class PostgresRecord(Protocol):
    def __getitem__(self, key: str) -> object: ...


class PostgresConnection(Protocol):
    async def execute(self, query: str) -> str: ...

    async def fetch(self, query: str) -> list[PostgresRecord]: ...

    async def close(self) -> None: ...


def _json_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("bool is not a valid integer metric")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    raise ValueError(f"expected numeric value, got {type(value)!r}")


def _json_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("bool is not a valid float metric")
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return value
    raise ValueError(f"expected numeric value, got {type(value)!r}")


def _require_int(value: object) -> int:
    parsed = _json_int(value)
    if parsed is None:
        raise ValueError("integer value is required")
    return parsed


def _int_or_zero(value: object) -> int:
    parsed = _json_int(value)
    if parsed is None:
        return 0
    return parsed


def _float_or_zero(value: object) -> float:
    parsed = _json_float(value)
    if parsed is None:
        return 0.0
    return parsed


def _require_float(value: object) -> float:
    parsed = _json_float(value)
    if parsed is None:
        raise ValueError("float value is required")
    return parsed


def _postgres_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    raise ValueError(f"expected text-like value, got {type(value)!r}")


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _postgres_text(value)


class StatementRow(TypedDict):
    queryid: str
    query: str
    calls: int
    total_exec_time_ms: float
    mean_exec_time_ms: float
    max_exec_time_ms: float
    rows: int
    shared_blks_hit: int
    shared_blks_read: int
    temp_blks_written: int


class TableStatRow(TypedDict):
    schemaname: str
    relname: str
    seq_scan: int
    seq_tup_read: int
    idx_scan: int
    idx_tup_fetch: int
    n_live_tup: int
    n_dead_tup: int


class IndexStatRow(TypedDict):
    schemaname: str
    relname: str
    indexrelname: str
    idx_scan: int
    idx_tup_read: int
    idx_tup_fetch: int


class DatabaseStatRow(TypedDict):
    datname: str
    deadlocks: int
    conflicts: int
    temp_files: int
    temp_bytes: int
    blks_read: int
    blks_hit: int


class ActivityRow(TypedDict):
    pid: int
    state: str
    wait_event_type: str | None
    wait_event: str | None
    xact_seconds: float | None
    query_preview: str


class SeqScanPlan(TypedDict):
    relation: str | None
    node_type: str
    actual_rows: int | None
    plan_rows: int | None
    total_cost: float | None
    query_text: str | None


class DatabaseSnapshot(TypedDict):
    database: str
    service: str
    statements: list[StatementRow]
    user_tables: list[TableStatRow]
    user_indexes: list[IndexStatRow]
    database_stats: DatabaseStatRow | None
    activity: list[ActivityRow]


class ClusterRollupRow(TypedDict):
    query_key: str
    query: str
    services: list[str]
    calls: int
    total_exec_time_ms: float
    mean_exec_time_ms: float
    max_exec_time_ms: float
    rows: int
    temp_blks_written: int
    shared_blks_read: int


class DeadTupTableRow(TypedDict):
    service: str
    database: str
    schemaname: str
    relname: str
    n_live_tup: int
    n_dead_tup: int
    dead_ratio_pct: float


class CacheHitRow(TypedDict):
    service: str
    database: str
    cache_hit_ratio_pct: float
    blks_hit: int
    blks_read: int


class DeltaQueryRow(TypedDict):
    query_key: str
    query: str
    calls: int
    calls_delta: int
    total_exec_time_ms: float
    total_exec_ms_delta: float
    calls_pct_change: float | None


class DeltaVsPrevious(TypedDict):
    has_previous: bool
    previous_run_id: str | None
    total_exec_time_ms_delta: float | None
    total_calls_delta: int | None
    slow_query_count_total_delta: int | None
    query_deltas: list[DeltaQueryRow]


@dataclass(frozen=True)
class ServiceDatabase:
    service_name: str
    database_name: str


def _service_database_name(service_name: str) -> str:
    if service_name == "shared":
        return "platform_shared"
    if service_name == "flows":
        return "platform_agents"
    return f"platform_{service_name}"


def _load_service_databases() -> list[ServiceDatabase]:
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    databases = manifest.get("postgres", {}).get("databases")
    if not isinstance(databases, list) or not databases:
        raise RuntimeError(f"migrations/services.json: postgres.databases missing: {manifest}")
    services = manifest.get("services")
    if not isinstance(services, list):
        raise RuntimeError("migrations/services.json: services missing")
    result: list[ServiceDatabase] = []
    seen_databases: set[str] = set()
    for entry in services:
        if not isinstance(entry, dict):
            continue
        service_name = entry.get("name")
        if not isinstance(service_name, str):
            continue
        database_name = _service_database_name(service_name)
        if database_name not in databases:
            raise RuntimeError(
                f"service {service_name!r} maps to {database_name!r}, missing in postgres.databases"
            )
        if database_name in seen_databases:
            continue
        seen_databases.add(database_name)
        result.append(ServiceDatabase(service_name=service_name, database_name=database_name))
    for database_name in databases:
        if not isinstance(database_name, str):
            continue
        if database_name in seen_databases:
            continue
        service_name = database_name.removeprefix("platform_")
        result.append(ServiceDatabase(service_name=service_name, database_name=database_name))
    return result


def _assert_test_postgres(dsn: str) -> None:
    parsed = urlparse(dsn)
    if parsed.hostname not in _TEST_POSTGRES_HOSTS:
        raise RuntimeError(
            f"db_test_profile: запрещено на host {parsed.hostname!r}, только test localhost"
        )
    if parsed.port != _TEST_POSTGRES_PORT:
        raise RuntimeError(
            f"db_test_profile: запрещено на port {parsed.port}, только {_TEST_POSTGRES_PORT}"
        )


def _postgres_dsn(base_dsn: str, database_name: str) -> str:
    parsed = urlparse(base_dsn)
    return (
        f"postgresql://{parsed.username}:{parsed.password}"
        f"@{parsed.hostname}:{parsed.port}/{database_name}"
    )


async def _connect(database_name: str, base_dsn: str) -> PostgresConnection:
    asyncpg_module = importlib.import_module("asyncpg")
    connect_fn = getattr(asyncpg_module, "connect")
    return await connect_fn(_postgres_dsn(base_dsn, database_name))


async def _reset_database(connection: PostgresConnection) -> None:
    _ = await connection.execute("SELECT pg_stat_statements_reset()")


async def cmd_reset(base_dsn: str) -> None:
    _assert_test_postgres(base_dsn)
    for entry in _load_service_databases():
        connection = await _connect(entry.database_name, base_dsn)
        try:
            await _reset_database(connection)
        finally:
            await connection.close()
    print(f"db_test_profile: reset pg_stat_statements on {len(_load_service_databases())} databases")


def _row_to_statement(record: PostgresRecord) -> StatementRow:
    return StatementRow(
        queryid=_postgres_text(record["queryid"]),
        query=_postgres_text(record["query"]),
        calls=_require_int(record["calls"]),
        total_exec_time_ms=_require_float(record["total_exec_time"]),
        mean_exec_time_ms=_require_float(record["mean_exec_time"]),
        max_exec_time_ms=_require_float(record["max_exec_time"]),
        rows=_require_int(record["rows"]),
        shared_blks_hit=_require_int(record["shared_blks_hit"]),
        shared_blks_read=_require_int(record["shared_blks_read"]),
        temp_blks_written=_require_int(record["temp_blks_written"]),
    )


async def _collect_database(
    entry: ServiceDatabase,
    base_dsn: str,
) -> DatabaseSnapshot:
    connection = await _connect(entry.database_name, base_dsn)
    try:
        statement_records = await connection.fetch(
            """
            SELECT
                queryid,
                query,
                calls,
                total_exec_time,
                mean_exec_time,
                max_exec_time,
                rows,
                shared_blks_hit,
                shared_blks_read,
                temp_blks_written
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
            ORDER BY total_exec_time DESC
            LIMIT 5000
            """
        )
        table_records = await connection.fetch(
            """
            SELECT
                schemaname,
                relname,
                seq_scan,
                seq_tup_read,
                idx_scan,
                idx_tup_fetch,
                n_live_tup,
                n_dead_tup
            FROM pg_stat_user_tables
            ORDER BY seq_scan DESC, seq_tup_read DESC
            """
        )
        index_records = await connection.fetch(
            """
            SELECT
                schemaname,
                relname,
                indexrelname,
                idx_scan,
                idx_tup_read,
                idx_tup_fetch
            FROM pg_stat_user_indexes
            ORDER BY idx_scan ASC, relname
            """
        )
        db_stat_records = await connection.fetch(
            """
            SELECT
                datname,
                deadlocks,
                conflicts,
                temp_files,
                temp_bytes,
                blks_read,
                blks_hit
            FROM pg_stat_database
            WHERE datname = current_database()
            """
        )
        activity_records = await connection.fetch(
            """
            SELECT
                pid,
                state,
                wait_event_type,
                wait_event,
                EXTRACT(EPOCH FROM (now() - xact_start)) AS xact_seconds,
                LEFT(query, 500) AS query_preview
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND pid <> pg_backend_pid()
            """
        )
    finally:
        await connection.close()

    database_stats: DatabaseStatRow | None = None
    if db_stat_records:
        row = db_stat_records[0]
        database_stats = DatabaseStatRow(
            datname=_postgres_text(row["datname"]),
            deadlocks=_require_int(row["deadlocks"]),
            conflicts=_require_int(row["conflicts"]),
            temp_files=_require_int(row["temp_files"]),
            temp_bytes=_require_int(row["temp_bytes"]),
            blks_read=_require_int(row["blks_read"]),
            blks_hit=_require_int(row["blks_hit"]),
        )

    return DatabaseSnapshot(
        database=entry.database_name,
        service=entry.service_name,
        statements=[_row_to_statement(record) for record in statement_records],
        user_tables=[
            TableStatRow(
                schemaname=_postgres_text(record["schemaname"]),
                relname=_postgres_text(record["relname"]),
                seq_scan=_require_int(record["seq_scan"]),
                seq_tup_read=_require_int(record["seq_tup_read"]),
                idx_scan=_require_int(record["idx_scan"]),
                idx_tup_fetch=_require_int(record["idx_tup_fetch"]),
                n_live_tup=_require_int(record["n_live_tup"]),
                n_dead_tup=_require_int(record["n_dead_tup"]),
            )
            for record in table_records
        ],
        user_indexes=[
            IndexStatRow(
                schemaname=_postgres_text(record["schemaname"]),
                relname=_postgres_text(record["relname"]),
                indexrelname=_postgres_text(record["indexrelname"]),
                idx_scan=_require_int(record["idx_scan"]),
                idx_tup_read=_require_int(record["idx_tup_read"]),
                idx_tup_fetch=_require_int(record["idx_tup_fetch"]),
            )
            for record in index_records
        ],
        database_stats=database_stats,
        activity=[
            ActivityRow(
                pid=_require_int(record["pid"]),
                state=_postgres_text(record["state"] or ""),
                wait_event_type=_optional_text(record["wait_event_type"]),
                wait_event=_optional_text(record["wait_event"]),
                xact_seconds=_json_float(record["xact_seconds"]),
                query_preview=_postgres_text(record["query_preview"] or ""),
            )
            for record in activity_records
        ],
    )


async def cmd_collect(base_dsn: str, run_id: str) -> Path:
    _assert_test_postgres(base_dsn)
    run_dir = _REPORTS_ROOT / run_id
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    snapshots: list[DatabaseSnapshot] = []
    for entry in _load_service_databases():
        snapshot = await _collect_database(entry, base_dsn)
        snapshots.append(snapshot)
        out_path = raw_dir / f"{entry.service_name}.json"
        out_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    meta = {
        "run_id": run_id,
        "collected_at": datetime.now(tz=UTC).isoformat(),
        "database_count": len(snapshots),
        "pg_stat_statements_scope": "filtered_by_current_database_dbid",
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"db_test_profile: collected {len(snapshots)} databases → {run_dir}")
    return run_dir


def _find_plan_nodes(plan: object, node_type: str) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    if isinstance(plan, dict):
        if plan.get("Node Type") == node_type:
            found.append(plan)
        child = plan.get("Plans")
        if isinstance(child, list):
            for item in child:
                found.extend(_find_plan_nodes(item, node_type))
    return found


def _parse_auto_explain_logs(log_dir: Path) -> list[SeqScanPlan]:
    if not log_dir.is_dir():
        return []
    seq_scans: list[SeqScanPlan] = []
    json_line_pattern = re.compile(r"^\s*(\{.*\})\s*$")
    current_query: str | None = None
    for log_path in sorted(log_dir.glob("*.log*")):
        if not log_path.is_file():
            continue
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "Query Text:" in line:
                current_query = line.split("Query Text:", maxsplit=1)[-1].strip()
                continue
            match = json_line_pattern.match(line)
            if match is None:
                continue
            try:
                payload = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            plan_root = payload.get("Plan") if isinstance(payload, dict) else None
            if plan_root is None:
                continue
            for node in _find_plan_nodes(plan_root, "Seq Scan"):
                relation_name = node.get("Relation Name")
                seq_scans.append(
                    SeqScanPlan(
                        relation=str(relation_name) if relation_name is not None else None,
                        node_type="Seq Scan",
                        actual_rows=_json_int(node.get("Actual Rows")),
                        plan_rows=_json_int(node.get("Plan Rows")),
                        total_cost=_json_float(node.get("Total Cost")),
                        query_text=current_query,
                    )
                )
    return seq_scans


def _top_statements(
    snapshots: list[DatabaseSnapshot],
    *,
    sort_key: Literal["total", "mean", "max", "rows", "calls", "blks", "temp"],
    limit: int,
) -> list[tuple[str, str, StatementRow]]:
    ranked: list[tuple[str, str, StatementRow]] = []
    for snapshot in snapshots:
        for statement in snapshot["statements"]:
            ranked.append((snapshot["service"], snapshot["database"], statement))
    if sort_key == "total":
        ranked.sort(key=lambda item: item[2]["total_exec_time_ms"], reverse=True)
    elif sort_key == "mean":
        ranked.sort(key=lambda item: item[2]["mean_exec_time_ms"], reverse=True)
    elif sort_key == "max":
        ranked.sort(key=lambda item: item[2]["max_exec_time_ms"], reverse=True)
    elif sort_key == "rows":
        ranked.sort(key=lambda item: item[2]["rows"], reverse=True)
    elif sort_key == "calls":
        ranked.sort(key=lambda item: item[2]["calls"], reverse=True)
    elif sort_key == "temp":
        ranked.sort(key=lambda item: item[2]["temp_blks_written"], reverse=True)
    else:
        ranked.sort(key=lambda item: item[2]["shared_blks_read"], reverse=True)
    return ranked[:limit]


def _normalize_query(query: str) -> str:
    normalized = " ".join(query.split())
    if len(normalized) > 200:
        return normalized[:200]
    return normalized


def _statement_to_dict(service: str, database: str, statement: StatementRow) -> dict[str, object]:
    return {
        "service": service,
        "database": database,
        **statement,
    }


def _cluster_rollup_by_query(
    snapshots: list[DatabaseSnapshot],
    limit: int,
) -> list[ClusterRollupRow]:
    aggregated: dict[str, ClusterRollupRow] = {}
    for snapshot in snapshots:
        for statement in snapshot["statements"]:
            query_key = _normalize_query(statement["query"])
            existing = aggregated.get(query_key)
            if existing is None:
                aggregated[query_key] = ClusterRollupRow(
                    query_key=query_key,
                    query=statement["query"],
                    services=[snapshot["service"]],
                    calls=statement["calls"],
                    total_exec_time_ms=statement["total_exec_time_ms"],
                    mean_exec_time_ms=statement["mean_exec_time_ms"],
                    max_exec_time_ms=statement["max_exec_time_ms"],
                    rows=statement["rows"],
                    temp_blks_written=statement["temp_blks_written"],
                    shared_blks_read=statement["shared_blks_read"],
                )
                continue
            if snapshot["service"] not in existing["services"]:
                existing["services"].append(snapshot["service"])
            existing["calls"] += statement["calls"]
            existing["total_exec_time_ms"] += statement["total_exec_time_ms"]
            existing["rows"] += statement["rows"]
            existing["temp_blks_written"] += statement["temp_blks_written"]
            existing["shared_blks_read"] += statement["shared_blks_read"]
            if statement["max_exec_time_ms"] > existing["max_exec_time_ms"]:
                existing["max_exec_time_ms"] = statement["max_exec_time_ms"]
            if existing["calls"] > 0:
                existing["mean_exec_time_ms"] = existing["total_exec_time_ms"] / existing["calls"]
    ranked = sorted(
        aggregated.values(),
        key=lambda row: row["total_exec_time_ms"],
        reverse=True,
    )
    return ranked[:limit]


def _cache_hit_by_service(snapshots: list[DatabaseSnapshot]) -> list[CacheHitRow]:
    rows: list[CacheHitRow] = []
    for snapshot in snapshots:
        stats = snapshot["database_stats"]
        if stats is None:
            continue
        blks_hit = stats["blks_hit"]
        blks_read = stats["blks_read"]
        total = blks_hit + blks_read
        ratio = (blks_hit / total * 100.0) if total > 0 else 100.0
        rows.append(
            CacheHitRow(
                service=snapshot["service"],
                database=snapshot["database"],
                cache_hit_ratio_pct=round(ratio, 2),
                blks_hit=blks_hit,
                blks_read=blks_read,
            )
        )
    rows.sort(key=lambda row: row["cache_hit_ratio_pct"])
    return rows


def _top_dead_tup_tables(
    snapshots: list[DatabaseSnapshot],
    limit: int,
) -> list[DeadTupTableRow]:
    flagged: list[DeadTupTableRow] = []
    for snapshot in snapshots:
        for table in snapshot["user_tables"]:
            if table["n_dead_tup"] == 0:
                continue
            live = table["n_live_tup"]
            if live == 0:
                ratio = 100.0 if table["n_dead_tup"] > 0 else 0.0
            else:
                ratio = table["n_dead_tup"] / live * 100.0
            flagged.append(
                DeadTupTableRow(
                    service=snapshot["service"],
                    database=snapshot["database"],
                    schemaname=table["schemaname"],
                    relname=table["relname"],
                    n_live_tup=live,
                    n_dead_tup=table["n_dead_tup"],
                    dead_ratio_pct=round(ratio, 2),
                )
            )
    flagged.sort(key=lambda row: row["n_dead_tup"], reverse=True)
    return flagged[:limit]


def _load_previous_summary(current_run_id: str) -> dict[str, object] | None:
    latest_link = _REPORTS_ROOT / "latest"
    if not latest_link.is_symlink():
        return None
    previous_run_dir = latest_link.resolve()
    if previous_run_dir.name == current_run_id:
        return None
    summary_path = previous_run_dir / "summary.json"
    if not summary_path.is_file():
        return None
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid previous summary.json: {summary_path}")
    return payload


def _rollup_index_by_query_key(summary: dict[str, object]) -> dict[str, ClusterRollupRow]:
    rollup_rows = summary.get("cluster_rollup_by_query")
    if not isinstance(rollup_rows, list):
        return {}
    indexed: dict[str, ClusterRollupRow] = {}
    for row in rollup_rows:
        if not isinstance(row, dict):
            continue
        query_key = row.get("query_key")
        if not isinstance(query_key, str):
            continue
        indexed[query_key] = ClusterRollupRow(
            query_key=query_key,
            query=str(row.get("query", "")),
            services=[str(item) for item in row.get("services", []) if isinstance(item, str)],
            calls=_require_int(row.get("calls")),
            total_exec_time_ms=_require_float(row.get("total_exec_time_ms")),
            mean_exec_time_ms=_require_float(row.get("mean_exec_time_ms")),
            max_exec_time_ms=_require_float(row.get("max_exec_time_ms")),
            rows=_require_int(row.get("rows")),
            temp_blks_written=_require_int(row.get("temp_blks_written")),
            shared_blks_read=_require_int(row.get("shared_blks_read")),
        )
    return indexed


def _build_delta_vs_previous(
    current: dict[str, object],
    previous: dict[str, object] | None,
) -> DeltaVsPrevious:
    if previous is None:
        return DeltaVsPrevious(
            has_previous=False,
            previous_run_id=None,
            total_exec_time_ms_delta=None,
            total_calls_delta=None,
            slow_query_count_total_delta=None,
            query_deltas=[],
        )
    previous_run_id = previous.get("run_id")
    if not isinstance(previous_run_id, str):
        previous_run_id = None
    current_total_exec = _require_float(current.get("total_exec_time_ms"))
    previous_total_exec = _float_or_zero(previous.get("total_exec_time_ms"))
    current_calls = _require_int(current.get("total_calls"))
    previous_calls = _int_or_zero(previous.get("total_calls"))
    current_slow = _require_int(current.get("slow_query_count_total"))
    previous_slow = _int_or_zero(previous.get("slow_query_count_total"))
    current_rollup = _rollup_index_by_query_key(current)
    previous_rollup = _rollup_index_by_query_key(previous)
    query_deltas: list[DeltaQueryRow] = []
    for query_key, current_row in current_rollup.items():
        previous_row = previous_rollup.get(query_key)
        if previous_row is None:
            continue
        calls_delta = current_row["calls"] - previous_row["calls"]
        exec_delta = current_row["total_exec_time_ms"] - previous_row["total_exec_time_ms"]
        if previous_row["calls"] == 0:
            pct_change: float | None = None
        else:
            pct_change = round(calls_delta / previous_row["calls"] * 100.0, 1)
        query_deltas.append(
            DeltaQueryRow(
                query_key=query_key,
                query=current_row["query"],
                calls=current_row["calls"],
                calls_delta=calls_delta,
                total_exec_time_ms=current_row["total_exec_time_ms"],
                total_exec_ms_delta=round(exec_delta, 3),
                calls_pct_change=pct_change,
            )
        )
    query_deltas.sort(key=lambda row: abs(row["total_exec_ms_delta"]), reverse=True)
    return DeltaVsPrevious(
        has_previous=True,
        previous_run_id=previous_run_id,
        total_exec_time_ms_delta=round(current_total_exec - previous_total_exec, 3),
        total_calls_delta=current_calls - previous_calls,
        slow_query_count_total_delta=current_slow - previous_slow,
        query_deltas=query_deltas[:_TERMINAL_TOP_N],
    )


def _seq_scan_tables(snapshots: list[DatabaseSnapshot]) -> list[tuple[str, str, TableStatRow]]:
    flagged: list[tuple[str, str, TableStatRow]] = []
    for snapshot in snapshots:
        for table in snapshot["user_tables"]:
            if table["n_live_tup"] < _SEQ_SCAN_TABLE_MIN_ROWS:
                continue
            if table["seq_scan"] <= table["idx_scan"]:
                continue
            if table["seq_scan"] == 0:
                continue
            flagged.append((snapshot["service"], snapshot["database"], table))
    flagged.sort(key=lambda item: item[2]["seq_tup_read"], reverse=True)
    return flagged[:_TOP_N]


def _unused_indexes(snapshots: list[DatabaseSnapshot]) -> list[tuple[str, str, IndexStatRow]]:
    unused: list[tuple[str, str, IndexStatRow]] = []
    table_seq_scan: dict[tuple[str, str], int] = {}
    for snapshot in snapshots:
        for table in snapshot["user_tables"]:
            table_seq_scan[(snapshot["database"], table["relname"])] = table["seq_scan"]
    for snapshot in snapshots:
        for index in snapshot["user_indexes"]:
            if index["idx_scan"] != 0:
                continue
            seq_scans = table_seq_scan.get((snapshot["database"], index["relname"]), 0)
            if seq_scans < 10:
                continue
            unused.append((snapshot["service"], snapshot["database"], index))
    return unused[:_TOP_N]


def _build_summary(snapshots: list[DatabaseSnapshot], seq_scans: list[SeqScanPlan]) -> dict[str, object]:
    total_exec_ms = sum(
        statement["total_exec_time_ms"]
        for snapshot in snapshots
        for statement in snapshot["statements"]
    )
    total_calls = sum(
        statement["calls"]
        for snapshot in snapshots
        for statement in snapshot["statements"]
    )
    statement_count = sum(len(snapshot["statements"]) for snapshot in snapshots)
    total_temp_blks = sum(
        statement["temp_blks_written"]
        for snapshot in snapshots
        for statement in snapshot["statements"]
    )
    slow_by_mean = [
        item
        for item in _top_statements(snapshots, sort_key="mean", limit=10_000)
        if item[2]["mean_exec_time_ms"] >= _SLOW_MEAN_MS
    ]
    slow_by_total = [
        item
        for item in _top_statements(snapshots, sort_key="total", limit=10_000)
        if item[2]["total_exec_time_ms"] >= _SLOW_TOTAL_MS
    ]
    per_db_time: dict[str, float] = {}
    for snapshot in snapshots:
        per_db_time[snapshot["service"]] = sum(
            statement["total_exec_time_ms"] for statement in snapshot["statements"]
        )
    top_dbs = sorted(per_db_time.items(), key=lambda item: item[1], reverse=True)
    idle_in_tx = sum(
        1
        for snapshot in snapshots
        for activity in snapshot["activity"]
        if activity["state"] == "idle in transaction"
    )
    deadlocks = sum(
        snapshot["database_stats"]["deadlocks"]
        for snapshot in snapshots
        if snapshot["database_stats"] is not None
    )
    cache_hits = _cache_hit_by_service(snapshots)
    cluster_rollup = _cluster_rollup_by_query(snapshots, _TOP_N)
    low_stats = total_exec_ms < _EMPTY_TOTAL_EXEC_MS or total_calls < _EMPTY_TOTAL_CALLS
    return {
        "total_exec_time_ms": total_exec_ms,
        "total_calls": total_calls,
        "statement_count": statement_count,
        "total_temp_blks_written": total_temp_blks,
        "top_databases_by_exec_ms": [
            {"service": name, "total_exec_time_ms": ms} for name, ms in top_dbs[:10]
        ],
        "cache_hit_by_service": cache_hits,
        "slow_query_count_mean": len(slow_by_mean),
        "slow_query_count_total": len(slow_by_total),
        "seq_scan_table_count": len(_seq_scan_tables(snapshots)),
        "auto_explain_seq_scan_count": len(seq_scans),
        "idle_in_transaction_sessions": idle_in_tx,
        "deadlocks": deadlocks,
        "low_activity_warning": low_stats,
        "thresholds": {
            "slow_mean_ms": _SLOW_MEAN_MS,
            "slow_total_ms": _SLOW_TOTAL_MS,
            "heavy_rows": _HEAVY_ROWS,
            "top_n": _TOP_N,
            "terminal_top_n": _TERMINAL_TOP_N,
            "unconditional_top_n": _UNCONDITIONAL_TOP_N,
        },
        "pg_stat_statements_scope": "filtered_by_current_database_dbid",
        "profile_scope": "pytest_phase_1_not_integration",
        "top_by_total": [
            _statement_to_dict(service, database, statement)
            for service, database, statement in _top_statements(
                snapshots, sort_key="total", limit=_UNCONDITIONAL_TOP_N
            )
        ],
        "top_by_max": [
            _statement_to_dict(service, database, statement)
            for service, database, statement in _top_statements(
                snapshots, sort_key="max", limit=_UNCONDITIONAL_TOP_N
            )
        ],
        "top_by_temp_blks": [
            _statement_to_dict(service, database, statement)
            for service, database, statement in _top_statements(
                snapshots, sort_key="temp", limit=_UNCONDITIONAL_TOP_N
            )
        ],
        "top_by_shared_blks_read": [
            _statement_to_dict(service, database, statement)
            for service, database, statement in _top_statements(
                snapshots, sort_key="blks", limit=_UNCONDITIONAL_TOP_N
            )
        ],
        "cluster_rollup_by_query": cluster_rollup,
        "top_dead_tup_tables": _top_dead_tup_tables(snapshots, _UNCONDITIONAL_TOP_N),
        "top_slow_by_total": [
            _statement_to_dict(service, database, statement)
            for service, database, statement in _top_statements(snapshots, sort_key="total", limit=_TOP_N)
            if statement["total_exec_time_ms"] >= _SLOW_TOTAL_MS
        ],
        "top_slow_by_mean": [
            _statement_to_dict(service, database, statement)
            for service, database, statement in _top_statements(snapshots, sort_key="mean", limit=_TOP_N)
            if statement["mean_exec_time_ms"] >= _SLOW_MEAN_MS
        ],
        "top_heavy_by_rows": [
            _statement_to_dict(service, database, statement)
            for service, database, statement in _top_statements(snapshots, sort_key="rows", limit=_TOP_N)
            if statement["rows"] >= _HEAVY_ROWS
        ],
        "top_chatty": [
            _statement_to_dict(service, database, statement)
            for service, database, statement in _top_statements(snapshots, sort_key="calls", limit=_TOP_N)
            if statement["calls"] >= _MIN_CALLS_FOR_CHATTY
        ],
        "seq_scan_tables": [
            {"service": service, "database": database, **table}
            for service, database, table in _seq_scan_tables(snapshots)
        ],
        "unused_indexes": [
            {"service": service, "database": database, **index}
            for service, database, index in _unused_indexes(snapshots)
        ],
        "auto_explain_seq_scans": seq_scans[: _TOP_N],
    }


def _format_duration_ms(ms: float) -> str:
    if ms >= 1000.0:
        return f"{ms / 1000.0:.1f}s"
    return f"{ms:.0f}ms"


def _format_int(value: int) -> str:
    return f"{value:,}"


def _truncate_text(text: str, width: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= width:
        return normalized
    return normalized[: width - 3] + "..."


def _terminal_use_unicode_box() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return True


def _mini_bar(value: float, max_value: float, width: int = 16) -> str:
    if max_value <= 0:
        fill_char = "#" if not _terminal_use_unicode_box() else "░"
        return fill_char * width
    filled = min(width, int(value / max_value * width))
    if _terminal_use_unicode_box():
        return ("█" * filled) + ("░" * (width - filled))
    return ("#" * filled) + ("." * (width - filled))


def _box_line(text: str, width: int, *, unicode_box: bool) -> str:
    inner_width = width - 2
    padded = text[:inner_width].ljust(inner_width)
    if unicode_box:
        return f"║ {padded} ║"
    return f"| {padded} |"


def _render_terminal(summary: dict[str, object]) -> str:
    unicode_box = _terminal_use_unicode_box()
    width = 72
    if unicode_box:
        top = "╔" + "═" * (width - 2) + "╗"
        mid = "╠" + "═" * (width - 2) + "╣"
        bottom = "╚" + "═" * (width - 2) + "╝"
    else:
        top = "+" + "-" * (width - 2) + "+"
        mid = "+" + "-" * (width - 2) + "+"
        bottom = "+" + "-" * (width - 2) + "+"

    run_id = str(summary.get("run_id", ""))
    total_exec = _require_float(summary.get("total_exec_time_ms"))
    total_calls = _require_int(summary.get("total_calls"))
    slow_total = _require_int(summary.get("slow_query_count_total"))
    temp_blks = _require_int(summary.get("total_temp_blks_written"))
    deadlocks = _require_int(summary.get("deadlocks"))
    cache_hits = summary.get("cache_hit_by_service")
    avg_cache_hit = 100.0
    if isinstance(cache_hits, list) and cache_hits:
        ratios: list[float] = []
        for row in cache_hits:
            if isinstance(row, dict):
                ratios.append(_require_float(row.get("cache_hit_ratio_pct")))
        if ratios:
            avg_cache_hit = sum(ratios) / len(ratios)

    lines: list[str] = [
        top,
        _box_line(f"DB test profile  run={run_id}", width, unicode_box=unicode_box),
        mid,
        _box_line(
            f"total exec {_format_duration_ms(total_exec):>8}  calls {_format_int(total_calls):>10}",
            width,
            unicode_box=unicode_box,
        ),
        _box_line(
            f"slow(total) {slow_total:>8}  cache hit {avg_cache_hit:>5.1f}%",
            width,
            unicode_box=unicode_box,
        ),
        _box_line(
            f"temp blks {_format_int(temp_blks):>10}  deadlocks {deadlocks:>8}",
            width,
            unicode_box=unicode_box,
        ),
        bottom,
        "",
    ]

    if summary.get("low_activity_warning"):
        lines.extend(
            [
                "WARNING: very low pg_stat activity for phase 1 snapshot.",
                "         Check lint/test did not abort early; integration tests are excluded.",
                "",
            ]
        )

    delta = summary.get("delta_vs_previous")
    if isinstance(delta, dict) and delta.get("has_previous"):
        prev_run = delta.get("previous_run_id")
        exec_delta = delta.get("total_exec_time_ms_delta")
        calls_delta = delta.get("total_calls_delta")
        lines.append(f"Delta vs previous run {prev_run}:")
        if isinstance(exec_delta, (int, float)):
            sign = "+" if exec_delta >= 0 else ""
            lines.append(f"  total exec {sign}{_format_duration_ms(float(exec_delta))}")
        if isinstance(calls_delta, int):
            sign = "+" if calls_delta >= 0 else ""
            lines.append(f"  total calls {sign}{_format_int(calls_delta)}")
        lines.append("")

    top_dbs = summary.get("top_databases_by_exec_ms")
    if isinstance(top_dbs, list) and top_dbs:
        lines.append("Top databases by exec time")
        max_ms = max(
            _require_float(item["total_exec_time_ms"])
            for item in top_dbs
            if isinstance(item, dict)
        )
        for item in top_dbs[:5]:
            if not isinstance(item, dict):
                continue
            service = str(item.get("service", ""))
            exec_ms = _require_float(item.get("total_exec_time_ms"))
            bar = _mini_bar(exec_ms, max_ms)
            lines.append(
                f"  {service:<12} {_format_duration_ms(exec_ms):>8}  {bar}"
            )
        lines.append("")

    rollup = summary.get("cluster_rollup_by_query")
    if isinstance(rollup, list) and rollup:
        lines.append("Top queries by total time (cluster rollup)")
        header = f"  {'query':<44} {'calls':>8} {'total':>8} {'delta':>8}"
        lines.append(header)
        delta_index: dict[str, DeltaQueryRow] = {}
        if isinstance(delta, dict):
            query_deltas = delta.get("query_deltas")
            if isinstance(query_deltas, list):
                for item in query_deltas:
                    if isinstance(item, dict):
                        query_key = item.get("query_key")
                        if isinstance(query_key, str):
                            delta_index[query_key] = DeltaQueryRow(
                                query_key=query_key,
                                query=str(item.get("query", "")),
                                calls=_require_int(item.get("calls")),
                                calls_delta=_require_int(item.get("calls_delta")),
                                total_exec_time_ms=_require_float(item.get("total_exec_time_ms")),
                                total_exec_ms_delta=_require_float(item.get("total_exec_ms_delta")),
                                calls_pct_change=_json_float(item.get("calls_pct_change")),
                            )
        for row in rollup[:_TERMINAL_TOP_N]:
            if not isinstance(row, dict):
                continue
            query_key = str(row.get("query_key", ""))
            query_text = _truncate_text(str(row.get("query", "")), 44)
            calls = _require_int(row.get("calls"))
            total_ms = _require_float(row.get("total_exec_time_ms"))
            delta_row = delta_index.get(query_key)
            if delta_row is None or delta_row["calls_pct_change"] is None:
                delta_label = "   n/a"
            else:
                pct = delta_row["calls_pct_change"]
                sign = "+" if pct >= 0 else ""
                delta_label = f"{sign}{pct:.0f}%"
            below = " *" if total_ms < _SLOW_TOTAL_MS else ""
            lines.append(
                f"  {query_text:<44} {_format_int(calls):>8} "
                f"{_format_duration_ms(total_ms):>8} {delta_label:>8}{below}"
            )
        if slow_total == 0:
            lines.append(
                f"  * below slow threshold ({_format_duration_ms(_SLOW_TOTAL_MS)} total)"
            )
        lines.append("")

    def append_statement_section(title: str, rows_key: str, metric_key: str) -> None:
        rows = summary.get(rows_key)
        if not isinstance(rows, list) or not rows:
            return
        lines.append(title)
        for row in rows[:5]:
            if not isinstance(row, dict):
                continue
            service = str(row.get("service", ""))
            query_text = _truncate_text(str(row.get("query", "")), 36)
            metric_value = _require_float(row.get(metric_key))
            if metric_key == "max_exec_time_ms":
                metric_label = _format_duration_ms(metric_value)
            elif metric_key == "temp_blks_written":
                metric_label = _format_int(int(metric_value))
            else:
                metric_label = _format_int(int(metric_value))
            lines.append(f"  {service:<10} {metric_label:>10}  {query_text}")
        lines.append("")

    append_statement_section("Top by max latency", "top_by_max", "max_exec_time_ms")
    append_statement_section("Top by temp blks written", "top_by_temp_blks", "temp_blks_written")
    append_statement_section("Top by shared blks read", "top_by_shared_blks_read", "shared_blks_read")

    seq_count = _require_int(summary.get("seq_scan_table_count"))
    auto_count = _require_int(summary.get("auto_explain_seq_scan_count"))
    if seq_count > 0 or auto_count > 0:
        lines.append(f"Seq-scan tables: {seq_count}; auto_explain seq scans: {auto_count}")
        lines.append("")

    lines.append("Scope: pytest phase 1 only (not integration/network).")
    lines.append("HTML: reports/db_test_profile/latest/report.html")
    return "\n".join(lines)


def _render_html(summary: dict[str, object], run_id: str) -> str:
    def esc(value: object) -> str:
        return html.escape(str(value))

    sections: list[str] = []
    sections.append("<h1>DB test profile</h1>")
    sections.append(f"<p>Run: <code>{esc(run_id)}</code></p>")
    sections.append(
        "<p><em>pg_stat_statements filtered by current database dbid (not cluster-wide). "
        "Snapshot scope: pytest phase 1 only.</em></p>"
    )

    if summary.get("low_activity_warning"):
        sections.append(
            "<p><strong>Warning:</strong> very low pg_stat activity — phase 1 may have aborted "
            "early or integration load is excluded from this snapshot.</p>"
        )

    sections.append("<h2>Summary</h2><ul>")
    for key in (
        "total_exec_time_ms",
        "total_calls",
        "statement_count",
        "total_temp_blks_written",
        "slow_query_count_mean",
        "slow_query_count_total",
        "seq_scan_table_count",
        "auto_explain_seq_scan_count",
        "idle_in_transaction_sessions",
        "deadlocks",
    ):
        sections.append(f"<li>{esc(key)}: {esc(summary.get(key, ''))}</li>")
    sections.append("</ul>")

    cache_hits = summary.get("cache_hit_by_service")
    if isinstance(cache_hits, list) and cache_hits:
        sections.append("<h2>Cache hit by database</h2><table border='1' cellpadding='4'>")
        sections.append("<tr><th>service</th><th>cache_hit_ratio_pct</th><th>blks_hit</th><th>blks_read</th></tr>")
        for row in cache_hits:
            if not isinstance(row, dict):
                continue
            sections.append(
                "<tr>"
                f"<td>{esc(row.get('service'))}</td>"
                f"<td>{esc(row.get('cache_hit_ratio_pct'))}</td>"
                f"<td>{esc(row.get('blks_hit'))}</td>"
                f"<td>{esc(row.get('blks_read'))}</td>"
                "</tr>"
            )
        sections.append("</table>")

    top_dbs = summary.get("top_databases_by_exec_ms")
    if isinstance(top_dbs, list) and top_dbs:
        sections.append("<h2>Top databases by exec time</h2><ol>")
        for item in top_dbs:
            if isinstance(item, dict):
                sections.append(
                    f"<li>{esc(item.get('service'))}: {esc(item.get('total_exec_time_ms'))} ms</li>"
                )
        sections.append("</ol>")

    delta = summary.get("delta_vs_previous")
    if isinstance(delta, dict) and delta.get("has_previous"):
        sections.append("<h2>Delta vs previous run</h2><ul>")
        sections.append(f"<li>previous_run_id: {esc(delta.get('previous_run_id'))}</li>")
        sections.append(f"<li>total_exec_time_ms_delta: {esc(delta.get('total_exec_time_ms_delta'))}</li>")
        sections.append(f"<li>total_calls_delta: {esc(delta.get('total_calls_delta'))}</li>")
        sections.append(
            f"<li>slow_query_count_total_delta: {esc(delta.get('slow_query_count_total_delta'))}</li>"
        )
        sections.append("</ul>")
        query_deltas = delta.get("query_deltas")
        if isinstance(query_deltas, list) and query_deltas:
            sections.append("<table border='1' cellpadding='4'>")
            sections.append(
                "<tr><th>query</th><th>calls</th><th>calls_delta</th>"
                "<th>total_ms</th><th>total_ms_delta</th><th>calls_pct_change</th></tr>"
            )
            for row in query_deltas:
                if not isinstance(row, dict):
                    continue
                query = str(row.get("query", ""))
                if len(query) > 300:
                    query = query[:300] + "..."
                sections.append(
                    "<tr>"
                    f"<td><pre>{esc(query)}</pre></td>"
                    f"<td>{esc(row.get('calls'))}</td>"
                    f"<td>{esc(row.get('calls_delta'))}</td>"
                    f"<td>{esc(row.get('total_exec_time_ms'))}</td>"
                    f"<td>{esc(row.get('total_exec_ms_delta'))}</td>"
                    f"<td>{esc(row.get('calls_pct_change'))}</td>"
                    "</tr>"
                )
            sections.append("</table>")

    def render_statement_table(title: str, rows_key: str, extra_columns: tuple[str, ...] = ()) -> None:
        rows = summary.get(rows_key)
        if not isinstance(rows, list) or not rows:
            return
        sections.append(f"<h2>{esc(title)}</h2>")
        header = (
            "<th>service</th><th>calls</th><th>total_ms</th><th>mean_ms</th>"
            "<th>max_ms</th><th>rows</th><th>temp_blks</th><th>shared_blks_read</th><th>query</th>"
        )
        for column in extra_columns:
            header += f"<th>{esc(column)}</th>"
        sections.append(f"<table border='1' cellpadding='4'><tr>{header}</tr>")
        for row in rows[:_TOP_N]:
            if not isinstance(row, dict):
                continue
            query = str(row.get("query", ""))
            if len(query) > 300:
                query = query[:300] + "..."
            sections.append(
                "<tr>"
                f"<td>{esc(row.get('service'))}</td>"
                f"<td>{esc(row.get('calls'))}</td>"
                f"<td>{esc(row.get('total_exec_time_ms'))}</td>"
                f"<td>{esc(row.get('mean_exec_time_ms'))}</td>"
                f"<td>{esc(row.get('max_exec_time_ms'))}</td>"
                f"<td>{esc(row.get('rows'))}</td>"
                f"<td>{esc(row.get('temp_blks_written'))}</td>"
                f"<td>{esc(row.get('shared_blks_read'))}</td>"
                f"<td><pre>{esc(query)}</pre></td>"
                "</tr>"
            )
        sections.append("</table>")

    render_statement_table("Top by total time (unconditional)", "top_by_total")
    cluster_rows = summary.get("cluster_rollup_by_query")
    if isinstance(cluster_rows, list) and cluster_rows:
        sections.append("<h2>Cluster rollup by query</h2>")
        sections.append("<table border='1' cellpadding='4'>")
        sections.append(
            "<tr><th>services</th><th>calls</th><th>total_ms</th><th>mean_ms</th>"
            "<th>max_ms</th><th>temp_blks</th><th>shared_blks_read</th><th>query</th></tr>"
        )
        for row in cluster_rows[:_TOP_N]:
            if not isinstance(row, dict):
                continue
            services = row.get("services")
            service_label = ", ".join(str(item) for item in services) if isinstance(services, list) else ""
            query = str(row.get("query", ""))
            if len(query) > 300:
                query = query[:300] + "..."
            sections.append(
                "<tr>"
                f"<td>{esc(service_label)}</td>"
                f"<td>{esc(row.get('calls'))}</td>"
                f"<td>{esc(row.get('total_exec_time_ms'))}</td>"
                f"<td>{esc(row.get('mean_exec_time_ms'))}</td>"
                f"<td>{esc(row.get('max_exec_time_ms'))}</td>"
                f"<td>{esc(row.get('temp_blks_written'))}</td>"
                f"<td>{esc(row.get('shared_blks_read'))}</td>"
                f"<td><pre>{esc(query)}</pre></td>"
                "</tr>"
            )
        sections.append("</table>")
    render_statement_table("Top by max latency", "top_by_max")
    render_statement_table("Top by temp blks written", "top_by_temp_blks")
    render_statement_table("Top by shared blks read", "top_by_shared_blks_read")
    render_statement_table("Slow by total time (threshold)", "top_slow_by_total")
    render_statement_table("Slow by mean time (threshold)", "top_slow_by_mean")
    render_statement_table("Heavy by rows", "top_heavy_by_rows")
    render_statement_table("Chatty queries", "top_chatty")

    dead_tup = summary.get("top_dead_tup_tables")
    if isinstance(dead_tup, list) and dead_tup:
        sections.append("<h2>Top dead tuples</h2><table border='1' cellpadding='4'>")
        sections.append(
            "<tr><th>service</th><th>table</th><th>n_live_tup</th><th>n_dead_tup</th><th>dead_ratio_pct</th></tr>"
        )
        for row in dead_tup:
            if not isinstance(row, dict):
                continue
            sections.append(
                "<tr>"
                f"<td>{esc(row.get('service'))}</td>"
                f"<td>{esc(row.get('relname'))}</td>"
                f"<td>{esc(row.get('n_live_tup'))}</td>"
                f"<td>{esc(row.get('n_dead_tup'))}</td>"
                f"<td>{esc(row.get('dead_ratio_pct'))}</td>"
                "</tr>"
            )
        sections.append("</table>")

    seq_tables = summary.get("seq_scan_tables")
    if isinstance(seq_tables, list) and seq_tables:
        sections.append("<h2>Tables with seq_scan &gt; idx_scan</h2><table border='1' cellpadding='4'>")
        sections.append(
            "<tr><th>service</th><th>table</th><th>seq_scan</th><th>idx_scan</th><th>n_live_tup</th></tr>"
        )
        for row in seq_tables:
            if not isinstance(row, dict):
                continue
            sections.append(
                "<tr>"
                f"<td>{esc(row.get('service'))}</td>"
                f"<td>{esc(row.get('relname'))}</td>"
                f"<td>{esc(row.get('seq_scan'))}</td>"
                f"<td>{esc(row.get('idx_scan'))}</td>"
                f"<td>{esc(row.get('n_live_tup'))}</td>"
                "</tr>"
            )
        sections.append("</table>")

    auto_scans = summary.get("auto_explain_seq_scans")
    if isinstance(auto_scans, list) and auto_scans:
        sections.append("<h2>auto_explain Seq Scan</h2><ul>")
        for row in auto_scans:
            if not isinstance(row, dict):
                continue
            sections.append(
                "<li>"
                f"<strong>{esc(row.get('relation'))}</strong> "
                f"rows={esc(row.get('actual_rows'))} "
                f"<pre>{esc(row.get('query_text'))}</pre>"
                "</li>"
            )
        sections.append("</ul>")

    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>DB test profile</title></head><body>"
        + "".join(sections)
        + "</body></html>"
    )


def _resolve_run_dir(run_id: str | None) -> Path:
    if run_id is not None:
        run_dir = _REPORTS_ROOT / run_id
        if not run_dir.is_dir():
            raise RuntimeError(f"run dir not found: {run_dir}")
        return run_dir
    latest = _REPORTS_ROOT / "latest"
    if latest.is_symlink() or latest.is_file():
        target = latest.resolve()
        if target.is_dir():
            return target
    candidates = sorted(_REPORTS_ROOT.glob("*"), key=lambda path: path.stat().st_mtime, reverse=True)
    for candidate in candidates:
        if candidate.name == "latest":
            continue
        if candidate.is_dir():
            return candidate
    raise RuntimeError(f"no collect runs under {_REPORTS_ROOT}")


def cmd_report(run_id: str | None) -> Path:
    run_dir = _resolve_run_dir(run_id)
    raw_dir = run_dir / "raw"
    if not raw_dir.is_dir():
        raise RuntimeError(f"missing raw snapshots: {raw_dir}")
    previous_summary = _load_previous_summary(run_dir.name)
    snapshots: list[DatabaseSnapshot] = []
    for path in sorted(raw_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshots.append(DatabaseSnapshot(**payload))
    seq_scans = _parse_auto_explain_logs(_POSTGRES_LOG_DIR)
    summary = _build_summary(snapshots, seq_scans)
    summary["run_id"] = run_dir.name
    summary["delta_vs_previous"] = _build_delta_vs_previous(summary, previous_summary)
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    html_path = run_dir / "report.html"
    html_path.write_text(_render_html(summary, run_dir.name), encoding="utf-8")
    latest_link = _REPORTS_ROOT / "latest"
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    latest_link.symlink_to(run_dir.name)
    print(_render_terminal(summary))
    print(f"db_test_profile: report → {html_path}")
    return html_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Postgres DB profiling for make test (default-on, DB_PROFILE=0 to disable)")
    parser.add_argument(
        "--dsn",
        default=os.environ.get("DB_PROFILE_DSN", _DEFAULT_DSN),
        help="Postgres DSN (host must be test localhost:54322)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("reset", help="Reset pg_stat_statements on all test databases")

    collect_parser = subparsers.add_parser("collect", help="Collect pg_stat snapshots")
    collect_parser.add_argument(
        "--run-id",
        required=True,
        help="Run identifier (e.g. 20260704T201500)",
    )

    report_parser = subparsers.add_parser("report", help="Build summary.json + report.html")
    report_parser.add_argument("--run-id", default=None, help="Run id (default: latest)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    dsn: str = args.dsn

    if args.command == "reset":
        asyncio.run(cmd_reset(dsn))
        return 0
    if args.command == "collect":
        asyncio.run(cmd_collect(dsn, args.run_id))
        return 0
    if args.command == "report":
        _ = cmd_report(args.run_id)
        return 0
    raise RuntimeError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
