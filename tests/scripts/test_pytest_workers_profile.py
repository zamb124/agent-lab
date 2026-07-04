"""Unit tests for pytest_workers_profile issues, delta, terminal and HTML."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.pytest_workers_profile import (
    CollectPayload,
    FailureRow,
    _build_delta,
    _build_issues,
    _build_summary,
    _classify_failure_message,
    _render_html,
    _render_terminal,
)


def _collect_payload(
    *,
    workers: str = "5",
    workers_numeric: int | None = 5,
    exit_code: int = 0,
    stack_manifest: dict[str, object] | None = None,
    junit_failures: list[FailureRow] | None = None,
    failed_nodeids: list[str] | None = None,
    wall_time: float | None = 120.0,
) -> CollectPayload:
    return CollectPayload(
        run_id="20260101T120000",
        collected_at="2026-01-01T12:00:00+00:00",
        pytest_workers=workers,
        pytest_workers_numeric=workers_numeric,
        phase1_exit_code=exit_code,
        max_worker_restart=2,
        phase1_wall_time_seconds=wall_time,
        failed_nodeids=failed_nodeids or [],
        junit_failures=junit_failures or [],
        stack_manifest=stack_manifest,
        xdist_counts={
            "total_phase1_estimate": 100,
            "code_sandbox_estimate": 20,
            "real_taskiq_estimate": 10,
            "parallelizable_estimate": 70,
        },
    )


def test_classify_failure_message_detects_parallelism_patterns() -> None:
    suspect, pattern = _classify_failure_message("TaskiqResultTimeout after 60s")
    assert suspect is True
    assert pattern == "taskiq_timeout"

    suspect, pattern = _classify_failure_message("ServiceClientError: connection refused")
    assert suspect is True
    assert pattern == "service_client_error"

    suspect, pattern = _classify_failure_message("AssertionError: expected 1")
    assert suspect is False
    assert pattern is None


def test_stack_undersized_when_workers_above_baseline_and_scale_low() -> None:
    payload = _collect_payload(
        workers="12",
        workers_numeric=12,
        stack_manifest={"stack_scale_factor": 1.0},
    )
    issues = _build_issues(payload)
    codes = {issue["code"] for issue in issues}
    assert "stack_undersized" in codes


def test_stack_not_undersized_when_scale_matches_workers() -> None:
    payload = _collect_payload(
        workers="12",
        workers_numeric=12,
        stack_manifest={"stack_scale_factor": 1.2},
    )
    issues = _build_issues(payload)
    codes = {issue["code"] for issue in issues}
    assert "stack_undersized" not in codes


def test_phase1_failed_issue_on_nonzero_exit_code() -> None:
    payload = _collect_payload(exit_code=1, failed_nodeids=["tests/foo.py::test_bar"])
    issues = _build_issues(payload)
    assert any(issue["code"] == "phase1_failed" for issue in issues)


def test_likely_parallelism_failure_from_junit_message() -> None:
    payload = _collect_payload(
        exit_code=1,
        junit_failures=[
            FailureRow(
                nodeid="tests/flows/integration/test_x.py::test_y",
                message="ReadTimeout: timed out",
                parallelism_suspect=True,
                suspect_pattern="read_timeout",
            )
        ],
    )
    issues = _build_issues(payload)
    assert any(issue["code"] == "likely_parallelism_failure" for issue in issues)


def test_build_delta_vs_previous_run() -> None:
    current: dict[str, object] = {
        "run_id": "run_b",
        "failed_count": 3,
        "parallelism_suspect_count": 2,
        "phase1_wall_time_seconds": 200.0,
        "issue_count_error": 1,
    }
    previous: dict[str, object] = {
        "run_id": "run_a",
        "failed_count": 5,
        "parallelism_suspect_count": 4,
        "phase1_wall_time_seconds": 240.0,
        "issue_count_error": 2,
    }
    delta = _build_delta(current, previous)
    assert delta["has_previous"] is True
    assert delta["previous_run_id"] == "run_a"
    assert delta["failed_count_delta"] == -2
    assert delta["parallelism_suspect_count_delta"] == -2
    assert delta["phase1_wall_time_seconds_delta"] == pytest.approx(-40.0)


def test_render_terminal_and_html_smoke() -> None:
    payload = _collect_payload(
        exit_code=1,
        failed_nodeids=["tests/foo.py::test_bar"],
        junit_failures=[
            FailureRow(
                nodeid="tests/foo.py::test_bar",
                message="too many connections",
                parallelism_suspect=True,
                suspect_pattern="postgres_connections",
            )
        ],
    )
    summary = _build_summary(payload)
    terminal = _render_terminal(summary)
    assert "Pytest workers profile" in terminal
    assert "WORKERS=5" in terminal
    assert "phase1=FAIL" in terminal

    html = _render_html(summary, "20260101T120000")
    assert "<h1>Pytest workers profile</h1>" in html
    assert "too many connections" in html
    assert "tests/foo.py::test_bar" in html


def test_report_writes_summary_and_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import pytest_workers_profile as module

    reports_root = tmp_path / "reports" / "pytest_workers_profile"
    run_id = "20260101T120000"
    run_dir = reports_root / run_id
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True)
    payload = _collect_payload()
    _ = (raw_dir / "phase1.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_REPORTS_ROOT", reports_root)

    _ = module.cmd_report(run_id)
    assert (run_dir / "summary.json").is_file()
    assert (run_dir / "report.html").is_file()
    assert (reports_root / "latest").is_symlink()
