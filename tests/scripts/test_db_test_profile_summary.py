"""Unit tests for db_test_profile summary, rollup, terminal, delta."""

from __future__ import annotations

import pytest

from scripts.testing.db_profile import (
    DatabaseSnapshot,
    StatementRow,
    _build_delta_vs_previous,
    _build_summary,
    _cluster_rollup_by_query,
    _normalize_query,
    _render_terminal,
)


def _statement(
    query: str,
    *,
    queryid: str = "1",
    calls: int = 10,
    total_exec_time_ms: float = 100.0,
    mean_exec_time_ms: float = 10.0,
    max_exec_time_ms: float = 20.0,
    rows: int = 50,
    temp_blks_written: int = 0,
    shared_blks_read: int = 1,
) -> StatementRow:
    return StatementRow(
        queryid=queryid,
        query=query,
        calls=calls,
        total_exec_time_ms=total_exec_time_ms,
        mean_exec_time_ms=mean_exec_time_ms,
        max_exec_time_ms=max_exec_time_ms,
        rows=rows,
        shared_blks_hit=100,
        shared_blks_read=shared_blks_read,
        temp_blks_written=temp_blks_written,
    )


def _snapshot(service: str, database: str, statements: list[StatementRow]) -> DatabaseSnapshot:
    return DatabaseSnapshot(
        database=database,
        service=service,
        statements=statements,
        user_tables=[],
        user_indexes=[],
        database_stats={
            "datname": database,
            "deadlocks": 0,
            "conflicts": 0,
            "temp_files": 0,
            "temp_bytes": 0,
            "blks_read": 10,
            "blks_hit": 990,
        },
        activity=[],
    )


def test_normalize_query_collapses_whitespace_and_truncates() -> None:
    long_query = "SELECT   foo\nFROM   bar   " + ("x" * 300)
    normalized = _normalize_query(long_query)
    assert "  " not in normalized
    assert len(normalized) == 200


def test_cluster_rollup_merges_same_query_across_databases() -> None:
    query = "SELECT entity_types.type_id FROM entity_types"
    snapshots = [
        _snapshot("crm", "platform_crm", [_statement(query, calls=100, total_exec_time_ms=1000.0)]),
        _snapshot("flows", "platform_agents", [_statement(query, calls=50, total_exec_time_ms=500.0)]),
    ]
    rollup = _cluster_rollup_by_query(snapshots, limit=10)
    assert len(rollup) == 1
    row = rollup[0]
    assert row["calls"] == 150
    assert row["total_exec_time_ms"] == 1500.0
    assert sorted(row["services"]) == ["crm", "flows"]


def test_build_summary_includes_new_metrics() -> None:
    snapshots = [
        _snapshot(
            "crm",
            "platform_crm",
            [
                _statement(
                    "SELECT slow FROM big_table",
                    calls=200,
                    total_exec_time_ms=6000.0,
                    temp_blks_written=5000,
                )
            ],
        )
    ]
    summary = _build_summary(snapshots, [])
    assert summary["total_calls"] == 200
    assert summary["statement_count"] == 1
    assert summary["total_temp_blks_written"] == 5000
    cache_hits = summary["cache_hit_by_service"]
    assert isinstance(cache_hits, list)
    top_by_total = summary["top_by_total"]
    cluster_rollup = summary["cluster_rollup_by_query"]
    assert isinstance(top_by_total, list)
    assert isinstance(cluster_rollup, list)
    assert len(top_by_total) == 1
    assert len(cluster_rollup) == 1
    assert summary["slow_query_count_total"] == 1


def test_build_delta_vs_previous_computes_query_and_kpi_deltas() -> None:
    query = "SELECT entity_types FROM entity_types"
    current = _build_summary(
        [_snapshot("crm", "platform_crm", [_statement(query, calls=120, total_exec_time_ms=1200.0)])],
        [],
    )
    current["run_id"] = "run_b"
    previous = _build_summary(
        [_snapshot("crm", "platform_crm", [_statement(query, calls=100, total_exec_time_ms=1000.0)])],
        [],
    )
    previous["run_id"] = "run_a"
    delta = _build_delta_vs_previous(current, previous)
    assert delta["has_previous"] is True
    assert delta["previous_run_id"] == "run_a"
    assert delta["total_calls_delta"] == 20
    assert delta["total_exec_time_ms_delta"] == 200.0
    assert len(delta["query_deltas"]) == 1
    assert delta["query_deltas"][0]["calls_delta"] == 20
    assert delta["query_deltas"][0]["calls_pct_change"] == 20.0


def test_build_delta_without_previous_is_empty() -> None:
    current = _build_summary([], [])
    delta = _build_delta_vs_previous(current, None)
    assert delta["has_previous"] is False
    assert delta["query_deltas"] == []


def test_render_terminal_contains_kpi_and_rollup(monkeypatch: pytest.MonkeyPatch) -> None:
    query = "SELECT entity_types FROM entity_types"
    summary = _build_summary(
        [_snapshot("crm", "platform_crm", [_statement(query, calls=10, total_exec_time_ms=100.0)])],
        [],
    )
    summary["run_id"] = "test_run"
    summary["delta_vs_previous"] = _build_delta_vs_previous(summary, None)
    monkeypatch.delenv("NO_COLOR", raising=False)
    rendered = _render_terminal(summary)
    assert "DB test profile" in rendered
    assert "test_run" in rendered
    assert "Top queries by total time" in rendered
    assert "entity_types" in rendered
    assert "reports/db_test_profile/latest/report.html" in rendered


def test_render_terminal_no_color_uses_ascii_box(monkeypatch: pytest.MonkeyPatch) -> None:
    summary = _build_summary([], [])
    summary["run_id"] = "plain_run"
    summary["delta_vs_previous"] = _build_delta_vs_previous(summary, None)
    monkeypatch.setenv("NO_COLOR", "1")
    rendered = _render_terminal(summary)
    assert "╔" not in rendered
    assert "+" in rendered
    assert "WARNING" in rendered
