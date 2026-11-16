"""JSON-типы пакета. Разбор сырого значения — один TypeAdapter на границе."""

from __future__ import annotations

from pydantic import TypeAdapter, ValidationError

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

_JSON = TypeAdapter(JsonValue)
_OBJECT = TypeAdapter(JsonObject)
_LIST = TypeAdapter(list[JsonValue])


def require_object(value: object, label: str) -> JsonObject:
    try:
        return _OBJECT.validate_python(value)
    except ValidationError as exc:
        raise ValueError(f"{label} must be a JSON object") from exc


def as_list(value: object) -> list[JsonValue] | None:
    try:
        return _LIST.validate_python(value)
    except ValidationError:
        return None


def as_json(value: object, label: str) -> JsonValue:
    """Принимает результат yaml/json и отвергает не-JSON значения."""
    try:
        return _JSON.validate_python(value)
    except ValidationError as exc:
        raise ValueError(f"{label} is not a JSON value") from exc
