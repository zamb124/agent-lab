#!/usr/bin/env python3
"""Нарушения ratchet-метрик по файлам.

Метрики, корни и регэкспы берутся из `scripts/check_ratchet_counts.py` (`METRICS`),
лимиты — из `scripts/ratchet_baseline.json`. Без аргументов печатает сводку
«метрика: текущее / baseline» и топ файлов; с именем метрики — все `файл:строка`.

Запуск: `uv run python .cursor/skills/refactor-engineer/scripts/ratchet_list.py [<metric>] [--top N]`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
GATE = REPO / "scripts" / "check_ratchet_counts.py"
BASELINE = REPO / "scripts" / "ratchet_baseline.json"


def load_gate():
    spec = importlib.util.spec_from_file_location("check_ratchet_counts", GATE)
    if spec is None or spec.loader is None:
        raise SystemExit(f"не загружается {GATE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metric", nargs="?", help="имя метрики из METRICS")
    parser.add_argument("--top", type=int, default=5, help="сколько файлов показать в сводке")
    args = parser.parse_args()
    gate = load_gate()
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    metrics = [metric for metric in gate.METRICS if args.metric in (None, metric.name)]
    if not metrics:
        names = ", ".join(metric.name for metric in gate.METRICS)
        raise SystemExit(f"нет метрики {args.metric}; есть: {names}")
    for metric in metrics:
        regex = re.compile(metric.pattern, re.MULTILINE)
        hits: list[tuple[str, int]] = []
        for path in gate._files(metric.roots):
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(REPO).as_posix()
            if metric.name == "os_environ" and gate.os_environ_path_allowed(rel):
                continue
            for match in regex.finditer(text):
                hits.append((rel, text.count("\n", 0, match.start()) + 1))
        limit = baseline.get(metric.name)
        marker = "  РОСТ" if isinstance(limit, int) and len(hits) > limit else ""
        print(f"{metric.name}: {len(hits)} / baseline {limit}{marker} — {metric.rule}")
        if args.metric:
            for rel, line in hits:
                print(f"  {rel}:{line}")
        else:
            for rel, count in Counter(rel for rel, _ in hits).most_common(args.top):
                print(f"  {count:4d}  {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
