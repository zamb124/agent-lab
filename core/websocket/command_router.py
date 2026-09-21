"""
Каталог `op_*` владельца: bus `realtime` зовёт
`POST /{svc}/api/internal/realtime/command` с телом `PlatformEvent`.

Каждый сервис регистрирует handlers через `register_ws_command_handler`.
Вход — `PlatformEvent.type` (`…/_requested`) и `payload`. Исход —
`publish_event` с `*_succeeded` / `*_failed` и `meta.causation_id = event_id`.

Тип reply выводится механически: суффикс `_requested` → `_succeeded` / `_failed`.
Команды без `_requested` запрещены — `register_ws_command_handler` бросает `ValueError`.

Доменная ошибка — `WsCommandError`; ошибки границы `core/errors/boundary.py`
(`PlatformNotFoundError` / `PlatformConflictError` / `PlatformAccessDeniedError`)
превращаются в `not_found` / `conflict` / `forbidden` так же, как в REST-фабрике.
Любая другая ошибка handler'а пробрасывается.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from core.errors.boundary import (
    PlatformAccessDeniedError,
    PlatformConflictError,
    PlatformNotFoundError,
)
from core.events import register_platform_event
from core.logging import get_logger
from core.models.identity_models import User
from core.realtime.models import PlatformCommandEventPayload
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
    _register_command_platform_events(command_type)
    _handlers[command_type] = handler


def _register_command_platform_events(command_type: str) -> None:
    succeeded = derive_succeeded_type(command_type)
    failed = derive_failed_type(command_type)
    register_platform_event(
        command_type,
        PlatformCommandEventPayload,
        description=f"Command {command_type}",
    )
    register_platform_event(
        succeeded,
        PlatformCommandEventPayload,
        description=f"Command result {succeeded}",
    )
    register_platform_event(
        failed,
        PlatformCommandEventPayload,
        description=f"Command result {failed}",
    )


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
    - На `WsCommandError` и ошибки границы `Platform*Error`:
      `(<command_type без _requested>_failed, { error_code, error_detail })`.
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
        return derive_failed_type(command_type), {"error_code": err.code, "error_detail": err.detail}
    except PlatformNotFoundError as err:
        return derive_failed_type(command_type), {"error_code": "not_found", "error_detail": str(err)}
    except PlatformConflictError as err:
        return derive_failed_type(command_type), {"error_code": "conflict", "error_detail": str(err)}
    except PlatformAccessDeniedError as err:
        return derive_failed_type(command_type), {"error_code": "forbidden", "error_detail": str(err)}
    return (derive_succeeded_type(command_type), result)
