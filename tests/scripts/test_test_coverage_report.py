"""Smoke tests for scripts/testing/coverage_report.py."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.testing.coverage_report import (
    _TOP_UNCOVERED_FILES,
    _format_missing_lines,
    _parse_lcov,
    _parse_python_summary,
    _render_html,
    _render_python_files_table,
    _render_terminal,
    cmd_report,
    cmd_reset,
)


def test_reset_creates_run_directory(tmp_path: Path, monkeypatch) -> None:
    reports_root = tmp_path / "coverage"
    monkeypatch.setattr("scripts.testing.coverage_report._REPORTS_ROOT", reports_root)

    run_dir = cmd_reset("20260101T120000", workers="10")

    assert run_dir.is_dir()
    meta_path = run_dir / "meta.json"
    assert meta_path.is_file()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["run_id"] == "20260101T120000"
    assert meta["workers"] == "10"


def test_parse_lcov_aggregates_totals() -> None:
    lcov_text = "\n".join(
        [
            "SF:core/frontend/static/lib/events/bus.js",
            "LF:10",
            "LH:8",
            "BRF:4",
            "BRH:3",
            "end_of_record",
            "SF:core/frontend/static/lib/events/http.js",
            "LF:20",
            "LH:15",
            "BRF:6",
            "BRH:4",
            "end_of_record",
        ]
    )
    lcov_path = Path("/tmp/test_coverage_lcov.info")
    lcov_path.write_text(lcov_text, encoding="utf-8")
    try:
        totals = _parse_lcov(lcov_path)
    finally:
        lcov_path.unlink(missing_ok=True)

    assert totals["lines_covered"] == 23
    assert totals["lines_total"] == 30
    assert totals["lines_pct"] == 76.67
    assert totals["branches_covered"] == 7
    assert totals["branches_total"] == 10


def test_format_missing_lines_collapses_ranges() -> None:
    assert _format_missing_lines([]) == ""
    assert _format_missing_lines([3]) == "3"
    assert _format_missing_lines([1, 2, 3, 7, 9, 10]) == "1-3, 7, 9-10"


def test_report_generates_html_and_terminal(tmp_path: Path, monkeypatch) -> None:
    reports_root = tmp_path / "coverage"
    monkeypatch.setattr("scripts.testing.coverage_report._REPORTS_ROOT", reports_root)

    run_id = "20260101T130000"
    run_dir = cmd_reset(run_id, workers="5")

    python_summary = {
        "totals": {
            "covered_lines": 80,
            "num_statements": 100,
            "covered_branches": 10,
            "num_branches": 20,
        },
        "files": {
            "apps/flows/main.py": {
                "summary": {"covered_lines": 40, "num_statements": 50},
                "missing_lines": [41, 42, 43, 50],
            },
            "core/db/database.py": {
                "summary": {"covered_lines": 40, "num_statements": 50},
                "missing_lines": [10],
            },
        },
    }
    python_dir = run_dir / "python"
    python_dir.mkdir(parents=True, exist_ok=True)
    (python_dir / "summary.json").write_text(
        json.dumps(python_summary),
        encoding="utf-8",
    )

    js_dir = run_dir / "js"
    js_dir.mkdir(parents=True, exist_ok=True)
    (js_dir / "lcov.info").write_text(
        "LF:10\nLH:9\nBRF:2\nBRH:1\n",
        encoding="utf-8",
    )
    (js_dir / "index.html").write_text("<html><body>js</body></html>", encoding="utf-8")

    report_path = cmd_report(run_id)

    assert report_path.is_file()
    summary_path = run_dir / "summary.json"
    assert summary_path.is_file()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["python"]["lines_pct"] == 80.0
    assert summary["js"]["lines_pct"] == 90.0
    assert len(summary["python_files_low"]) == 2

    terminal = _render_terminal(summary)
    assert "=== Test coverage ===" in terminal
    assert "Python (apps+core):" in terminal
    assert "JS (core/frontend unit):" in terminal
    assert "Top 2 uncovered Python files" in terminal
    assert "apps/flows/main.py" in terminal
    assert "41-43, 50" in terminal
    assert "Python packages" not in terminal

    html_text = _render_html(summary, run_dir=run_dir)
    assert "Test coverage report" in html_text
    assert "Top 2 uncovered Python files" in html_text
    assert "apps/flows/main.py" in html_text


def test_parse_python_summary_returns_top_uncovered_files() -> None:
    summary_path = Path("/tmp/test_python_coverage_summary.json")
    files: dict[str, object] = {
        "apps/flows/a.py": {
            "summary": {"covered_lines": 1, "num_statements": 5},
            "missing_lines": [2, 3, 4, 5],
        },
        "apps/crm/b.py": {
            "summary": {"covered_lines": 4, "num_statements": 5},
            "missing_lines": [5],
        },
        "apps/frontend/c.py": {
            "summary": {"covered_lines": 91, "num_statements": 100},
            "missing_lines": [1, 2, 3, 4, 5, 6, 7, 8, 9],
        },
    }
    for index in range(_TOP_UNCOVERED_FILES + 5):
        covered = 50 + index
        files[f"apps/extra/file_{index:02d}.py"] = {
            "summary": {"covered_lines": covered, "num_statements": 100},
            "missing_lines": list(range(1, 100 - covered + 1)),
        }
    payload = {
        "totals": {"covered_lines": 96, "num_statements": 110},
        "files": files,
    }
    summary_path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        totals, low_packages, low_files = _parse_python_summary(summary_path)
    finally:
        summary_path.unlink(missing_ok=True)

    assert totals["lines_pct"] == 87.27
    assert low_packages[0]["package"] == "apps.flows"
    assert low_packages[0]["lines_pct"] == 20.0
    assert len(low_files) == _TOP_UNCOVERED_FILES
    assert low_files[0]["path"] == "apps/flows/a.py"
    assert low_files[0]["lines_pct"] == 20.0
    file_paths = [row["path"] for row in low_files]
    assert file_paths[0] == "apps/flows/a.py"
    assert "apps/frontend/c.py" not in file_paths
    assert all(
        low_files[index]["lines_pct"] <= low_files[index + 1]["lines_pct"]
        for index in range(len(low_files) - 1)
    )

    table = _render_python_files_table(low_files)
    assert f"Top {_TOP_UNCOVERED_FILES} uncovered Python files" in table
    assert "apps/flows/a.py" in table
    assert "apps/frontend/c.py" not in table
