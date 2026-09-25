"""Каталог команд: одна `Operation` на verb, REST и WS RPC вызывают один `op_*`."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from typing import Generic, Never, Protocol, TypeVar

from pydantic import BaseModel

from core.di.kit import ServiceDi
from core.errors.boundary import PlatformBoundaryError
from core.models.base import StrictBaseModel
from core.models.identity_models import User
from core.types import JsonObject, JsonValue
from core.websocket.command_router import (
    CommandHandler,
    WsCommandError,
    dump_ws_result,
    register_ws_command_handler,
    validate_ws_payload,
)

DiT = TypeVar("DiT", bound=ServiceDi)
PayloadT = TypeVar("PayloadT", bound=BaseModel)
OperationPayloadT = TypeVar("OperationPayloadT", bound=BaseModel, contravariant=True)
OperationDiT = TypeVar("OperationDiT", bound=ServiceDi, contravariant=True)


class OperationFn(Protocol[OperationPayloadT, OperationDiT]):
    def __call__(
        self,
        payload: OperationPayloadT,
        /,
        *,
        user: User,
        di: OperationDiT,
    ) -> Awaitable[BaseModel | JsonValue | None]: ...


class RegisteredOperation(Protocol[OperationDiT]):
    @property
    def payload_model(self) -> type[BaseModel]: ...

    async def run(
        self,
        payload: JsonObject,
        *,
        user: User,
        di: OperationDiT,
    ) -> JsonObject | None: ...


WS_COMMAND_ERROR_HTTP_STATUS: dict[str, int] = {
    "ws_invalid_frame": 400,
    "ws_invalid_payload": 400,
    "ws_invalid_cursor": 400,
    "ws_unknown_type": 404,
    "ws_handler_not_found": 404,
    "not_found": 404,
    "unauthorized": 401,
    "forbidden": 403,
    "conflict": 409,
    "gone": 410,
    "rate_limited": 429,
    "method_not_allowed": 405,
    "unavailable": 503,
    "upstream": 502,
    "ws_invalid_result": 500,
    "internal": 500,
}


def ws_command_error_status(error: WsCommandError) -> int:
    if error.code not in WS_COMMAND_ERROR_HTTP_STATUS:
        raise ValueError(f"unknown WsCommandError.code: {error.code}")
    return WS_COMMAND_ERROR_HTTP_STATUS[error.code]


def _command_error(
    transport_code: str,
    exc: Exception,
    detail: str | None,
    *,
    error_code: str | None,
    error_params: JsonObject | None,
) -> WsCommandError:
    message = detail if detail is not None else str(exc)
    if isinstance(exc, PlatformBoundaryError):
        resolved_code = error_code if error_code is not None else exc.error_code
        resolved_params = error_params if error_params is not None else exc.error_params
    else:
        resolved_code = error_code if error_code is not None else transport_code
        resolved_params = error_params if error_params is not None else {}
    return WsCommandError(
        transport_code,
        message,
        error_code=resolved_code,
        error_params=resolved_params,
    )


def raise_forbidden(
    exc: Exception,
    *,
    error_code: str | None = None,
    error_params: JsonObject | None = None,
) -> Never:
    raise _command_error("forbidden", exc, None, error_code=error_code, error_params=error_params) from exc


def raise_not_found(
    exc: Exception,
    detail: str | None = None,
    *,
    error_code: str | None = None,
    error_params: JsonObject | None = None,
) -> Never:
    raise _command_error("not_found", exc, detail, error_code=error_code, error_params=error_params) from exc


def raise_invalid(
    exc: Exception,
    *,
    error_code: str | None = None,
    error_params: JsonObject | None = None,
) -> Never:
    raise _command_error("ws_invalid_payload", exc, None, error_code=error_code, error_params=error_params) from exc


def raise_conflict(
    exc: Exception,
    detail: str | None = None,
    *,
    error_code: str | None = None,
    error_params: JsonObject | None = None,
) -> Never:
    raise _command_error("conflict", exc, detail, error_code=error_code, error_params=error_params) from exc


def raise_internal(
    exc: Exception,
    *,
    error_code: str | None = None,
    error_params: JsonObject | None = None,
) -> Never:
    raise _command_error("internal", exc, None, error_code=error_code, error_params=error_params) from exc


def raise_upstream(
    exc: Exception,
    *,
    error_code: str | None = None,
    error_params: JsonObject | None = None,
) -> Never:
    raise _command_error("upstream", exc, None, error_code=error_code, error_params=error_params) from exc


def raise_unavailable(
    exc: Exception,
    *,
    error_code: str | None = None,
    error_params: JsonObject | None = None,
) -> Never:
    raise _command_error("unavailable", exc, None, error_code=error_code, error_params=error_params) from exc


class EmptyPayload(StrictBaseModel):
    """Команда без аргументов: WS `payload: null|{}` и REST без тела/query."""


@dataclass(frozen=True)
class Operation(Generic[PayloadT, DiT]):
    payload_model: type[PayloadT]
    fn: OperationFn[PayloadT, DiT]

    def parse_payload(self, payload: JsonObject) -> PayloadT:
        return validate_ws_payload(self.payload_model, payload)

    async def run(
        self,
        payload: JsonObject,
        *,
        user: User,
        di: DiT,
    ) -> JsonObject | None:
        parsed = self.parse_payload(payload)
        result = await self.fn(parsed, user=user, di=di)
        return dump_ws_result(result)


# command_type → id(Operation) каталога-владельца (каталоги — константы модуля на весь процесс).
_registered_operation_ids: dict[str, int] = {}


def register_operations(
    catalog: Mapping[str, RegisteredOperation[DiT]],
    di_class: type[DiT],
) -> None:
    """Зарегистрировать каталог владельца; DI команда получает из ASGI-приложения владельца.

    Повторный вызов с тем же объектом `Operation` — no-op (в одном процессе тестов
    приложение создаётся один раз, а lifespan поднимается многократно);
    другой handler на уже занятый `command_type` — ошибка.
    """
    for command_type, operation in catalog.items():
        if _registered_operation_ids.get(command_type) == id(operation):
            continue
        register_ws_command_handler(command_type, _make_ws_handler(operation, di_class))
        _registered_operation_ids[command_type] = id(operation)


def _make_ws_handler(
    operation: RegisteredOperation[DiT],
    di_class: type[DiT],
) -> CommandHandler:
    async def handler(payload: JsonObject, user: User, di: ServiceDi) -> JsonObject | None:
        if not isinstance(di, di_class):
            raise WsCommandError(
                "internal",
                f"command expects {di_class.__qualname__}, the owner app DI is {type(di).__qualname__}",
                error_code="internal",
            )
        return await operation.run(payload, user=user, di=di)

    return handler
