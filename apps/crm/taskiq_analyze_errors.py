"""
ValidationError из воркера TaskIQ при передаче в API часто теряет тип и .errors();
кодируем список ошибок в str(ValueError) с фиксированным префиксом.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TypedDict
from typing import cast as type_cast

PREFIX = "TASKIQ_ANALYZE_VALIDATION_ERROR:"

PREFIX_MENTIONED_ENTITY_SHORT_DESCRIPTION = "TASKIQ_ANALYZE_MENTIONED_ENTITY_SHORT_DESCRIPTION:"

type TaskiqValidationError = dict[str, object]


class MentionedEntityShortDescriptionError(TypedDict):
    entity_id: str
    entity_name: str
    entity_type: str
    min_len: int


def _as_json_object(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, object] = {}
    for key, item in type_cast(dict[object, object], value).items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result


def _as_json_object_list(value: object) -> list[TaskiqValidationError] | None:
    if not isinstance(value, list):
        return None
    items: list[TaskiqValidationError] = []
    for item in type_cast(list[object], value):
        item_obj = _as_json_object(item)
        if item_obj is None:
            return None
        items.append(item_obj)
    return items


def format_validation_for_taskiq(exc_errors: Sequence[Mapping[str, object]]) -> str:
    return PREFIX + json.dumps(list(exc_errors), default=str)


def parse_validation_from_task_message(message: str) -> list[TaskiqValidationError] | None:
    if not message.startswith(PREFIX):
        return None
    raw = message[len(PREFIX) :]
    try:
        parsed = type_cast(object, json.loads(raw))
    except json.JSONDecodeError:
        return None
    return _as_json_object_list(parsed)


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
) -> MentionedEntityShortDescriptionError | None:
    if not message.startswith(PREFIX_MENTIONED_ENTITY_SHORT_DESCRIPTION):
        return None
    raw = message[len(PREFIX_MENTIONED_ENTITY_SHORT_DESCRIPTION) :]
    try:
        parsed = type_cast(object, json.loads(raw))
    except json.JSONDecodeError:
        return None
    payload = _as_json_object(parsed)
    if payload is None:
        return None
    entity_id = payload.get("entity_id")
    entity_name = payload.get("entity_name")
    entity_type = payload.get("entity_type")
    min_len = payload.get("min_len")
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
