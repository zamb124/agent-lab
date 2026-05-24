"""
Платформенный command-router поверх WS-сокета `/<svc>/api/ws/notifications`.

Каждый сервис регистрирует свои command-handlers через `register_ws_command_handler`.
Контракт фрейма от клиента:

    { "request_id": "<id>", "type": "<scope>/<entity>/<verb>_requested", "payload": <object> }

WS-роутер ищет handler по `type`, передаёт ему `(payload, user)` и формирует
обратный фрейм:

    { "request_id": "<id>", "type": "<scope>/<entity>/<verb>_succeeded", "payload": <result> }

либо при `WsCommandError`:

    { "request_id": "<id>", "type": "<scope>/<entity>/<verb>_failed",
      "payload": { "error_code": "<code>", "error_detail": "<detail>" } }

Тип reply'я выводится из имени команды механически: суффикс `_requested`
заменяется на `_succeeded` / `_failed`. Команды без суффикса `_requested`
запрещены — `register_ws_command_handler` бросает `ValueError`.

Никаких фолбеков: если handler выбросил исключение не `WsCommandError` —
оно пробрасывается, фрейм reply не отправляется (клиент дождётся timeout).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from core.logging import get_logger
from core.models.identity_models import User
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

logger = get_logger(__name__)


_REQUESTED_SUFFIX = "_requested"
_EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\/[a-z][a-z0-9_]*){2,}$")
PayloadModelT = TypeVar("PayloadModelT", bound=BaseModel)


class WsCommandError(Exception):
    """Доменная ошибка WS-команды. Превращается в `*_failed` фрейм."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        if not code:
            raise ValueError("WsCommandError.code must be non-empty string")
        if not detail:
            raise ValueError("WsCommandError.detail must be non-empty string")
        self.code: str = code
        self.detail: str = detail


CommandHandler = Callable[[JsonObject, User], Awaitable[JsonObject | None]]


_handlers: dict[str, CommandHandler] = {}


def _validate_command_type(command_type: str) -> None:
    if not command_type:
        raise ValueError("WS command type must be non-empty string")
    if not _EVENT_TYPE_PATTERN.match(command_type):
        message = (
            f'WS command type "{command_type}" violates contract. Expected scope/entity/verb '
            +
            "(lowercase, snake_case, >= 3 segments)."
        )
        raise ValueError(message)
    if not command_type.endswith(_REQUESTED_SUFFIX):
        message = (
            f'WS command type "{command_type}" must end with "_requested" '
            +
            "(reply types are derived as *_succeeded / *_failed)."
        )
        raise ValueError(message)


def register_ws_command_handler(command_type: str, handler: CommandHandler) -> None:
    """
    Зарегистрировать handler команды. Повторная регистрация того же `command_type` — ошибка.

    Handler получает `(payload, user)` и возвращает `dict` (станет payload'ом
    `*_succeeded`) или `None` (payload reply'я будет `null`). Доменная
    ошибка — `raise WsCommandError(code, detail)`.
    """
    _validate_command_type(command_type)
    if command_type in _handlers:
        raise ValueError(f"WS command handler for {command_type!r} already registered")
    _handlers[command_type] = handler


def has_ws_command_handler(command_type: str) -> bool:
    return command_type in _handlers


def get_ws_command_handler(command_type: str) -> CommandHandler | None:
    return _handlers.get(command_type)


def list_ws_command_types() -> list[str]:
    return sorted(_handlers.keys())


def derive_succeeded_type(command_type: str) -> str:
    _validate_command_type(command_type)
    return command_type[: -len(_REQUESTED_SUFFIX)] + "_succeeded"


def derive_failed_type(command_type: str) -> str:
    _validate_command_type(command_type)
    return command_type[: -len(_REQUESTED_SUFFIX)] + "_failed"


def validate_ws_payload(model: type[PayloadModelT], payload: JsonObject) -> PayloadModelT:
    """Проверить WS payload на Pydantic-модели владельца команды."""
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise WsCommandError("ws_invalid_payload", str(exc)) from exc


def dump_ws_result(result: BaseModel | JsonValue | None) -> JsonObject | None:
    """Сериализовать результат WS-команды в JSON object транспортного payload."""
    if result is None:
        return None
    if isinstance(result, BaseModel):
        return parse_json_object(result.model_dump_json(), type(result).__name__)
    return require_json_object(result, "WS command result")


async def dispatch_ws_command(
    command_type: str,
    payload: JsonValue | None,
    user: User,
) -> tuple[str, JsonObject | None]:
    """
    Выполнить command-handler. Возвращает кортеж `(reply_type, reply_payload)`.

    - На успех: `(<command_type без _requested>_succeeded, handler_result)`.
    - На `WsCommandError`: `(<command_type без _requested>_failed,
       { error_code, error_detail })`.
    - Любая другая ошибка handler'а пробрасывается наружу.
    """
    handler = get_ws_command_handler(command_type)
    if handler is None:
        raise WsCommandError("ws_handler_not_found", f"No WS command handler for {command_type!r}")
    if payload is None:
        payload_dict: JsonObject = {}
    else:
        try:
            payload_dict = require_json_object(payload, f"WS command {command_type!r} payload")
        except ValueError as exc:
            raise WsCommandError(
                "ws_invalid_payload",
                f"WS command {command_type!r} payload must be object|null",
            ) from exc
    try:
        result = await handler(payload_dict, user)
    except WsCommandError as err:
        failed_payload: JsonObject = {"error_code": err.code, "error_detail": err.detail}
        return (
            derive_failed_type(command_type),
            failed_payload,
        )
    return (derive_succeeded_type(command_type), result)
