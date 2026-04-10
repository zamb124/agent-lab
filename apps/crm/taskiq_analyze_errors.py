"""
ValidationError из воркера TaskIQ при передаче в API часто теряет тип и .errors();
кодируем список ошибок в str(ValueError) с фиксированным префиксом.
"""

from __future__ import annotations

import json
from typing import Any

PREFIX = "TASKIQ_ANALYZE_VALIDATION_ERROR:"

PREFIX_MENTIONED_ENTITY_SHORT_DESCRIPTION = (
    "TASKIQ_ANALYZE_MENTIONED_ENTITY_SHORT_DESCRIPTION:"
)


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


def format_mentioned_entity_short_description_error(
    *,
    entity_id: str,
    entity_name: str,
    entity_type: str,
    min_len: int,
) -> str:
    payload = {
        "entity_id": entity_id,
        "entity_name": entity_name,
        "entity_type": entity_type,
        "min_len": min_len,
    }
    return PREFIX_MENTIONED_ENTITY_SHORT_DESCRIPTION + json.dumps(
        payload,
        ensure_ascii=False,
    )


def parse_mentioned_entity_short_description_from_task_message(
    message: str,
) -> dict[str, Any] | None:
    if not message.startswith(PREFIX_MENTIONED_ENTITY_SHORT_DESCRIPTION):
        return None
    raw = message[len(PREFIX_MENTIONED_ENTITY_SHORT_DESCRIPTION) :]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    entity_id = parsed.get("entity_id")
    entity_name = parsed.get("entity_name")
    entity_type = parsed.get("entity_type")
    min_len = parsed.get("min_len")
    if (
        not isinstance(entity_id, str)
        or not entity_id.strip()
        or not isinstance(entity_name, str)
        or not isinstance(entity_type, str)
        or not isinstance(min_len, int)
        or min_len < 1
    ):
        return None
    return {
        "entity_id": entity_id.strip(),
        "entity_name": entity_name,
        "entity_type": entity_type,
        "min_len": min_len,
    }
