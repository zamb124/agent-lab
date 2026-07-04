"""
Объединённый отчёт покрытия после make test (Python pytest + JS Vitest unit).

Subcommands:
  reset  — reports/coverage/<run_id>/ + meta.json
  report — combine coverage, HTML, terminal summary, symlink latest

Opt-out: TEST_COVERAGE=0 make test
HTML: reports/coverage/latest/report.html
"""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REPORTS_ROOT = _REPO_ROOT / "reports" / "coverage"

_PYTHON_SCOPE_NOTE = (
    "Python: apps + core из pytest phase 1/2/4 (без integration/network маркеров)."
)
_JS_SCOPE_NOTE = "JS: Vitest unit (core/frontend/static/lib/events/**)."


class CoverageMeta(TypedDict, total=False):
    run_id: str
    reset_at: str
    workers: str | None
    python_phases: list[str]
    notes: list[str]


class CoverageTotals(TypedDict):
    lines_pct: float | None
    lines_covered: int | None
    lines_total: int | None
    branches_pct: float | None
    branches_covered: int | None
    branches_total: int | None


class PackageCoverageRow(TypedDict):
    package: str
    lines_pct: float
    lines_covered: int
    lines_total: int


class CoverageSummary(TypedDict, total=False):
    run_id: str
    reported_at: str
    python: CoverageTotals
    js: CoverageTotals
    python_packages_low: list[PackageCoverageRow]
    delta_vs_previous: dict[str, object]
    meta: CoverageMeta
    paths: dict[str, str]


def _run_command(args: list[str], *, cwd: Path | None = None) -> None:
    completed = subprocess.run(
        args,
        cwd=cwd or _REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(f"command failed ({' '.join(args)}): {detail}")


def _run_dir(run_id: str) -> Path:
    return _REPORTS_ROOT / run_id


def _coverage_data_path(run_dir: Path) -> Path:
    return run_dir / ".coverage"


def _load_meta(run_dir: Path) -> CoverageMeta:
    meta_path = run_dir / "meta.json"
    if not meta_path.is_file():
        return {"run_id": run_dir.name}
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid meta.json: {meta_path}")
    return cast(CoverageMeta, payload)


def _write_meta(run_dir: Path, meta: CoverageMeta) -> None:
    meta_path = run_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_reset(run_id: str, *, workers: str | None) -> Path:
    run_dir = _run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    for pattern in (".coverage", ".coverage.*"):
        for path in run_dir.glob(pattern):
            if path.is_file():
                path.unlink()
    js_dir = run_dir / "js"
    if js_dir.is_dir():
        for path in js_dir.rglob("*"):
            if path.is_file():
                path.unlink()
    python_dir = run_dir / "python"
    if python_dir.is_dir():
        for path in python_dir.rglob("*"):
            if path.is_file():
                path.unlink()

    meta: CoverageMeta = {
        "run_id": run_id,
        "reset_at": datetime.now(UTC).isoformat(),
        "workers": workers,
        "python_phases": ["phase1", "phase2_optional", "phase3_ui_optional", "phase4a", "phase4c"],
        "notes": [_PYTHON_SCOPE_NOTE, _JS_SCOPE_NOTE],
    }
    _write_meta(run_dir, meta)
    return run_dir


def _combine_python_coverage(run_dir: Path) -> None:
    data_path = _coverage_data_path(run_dir)
    env = os.environ.copy()
    env["COVERAGE_FILE"] = str(data_path)
    fragment_paths = sorted(run_dir.glob(".coverage.*"))
    if not data_path.is_file() and not fragment_paths:
        return
    if fragment_paths:
        combine_args = ["uv", "run", "coverage", "combine", "--keep"]
        combine_args.extend(str(path) for path in fragment_paths)
        if data_path.is_file():
            combine_args.append(str(data_path))
        completed = subprocess.run(
            combine_args,
            cwd=_REPO_ROOT,
            env=env,
            check=False,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            if "No data to combine" not in stderr:
                detail = stderr or completed.stdout.strip() or f"exit {completed.returncode}"
                raise RuntimeError(f"coverage combine failed: {detail}")


def _export_python_coverage(run_dir: Path) -> Path | None:
    data_path = _coverage_data_path(run_dir)
    if not data_path.is_file():
        return None
    python_dir = run_dir / "python"
    python_dir.mkdir(parents=True, exist_ok=True)
    html_dir = python_dir / "html"
    summary_path = python_dir / "summary.json"
    env = os.environ.copy()
    env["COVERAGE_FILE"] = str(data_path)
    _run_command(
        ["uv", "run", "coverage", "json", "-o", str(summary_path)],
        cwd=_REPO_ROOT,
    )
    subprocess.run(
        ["uv", "run", "coverage", "html", "-d", str(html_dir)],
        cwd=_REPO_ROOT,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    return summary_path if summary_path.is_file() else None


def _pct(covered: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(100.0 * covered / total, 2)


def _parse_python_summary(summary_path: Path) -> tuple[CoverageTotals, list[PackageCoverageRow]]:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid coverage json: {summary_path}")
    totals_raw = payload.get("totals")
    if not isinstance(totals_raw, dict):
        raise RuntimeError(f"missing totals in coverage json: {summary_path}")

    covered_lines = totals_raw.get("covered_lines")
    num_statements = totals_raw.get("num_statements")
    covered_branches = totals_raw.get("covered_branches")
    num_branches = totals_raw.get("num_branches")
    if not isinstance(covered_lines, int) or not isinstance(num_statements, int):
        raise RuntimeError(f"invalid line totals in coverage json: {summary_path}")
    branches_covered = covered_branches if isinstance(covered_branches, int) else None
    branches_total = num_branches if isinstance(num_branches, int) else None

    totals: CoverageTotals = {
        "lines_pct": _pct(covered_lines, num_statements),
        "lines_covered": covered_lines,
        "lines_total": num_statements,
        "branches_pct": (
            _pct(branches_covered, branches_total)
            if branches_covered is not None and branches_total is not None
            else None
        ),
        "branches_covered": branches_covered,
        "branches_total": branches_total,
    }

    files_raw = payload.get("files")
    if not isinstance(files_raw, dict):
        return totals, []

    package_stats: dict[str, list[int]] = {}
    for file_path, file_data in files_raw.items():
        if not isinstance(file_data, dict):
            continue
        summary = file_data.get("summary")
        if not isinstance(summary, dict):
            continue
        file_covered = summary.get("covered_lines")
        file_total = summary.get("num_statements")
        if not isinstance(file_covered, int) or not isinstance(file_total, int):
            continue
        normalized = str(file_path).replace("\\", "/")
        if normalized.startswith("apps/"):
            package = normalized.split("/", 2)[1]
            package_key = f"apps.{package}"
        elif normalized.startswith("core/"):
            parts = normalized.split("/")
            package_key = f"core.{parts[1]}" if len(parts) > 2 else "core"
        else:
            package_key = normalized.split("/")[0]
        bucket = package_stats.setdefault(package_key, [0, 0])
        bucket[0] += file_covered
        bucket[1] += file_total

    rows: list[PackageCoverageRow] = []
    for package, (covered, total) in package_stats.items():
        if total <= 0:
            continue
        lines_pct = _pct(covered, total)
        if lines_pct is None:
            continue
        rows.append(
            {
                "package": package,
                "lines_pct": lines_pct,
                "lines_covered": covered,
                "lines_total": total,
            }
        )
    rows.sort(key=lambda row: (row["lines_pct"], row["package"]))
    return totals, rows[:10]


def _parse_lcov(lcov_path: Path) -> CoverageTotals:
    lines_found = 0
    lines_hit = 0
    branches_found = 0
    branches_hit = 0
    for raw_line in lcov_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("LF:"):
            lines_found += int(line[3:])
        elif line.startswith("LH:"):
            lines_hit += int(line[3:])
        elif line.startswith("BRF:"):
            branches_found += int(line[4:])
        elif line.startswith("BRH:"):
            branches_hit += int(line[4:])
    return {
        "lines_pct": _pct(lines_hit, lines_found),
        "lines_covered": lines_hit,
        "lines_total": lines_found,
        "branches_pct": _pct(branches_hit, branches_found),
        "branches_covered": branches_hit,
        "branches_total": branches_found,
    }


def _find_lcov_file(js_dir: Path) -> Path | None:
    if not js_dir.is_dir():
        return None
    direct = js_dir / "lcov.info"
    if direct.is_file():
        return direct
    matches = sorted(js_dir.rglob("lcov.info"))
    if matches:
        return matches[0]
    return None


def _empty_totals() -> CoverageTotals:
    return {
        "lines_pct": None,
        "lines_covered": None,
        "lines_total": None,
        "branches_pct": None,
        "branches_covered": None,
        "branches_total": None,
    }


def _load_previous_summary(current_run_id: str) -> CoverageSummary | None:
    latest_link = _REPORTS_ROOT / "latest"
    if not latest_link.exists():
        return None
    previous_dir = latest_link.resolve()
    if previous_dir.name == current_run_id:
        return None
    summary_path = previous_dir / "summary.json"
    if not summary_path.is_file():
        return None
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return cast(CoverageSummary, payload)


def _delta_metric(
    current: float | None,
    previous: float | None,
) -> float | None:
    if current is None or previous is None:
        return None
    return round(current - previous, 2)


def _build_summary(run_dir: Path) -> CoverageSummary:
    meta = _load_meta(run_dir)
    python_summary_path = run_dir / "python" / "summary.json"
    if python_summary_path.is_file():
        python_totals, low_packages = _parse_python_summary(python_summary_path)
    else:
        python_totals = _empty_totals()
        low_packages = []

    lcov_path = _find_lcov_file(run_dir / "js")
    if lcov_path is not None:
        js_totals = _parse_lcov(lcov_path)
        js_summary_path = run_dir / "js" / "summary.json"
        js_summary_path.parent.mkdir(parents=True, exist_ok=True)
        js_summary_path.write_text(
            json.dumps(js_totals, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        js_totals = _empty_totals()

    previous = _load_previous_summary(run_dir.name)
    delta: dict[str, object] = {"has_previous": previous is not None}
    if previous is not None:
        prev_python = previous.get("python")
        prev_js = previous.get("js")
        if isinstance(prev_python, dict):
            delta["previous_run_id"] = previous.get("run_id")
            delta["python_lines_pct_delta"] = _delta_metric(
                python_totals.get("lines_pct"),
                prev_python.get("lines_pct") if isinstance(prev_python.get("lines_pct"), (int, float)) else None,
            )
        if isinstance(prev_js, dict):
            delta["js_lines_pct_delta"] = _delta_metric(
                js_totals.get("lines_pct"),
                prev_js.get("lines_pct") if isinstance(prev_js.get("lines_pct"), (int, float)) else None,
            )

    summary: CoverageSummary = {
        "run_id": run_dir.name,
        "reported_at": datetime.now(UTC).isoformat(),
        "python": python_totals,
        "js": js_totals,
        "python_packages_low": low_packages,
        "delta_vs_previous": delta,
        "meta": meta,
        "paths": {
            "report_html": "report.html",
            "python_html": "python/html/index.html",
            "js_html": "js/index.html",
            "python_summary": "python/summary.json",
            "js_summary": "js/summary.json",
        },
    }
    return summary


def _format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def _format_ratio(totals: CoverageTotals) -> str:
    covered = totals.get("lines_covered")
    total = totals.get("lines_total")
    pct = totals.get("lines_pct")
    if covered is None or total is None:
        return _format_pct(pct)
    return f"{_format_pct(pct)} ({covered}/{total})"


def _render_terminal(summary: CoverageSummary) -> str:
    lines: list[str] = []
    lines.append("=== Test coverage (full) ===")
    lines.append(f"Run: {summary['run_id']}")
    python = summary["python"]
    js = summary["js"]
    lines.append(f"Python (apps+core): {_format_ratio(python)}")
    if python.get("branches_pct") is not None:
        lines.append(
            f"  branches: {_format_pct(python.get('branches_pct'))} "
            f"({python.get('branches_covered')}/{python.get('branches_total')})"
        )
    lines.append(f"JS (core/frontend unit): {_format_ratio(js)}")
    if js.get("branches_pct") is not None:
        lines.append(
            f"  branches: {_format_pct(js.get('branches_pct'))} "
            f"({js.get('branches_covered')}/{js.get('branches_total')})"
        )

    low_packages = summary.get("python_packages_low")
    if isinstance(low_packages, list) and low_packages:
        lines.append("")
        lines.append("Python lowest packages (lines %):")
        for row in low_packages[:5]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"  {row.get('package', ''):<24} "
                f"{_format_pct(row.get('lines_pct') if isinstance(row.get('lines_pct'), (int, float)) else None)}"
            )

    delta = summary.get("delta_vs_previous")
    if isinstance(delta, dict) and delta.get("has_previous"):
        lines.append("")
        lines.append(f"Delta vs {delta.get('previous_run_id', 'previous')}:")
        py_delta = delta.get("python_lines_pct_delta")
        js_delta = delta.get("js_lines_pct_delta")
        if isinstance(py_delta, (int, float)):
            sign = "+" if py_delta >= 0 else ""
            lines.append(f"  Python lines: {sign}{py_delta:.2f} pp")
        if isinstance(js_delta, (int, float)):
            sign = "+" if js_delta >= 0 else ""
            lines.append(f"  JS lines: {sign}{js_delta:.2f} pp")

    lines.append("")
    for note in summary.get("meta", {}).get("notes", []):
        if isinstance(note, str):
            lines.append(note)
    lines.append("HTML: reports/coverage/latest/report.html")
    return "\n".join(lines)


def _render_html(summary: CoverageSummary, *, run_dir: Path) -> str:
    def esc(value: object) -> str:
        return html.escape(str(value))

    python = summary["python"]
    js = summary["js"]
    sections: list[str] = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>Test coverage report</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;margin:2rem;}",
        "table{border-collapse:collapse;margin:1rem 0;}",
        "th,td{border:1px solid #ccc;padding:0.4rem 0.8rem;}",
        "</style></head><body>",
        "<h1>Test coverage report</h1>",
        f"<p>Run: <code>{esc(summary['run_id'])}</code></p>",
        f"<p>Reported: {esc(summary.get('reported_at', ''))}</p>",
        "<h2>Summary</h2>",
        "<table><tr><th>Scope</th><th>Lines</th><th>Branches</th></tr>",
        "<tr>",
        "<td>Python (apps+core)</td>",
        f"<td>{esc(_format_ratio(python))}</td>",
        f"<td>{esc(_format_pct(python.get('branches_pct')))}</td>",
        "</tr>",
        "<tr>",
        "<td>JS (Vitest unit)</td>",
        f"<td>{esc(_format_ratio(js))}</td>",
        f"<td>{esc(_format_pct(js.get('branches_pct')))}</td>",
        "</tr>",
        "</table>",
        "<h2>Details</h2><ul>",
        "<li><a href='python/html/index.html'>Python HTML coverage</a></li>",
    ]
    js_html_path = run_dir / "js" / "index.html"
    if js_html_path.is_file():
        sections.append("<li><a href='js/index.html'>JS HTML coverage</a></li>")
    sections.append("</ul>")

    low_packages = summary.get("python_packages_low")
    if isinstance(low_packages, list) and low_packages:
        sections.append("<h2>Python lowest packages</h2><table>")
        sections.append("<tr><th>Package</th><th>Lines %</th><th>Covered</th><th>Total</th></tr>")
        for row in low_packages:
            if not isinstance(row, dict):
                continue
            sections.append(
                "<tr>"
                f"<td>{esc(row.get('package'))}</td>"
                f"<td>{esc(row.get('lines_pct'))}</td>"
                f"<td>{esc(row.get('lines_covered'))}</td>"
                f"<td>{esc(row.get('lines_total'))}</td>"
                "</tr>"
            )
        sections.append("</table>")

    delta = summary.get("delta_vs_previous")
    if isinstance(delta, dict) and delta.get("has_previous"):
        sections.append("<h2>Delta vs previous run</h2><ul>")
        sections.append(f"<li>previous_run_id: {esc(delta.get('previous_run_id'))}</li>")
        sections.append(f"<li>python_lines_pct_delta: {esc(delta.get('python_lines_pct_delta'))}</li>")
        sections.append(f"<li>js_lines_pct_delta: {esc(delta.get('js_lines_pct_delta'))}</li>")
        sections.append("</ul>")

    notes = summary.get("meta", {}).get("notes")
    if isinstance(notes, list) and notes:
        sections.append("<h2>Scope notes</h2><ul>")
        for note in notes:
            if isinstance(note, str):
                sections.append(f"<li>{esc(note)}</li>")
        sections.append("</ul>")

    sections.append("</body></html>")
    return "".join(sections)


def _update_latest_symlink(run_dir: Path) -> None:
    latest_link = _REPORTS_ROOT / "latest"
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    latest_link.symlink_to(run_dir.name)


def cmd_report(run_id: str) -> Path:
    run_dir = _run_dir(run_id)
    if not run_dir.is_dir():
        raise RuntimeError(f"run dir not found: {run_dir}")

    _combine_python_coverage(run_dir)
    _export_python_coverage(run_dir)
    summary = _build_summary(run_dir)
    summary_path = run_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_html_path = run_dir / "report.html"
    report_html_path.write_text(_render_html(summary, run_dir=run_dir), encoding="utf-8")
    _update_latest_symlink(run_dir)
    print(_render_terminal(summary))
    return report_html_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test coverage report for make test")
    subparsers = parser.add_subparsers(dest="command", required=True)

    reset_parser = subparsers.add_parser("reset", help="Prepare coverage run directory")
    reset_parser.add_argument("--run-id", required=True)
    reset_parser.add_argument("--workers", default=None)

    report_parser = subparsers.add_parser("report", help="Finalize and print coverage report")
    report_parser.add_argument("--run-id", required=True)

    args = parser.parse_args(argv)
    if args.command == "reset":
        cmd_reset(args.run_id, workers=args.workers)
        return 0
    if args.command == "report":
        cmd_report(args.run_id)
        return 0
    raise RuntimeError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
