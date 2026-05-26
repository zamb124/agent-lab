"""Typed boundary for TaskIQ messages.

TaskIQ exposes labels, args and kwargs as ``Any``. Platform tasks use JSON
payloads and string labels, so every middleware reads those fields through this
module instead of touching SDK containers directly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from taskiq import TaskiqMessage

from core.types import JsonValue, TaskLabelMap


def task_message_labels(message: TaskiqMessage) -> TaskLabelMap:
    labels = cast(Mapping[str, JsonValue], message.labels)
    typed_labels: TaskLabelMap = {}
    for key, value in labels.items():
        if not isinstance(value, str):
            raise ValueError(f"TaskIQ label {key!r} must be a string")
        typed_labels[key] = value
    return typed_labels


def task_message_string_kwarg(message: TaskiqMessage, key: str) -> str | None:
    kwargs = cast(Mapping[str, JsonValue], message.kwargs)
    value = kwargs.get(key)
    return value if isinstance(value, str) else None


def task_message_string_arg(message: TaskiqMessage, index: int) -> str | None:
    args = cast(Sequence[JsonValue], message.args)
    if len(args) <= index:
        return None
    value = args[index]
    return value if isinstance(value, str) else None
