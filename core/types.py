"""Платформенные низкоуровневые типы данных."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import (
    TYPE_CHECKING,
    Literal,
    NotRequired,
    Protocol,
    Required,
    TypeAlias,
    TypedDict,
    cast,
)

from pydantic import JsonValue as PydanticJsonValue
from pydantic import TypeAdapter, ValidationError

if TYPE_CHECKING:
    JsonScalar: TypeAlias = str | int | float | bool | None
    JsonValue: TypeAlias = JsonScalar | Mapping[str, "JsonValue"] | Sequence["JsonValue"]
    JsonObject: TypeAlias = dict[str, JsonValue]
    JsonArray: TypeAlias = list[JsonValue]
    DocxTemplateScalar: TypeAlias = JsonScalar | date | datetime | Decimal
    DocxTemplateContextValue: TypeAlias = (
        DocxTemplateScalar
        | Mapping[str, "DocxTemplateContextValue"]
        | Sequence["DocxTemplateContextValue"]
    )
    DocxTemplateContext: TypeAlias = Mapping[str, DocxTemplateContextValue]
    SpeechProvider: TypeAlias = Literal["litserve", "cloud_ru", "yandex", "sber", "mock"]
    VadProvider: TypeAlias = Literal["litserve", "silero_local", "mock"]
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
    DocxTemplateScalar: TypeAlias = JsonScalar | date | datetime | Decimal
    DocxTemplateContextValue: TypeAlias = (
        DocxTemplateScalar
        | Mapping[str, "DocxTemplateContextValue"]
        | Sequence["DocxTemplateContextValue"]
    )
    DocxTemplateContext: TypeAlias = Mapping[str, DocxTemplateContextValue]
    SpeechProvider: TypeAlias = Literal["litserve", "cloud_ru", "yandex", "sber", "mock"]
    VadProvider: TypeAlias = Literal["litserve", "silero_local", "mock"]
    OtelAttributeScalar: TypeAlias = str | bool | int | float
    OtelAttributeValue: TypeAlias = (
        OtelAttributeScalar | Sequence[str] | Sequence[bool] | Sequence[int] | Sequence[float]
    )
    OtelAttributes: TypeAlias = Mapping[str, OtelAttributeValue]


class ASGIScope(TypedDict, total=False):
    type: Required[str]
    headers: NotRequired[list[tuple[bytes, bytes]]]
    path: NotRequired[str]
    scheme: NotRequired[str]
    query_string: NotRequired[bytes]
    subprotocols: NotRequired[list[str]]


class ASGIWebSocketConnectMessage(TypedDict):
    type: Literal["websocket.connect"]


class ASGIWebSocketDisconnectMessage(TypedDict, total=False):
    type: Required[Literal["websocket.disconnect"]]
    code: int


class ASGIWebSocketReceiveMessage(TypedDict, total=False):
    type: Required[Literal["websocket.receive"]]
    bytes: bytes | None
    text: str | None


ASGIReceiveMessage: TypeAlias = (
    ASGIWebSocketConnectMessage | ASGIWebSocketDisconnectMessage | ASGIWebSocketReceiveMessage
)


class ASGIWebSocketAcceptMessage(TypedDict, total=False):
    type: Required[Literal["websocket.accept"]]
    subprotocol: str


class ASGIWebSocketCloseMessage(TypedDict):
    type: Literal["websocket.close"]
    code: int


class ASGIWebSocketSendBytesMessage(TypedDict):
    type: Literal["websocket.send"]
    bytes: bytes


class ASGIWebSocketSendTextMessage(TypedDict):
    type: Literal["websocket.send"]
    text: str


ASGISendMessage: TypeAlias = (
    ASGIWebSocketAcceptMessage
    | ASGIWebSocketCloseMessage
    | ASGIWebSocketSendBytesMessage
    | ASGIWebSocketSendTextMessage
)
ASGIReceive: TypeAlias = Callable[[], Awaitable[ASGIReceiveMessage]]
ASGISend: TypeAlias = Callable[[ASGISendMessage], Awaitable[None]]
ASGIApp: TypeAlias = Callable[[ASGIScope, ASGIReceive, ASGISend], Awaitable[None]]
MigrationDatabaseUrlKey: TypeAlias = Literal[
    "shared_url",
    "flows_url",
    "crm_url",
    "sync_url",
    "rag_url",
    "office_url",
    "tracing_url",
]


class RuntimeChannel(Protocol):
    """Минимальный контракт канала, который хранится в request context."""

    name: str

_JSON_VALUE_ADAPTER: TypeAdapter[PydanticJsonValue] = TypeAdapter(PydanticJsonValue)
_JSON_OBJECT_ADAPTER: TypeAdapter[dict[str, PydanticJsonValue]] = TypeAdapter(dict[str, PydanticJsonValue])
_JSON_ARRAY_ADAPTER: TypeAdapter[list[PydanticJsonValue]] = TypeAdapter(list[PydanticJsonValue])
_ASGI_RECEIVE_MESSAGE_ADAPTER: TypeAdapter[ASGIReceiveMessage] = TypeAdapter(ASGIReceiveMessage)


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


def require_asgi_receive_message(value: object, field_name: str = "message") -> ASGIReceiveMessage:
    """Проверить сообщение ASGI receive на WebSocket contract."""
    try:
        return _ASGI_RECEIVE_MESSAGE_ADAPTER.validate_python(value)
    except ValidationError as exc:
        raise ValueError(f"{field_name} must be an ASGI receive message") from exc


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
