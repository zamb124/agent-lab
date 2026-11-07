"""Probe every LogQL expression used by Grafana dashboards and alert rules against live Loki.

Answers "does this panel/alert actually receive data?" for the whole provisioned
observability surface. Read-only: executes instant/range queries, never mutates.

Usage:
    kubectl port-forward -n platform svc/loki 3100:3100
    uv run python -m scripts.observability.loki_probe --out /tmp/loki_probe.json
    uv run python -m scripts.observability.loki_probe --only 08-websocket --verbose
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARDS_DIR = REPO_ROOT / "deploy" / "helm" / "agent-lab" / "files" / "dashboards"
ALERTS_FILE = (
    REPO_ROOT / "deploy" / "helm" / "agent-lab" / "files" / "grafana-alerts" / "alert-rules.yaml"
)
LOKI_DATASOURCE_UID = "loki"

_STALE_AFTER_SECONDS = 2 * 3600
_WORKERS = 6


@dataclass
class ProbeTarget:
    source: str  # dashboard file name or "alert-rules.yaml"
    kind: str  # "panel" | "alert"
    dashboard: str  # dashboard title or alert group
    name: str  # panel title / alert title
    ref: str  # panel id / alert uid + refId
    expr: str


@dataclass
class ProbeResult:
    target: ProbeTarget
    status: str  # ok | stale | empty | error | skipped
    series: int = 0
    entries: int = 0
    last_ts: float | None = None
    error: str | None = None
    detail: dict = field(default_factory=dict)


def _var_value(var: dict) -> str:
    current = var.get("current") or {}
    value = current.get("value")
    if isinstance(value, list):
        value = value[0] if value else ""
    if value not in (None, "", []):
        return str(value)
    options = var.get("options") or []
    if options:
        opt_value = options[0].get("value")
        if isinstance(opt_value, list):
            opt_value = opt_value[0] if opt_value else ""
        return str(opt_value or "")
    query = var.get("query") or ""
    if isinstance(query, dict):
        query = query.get("query", "")
    return ".*" if "label_values" in str(query) else ".+"


def _resolve_variables(dashboard: dict) -> dict[str, str]:
    values: dict[str, str] = {}
    for var in (dashboard.get("templating") or {}).get("list") or []:
        name = var.get("name")
        if not name:
            continue
        raw = _var_value(var)
        if raw == "$__all" or var.get("includeAll"):
            raw = ".+"
        if "," in raw:
            raw = "|".join(raw.split(","))
        values[name] = raw
    values.setdefault("service", ".+")
    return values


def _substitute_variables(expr: str, variables: dict[str, str]) -> str:
    resolved = expr.replace("$__range", "24h").replace("${__range}", "24h")
    resolved = resolved.replace("$__interval", "5m").replace("${__interval}", "5m")
    resolved = resolved.replace("$__rate_interval", "5m").replace("${__rate_interval}", "5m")
    resolved = resolved.replace("$__dashboard", "dashboard")
    for name, value in sorted(variables.items(), key=lambda kv: -len(kv[0])):
        resolved = resolved.replace(f"${{{name}}}", value).replace(f"${name}", value)
    return resolved


def iter_panel_targets() -> list[ProbeTarget]:
    targets: list[ProbeTarget] = []
    for path in sorted(DASHBOARDS_DIR.glob("*.json")):
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        variables = _resolve_variables(dashboard)
        for panel in dashboard.get("panels") or []:
            for idx, target in enumerate(panel.get("targets") or []):
                expr = target.get("expr") or target.get("query")
                if not expr:
                    continue
                ds = target.get("datasource") or panel.get("datasource") or {}
                uid = ds.get("uid") if isinstance(ds, dict) else ds
                if uid == "__expr__":
                    continue
                targets.append(
                    ProbeTarget(
                        source=path.name,
                        kind="panel",
                        dashboard=dashboard.get("title") or path.stem,
                        name=panel.get("title") or f"panel-{panel.get('id')}",
                        ref=f"p{panel.get('id')}/{target.get('refId', idx)}",
                        expr=_substitute_variables(expr, variables),
                    )
                )
    return targets


def iter_alert_targets() -> list[ProbeTarget]:
    data = yaml.safe_load(ALERTS_FILE.read_text(encoding="utf-8"))
    targets: list[ProbeTarget] = []
    for group in data.get("groups") or []:
        for rule in group.get("rules") or []:
            for query in rule.get("data") or []:
                if query.get("datasourceUid") == "__expr__":
                    continue
                expr = (query.get("model") or {}).get("expr")
                if not expr:
                    continue
                targets.append(
                    ProbeTarget(
                        source=ALERTS_FILE.name,
                        kind="alert",
                        dashboard=group.get("name") or "alerts",
                        name=f"{rule.get('uid')}: {rule.get('title')}",
                        ref=str(query.get("refId")),
                        expr=expr,
                    )
                )
    return targets


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _loki_get(base_url: str, path: str, params: dict[str, str], timeout: float = 30.0) -> dict:
    url = f"{base_url}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with _OPENER.open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _is_metric_query(expr: str) -> bool:
    return bool(
        re.search(
            r"\b(rate|count_over_time|sum_over_time|avg_over_time|quantile_over_time|"
            r"max_over_time|min_over_time|stddev_over_time|stdvar_over_time|"
            r"bytes_rate|bytes_over_time|absent_over_time|first_over_time|last_over_time)\s*\(",
            expr,
        )
    )


def _series_stats(matrix: list[dict]) -> tuple[int, float | None]:
    series = len(matrix)
    last_ts: float | None = None
    for stream in matrix:
        for ts_str, _value in stream.get("values") or []:
            ts = float(ts_str)
            if last_ts is None or ts > last_ts:
                last_ts = ts
    return series, last_ts


def _entries_stats(streams: list[dict]) -> tuple[int, float | None]:
    entries = 0
    last_ts: float | None = None
    for stream in streams:
        for ts_str, _line in stream.get("values") or []:
            entries += 1
            ts = int(ts_str) / 1e9
            if last_ts is None or ts > last_ts:
                last_ts = ts
    return entries, last_ts


def _raw_log_query(expr: str) -> str:
    """Strip metric machinery so a panel's selector can run as a plain log query.

    Keeps `{selector} | json | field filters`; drops `| unwrap ...` and anything
    after it (unwrap value/label_format stages are metric-only).
    """
    idx = expr.find("| unwrap")
    head = expr if idx == -1 else expr[:idx]
    # unwrap with conversion function is written `| unwrap <field>`; also drop
    # `| label_format` if it trailed unwrap usage in metric context.
    return head.strip()


def probe_target(base_url: str, target: ProbeTarget, start: float, end: float, step: int) -> ProbeResult:
    if _is_metric_query(target.expr):
        params = {
            "query": target.expr,
            "start": str(int(start)),
            "end": str(int(end)),
            "step": str(step),
        }
        result_kind = "matrix"
    else:
        params = {
            "query": target.expr,
            "start": str(int(start * 1e9)),
            "end": str(int(end * 1e9)),
            "limit": "500",
            "direction": "backward",
        }
        result_kind = "streams"
    try:
        payload = _loki_get(base_url, "/loki/api/v1/query_range", params)
    except Exception as exc:  # noqa: BLE001 - probe reports, never raises
        return ProbeResult(target=target, status="error", error=f"request: {exc}")

    if payload.get("status") != "success":
        return ProbeResult(target=target, status="error", error=str(payload.get("error") or payload))

    result = ((payload.get("data") or {}).get("result")) or []
    if result_kind == "matrix":
        series, last_ts = _series_stats(result)
        entries = 0
    else:
        entries, last_ts = _entries_stats(result)
        series = len(result)

    if not result:
        status = "empty"
    elif last_ts is not None and (end - last_ts) > _STALE_AFTER_SECONDS:
        status = "stale"
    else:
        status = "ok"
    probe = ProbeResult(target=target, status=status, series=series, entries=entries, last_ts=last_ts)

    # Empty metric result: distinguish "underlying events never happened" from
    # "events exist but the rate/quantile window missed them" (sparse traffic).
    if status == "empty" and result_kind == "matrix":
        raw = _raw_log_query(target.expr)
        if raw != target.expr or "| json" in raw:
            entries_raw, last_raw = _raw_entry_count(base_url, raw, start, end)
            probe.detail["raw_events"] = entries_raw
            if last_raw is not None:
                probe.last_ts = last_raw
            if entries_raw:
                probe.status = "sparse"
    return probe


def _raw_entry_count(base_url: str, raw_query: str, start: float, end: float) -> tuple[int, float | None]:
    try:
        payload = _loki_get(
            base_url,
            "/loki/api/v1/query_range",
            {
                "query": raw_query,
                "start": str(int(start * 1e9)),
                "end": str(int(end * 1e9)),
                "limit": "500",
                "direction": "backward",
            },
        )
    except Exception:  # noqa: BLE001 - raw check is best-effort
        return 0, None
    if payload.get("status") != "success":
        return 0, None
    return _entries_stats((payload.get("data") or {}).get("result") or [])


def _age_text(last_ts: float | None, end: float) -> str:
    if last_ts is None:
        return "-"
    minutes = int((end - last_ts) // 60)
    if minutes <= 0:
        return "now"
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    return f"{hours}h{minutes % 60}m" if hours < 24 else f"{hours // 24}d"


def _print_report(results: list[ProbeResult], end: float) -> None:
    current_source = None
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
        if result.target.source != current_source:
            current_source = result.target.source
            print(f"\n=== {current_source} ===")
        icon = {"ok": "OK ", "stale": "STL", "empty": "EMP", "error": "ERR", "skipped": "SKP", "sparse": "SPR"}.get(
            result.status, "???"
        )
        age = _age_text(result.last_ts, end)
        extra = f"series={result.series}" if result.series else f"entries={result.entries}"
        err = f"  error={result.error}" if result.error else ""
        print(f"  [{icon}] {result.target.name[:60]:<62} last={age:>6} {extra}{err}")
    print("\n=== summary ===")
    total = sum(counts.values())
    for status in ("ok", "stale", "sparse", "empty", "error", "skipped"):
        if counts.get(status):
            print(f"  {status}: {counts[status]}")
    print(f"  total: {total}")


def _serialize(results: list[ProbeResult], end: float) -> dict:
    return {
        "generated_at": datetime.fromtimestamp(end, UTC).isoformat(),
        "results": [
            {
                "source": r.target.source,
                "kind": r.target.kind,
                "dashboard": r.target.dashboard,
                "name": r.target.name,
                "ref": r.target.ref,
                "expr": r.target.expr,
                "status": r.status,
                "series": r.series,
                "entries": r.entries,
                "raw_events": r.detail.get("raw_events"),
                "last_ts": r.last_ts,
                "age": _age_text(r.last_ts, end),
                "error": r.error,
            }
            for r in results
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--loki-url", default="http://localhost:3100")
    parser.add_argument("--range-hours", type=float, default=24.0)
    parser.add_argument("--step", type=int, default=1800, help="matrix query step seconds")
    parser.add_argument("--only", default=None, help="substring filter on source file or dashboard name")
    parser.add_argument("--out", default=None, help="write JSON report to path")
    parser.add_argument("--verbose", action="store_true", help="print every probe as it finishes")
    args = parser.parse_args(argv)

    end = time.time()
    start = end - args.range_hours * 3600

    targets = iter_panel_targets() + iter_alert_targets()
    if args.only:
        needle = args.only.lower()
        targets = [t for t in targets if needle in t.source.lower() or needle in t.dashboard.lower()]
    if not targets:
        print("no targets matched", file=sys.stderr)
        return 1

    try:
        ready_request = urllib.request.Request(f"{args.loki_url}/ready")
        with _OPENER.open(ready_request, timeout=5.0):
            pass
    except Exception as exc:  # noqa: BLE001
        print(
            f"loki at {args.loki_url} unreachable: {exc}\n"
            "hint: kubectl port-forward -n platform svc/loki 3100:3100",
            file=sys.stderr,
        )
        return 1

    print(f"probing {len(targets)} targets against {args.loki_url} (range {args.range_hours}h)")
    results: list[ProbeResult | None] = [None] * len(targets)
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures = {
            pool.submit(probe_target, args.loki_url, t, start, end, args.step): i
            for i, t in enumerate(targets)
        }
        for future in futures:
            idx = futures[future]
            result = future.result()
            results[idx] = result
            if args.verbose:
                print(f"[{result.status:>6}] {result.target.source} :: {result.target.name}")

    ordered: list[ProbeResult] = [r for r in results if r is not None]
    _print_report(ordered, end)
    if args.out:
        out_path = Path(args.out)
        out_path.write_text(json.dumps(_serialize(ordered, end), indent=2, ensure_ascii=False))
        print(f"\nreport written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
