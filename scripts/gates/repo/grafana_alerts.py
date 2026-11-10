#!/usr/bin/env python3
"""CI gate: схема провижининга ``deploy/helm/agent-lab/files/grafana-alerts/*.yaml``.

Grafana 13 падает panic ``assignment to entry in nil map`` при правиле,
у которого запрос без ``model`` (поле съехало внутрь ``relativeTimeRange``
отступом) — CrashLoopBackOff на старте и полная потеря алертинга. YAML
валиден, helm lint это не ловит, поэтому схема проверяется здесь.

Инварианты:
1. Каждый элемент ``data[]`` имеет ``refId``, ``datasourceUid``,
   ``relativeTimeRange.from/to`` и непустой dict ``model``.
2. ``relativeTimeRange`` содержит только ``from``/``to`` — съехавшие
   поля запроса (model/datasourceUid) это прямой регресс паники.
3. ``condition`` правила — существующий ``refId`` из его ``data``.
4. У правила есть ``uid`` (уникальный на файл), ``title``, ``for``,
   ``noDataState``/``execErrState`` из допустимых значений и
   ``labels.severity``.
5. ``datasourceUid`` — один из provisioned источников или ``__expr__``.
6. ``model.refId`` совпадает с ``refId`` элемента — Grafana требует паритет.
7. У группы есть ``name``, ``folder``, ``interval`` — без них группа
   не провижинится и правила молча не доедут.
8. Для loki-запросов ``relativeTimeRange.from`` + максимальный range-
   селектор ``[Nh]`` в ``model.expr`` не превышает лимит Loki ``1d1h`` —
   Grafana расширяет интервал запроса на range-вектор; переполнение даёт
   ``sse.dataQueryError``, правило висит в health=error и не алертит.
9. Loki-правило на отношении (``sum(...) / sum(...)``) или квантиле
   (``quantile_over_time``) обязано иметь volume floor — math-условие
   с ``&&`` на второй запрос объёма. Процент/квантиль на малой выборке
   — шум: 1 ошибка из 2 вызовов даёт 50%, один медленный запрос = p99.
"""

from __future__ import annotations

import re
import sys

import yaml

from scripts.gates.kit import REPO_ROOT, report

ALERTS_DIR = REPO_ROOT / "deploy" / "helm" / "agent-lab" / "files" / "grafana-alerts"

_DATASOURCES = {"loki", "prometheus", "__expr__"}
_NO_DATA_STATES = {"Alerting", "NoData", "OK"}
_EXEC_ERR_STATES = {"Alerting", "Error", "OK"}
_SEVERITIES = {"critical", "warning"}
_LOKI_MAX_QUERY_SECONDS = 25 * 60 * 60
_RANGE_RE = re.compile(r"\[(\d+)([smhd])\]")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_RATIO_OR_QUANTILE_RE = re.compile(r"quantile_over_time\(|/\s*\(?\s*sum")


def _check_rule(group: str, rule: dict[str, object], uids: set[str], errors: list[str]) -> None:
    uid = rule.get("uid")
    where = f"{group}/{uid or rule.get('title') or '?'}"
    if not isinstance(uid, str) or not uid:
        errors.append(f"{where}: отсутствует uid")
    elif uid in uids:
        errors.append(f"{where}: uid не уникален")
    else:
        uids.add(uid)
    for key in ("title", "condition", "for", "noDataState", "execErrState"):
        if key not in rule:
            errors.append(f"{where}: отсутствует поле {key}")
    if rule.get("noDataState") not in _NO_DATA_STATES:
        errors.append(f"{where}: noDataState={rule.get('noDataState')} вне {_NO_DATA_STATES}")
    if rule.get("execErrState") not in _EXEC_ERR_STATES:
        errors.append(f"{where}: execErrState={rule.get('execErrState')} вне {_EXEC_ERR_STATES}")
    labels = rule.get("labels")
    if not isinstance(labels, dict) or labels.get("severity") not in _SEVERITIES:
        errors.append(f"{where}: labels.severity отсутствует или вне {_SEVERITIES}")
    data = rule.get("data")
    if not isinstance(data, list) or not data:
        errors.append(f"{where}: data пуст или не список")
        return
    ref_ids: set[str] = set()
    for i, entry in enumerate(data):
        _check_query(f"{where} data[{i}]", entry, ref_ids, errors)
    condition = rule.get("condition")
    if condition and condition not in ref_ids:
        errors.append(f"{where}: condition={condition} не совпадает ни с одним refId")
    is_ratio_or_quantile = any(
        e.get("datasourceUid") == "loki"
        and isinstance(e.get("model"), dict)
        and _RATIO_OR_QUANTILE_RE.search(str(e["model"].get("expr") or ""))
        for e in data
        if isinstance(e, dict)
    )
    if is_ratio_or_quantile:
        maths = [
            str(e["model"].get("expression") or "")
            for e in data
            if isinstance(e, dict) and isinstance(e.get("model"), dict) and e["model"].get("type") == "math"
        ]
        if not any("&&" in expr for expr in maths):
            errors.append(f"{where}: отношение/квантиль без volume floor — math-условие должно содержать '&& $volumeRef'")


def _check_query(where: str, entry: object, ref_ids: set[str], errors: list[str]) -> None:
    if not isinstance(entry, dict):
        errors.append(f"{where}: запрос не объект")
        return
    for key in ("refId", "datasourceUid", "relativeTimeRange", "model"):
        if key not in entry:
            errors.append(f"{where}: отсутствует поле {key} — Grafana падает panic при провижининге")
    ref_id = entry.get("refId")
    if isinstance(ref_id, str):
        ref_ids.add(ref_id)
    if entry.get("datasourceUid") not in _DATASOURCES:
        errors.append(f"{where}: datasourceUid={entry.get('datasourceUid')} вне {_DATASOURCES}")
    time_range = entry.get("relativeTimeRange")
    if isinstance(time_range, dict):
        if not {"from", "to"} <= set(time_range):
            errors.append(f"{where}: relativeTimeRange без from/to")
        stray = set(time_range) - {"from", "to"}
        if stray:
            errors.append(f"{where}: поля {sorted(stray)} съехали внутрь relativeTimeRange")
    else:
        errors.append(f"{where}: relativeTimeRange не объект")
    model = entry.get("model")
    if not isinstance(model, dict) or not model:
        errors.append(f"{where}: model пуст или не объект — panic при вставке правила")
    elif model.get("refId") != ref_id:
        errors.append(f"{where}: model.refId={model.get('refId')} != refId={ref_id}")
    if entry.get("datasourceUid") == "loki" and isinstance(time_range, dict) and isinstance(model, dict):
        expr = model.get("expr")
        if isinstance(expr, str):
            ranges = [int(n) * _UNIT_SECONDS[u] for n, u in _RANGE_RE.findall(expr)]
            window = int(time_range.get("from") or 0) + max(ranges, default=0)
            if window > _LOKI_MAX_QUERY_SECONDS:
                errors.append(
                    f"{where}: from + range {window}s > лимита Loki {_LOKI_MAX_QUERY_SECONDS}s — правило уйдёт в health=error"
                )


def main() -> int:
    errors: list[str] = []
    uids: set[str] = set()
    files = sorted(ALERTS_DIR.glob("*.yaml"))
    if not files:
        return report("grafana_alerts", [f"{ALERTS_DIR}: нет *.yaml провижининга"])
    for path in files:
        doc = yaml.safe_load(path.read_text())
        if not isinstance(doc, dict) or "groups" not in doc:
            continue  # contact-points / notification-policies — другая схема
        groups = doc["groups"]
        if not isinstance(groups, list) or not groups:
            errors.append(f"{path.name}: groups пуст или не список")
            continue
        for group in groups:
            name = group.get("name", "?") if isinstance(group, dict) else "?"
            for key in ("name", "folder", "interval"):
                if key not in group:
                    errors.append(f"{path.name}/{name}: группа без поля {key}")
            rules = group.get("rules")
            if not isinstance(rules, list) or not rules:
                errors.append(f"{path.name}/{name}: rules пуст или не список")
                continue
            for rule in rules:
                if not isinstance(rule, dict):
                    errors.append(f"{path.name}/{name}: правило не объект")
                    continue
                _check_rule(f"{path.name}:{name}", rule, uids, errors)
    return report("grafana_alerts", errors)


if __name__ == "__main__":
    sys.exit(main())
