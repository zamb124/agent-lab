"""
ValidationError из воркера TaskIQ при передаче в API часто теряет тип и .errors();
кодируем список ошибок в str(ValueError) с фиксированным префиксом.
"""

from __future__ import annotations

import json
from typing import Any

PREFIX = "TASKIQ_ANALYZE_VALIDATION_ERROR:"


def format_validation_for_taskiq(exc_errors: list[dict[str, Any]]) -> str:
    return PREFIX + json.dumps(exc_errors, default=str)


def parse_validation_from_task_message(message: str) -> list[dict[str, Any]] | None:
    if not message.startswith(PREFIX):
        return None
    raw = message[len(PREFIX) :]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, list):
        return parsed
    return None
