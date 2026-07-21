"""Запись per-test JSON и сводного SUMMARY.md."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import cast

from tests.ui.perf.models import UiPerfTestReport

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ARTIFACTS_ROOT = _REPO_ROOT / "artifacts" / "ui-perf"
_TOP_PATHS_N = 25
_TOP_TESTS_N = 20


def artifacts_root() -> Path:
    return _ARTIFACTS_ROOT


def safe_nodeid(nodeid: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", nodeid)
    if not cleaned:
        raise ValueError(f"empty safe_nodeid for {nodeid!r}")
    return cleaned[:200]


def report_path(worker_id: str, nodeid: str) -> Path:
    return _ARTIFACTS_ROOT / worker_id / f"{safe_nodeid(nodeid)}.json"


def write_test_report(report: UiPerfTestReport) -> Path:
    path = report_path(report.worker_id, report.nodeid)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    _ = tmp.write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)
    return path


def _load_all_reports() -> list[UiPerfTestReport]:
    if not _ARTIFACTS_ROOT.is_dir():
        return []
    reports: list[UiPerfTestReport] = []
    for path in sorted(_ARTIFACTS_ROOT.glob("*/*.json")):
        if path.name.endswith(".tmp"):
            continue
        payload_raw = cast(object, json.loads(path.read_text(encoding="utf-8")))
        if not isinstance(payload_raw, dict):
            raise ValueError(f"perf report must be object: {path}")
        reports.append(
            UiPerfTestReport.model_validate(cast(dict[str, object], payload_raw))
        )
    return reports


def rebuild_summary() -> Path | None:
    reports = _load_all_reports()
    if not reports:
        return None

    _ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)
    summary_path = _ARTIFACTS_ROOT / "SUMMARY.md"
    lines: list[str] = [
        "# UI E2E perf SUMMARY",
        "",
        f"Tests with metrics: **{len(reports)}**",
        "",
        "## Slowest tests (wall_ms)",
        "",
        "| wall_ms | requests | long_tasks | max_long_ms | nodeid |",
        "|---:|---:|---:|---:|---|",
    ]
    by_wall = sorted(reports, key=lambda item: item.wall_ms, reverse=True)
    for item in by_wall[:_TOP_TESTS_N]:
        row = (
            f"| {item.wall_ms:.0f} | {item.request_count} | {item.long_task_count} "
            f"| {item.long_task_max_ms:.0f} | `{item.nodeid}` |"
        )
        lines.append(row)

    path_durations: dict[str, list[float]] = {}
    path_counts: dict[str, int] = {}
    for report in reports:
        for req in report.requests:
            if req.duration_ms is None:
                continue
            key = f"{req.method} {req.path}"
            path_durations.setdefault(key, []).append(req.duration_ms)
            path_counts[key] = path_counts.get(key, 0) + 1

    lines.extend(
        [
            "",
            "## Slowest API paths (avg duration_ms)",
            "",
            "| avg_ms | max_ms | count | path |",
            "|---:|---:|---:|---|",
        ]
    )
    ranked_paths = sorted(
        path_durations.items(),
        key=lambda pair: sum(pair[1]) / len(pair[1]),
        reverse=True,
    )
    for key, durations in ranked_paths[:_TOP_PATHS_N]:
        avg_ms = sum(durations) / len(durations)
        max_ms = max(durations)
        lines.append(
            f"| {avg_ms:.0f} | {max_ms:.0f} | {path_counts[key]} | `{key}` |"
        )

    lines.extend(
        [
            "",
            "## Most long-task heavy tests",
            "",
            "| long_total_ms | long_count | max_ms | requests | nodeid |",
            "|---:|---:|---:|---:|---|",
        ]
    )
    by_long = sorted(reports, key=lambda item: item.long_task_total_ms, reverse=True)
    for item in by_long[:_TOP_TESTS_N]:
        if item.long_task_count == 0:
            continue
        row = (
            f"| {item.long_task_total_ms:.0f} | {item.long_task_count} "
            f"| {item.long_task_max_ms:.0f} | {item.request_count} | `{item.nodeid}` |"
        )
        lines.append(row)

    lines.extend(
        [
            "",
            "## Errors",
            "",
            "| 4xx | 5xx | failed | nodeid |",
            "|---:|---:|---:|---|",
        ]
    )
    with_errors = [
        item
        for item in reports
        if item.error_4xx_count or item.error_5xx_count or item.failed_request_count
    ]
    if not with_errors:
        lines.append("| 0 | 0 | 0 | _(none)_ |")
    else:
        for item in sorted(
            with_errors,
            key=lambda row: row.error_5xx_count + row.failed_request_count,
            reverse=True,
        )[:_TOP_TESTS_N]:
            row = (
                f"| {item.error_4xx_count} | {item.error_5xx_count} "
                f"| {item.failed_request_count} | `{item.nodeid}` |"
            )
            lines.append(row)

    lines.append("")
    tmp = summary_path.with_suffix(".md.tmp")
    _ = tmp.write_text("\n".join(lines), encoding="utf-8")
    os.replace(tmp, summary_path)
    return summary_path
