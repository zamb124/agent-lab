"""
Отчёт о параллелизме pytest-xdist после phase 1 make test.

Subcommands:
  collect — snapshot phase 1 (workers, failures, stack, junit)
  report  — summary.json + report.html + terminal summary

Opt-out: PYTEST_WORKERS_PROFILE=0 make test
HTML: reports/pytest_workers_profile/latest/report.html
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict, cast

from core.types import JsonObject, parse_json_object

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPORTS_ROOT = _REPO_ROOT / "reports" / "pytest_workers_profile"
_LASTFAILED_PATH = _REPO_ROOT / ".pytest_cache" / "v" / "cache" / "lastfailed"
_TESTS_ROOT = _REPO_ROOT / "tests"
_HANG_GUARD_DIR = Path("/tmp")
_HANG_GUARD_EVENTS = _HANG_GUARD_DIR / "platform_test_hang_guard_events.jsonl"
_HANG_GUARD_KILLS = _HANG_GUARD_DIR / "platform_test_hang_guard_kills.jsonl"
_HANG_GUARD_HEARTBEAT_GLOB = "platform_test_hang_guard_*.json"

_BASELINE_PYTEST_WORKERS = 10

_PARALLELISM_FAILURE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("TaskiqResultTimeout", "taskiq_timeout"),
    ("ServiceClientError", "service_client_error"),
    ("ReadTimeout", "read_timeout"),
    ("too many connections", "postgres_connections"),
    ("TooManyConnectionsError", "postgres_connections"),
    ("code_runner", "code_runner"),
    ("NodeWallClockTimeout", "node_wall_clock_timeout"),
    ("ws_timeout", "ws_timeout"),
    ("ws_disconnected", "ws_disconnected"),
    ("ConnectError", "connect_error"),
    ("TaskiqResultTimeoutError", "taskiq_timeout"),
)

_SANDBOX_PREFIXES = (
    "tests/capabilities/",
    "tests/flows/integration/",
    "tests/flows/e2e/",
    "tests/flows/api/test_code_api.py",
    "tests/flows/api/test_node_execute.py",
    "tests/flows/core/agent/test_tool_node.py",
    "tests/flows/core/tasks/test_tasks.py",
    "tests/flows/e2e/test_tool_node_e2e.py",
    "tests/flows/e2e/test_full_flow_api.py",
)

_PHASE1_IGNORE_PREFIXES = (
    "tests/ui/",
)

_REAL_TASKIQ_MARKER = re.compile(
    r"@pytest\.mark\.real_taskiq|pytestmark\s*=\s*pytest\.mark\.real_taskiq"
)


class IssueRow(TypedDict):
    severity: Literal["warn", "error"]
    code: str
    message: str
    nodeid: str | None
    pattern: str | None


class FailureRow(TypedDict):
    nodeid: str
    message: str
    parallelism_suspect: bool
    suspect_pattern: str | None


class KillRow(TypedDict):
    worker: str
    pid: int
    nodeid: str
    phase: str
    timeout_sec: float
    age_seconds: float
    time: float


class WorkerTimelineRow(TypedDict):
    worker: str
    pids: list[int]
    spawned: int
    finished: bool
    final_phase: str
    final_nodeid: str


class HangGuardSnapshot(TypedDict):
    kills: list[KillRow]
    workers: list[WorkerTimelineRow]
    worker_spawn_count: int
    worker_restart_count: int
    session_start_time: float | None
    session_finish_time: float | None
    wall_time_seconds: float | None


class CollectPayload(TypedDict):
    run_id: str
    collected_at: str
    pytest_workers: str
    pytest_workers_numeric: int | None
    phase1_exit_code: int
    max_worker_restart: int
    phase1_wall_time_seconds: float | None
    junit_time_sum_seconds: float | None
    failed_nodeids: list[str]
    junit_failures: list[FailureRow]
    stack_manifest: dict[str, object] | None
    xdist_counts: dict[str, int]
    hang_guard: HangGuardSnapshot | None


def _require_int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("bool is not a valid integer metric")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    raise ValueError(f"expected integer, got {type(value)!r}")


def _require_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"expected number, got {type(value)!r}")
    return float(value)


def _parse_pytest_workers(raw: str) -> tuple[str, int | None]:
    stripped = raw.strip()
    if stripped == "auto":
        return stripped, None
    return stripped, int(stripped)


def _load_lastfailed() -> list[str]:
    if not _LASTFAILED_PATH.is_file():
        return []
    payload = json.loads(_LASTFAILED_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid lastfailed cache: {_LASTFAILED_PATH}")
    return sorted(str(key) for key in payload)


def _load_stack_manifest() -> dict[str, object] | None:
    from scripts.testing.stack import STACK_MANIFEST_PATH

    if not STACK_MANIFEST_PATH.is_file():
        return None
    payload = json.loads(STACK_MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid stack manifest: {STACK_MANIFEST_PATH}")
    return payload


def _is_phase1_test_file(path: Path) -> bool:
    rel = path.relative_to(_REPO_ROOT).as_posix()
    if not rel.startswith("tests/") or not rel.endswith(".py"):
        return False
    if "/test_" not in rel and not rel.endswith("_test.py"):
        return False
    for prefix in _PHASE1_IGNORE_PREFIXES:
        if rel.startswith(prefix):
            return False
    return True


def _is_sandbox_nodeid(nodeid: str) -> bool:
    file_part = nodeid.split("::", 1)[0]
    if file_part.startswith("tests/capabilities/"):
        return True
    if file_part.startswith("tests/flows/integration/"):
        return True
    if file_part.startswith("tests/flows/e2e/"):
        return True
    return any(file_part.startswith(prefix) for prefix in _SANDBOX_PREFIXES)


def _count_xdist_groups() -> dict[str, int]:
    code_sandbox = 0
    real_taskiq = 0
    parallelizable = 0
    for path in _TESTS_ROOT.rglob("test_*.py"):
        if not _is_phase1_test_file(path):
            continue
        rel = path.relative_to(_REPO_ROOT).as_posix()
        content = path.read_text(encoding="utf-8")
        test_count = len(re.findall(r"^\s*def test_", content, flags=re.MULTILINE))
        if test_count == 0:
            continue
        if _REAL_TASKIQ_MARKER.search(content):
            real_taskiq += test_count
        elif _is_sandbox_nodeid(rel):
            code_sandbox += test_count
        else:
            parallelizable += test_count
    total = code_sandbox + real_taskiq + parallelizable
    return {
        "total_phase1_estimate": total,
        "code_sandbox_estimate": code_sandbox,
        "real_taskiq_estimate": real_taskiq,
        "parallelizable_estimate": parallelizable,
    }


def _classify_failure_message(message: str) -> tuple[bool, str | None]:
    lowered = message.lower()
    for needle, pattern_code in _PARALLELISM_FAILURE_PATTERNS:
        if needle.lower() in lowered:
            return True, pattern_code
    return False, None


def _parse_junit(path: Path) -> tuple[float | None, float | None, list[FailureRow]]:
    if not path.is_file():
        return None, None, []
    root = ET.parse(path).getroot()
    wall_time_raw = root.attrib.get("time")
    wall_time = float(wall_time_raw) if wall_time_raw else None
    time_sum = 0.0
    failures: list[FailureRow] = []
    for testcase in root.iter("testcase"):
        classname = testcase.attrib.get("classname", "")
        name = testcase.attrib.get("name", "")
        time_raw = testcase.attrib.get("time")
        if time_raw:
            time_sum += float(time_raw)
        nodeid = f"{classname}::{name}" if classname else name
        for child in testcase:
            if child.tag not in {"failure", "error"}:
                continue
            message = child.attrib.get("message", "") or (child.text or "")
            suspect, pattern = _classify_failure_message(message)
            failures.append(
                FailureRow(
                    nodeid=nodeid,
                    message=message[:500],
                    parallelism_suspect=suspect,
                    suspect_pattern=pattern,
                )
            )
    return wall_time, time_sum, failures


def _read_jsonl(path: Path) -> list[JsonObject]:
    if not path.is_file():
        return []
    rows: list[JsonObject] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rows.append(parse_json_object(stripped, path.name))
        except ValueError:
            continue
    return rows


def _collect_hang_guard() -> HangGuardSnapshot | None:
    events = _read_jsonl(_HANG_GUARD_EVENTS)
    kills_raw = _read_jsonl(_HANG_GUARD_KILLS)
    heartbeat_files = list(_HANG_GUARD_DIR.glob(_HANG_GUARD_HEARTBEAT_GLOB))
    if not events and not kills_raw and not heartbeat_files:
        return None
    kills: list[KillRow] = []
    for row in kills_raw:
        kills.append(
            KillRow(
                worker=str(row.get("worker", "")),
                pid=_require_int(row.get("pid", 0)),
                nodeid=str(row.get("nodeid", "")),
                phase=str(row.get("phase", "")),
                timeout_sec=_require_float(row.get("timeout_sec", 0.0)),
                age_seconds=_require_float(row.get("age_seconds", 0.0)),
                time=_require_float(row.get("time", 0.0)),
            )
        )
    spawn_pids: dict[str, list[int]] = {}
    finished_workers: set[str] = set()
    session_start_time: float | None = None
    session_finish_time: float | None = None
    for event in events:
        worker = str(event.get("worker", ""))
        pid_raw = event.get("pid")
        kind = str(event.get("kind", ""))
        stamp_raw = event.get("time")
        stamp = float(stamp_raw) if isinstance(stamp_raw, (int, float)) else None
        if kind == "session_start":
            if worker != "master" and isinstance(pid_raw, int):
                spawn_pids.setdefault(worker, []).append(pid_raw)
            if stamp is not None and (session_start_time is None or stamp < session_start_time):
                session_start_time = stamp
        elif kind == "session_finish":
            if worker != "master":
                finished_workers.add(worker)
            if stamp is not None and (session_finish_time is None or stamp > session_finish_time):
                session_finish_time = stamp
    final_by_worker: dict[str, WorkerTimelineRow] = {}
    for path in heartbeat_files:
        try:
            loaded = parse_json_object(path.read_text(encoding="utf-8"), path.name)
        except (OSError, ValueError):
            continue
        worker_raw = loaded.get("worker")
        if not isinstance(worker_raw, str) or not worker_raw or worker_raw == "master":
            continue
        worker = worker_raw
        final_by_worker[worker] = WorkerTimelineRow(
            worker=worker,
            pids=spawn_pids.get(worker, []),
            spawned=len(spawn_pids.get(worker, [])),
            finished=worker in finished_workers,
            final_phase=str(loaded.get("phase", "")),
            final_nodeid=str(loaded.get("nodeid", "")),
        )
    for worker, pids in spawn_pids.items():
        if worker in final_by_worker:
            continue
        final_by_worker[worker] = WorkerTimelineRow(
            worker=worker,
            pids=pids,
            spawned=len(pids),
            finished=worker in finished_workers,
            final_phase="",
            final_nodeid="",
        )
    workers = sorted(final_by_worker.values(), key=lambda item: item["worker"])
    worker_spawn_count = sum(len(pids) for pids in spawn_pids.values())
    worker_restart_count = sum(max(0, len(pids) - 1) for pids in spawn_pids.values())
    wall_time: float | None = None
    if session_start_time is not None and session_finish_time is not None:
        wall_time = session_finish_time - session_start_time
    return HangGuardSnapshot(
        kills=kills,
        workers=workers,
        worker_spawn_count=worker_spawn_count,
        worker_restart_count=worker_restart_count,
        session_start_time=session_start_time,
        session_finish_time=session_finish_time,
        wall_time_seconds=wall_time,
    )


def cmd_collect(
    run_id: str,
    *,
    workers: str,
    exit_code: int,
    max_worker_restart: int,
) -> Path:
    run_dir = _REPORTS_ROOT / run_id
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    workers_label, workers_numeric = _parse_pytest_workers(workers)
    junit_path = run_dir / "junit.xml"
    junit_wall_time, junit_time_sum, junit_failures = _parse_junit(junit_path)
    hang_guard = _collect_hang_guard()
    wall_time = (
        hang_guard["wall_time_seconds"]
        if hang_guard is not None and hang_guard["wall_time_seconds"] is not None
        else junit_wall_time
    )
    payload: CollectPayload = {
        "run_id": run_id,
        "collected_at": datetime.now(UTC).isoformat(),
        "pytest_workers": workers_label,
        "pytest_workers_numeric": workers_numeric,
        "phase1_exit_code": exit_code,
        "max_worker_restart": max_worker_restart,
        "phase1_wall_time_seconds": wall_time,
        "junit_time_sum_seconds": junit_time_sum,
        "failed_nodeids": _load_lastfailed(),
        "junit_failures": junit_failures,
        "stack_manifest": _load_stack_manifest(),
        "xdist_counts": _count_xdist_groups(),
        "hang_guard": hang_guard,
    }
    raw_path = raw_dir / "phase1.json"
    _ = raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return run_dir


def _load_collect_payload(run_dir: Path) -> CollectPayload:
    raw_path = run_dir / "raw" / "phase1.json"
    if not raw_path.is_file():
        raise RuntimeError(f"missing collect snapshot: {raw_path}")
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid collect payload: {raw_path}")
    return cast(CollectPayload, cast(object, payload))


def _expected_scale_factor(workers_numeric: int | None) -> float:
    if workers_numeric is None or workers_numeric <= _BASELINE_PYTEST_WORKERS:
        return 1.0
    return workers_numeric / _BASELINE_PYTEST_WORKERS


def _stack_scale_from_manifest(manifest: dict[str, object] | None) -> float | None:
    if manifest is None:
        return None
    factor = manifest.get("stack_scale_factor")
    if isinstance(factor, (int, float)):
        return float(factor)
    return None


def _build_issues(payload: CollectPayload) -> list[IssueRow]:
    issues: list[IssueRow] = []
    workers_numeric = payload["pytest_workers_numeric"]
    expected_scale = _expected_scale_factor(workers_numeric)
    actual_scale = _stack_scale_from_manifest(payload["stack_manifest"])
    if workers_numeric is not None and workers_numeric > _BASELINE_PYTEST_WORKERS:
        if actual_scale is None:
            issues.append(
                IssueRow(
                    severity="warn",
                    code="stack_manifest_missing",
                    message="Манифест test_stack не найден — проверьте make test-up",
                    nodeid=None,
                    pattern=None,
                )
            )
        elif actual_scale + 0.01 < expected_scale:
            issues.append(
                IssueRow(
                    severity="error",
                    code="stack_undersized",
                    message=(
                        f"WORKERS={workers_numeric}, ожидаемый scale={expected_scale:.2f}, "
                        f"фактический stack_scale_factor={actual_scale:.2f}. "
                        "Перезапустите make test-up с тем же WORKERS."
                    ),
                    nodeid=None,
                    pattern=None,
                )
            )
    hang_guard = payload.get("hang_guard")
    if isinstance(hang_guard, dict):
        kills = hang_guard["kills"]
        if kills:
            killed_tests = ", ".join(
                kill["nodeid"].split("::")[-1][:40] for kill in kills[:5]
            )
            issues.append(
                IssueRow(
                    severity="error",
                    code="hang_guard_kills",
                    message=(
                        f"hang_guard SIGKILL: {len(kills)} воркеров убито "
                        f"(зависли > timeout+slack в call/setup/teardown): {killed_tests}"
                    ),
                    nodeid=None,
                    pattern=None,
                )
            )
        restart_count = hang_guard["worker_restart_count"]
        if restart_count > 0:
            issues.append(
                IssueRow(
                    severity="warn",
                    code="worker_restarts",
                    message=(
                        f"{restart_count} перезапусков воркеров — каждый платит "
                        "полную session-инициализацию и перераспределяет очередь"
                    ),
                    nodeid=None,
                    pattern=None,
                )
            )
    utilization = _worker_utilization(payload)
    if utilization is not None and utilization < 0.5:
        issues.append(
            IssueRow(
                severity="warn",
                code="low_worker_utilization",
                message=(
                    f"utilization={utilization:.0%}: суммарное время тестов / (workers × wall) "
                    "< 50% — воркеры простаивают (краши, session setup, shared-ресурсы)"
                ),
                nodeid=None,
                pattern=None,
            )
        )
    if payload["phase1_exit_code"] != 0:
        issues.append(
            IssueRow(
                severity="error",
                code="phase1_failed",
                message=f"pytest phase 1 завершился с exit_code={payload['phase1_exit_code']}",
                nodeid=None,
                pattern=None,
            )
        )
    xdist = payload["xdist_counts"]
    total = xdist.get("total_phase1_estimate", 0)
    serial = xdist.get("code_sandbox_estimate", 0) + xdist.get("real_taskiq_estimate", 0)
    if total > 0 and serial / total > 0.35:
        issues.append(
            IssueRow(
                severity="warn",
                code="xdist_bottleneck",
                message=(
                    f"~{serial}/{total} тестов phase 1 в serial xdist_group "
                    "(code_sandbox/real_taskiq) — рост WORKERS даст ограниченный выигрыш"
                ),
                nodeid=None,
                pattern=None,
            )
        )
    for failure in payload["junit_failures"]:
        if not failure["parallelism_suspect"]:
            continue
        issues.append(
            IssueRow(
                severity="warn",
                code="likely_parallelism_failure",
                message=failure["message"][:200],
                nodeid=failure["nodeid"],
                pattern=failure["suspect_pattern"],
            )
        )
    sandbox_failures = [
        item
        for item in payload["junit_failures"]
        if item["parallelism_suspect"] and _is_sandbox_nodeid(item["nodeid"])
    ]
    if sandbox_failures:
        issues.append(
            IssueRow(
                severity="warn",
                code="worker_restart_risk",
                message=(
                    f"{len(sandbox_failures)} падений в sandbox/taskiq-зоне — "
                    "проверьте code_runner/flows_worker и phase 2 retry"
                ),
                nodeid=None,
                pattern=None,
            )
        )
    return issues


def _worker_utilization(payload: CollectPayload) -> float | None:
    time_sum = payload.get("junit_time_sum_seconds")
    wall = payload.get("phase1_wall_time_seconds")
    workers_numeric = payload.get("pytest_workers_numeric")
    if not isinstance(time_sum, (int, float)) or not isinstance(wall, (int, float)):
        return None
    if not isinstance(workers_numeric, int) or workers_numeric <= 0 or wall <= 0:
        return None
    return float(time_sum) / (workers_numeric * float(wall))


def _build_recommendations(payload: CollectPayload, issues: list[IssueRow]) -> list[str]:
    recs: list[str] = []
    codes = {issue["code"] for issue in issues}
    workers_numeric = payload["pytest_workers_numeric"]
    if "stack_undersized" in codes and workers_numeric is not None:
        recs.append(f"make test-down && WORKERS={workers_numeric} make test-up")
    if "phase1_failed" in codes:
        recs.append("Дождитесь phase 2 retry или запустите: make test с меньшим WORKERS")
    if "likely_parallelism_failure" in codes and workers_numeric is not None and workers_numeric > _BASELINE_PYTEST_WORKERS:
        recs.append(f"Попробуйте WORKERS={_BASELINE_PYTEST_WORKERS} или снизьте на 1–2 воркера")
    if not issues:
        recs.append("Параллелизм phase 1 в норме; сравните delta с прошлым прогоном")
    return recs


def _load_previous_summary(current_run_id: str) -> dict[str, object] | None:
    latest = _REPORTS_ROOT / "latest"
    if not latest.is_symlink():
        return None
    previous_dir = latest.resolve()
    if previous_dir.name == current_run_id:
        return None
    summary_path = previous_dir / "summary.json"
    if not summary_path.is_file():
        return None
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid previous summary: {summary_path}")
    return payload


def _build_summary(payload: CollectPayload) -> dict[str, object]:
    issues = _build_issues(payload)
    suspect_count = sum(1 for item in payload["junit_failures"] if item["parallelism_suspect"])
    failed_count = len(payload["failed_nodeids"])
    if failed_count == 0 and payload["phase1_exit_code"] != 0:
        failed_count = len(payload["junit_failures"])
    summary: dict[str, object] = {
        "run_id": payload["run_id"],
        "pytest_workers": payload["pytest_workers"],
        "pytest_workers_numeric": payload["pytest_workers_numeric"],
        "phase1_passed": payload["phase1_exit_code"] == 0,
        "phase1_exit_code": payload["phase1_exit_code"],
        "failed_count": failed_count,
        "parallelism_suspect_count": suspect_count,
        "phase1_wall_time_seconds": payload["phase1_wall_time_seconds"],
        "max_worker_restart": payload["max_worker_restart"],
        "stack_scale_factor": _stack_scale_from_manifest(payload["stack_manifest"]),
        "stack_capacity": (
            payload["stack_manifest"].get("stack_capacity")
            if payload["stack_manifest"] is not None
            else None
        ),
        "xdist_counts": payload["xdist_counts"],
        "junit_time_sum_seconds": payload.get("junit_time_sum_seconds"),
        "worker_utilization": _worker_utilization(payload),
        "hang_guard": payload.get("hang_guard"),
        "failed_nodeids": payload["failed_nodeids"],
        "issues": issues,
        "recommendations": _build_recommendations(payload, issues),
        "issue_count_error": sum(1 for item in issues if item["severity"] == "error"),
        "issue_count_warn": sum(1 for item in issues if item["severity"] == "warn"),
    }
    previous = _load_previous_summary(payload["run_id"])
    summary["delta_vs_previous"] = _build_delta(summary, previous)
    return summary


def _build_delta(
    current: dict[str, object],
    previous: dict[str, object] | None,
) -> dict[str, object]:
    if previous is None:
        return {"has_previous": False}
    def _delta(key: str) -> int | float | None:
        cur = current.get(key)
        prev = previous.get(key)
        if isinstance(cur, (int, float)) and isinstance(prev, (int, float)):
            return cur - prev
        return None

    return {
        "has_previous": True,
        "previous_run_id": previous.get("run_id"),
        "failed_count_delta": _delta("failed_count"),
        "parallelism_suspect_count_delta": _delta("parallelism_suspect_count"),
        "phase1_wall_time_seconds_delta": _delta("phase1_wall_time_seconds"),
        "issue_count_error_delta": _delta("issue_count_error"),
    }


def _terminal_use_unicode_box() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return True


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
    lines = [top, _box_line("Pytest workers profile (phase 1)", width, unicode_box=unicode_box), mid]
    workers = summary.get("pytest_workers", "?")
    passed = summary.get("phase1_passed")
    failed = _require_int(summary.get("failed_count", 0))
    suspects = _require_int(summary.get("parallelism_suspect_count", 0))
    wall = summary.get("phase1_wall_time_seconds")
    wall_label = f"{float(wall):.1f}s" if isinstance(wall, (int, float)) else "n/a"
    lines.append(_box_line(f"WORKERS={workers}  phase1={'OK' if passed else 'FAIL'}  failed={failed}", width, unicode_box=unicode_box))
    lines.append(_box_line(f"suspect={suspects}  wall_time={wall_label}", width, unicode_box=unicode_box))
    scale = summary.get("stack_scale_factor")
    if isinstance(scale, (int, float)):
        lines.append(_box_line(f"stack_scale_factor={float(scale):.2f}", width, unicode_box=unicode_box))
    xdist = summary.get("xdist_counts")
    if isinstance(xdist, dict):
        parallel = xdist.get("parallelizable_estimate", 0)
        serial = xdist.get("code_sandbox_estimate", 0) + xdist.get("real_taskiq_estimate", 0)
        lines.append(_box_line(f"xdist: parallel~{parallel} serial~{serial}", width, unicode_box=unicode_box))
    utilization = summary.get("worker_utilization")
    if isinstance(utilization, (int, float)):
        lines.append(_box_line(f"worker_utilization={float(utilization):.0%}", width, unicode_box=unicode_box))
    hang_guard = summary.get("hang_guard")
    if isinstance(hang_guard, dict):
        kills = hang_guard.get("kills")
        restarts = hang_guard.get("worker_restart_count")
        kills_count = len(kills) if isinstance(kills, list) else 0
        if kills_count or (isinstance(restarts, (int, float)) and restarts > 0):
            lines.append(
                _box_line(
                    f"hang_guard: kills={kills_count} restarts={int(restarts or 0)}",
                    width,
                    unicode_box=unicode_box,
                )
            )
    issues = summary.get("issues")
    if isinstance(issues, list) and issues:
        lines.append(mid)
        lines.append(_box_line("Issues", width, unicode_box=unicode_box))
        for issue in issues[:8]:
            if not isinstance(issue, dict):
                continue
            sev = str(issue.get("severity", ""))
            code = str(issue.get("code", ""))
            lines.append(_box_line(f"  [{sev}] {code}", width, unicode_box=unicode_box))
    delta = summary.get("delta_vs_previous")
    if isinstance(delta, dict) and delta.get("has_previous"):
        lines.append(mid)
        prev_id = delta.get("previous_run_id", "?")
        f_delta = delta.get("failed_count_delta")
        t_delta = delta.get("phase1_wall_time_seconds_delta")
        lines.append(_box_line(f"delta vs {prev_id}", width, unicode_box=unicode_box))
        if isinstance(f_delta, (int, float)):
            lines.append(_box_line(f"  failed_count {f_delta:+.0f}", width, unicode_box=unicode_box))
        if isinstance(t_delta, (int, float)):
            lines.append(_box_line(f"  wall_time {t_delta:+.1f}s", width, unicode_box=unicode_box))
    recs = summary.get("recommendations")
    if isinstance(recs, list) and recs:
        lines.append(mid)
        lines.append(_box_line("Recommendations", width, unicode_box=unicode_box))
        for rec in recs[:4]:
            lines.append(_box_line(f"  - {rec}", width, unicode_box=unicode_box))
    lines.append(bottom)
    lines.append("Scope: pytest phase 1 only.")
    lines.append("HTML: reports/pytest_workers_profile/latest/report.html")
    return "\n".join(lines)


def _render_html(summary: dict[str, object], run_id: str) -> str:
    def esc(value: object) -> str:
        return html.escape(str(value))

    sections = [
        "<h1>Pytest workers profile</h1>",
        f"<p>Run: <code>{esc(run_id)}</code></p>",
        "<p><em>Snapshot scope: pytest phase 1 only (not integration/network/agent E2E).</em></p>",
        "<h2>Summary</h2><ul>",
        f"<li>pytest_workers: {esc(summary.get('pytest_workers'))}</li>",
        f"<li>phase1_passed: {esc(summary.get('phase1_passed'))}</li>",
        f"<li>failed_count: {esc(summary.get('failed_count'))}</li>",
        f"<li>parallelism_suspect_count: {esc(summary.get('parallelism_suspect_count'))}</li>",
        f"<li>phase1_wall_time_seconds: {esc(summary.get('phase1_wall_time_seconds'))}</li>",
        f"<li>stack_scale_factor: {esc(summary.get('stack_scale_factor'))}</li>",
        f"<li>junit_time_sum_seconds: {esc(summary.get('junit_time_sum_seconds'))}</li>",
        f"<li>worker_utilization: {esc(summary.get('worker_utilization'))}</li>",
        "</ul>",
    ]
    hang_guard = summary.get("hang_guard")
    if isinstance(hang_guard, dict):
        kills = hang_guard.get("kills")
        workers = hang_guard.get("workers")
        sections.append("<h2>Hang guard</h2><ul>")
        sections.append(f"<li>worker_spawn_count: {esc(hang_guard.get('worker_spawn_count'))}</li>")
        sections.append(f"<li>worker_restart_count: {esc(hang_guard.get('worker_restart_count'))}</li>")
        sections.append(f"<li>wall_time_seconds: {esc(hang_guard.get('wall_time_seconds'))}</li>")
        sections.append("</ul>")
        if isinstance(kills, list) and kills:
            sections.append("<h3>SIGKILLs</h3><table border='1' cellpadding='4'>")
            sections.append(
                "<tr><th>worker</th><th>pid</th><th>phase</th><th>age_s</th><th>timeout_s</th><th>nodeid</th></tr>"
            )
            for kill in kills:
                if not isinstance(kill, dict):
                    continue
                sections.append(
                    "<tr>"
                    + f"<td>{esc(kill.get('worker'))}</td>"
                    + f"<td>{esc(kill.get('pid'))}</td>"
                    + f"<td>{esc(kill.get('phase'))}</td>"
                    + f"<td>{esc(kill.get('age_seconds'))}</td>"
                    + f"<td>{esc(kill.get('timeout_sec'))}</td>"
                    + f"<td><code>{esc(kill.get('nodeid'))}</code></td>"
                    + "</tr>"
                )
            sections.append("</table>")
        if isinstance(workers, list) and workers:
            sections.append("<h3>Workers</h3><table border='1' cellpadding='4'>")
            sections.append(
                "<tr><th>worker</th><th>pids</th><th>spawned</th><th>finished</th><th>final_phase</th><th>final_nodeid</th></tr>"
            )
            for row in workers:
                if not isinstance(row, dict):
                    continue
                sections.append(
                    "<tr>"
                    + f"<td>{esc(row.get('worker'))}</td>"
                    + f"<td>{esc(row.get('pids'))}</td>"
                    + f"<td>{esc(row.get('spawned'))}</td>"
                    + f"<td>{esc(row.get('finished'))}</td>"
                    + f"<td>{esc(row.get('final_phase'))}</td>"
                    + f"<td><code>{esc(row.get('final_nodeid'))}</code></td>"
                    + "</tr>"
                )
            sections.append("</table>")
    issues = summary.get("issues")
    if isinstance(issues, list) and issues:
        sections.append("<h2>Issues</h2><table border='1' cellpadding='4'>")
        sections.append("<tr><th>severity</th><th>code</th><th>nodeid</th><th>message</th></tr>")
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            sections.append(
                "<tr>"
                + f"<td>{esc(issue.get('severity'))}</td>"
                + f"<td>{esc(issue.get('code'))}</td>"
                + f"<td>{esc(issue.get('nodeid'))}</td>"
                + f"<td>{esc(issue.get('message'))}</td>"
                + "</tr>"
            )
        sections.append("</table>")
    recs = summary.get("recommendations")
    if isinstance(recs, list) and recs:
        sections.append("<h2>Recommendations</h2><ul>")
        for rec in recs:
            sections.append(f"<li>{esc(rec)}</li>")
        sections.append("</ul>")
    failed = summary.get("failed_nodeids")
    if isinstance(failed, list) and failed:
        sections.append("<h2>Failed nodeids</h2><ul>")
        for nodeid in failed[:50]:
            sections.append(f"<li><code>{esc(nodeid)}</code></li>")
        sections.append("</ul>")
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        + "<title>Pytest workers profile</title></head><body>"
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
    if latest.is_symlink():
        target = latest.resolve()
        if target.is_dir():
            return target
    raise RuntimeError(f"no collect runs under {_REPORTS_ROOT}")


def cmd_report(run_id: str | None) -> Path:
    run_dir = _resolve_run_dir(run_id)
    payload = _load_collect_payload(run_dir)
    summary = _build_summary(payload)
    summary_path = run_dir / "summary.json"
    _ = summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    html_path = run_dir / "report.html"
    _ = html_path.write_text(_render_html(summary, run_dir.name), encoding="utf-8")
    latest = _REPORTS_ROOT / "latest"
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.symlink_to(run_dir.name)
    print(_render_terminal(summary))
    print(f"pytest_workers_profile: report → {html_path}")
    return html_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pytest-xdist parallelism profile for make test phase 1"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect_parser = subparsers.add_parser("collect", help="Collect phase 1 snapshot")
    collect_parser.add_argument("--run-id", required=True)
    collect_parser.add_argument("--workers", required=True)
    collect_parser.add_argument("--exit-code", type=int, required=True)
    collect_parser.add_argument(
        "--max-worker-restart",
        type=int,
        default=int(os.environ.get("PYTEST_MAX_WORKER_RESTART", "2")),
    )
    report_parser = subparsers.add_parser("report", help="Build summary + HTML")
    report_parser.add_argument("--run-id", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "collect":
        cmd_collect(
            args.run_id,
            workers=args.workers,
            exit_code=args.exit_code,
            max_worker_restart=args.max_worker_restart,
        )
        return 0
    if args.command == "report":
        _ = cmd_report(args.run_id)
        return 0
    raise RuntimeError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
