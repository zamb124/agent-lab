"""Нормализация source-кода перед сохранением/передачей в isolated code runner."""

from __future__ import annotations


def strip_forbidden_platform_import_lines(code: str) -> str:
    """Удаляет строки import из apps.* и core.*: пользовательский код не импортирует платформу."""
    lines = code.split("\n")
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("from apps.") or stripped.startswith("from core."):
            continue
        if stripped.startswith("import apps") or stripped.startswith("import core"):
            continue
        kept.append(line)
    return "\n".join(kept)
