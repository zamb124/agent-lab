#!/usr/bin/env python3
"""CI: единственная реализация пост-retrieval реранка в core/rag.

Определения клиента и функций rerank-after-retrieve только в одном модуле
(см. константу ``_CANON`` ниже). Параллельные HTTP-клиенты реранка в ``apps/**``
запрещены (сервер ``apps/provider_litserve`` — не клиент).

Выход: 0 — ОК, 1 — нарушение.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_CANON = "core/rag/post_retrieval_rerank.py"
_SELF = "scripts/check_rag_post_retrieval_rerank_single.py"

_MARKERS = (
    "class RerankerHTTPClient",
    "class RerankerClientError",
    "async def apply_rerank_after_retrieve(",
    "async def apply_rerank_after_retrieve_grouped(",
)

_SKIP_PREFIXES = (
    ".venv/",
    "venv/",
    "documentation-dist/",
    "node_modules/",
)


def _skip(rel: str) -> bool:
    return any(rel.startswith(p) or f"/{p}" in rel for p in _SKIP_PREFIXES)


def main() -> int:
    violations: list[str] = []

    for py_file in ROOT.rglob("*.py"):
        if not py_file.is_file():
            continue
        rel = py_file.relative_to(ROOT).as_posix()
        if _skip(rel):
            continue
        if rel in (_CANON, _SELF):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for marker in _MARKERS:
            if marker in content:
                violations.append(f"  {rel}: найдено {marker!r} (разрешено только в {_CANON})")

    if violations:
        print("check_rag_post_retrieval_rerank_single: FAILED", file=sys.stderr)
        print(
            "Пост-retrieval реранк — только core/rag/post_retrieval_rerank.py (см. rag.mdc).",
            file=sys.stderr,
        )
        print("Нарушения:", file=sys.stderr)
        for v in violations:
            print(v, file=sys.stderr)
        return 1

    print("check_rag_post_retrieval_rerank_single: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
