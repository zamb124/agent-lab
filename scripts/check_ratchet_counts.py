#!/usr/bin/env python3
"""
Ratchet-гейт: счётчики технического долга не растут.

Каждая метрика — regex по файлам `apps/`, `core/` (или `tests/`), baseline —
`scripts/ratchet_baseline.json`. Рост счётчика — FAIL. Снижение — OK с подсказкой
обновить baseline (`--update`), чтобы новый минимум стал обязательным.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "scripts" / "ratchet_baseline.json"
SKIP_PARTS: frozenset[str] = frozenset({"vendor", "__pycache__", "desktop", "node_modules"})


@dataclass(frozen=True)
class RatchetMetric:
    name: str
    roots: tuple[str, ...]
    pattern: str
    rule: str


METRICS: tuple[RatchetMetric, ...] = (
    RatchetMetric("cast_calls", ("apps", "core"), r"\bcast\(", "main.mdc: Any/cast запрещены — лечить источник потери типа"),
    RatchetMetric("type_ignore", ("apps", "core"), r"#\s*type:\s*ignore", "main.mdc: type: ignore не лечит потерю типа"),
    RatchetMetric("object_annotations", ("apps", "core"), r":\s*object\b|\[object\]|-> object\b", "main.mdc: голый object как тип запрещён"),
    RatchetMetric("os_environ", ("apps", "core"), r"\bos\.(environ|getenv)\b", "configuration.mdc: только Pydantic Settings"),
    RatchetMetric("except_pass", ("apps", "core"), r"except[^\n]*:\n\s+pass\b", "main.mdc: проглоченное исключение"),
    RatchetMetric("force_global", ("apps", "core"), r"force_global\s*=\s*True", "database.mdc: доступ через репозиторий с company_id из контекста"),
    RatchetMetric("raw_storage_in_services", ("apps",), r"^\s*(?!.*repositories).*\bStorage\(db_url", "database.mdc: Storage — приватный слой репозитория"),
    RatchetMetric("http_exception_in_services", ("apps",), r"raise HTTPException\(", "architecture.mdc: HTTPException только в api/, в op_*/services — WsCommandError/boundary errors"),
    RatchetMetric("logger_fstring", ("apps", "core"), r"logger\.(debug|info|warning|error|exception|critical)\(\s*f[\"']", "logging.mdc: event-id + kwargs вместо f-строк"),
    RatchetMetric("tests_monkeypatch_internal", ("tests",), r"monkeypatch\.setattr\(\s*[\"']?(core|apps)\.", "testing_invariants.mdc: внутренние компоненты не мокаются"),
    RatchetMetric("tests_asyncmock", ("tests",), r"\bAsyncMock\(", "testing_invariants.mdc: единственный мок — MockLLM"),
    RatchetMetric("tests_skip_markers", ("tests",), r"pytest\.mark\.skip\(|pytest\.skip\(", "testing.mdc: skip — только fail-loud с причиной инфраструктуры"),
)


def _files(roots: tuple[str, ...]) -> list[Path]:
    result: list[Path] = []
    for root in roots:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            if SKIP_PARTS & set(path.parts):
                continue
            result.append(path)
    return result


def collect_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for metric in METRICS:
        regex = re.compile(metric.pattern, re.MULTILINE)
        total = 0
        for path in _files(metric.roots):
            total += len(regex.findall(path.read_text(encoding="utf-8")))
        counts[metric.name] = total
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--update", action="store_true", help="записать текущие счётчики как baseline")
    args = parser.parse_args()
    counts = collect_counts()
    if args.update or not BASELINE_PATH.exists():
        BASELINE_PATH.write_text(json.dumps(counts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"check_ratchet_counts: baseline записан ({len(counts)} метрик)")
        return 0
    baseline_raw = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if not isinstance(baseline_raw, dict):
        raise SystemExit(f"{BASELINE_PATH}: ожидается JSON-объект")
    rules = {metric.name: metric.rule for metric in METRICS}
    failures: list[str] = []
    improvements: list[str] = []
    for name, current in counts.items():
        allowed = baseline_raw.get(name)
        if not isinstance(allowed, int):
            failures.append(f"{name}: нет в baseline — запусти --update")
            continue
        if current > allowed:
            failures.append(f"{name}: {current} > {allowed} — {rules[name]}")
        elif current < allowed:
            improvements.append(f"{name}: {current} < {allowed}")
    if failures:
        print("check_ratchet_counts: FAIL — долг вырос:")
        for line in failures:
            print(f"  {line}")
        return 1
    if improvements:
        print("check_ratchet_counts: долг снизился, зафиксируй новый минимум `--update`:")
        for line in improvements:
            print(f"  {line}")
    print(f"check_ratchet_counts: OK ({len(counts)} метрик)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
