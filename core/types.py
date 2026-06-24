"""Платформенные низкоуровневые типы данных."""

from __future__ import annotations

import re
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
    SqlParameterValue: TypeAlias = JsonValue | date | datetime | Decimal
    TaskiqLabelValue: TypeAlias = str | int | float | bool | bytes
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
    SqlParameterValue: TypeAlias = JsonValue | date | datetime | Decimal
    TaskiqLabelValue: TypeAlias = str | int | float | bool | bytes


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
    "worktracker_url",
    "tracing_url",
    "search_url",
]
PushSubscriptionKeys: TypeAlias = dict[str, str]
TaskLabelMap: TypeAlias = dict[str, str]


class RuntimeChannel(Protocol):
    """Минимальный контракт канала, который хранится в request context."""

    name: str

_JSON_VALUE_ADAPTER: TypeAdapter[PydanticJsonValue] = TypeAdapter(PydanticJsonValue)
_JSON_OBJECT_ADAPTER: TypeAdapter[dict[str, PydanticJsonValue]] = TypeAdapter(dict[str, PydanticJsonValue])
_JSON_ARRAY_ADAPTER: TypeAdapter[list[PydanticJsonValue]] = TypeAdapter(list[PydanticJsonValue])
_ASGI_RECEIVE_MESSAGE_ADAPTER: TypeAdapter[ASGIReceiveMessage] = TypeAdapter(ASGIReceiveMessage)
_TASKIQ_LABEL_VALUE_ADAPTER: TypeAdapter[TaskiqLabelValue] = TypeAdapter(TaskiqLabelValue)


def require_json_value(value: object, field_name: str = "value") -> JsonValue:
    """Проверить внешнее значение на совместимость с JSON."""
    try:
        return cast(JsonValue, _JSON_VALUE_ADAPTER.validate_python(value))
    except ValidationError as exc:
        raise ValueError(f"{field_name} must be JSON-compatible") from exc


def extract_json_payload_text(data: str) -> str:
    """Выделить JSON object/array из markdown fences или текста с обрамлением."""
    stripped = data.strip()
    if not stripped:
        return stripped
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped, flags=re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return stripped
    object_start = stripped.find("{")
    array_start = stripped.find("[")
    if object_start == -1 and array_start == -1:
        return stripped
    if object_start == -1:
        start = array_start
    elif array_start == -1:
        start = object_start
    else:
        start = min(object_start, array_start)
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(stripped)):
        char = stripped[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0:
                return stripped[start : index + 1]
    return stripped[start:]


def repair_json_text(candidate: str) -> str:
    """Нормализовать типичные нарушения strict JSON от LLM."""
    repaired = candidate.strip()
    if not repaired:
        return repaired
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    repaired = re.sub(r"\bNone\b", "null", repaired)
    repaired = re.sub(r"\bTrue\b", "true", repaired)
    repaired = re.sub(r"\bFalse\b", "false", repaired)
    repaired = re.sub(r"\bNaN\b", "null", repaired)
    repaired = re.sub(r"\b-Infinity\b", "null", repaired)
    repaired = re.sub(r"\bInfinity\b", "null", repaired)
    return repaired


def parse_json_value(data: str | bytes, field_name: str = "value") -> JsonValue:
    """Распарсить JSON-строку в строгий JSON value."""
    text = data.decode("utf-8") if isinstance(data, bytes) else data
    candidates: list[str] = []
    stripped = text.strip()
    if stripped:
        candidates.append(stripped)
    extracted = extract_json_payload_text(text)
    if extracted and extracted not in candidates:
        candidates.append(extracted)
    last_exc: ValidationError | None = None
    for candidate in candidates:
        parse_variants = [candidate]
        repaired = repair_json_text(candidate)
        if repaired != candidate:
            parse_variants.append(repaired)
        for parse_candidate in parse_variants:
            try:
                return cast(JsonValue, _JSON_VALUE_ADAPTER.validate_json(parse_candidate))
            except ValidationError as exc:
                last_exc = exc
    if last_exc is not None:
        raise ValueError(f"{field_name} must be JSON-compatible") from last_exc
    raise ValueError(f"{field_name} must be JSON-compatible")


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


def require_taskiq_label_value(
    value: object,
    field_name: str = "value",
) -> TaskiqLabelValue:
    """Проверить внешнее значение на совместимость с TaskIQ label."""
    try:
        return _TASKIQ_LABEL_VALUE_ADAPTER.validate_python(value, strict=True)
    except ValidationError as exc:
        raise ValueError(f"{field_name} must be a TaskIQ label value") from exc


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
