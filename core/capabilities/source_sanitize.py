"""Нормализация source-кода перед сохранением/передачей в isolated code runner."""

from __future__ import annotations


def reject_forbidden_platform_imports(code: str) -> str:
    """Отклоняет source с import apps.* / core.*: пользовательский код не импортирует платформу.

    Возвращает исходный code без изменений, если запрещённых строк нет.
    """
    forbidden_lines: list[str] = []
    for line_number, line in enumerate(code.split("\n"), start=1):
        stripped = line.strip()
        if (
            stripped.startswith("from apps.")
            or stripped.startswith("from core.")
            or stripped.startswith("import apps")
            or stripped.startswith("import core")
        ):
            forbidden_lines.append(f"{line_number}: {stripped}")

    if forbidden_lines:
        listed = "\n".join(forbidden_lines)
        raise ValueError(
            "User source must not import platform modules (apps.* / core.*). "
            + f"Forbidden lines:\n{listed}"
        )
    return code
