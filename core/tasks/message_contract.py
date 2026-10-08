"""Типизированная граница для сообщений TaskIQ.

TaskIQ отдаёт labels, args и kwargs как динамические структуры SDK.
Платформенные метки — только строки; внутренние метки TaskIQ сохраняют
нативные типы для middleware вроде retry.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Protocol

from taskiq import TaskiqMessage
from taskiq.labels import LabelType

from core.types import (
    JsonValue,
    TaskiqLabelValue,
    TaskLabelMap,
    require_json_array,
    require_json_object,
    require_taskiq_label_value,
)

_TASKIQ_STRING_LABEL_TYPE = int(LabelType.STR.value)


class _TaskiqMessagePayload(Protocol):
    labels: dict[str, TaskiqLabelValue]
    args: list[JsonValue]
    kwargs: dict[str, JsonValue]


def task_message_string_labels(
    message: TaskiqMessage,
    *,
    keys: Collection[str],
) -> TaskLabelMap:
    typed_labels: TaskLabelMap = {}
    for key in keys:
        value = _task_message_label_value(message, key)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"Platform TaskIQ label {key!r} must be a string")
        typed_labels[key] = value
    return typed_labels


def task_message_string_label(message: TaskiqMessage, key: str) -> str | None:
    value = _task_message_label_value(message, key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Platform TaskIQ label {key!r} must be a string")
    return value


def require_task_message_string_label(message: TaskiqMessage, key: str) -> str:
    value = _task_message_label_value(message, key)
    if value is None:
        raise ValueError(f"TaskIQ label {key} is required")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"TaskIQ label {key} must be a non-empty string")
    return value


def task_message_int_label(message: TaskiqMessage, key: str) -> int | None:
    value = _task_message_label_value(message, key)
    if value is None:
        return None
    if type(value) is int:
        return value
    if isinstance(value, str):
        return int(value)
    raise ValueError(f"TaskIQ label {key!r} must be compatible with int")


def set_task_message_string_label(message: TaskiqMessage, key: str, value: str) -> None:
    if not value:
        raise ValueError(f"Platform TaskIQ label {key!r} must be a non-empty string")
    message.labels[key] = value
    if message.labels_types is None:
        message.labels_types = {}
    message.labels_types[key] = _TASKIQ_STRING_LABEL_TYPE


def set_task_message_string_labels(message: TaskiqMessage, labels: TaskLabelMap) -> None:
    for key, value in labels.items():
        set_task_message_string_label(message, key, value)


def _task_message_label_value(
    message: _TaskiqMessagePayload,
    key: str,
) -> TaskiqLabelValue | None:
    if key not in message.labels:
        return None
    return require_taskiq_label_value(message.labels[key], f"TaskIQ label {key!r}")


def task_message_string_kwarg(message: TaskiqMessage, key: str) -> str | None:
    kwargs = require_json_object(message.kwargs, "TaskIQ kwargs")
    value = kwargs.get(key)
    return value if isinstance(value, str) else None


def task_message_string_arg(message: TaskiqMessage, index: int) -> str | None:
    args = require_json_array(message.args, "TaskIQ args")
    if len(args) <= index:
        return None
    value = args[index]
    return value if isinstance(value, str) else None
