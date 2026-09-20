"""Каталог команд: одна `Operation` на verb, REST и WS RPC вызывают один `op_*`."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Generic, Never, Protocol, TypeVar

from pydantic import BaseModel

from core.models.identity_models import User
from core.types import JsonObject, JsonValue
from core.websocket.command_router import (
    CommandHandler,
    WsCommandError,
    dump_ws_result,
    register_ws_command_handler,
    validate_ws_payload,
)

ContainerT = TypeVar("ContainerT")
PayloadT = TypeVar("PayloadT", bound=BaseModel)
OperationPayloadT = TypeVar("OperationPayloadT", bound=BaseModel, contravariant=True)
OperationContainerT = TypeVar("OperationContainerT", contravariant=True)


class OperationFn(Protocol[OperationPayloadT, OperationContainerT]):
    def __call__(
        self,
        payload: OperationPayloadT,
        /,
        *,
        user: User,
        container: OperationContainerT,
    ) -> Awaitable[BaseModel | JsonValue | None]: ...


class RegisteredOperation(Protocol[OperationContainerT]):
    @property
    def payload_model(self) -> type[BaseModel]: ...

    async def run(
        self,
        payload: JsonObject,
        *,
        user: User,
        container: OperationContainerT,
    ) -> JsonObject | None: ...


WS_COMMAND_ERROR_HTTP_STATUS: dict[str, int] = {
    "ws_invalid_frame": 400,
    "ws_invalid_payload": 400,
    "ws_invalid_cursor": 400,
    "ws_unknown_type": 404,
    "ws_handler_not_found": 404,
    "not_found": 404,
    "forbidden": 403,
    "conflict": 409,
    "rate_limited": 429,
    "unavailable": 503,
    "upstream": 502,
    "ws_invalid_result": 500,
    "internal": 500,
}


def ws_command_error_status(error: WsCommandError) -> int:
    if error.code not in WS_COMMAND_ERROR_HTTP_STATUS:
        raise ValueError(f"неизвестный WsCommandError.code: {error.code}")
    return WS_COMMAND_ERROR_HTTP_STATUS[error.code]


def raise_forbidden(exc: Exception) -> Never:
    raise WsCommandError("forbidden", str(exc)) from exc


def raise_not_found(exc: Exception, detail: str | None = None) -> Never:
    raise WsCommandError("not_found", detail if detail is not None else str(exc)) from exc


def raise_invalid(exc: Exception) -> Never:
    raise WsCommandError("ws_invalid_payload", str(exc)) from exc


def raise_conflict(exc: Exception, detail: str | None = None) -> Never:
    raise WsCommandError("conflict", detail if detail is not None else str(exc)) from exc


def raise_internal(exc: Exception) -> Never:
    raise WsCommandError("internal", str(exc)) from exc


def raise_upstream(exc: Exception) -> Never:
    raise WsCommandError("upstream", str(exc)) from exc


def raise_unavailable(exc: Exception) -> Never:
    raise WsCommandError("unavailable", str(exc)) from exc


@dataclass(frozen=True)
class Operation(Generic[PayloadT, ContainerT]):
    payload_model: type[PayloadT]
    fn: OperationFn[PayloadT, ContainerT]

    def parse_payload(self, payload: JsonObject) -> PayloadT:
        return validate_ws_payload(self.payload_model, payload)

    async def run(
        self,
        payload: JsonObject,
        *,
        user: User,
        container: ContainerT,
    ) -> JsonObject | None:
        parsed = self.parse_payload(payload)
        result = await self.fn(parsed, user=user, container=container)
        return dump_ws_result(result)


def register_service_operations(
    catalog: Mapping[str, RegisteredOperation[ContainerT]],
    get_container: Callable[[], ContainerT],
) -> None:
    for command_type, operation in catalog.items():
        register_ws_command_handler(command_type, _make_ws_handler(operation, get_container))


def _make_ws_handler(
    operation: RegisteredOperation[ContainerT],
    get_container: Callable[[], ContainerT],
) -> CommandHandler:
    async def handler(payload: JsonObject, user: User) -> JsonObject | None:
        return await operation.run(payload, user=user, container=get_container())

    return handler
