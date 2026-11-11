#!/usr/bin/env python3
"""CI gate: схема провижининга ``deploy/helm/agent-lab/files/dashboards/*.json``.

Провижининг Grafana молча пропускает битый JSON или панель без datasource —
в UI появляется "dashboard provisioning failed" / пустые панели, а причина
видна только в логах графаны. Helm lint структуру не проверяет.

Инварианты:
1. Файл — валидный JSON-объект с ``uid`` (уникальный среди файлов), ``title``.
2. Каждая панель имеет ``type``, ``gridPos`` с h/w/x/y — без него Grafana
   укладывает панели в ноль и дашборд "схлопывается".
3. Не-row панель обязана иметь ``datasource.uid`` из provisioned источников
   (loki/prometheus/tempo) — литерал другого UID означает пустую панель.
4. Каждый ``targets[]`` имеет ``refId`` и непустой ``expr`` —
   Grafana-запрос без expr отдаёт "panel data error".
5. ``$__interval``/``$__range`` используются только в expr — в других полях
   это нераскрытый литерал.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.gates.kit import REPO_ROOT, report

DASHBOARDS_DIR = REPO_ROOT / "deploy" / "helm" / "agent-lab" / "files" / "dashboards"

_DATASOURCES = {"loki", "prometheus", "tempo"}
_VALID_TYPES = {
    "timeseries", "stat", "table", "logs", "piechart", "bargauge",
    "barchart", "gauge", "heatmap", "row", "text", "traces",
}


def _check_panel(where: str, panel: object, errors: list[str]) -> None:
    if not isinstance(panel, dict):
        errors.append(f"{where}: панель не объект")
        return
    ptype = panel.get("type")
    if ptype not in _VALID_TYPES:
        errors.append(f"{where}: type={ptype} вне {_VALID_TYPES}")
    grid = panel.get("gridPos")
    if not isinstance(grid, dict) or not {"h", "w", "x", "y"} <= set(grid):
        errors.append(f"{where}: gridPos без h/w/x/y")
    if ptype == "row":
        return
    ds = panel.get("datasource")
    if not isinstance(ds, dict) or ds.get("uid") not in _DATASOURCES:
        errors.append(f"{where}: datasource.uid={ds} вне {_DATASOURCES}")
    targets = panel.get("targets")
    if not isinstance(targets, list) or not targets:
        errors.append(f"{where}: targets пуст или не список")
        return
    for i, target in enumerate(targets):
        if not isinstance(target, dict):
            errors.append(f"{where} target[{i}]: не объект")
            continue
        if "refId" not in target:
            errors.append(f"{where} target[{i}]: без refId")
        expr = target.get("expr")
        if not isinstance(expr, str) or not expr.strip():
            errors.append(f"{where} target[{i}]: без expr")


def _check_dashboard(path: Path, uids: set[str], errors: list[str]) -> None:
    where = path.name
    try:
        doc = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        errors.append(f"{where}: невалидный JSON: {exc}")
        return
    if not isinstance(doc, dict):
        errors.append(f"{where}: не JSON-объект")
        return
    uid = doc.get("uid")
    if not isinstance(uid, str) or not uid:
        errors.append(f"{where}: отсутствует uid")
    elif uid in uids:
        errors.append(f"{where}: uid {uid} не уникален")
    else:
        uids.add(uid)
    if not doc.get("title"):
        errors.append(f"{where}: отсутствует title")
    panels = doc.get("panels")
    if not isinstance(panels, list) or not panels:
        errors.append(f"{where}: panels пуст или не список")
        return
    for i, panel in enumerate(panels):
        title = panel.get("title") if isinstance(panel, dict) else "?"
        _check_panel(f"{where} panel[{i}] {title}", panel, errors)


def main() -> int:
    errors: list[str] = []
    uids: set[str] = set()
    files = sorted(DASHBOARDS_DIR.glob("*.json"))
    if not files:
        return report("grafana_dashboards", [f"{DASHBOARDS_DIR}: нет *.json дашбордов"])
    for path in files:
        _check_dashboard(path, uids, errors)
    return report("grafana_dashboards", errors)


if __name__ == "__main__":
    sys.exit(main())
