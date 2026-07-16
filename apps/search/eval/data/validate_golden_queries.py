"""Проверка golden set: каждый URL должен отвечать HTTP 2xx/3xx.

Запуск:
    uv run python apps/search/eval/data/validate_golden_queries.py

Golden set — только ручная разметка. Автогенерация query→URL запрещена.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

from apps.search.eval.harness import load_golden_queries

_DATA_DIR = Path(__file__).resolve().parent
_GOLDEN_PATH = _DATA_DIR / "golden_queries.jsonl"


def validate_urls(*, timeout_seconds: float = 15.0) -> list[str]:
    queries = load_golden_queries(_GOLDEN_PATH)
    errors: list[str] = []
    with httpx.Client(
        timeout=timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": "runet-eval-validator/1.0"},
    ) as client:
        for eval_query in queries:
            for rel in eval_query.relevances:
                try:
                    response = client.get(rel.url)
                except httpx.HTTPError as exc:
                    errors.append(f"{eval_query.query_id}: {rel.url} — {exc}")
                    continue
                if response.status_code >= 400:
                    errors.append(
                        f"{eval_query.query_id}: {rel.url} — HTTP {response.status_code}",
                    )
    return errors


def main() -> None:
    queries = load_golden_queries(_GOLDEN_PATH)
    rare = sum(1 for q in queries if q.query_type == "rare_term")
    print(f"queries={len(queries)} rare_term={rare} path={_GOLDEN_PATH}")
    errors = validate_urls()
    if errors:
        for line in errors:
            print(f"FAIL {line}", file=sys.stderr)
        raise SystemExit(1)
    print("OK: all relevance URLs reachable")


if __name__ == "__main__":
    main()
