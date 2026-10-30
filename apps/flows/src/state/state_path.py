"""Запись значения в ``ExecutionState`` по dotted-пути (``order.customer.email``).

Общий путь для полей интерфейса (ui-action), тула ``state_set`` и любого кода,
которому нужно положить значение во вложенный объект state. Корень пути — обычное
поле state; системные (frozen) поля недоступны.
"""

from __future__ import annotations

from core.state.execution_state import ExecutionState, ExecutionStateValue
from core.state.mutation_policy import raise_if_frozen_field
from core.types import JsonObject, JsonValue, require_json_object


def _object_copy(value: ExecutionStateValue | None, path: str) -> JsonObject:
    """Промежуточный узел пути: отсутствует — новый объект, скаляр или список — ошибка."""
    if value is None:
        return {}
    return dict(require_json_object(value, f"state path {path!r} parent"))


def assign_state_path(state: ExecutionState, path: str, value: JsonValue) -> None:
    segments = path.split(".")
    if any(segment == "" for segment in segments):
        raise ValueError(f"invalid state path {path!r}")
    raise_if_frozen_field(segments[0], reason="state path assign")
    if len(segments) == 1:
        state[segments[0]] = value
        return
    root = state.get(segments[0])
    copied_root = _object_copy(root, path)
    current = copied_root
    for segment in segments[1:-1]:
        copied_child = _object_copy(current.get(segment), path)
        current[segment] = copied_child
        current = copied_child
    current[segments[-1]] = value
    state[segments[0]] = copied_root


__all__ = ["assign_state_path"]
