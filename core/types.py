"""Платформенные низкоуровневые типы данных."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, TypeAlias, cast

from pydantic import JsonValue as PydanticJsonValue
from pydantic import TypeAdapter, ValidationError

if TYPE_CHECKING:
    JsonScalar: TypeAlias = str | int | float | bool | None
    JsonValue: TypeAlias = JsonScalar | Mapping[str, "JsonValue"] | Sequence["JsonValue"]
    JsonObject: TypeAlias = dict[str, JsonValue]
    JsonArray: TypeAlias = list[JsonValue]
    OtelAttributeScalar: TypeAlias = str | bool | int | float
    OtelAttributeValue: TypeAlias = (
        OtelAttributeScalar | Sequence[str] | Sequence[bool] | Sequence[int] | Sequence[float]
    )
    OtelAttributes: TypeAlias = Mapping[str, OtelAttributeValue]
else:
    JsonScalar: TypeAlias = str | int | float | bool | None
    JsonValue: TypeAlias = PydanticJsonValue
    JsonObject: TypeAlias = dict[str, PydanticJsonValue]
    JsonArray: TypeAlias = list[PydanticJsonValue]
    OtelAttributeScalar: TypeAlias = str | bool | int | float
    OtelAttributeValue: TypeAlias = (
        OtelAttributeScalar | Sequence[str] | Sequence[bool] | Sequence[int] | Sequence[float]
    )
    OtelAttributes: TypeAlias = Mapping[str, OtelAttributeValue]

_JSON_VALUE_ADAPTER: TypeAdapter[PydanticJsonValue] = TypeAdapter(PydanticJsonValue)
_JSON_OBJECT_ADAPTER: TypeAdapter[dict[str, PydanticJsonValue]] = TypeAdapter(dict[str, PydanticJsonValue])
_JSON_ARRAY_ADAPTER: TypeAdapter[list[PydanticJsonValue]] = TypeAdapter(list[PydanticJsonValue])


def require_json_value(value: object, field_name: str = "value") -> JsonValue:
    """Проверить внешнее значение на совместимость с JSON."""
    try:
        return cast(JsonValue, _JSON_VALUE_ADAPTER.validate_python(value))
    except ValidationError as exc:
        raise ValueError(f"{field_name} must be JSON-compatible") from exc


def parse_json_value(data: str | bytes, field_name: str = "value") -> JsonValue:
    """Распарсить JSON-строку в строгий JSON value."""
    try:
        return cast(JsonValue, _JSON_VALUE_ADAPTER.validate_json(data))
    except ValidationError as exc:
        raise ValueError(f"{field_name} must be JSON-compatible") from exc


def require_json_object(value: object, field_name: str = "value") -> JsonObject:
    """Проверить внешнее значение на JSON object."""
    try:
        return cast(JsonObject, _JSON_OBJECT_ADAPTER.validate_python(value))
    except ValidationError as exc:
        raise ValueError(f"{field_name} must be a JSON object") from exc


def parse_json_object(data: str | bytes, field_name: str = "value") -> JsonObject:
    """Распарсить JSON-строку в строгий JSON object."""
    try:
        return cast(JsonObject, _JSON_OBJECT_ADAPTER.validate_json(data))
    except ValidationError as exc:
        raise ValueError(f"{field_name} must be a JSON object") from exc


def require_json_array(value: object, field_name: str = "value") -> JsonArray:
    """Проверить внешнее значение на JSON array."""
    try:
        return cast(JsonArray, _JSON_ARRAY_ADAPTER.validate_python(value))
    except ValidationError as exc:
        raise ValueError(f"{field_name} must be a JSON array") from exc


def parse_json_array(data: str | bytes, field_name: str = "value") -> JsonArray:
    """Распарсить JSON-строку в строгий JSON array."""
    try:
        return cast(JsonArray, _JSON_ARRAY_ADAPTER.validate_json(data))
    except ValidationError as exc:
        raise ValueError(f"{field_name} must be a JSON array") from exc


def otel_attribute_value_to_json_value(value: OtelAttributeValue) -> JsonValue:
    """Преобразовать OpenTelemetry AttributeValue в JSON-compatible значение."""
    if isinstance(value, str | bool | int | float):
        return value
    return list(value)


def otel_attributes_to_json_object(attributes: OtelAttributes | None) -> JsonObject:
    """Преобразовать OpenTelemetry attributes в JSON object для хранения."""
    if attributes is None:
        return {}
    return {
        key: otel_attribute_value_to_json_value(value)
        for key, value in attributes.items()
    }
