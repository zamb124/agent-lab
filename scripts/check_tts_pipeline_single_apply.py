#!/usr/bin/env python3
"""CI: проверяет, что TtsTextPipeline.transform вызывается ровно из одного места.

Единственное легальное место вызова — ``PronunciationAwareTTSClient`` в
``core/clients/tts_client.py``. Любой прямой импорт ``TtsTextPipeline`` или
``get_tts_text_pipeline`` в ``apps/**`` запрещён.

Выход: 0 — ОК, 1 — нарушение.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_ALLOWED_FILES = frozenset([
    "core/clients/tts_client.py",
    "core/clients/tts_pronunciation/pipeline.py",
    "core/clients/tts_pronunciation/__init__.py",
    # dry-run REST эндпоинт: единственное легальное использование pipeline вне PronunciationAwareTTSClient
    "apps/frontend/api/company_pronunciation_rules.py",
])

_FORBIDDEN_PATTERNS = [
    "TtsTextPipeline",
    "get_tts_text_pipeline",
]

_ALLOWED_PREFIXES_FOR_TESTS = ("tests/",)


def _is_allowed(path: Path, rel: str) -> bool:
    if rel in _ALLOWED_FILES:
        return True
    # В тестовых файлах прямое использование pipeline разрешено
    for prefix in _ALLOWED_PREFIXES_FOR_TESTS:
        if rel.startswith(prefix):
            return True
    return False


def main() -> int:
    violations: list[str] = []

    for py_file in ROOT.rglob("*.py"):
        if not py_file.is_file():
            continue
        rel = py_file.relative_to(ROOT).as_posix()
        # Пропускаем сам pipeline и допустимые файлы
        if _is_allowed(py_file, rel):
            continue
        # Только apps/ проверяем на запрет (tests исключены выше)
        if not rel.startswith("apps/"):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern in content:
                violations.append(f"  {rel}: запрещённый импорт/использование {pattern!r}")

    if violations:
        print("check_tts_pipeline_single_apply: FAILED", file=sys.stderr)
        print("TtsTextPipeline должен вызываться только из PronunciationAwareTTSClient.", file=sys.stderr)
        print("Нарушения:", file=sys.stderr)
        for v in violations:
            print(v, file=sys.stderr)
        return 1

    print("check_tts_pipeline_single_apply: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
