#!/usr/bin/env python3
"""CI: strict rerank boundaries.

HTTP-клиент реранка живёт только в ``core/ai/rerank_client.py``.
RAG post-retrieval orchestration живёт только в ``core/rag/post_retrieval_rerank.py``.
Параллельные HTTP-клиенты реранка в ``apps/**`` запрещены.

Выход: 0 — ОК, 1 — нарушение.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_RAG_CANON = "core/rag/post_retrieval_rerank.py"
_AI_CANON = "core/ai/rerank_client.py"
_SELF = "scripts/check_rag_post_retrieval_rerank_single.py"

_MARKER_ALLOWED_PATHS = {
    "class AIRerankerHTTPClient": _AI_CANON,
    "class AIRerankerClientError": _AI_CANON,
    "async def apply_rerank_after_retrieve(": _RAG_CANON,
    "async def apply_rerank_after_retrieve_grouped(": _RAG_CANON,
}

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
        if rel in (_AI_CANON, _RAG_CANON, _SELF):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for marker, allowed_path in _MARKER_ALLOWED_PATHS.items():
            if marker in content:
                violations.append(f"  {rel}: найдено {marker!r} (разрешено только в {allowed_path})")

    if violations:
        print("check_rag_post_retrieval_rerank_single: FAILED", file=sys.stderr)
        print(
            "Rerank HTTP — только core/ai/rerank_client.py; RAG orchestration — только core/rag/post_retrieval_rerank.py.",
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
