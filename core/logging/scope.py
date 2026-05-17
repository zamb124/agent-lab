"""
Лог-скоупы и контракт обязательных полей.

В платформе различаются два типа жизненных циклов записи:

* **system** — стартовая инициализация процесса, lifecycle, фоновые ticks
  без привязки к запросу пользователя. Достаточно полей `service.name`,
  `service.version`, `deployment.environment`, `timestamp`, `level`,
  `logger`, `message`.

* **request** — обработка одного запроса (HTTP, WS-команда, TaskIQ-задача,
  scheduler tick, фоновая задача, инициированная запросом). В каждой
  записи **обязательно** есть `request_id`, `trace_id` и `service.name`;
  для авторизованных контекстов — также `user.id` и `company.id`.

Скоуп управляется contextvar `_LOG_SCOPE`. По умолчанию — `system`.
Точки входа (HTTP middleware, TaskIQ middleware, WS connect, scheduler
dispatch, run_with_log_context) переключают на `request` через
`enter_request_scope(...)`. Процессор `enforce_required_fields` падает
(`LogContractViolation`), если запись пишется в `request`-скоупе без
обязательных полей.

NB: scope — это исключительно контракт лог-записи. Он не подменяет
бизнес-`Context` и не отвечает за маршрутизацию или авторизацию.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Literal

from core.logging.attributes import (
    LOG_COMPANY_ID,
    LOG_REQUEST_ID,
    LOG_SERVICE_NAME,
    LOG_TRACE_ID,
    LOG_USER_ID,
)
from core.logging.context import (
    bind_log_context,
    clear_log_context,
    get_log_context,
    restore_log_context,
)

LogScope = Literal["system", "request"]


_LOG_SCOPE: ContextVar[LogScope] = ContextVar("_log_scope", default="system")
_LOG_SCOPE_REQUIRES_USER: ContextVar[bool] = ContextVar(
    "_log_scope_requires_user", default=False
)


REQUIRED_REQUEST_KEYS: tuple[str, ...] = (
    LOG_REQUEST_ID,
    LOG_TRACE_ID,
    LOG_SERVICE_NAME,
)
"""Поля, без которых запись в request-скоупе считается нарушением контракта."""

REQUIRED_AUTHENTICATED_REQUEST_KEYS: tuple[str, ...] = (
    LOG_USER_ID,
    LOG_COMPANY_ID,
)
"""Дополнительные поля для авторизованных request-скоупов (HTTP с auth, TaskIQ user-задачи)."""


class LogContractViolation(RuntimeError):
    """
    Запись лога нарушает контракт обязательных полей request-скоупа.

    Поднимается процессором `enforce_required_fields` и **прерывает запись
    конкретной строки** (DropEvent). Дополнительно процессор пишет
    отдельную ERROR-запись с подробностями нарушения, чтобы факт сам по
    себе был виден в логах.
    """


@dataclass(frozen=True)
class _ScopeToken:
    """Снимок токенов скоупа и контекста для аккуратного выхода."""

    scope_token: Token[LogScope]
    auth_token: Token[bool]
    snapshot: dict[str, Any]


def get_log_scope() -> LogScope:
    return _LOG_SCOPE.get()


def get_log_scope_requires_user() -> bool:
    return _LOG_SCOPE_REQUIRES_USER.get()


def enter_request_scope(
    *,
    request_id: str,
    trace_id: str,
    service_name: str,
    user_id: str | None = None,
    company_id: str | None = None,
    requires_user: bool = False,
    **extra: Any,
) -> _ScopeToken:
    """
    Перевести логирование в request-скоуп и забиндить обязательные поля.

    Args:
        request_id: непустой идентификатор запроса (E2E между сервисами).
        trace_id: непустой OTel trace_id или платформенная альтернатива.
        service_name: имя сервиса, обслуживающего этот scope (для проверки).
        user_id: идентификатор пользователя; обязательно при requires_user=True.
        company_id: идентификатор активной компании; обязательно при requires_user=True.
        requires_user: если True, запись без user_id/company_id считается нарушением.
        **extra: дополнительные поля к bind_log_context.

    Raises:
        ValueError: при пустом request_id/trace_id/service_name или при
            requires_user=True и отсутствии user_id/company_id.
    """
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("enter_request_scope: request_id обязателен и непустой")
    if not isinstance(trace_id, str) or not trace_id.strip():
        raise ValueError("enter_request_scope: trace_id обязателен и непустой")
    if not isinstance(service_name, str) or not service_name.strip():
        raise ValueError("enter_request_scope: service_name обязателен и непустой")

    if requires_user:
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError(
                "enter_request_scope(requires_user=True): user_id обязателен"
            )
        if not isinstance(company_id, str) or not company_id.strip():
            raise ValueError(
                "enter_request_scope(requires_user=True): company_id обязателен"
            )

    snapshot = get_log_context()

    fields: dict[str, Any] = {
        LOG_REQUEST_ID: request_id,
        LOG_TRACE_ID: trace_id,
        LOG_SERVICE_NAME: service_name,
    }
    if user_id:
        fields[LOG_USER_ID] = user_id
    if company_id:
        fields[LOG_COMPANY_ID] = company_id
    fields.update({k: v for k, v in extra.items() if v not in (None, "")})
    bind_log_context(**fields)

    scope_token = _LOG_SCOPE.set("request")
    auth_token = _LOG_SCOPE_REQUIRES_USER.set(bool(requires_user))
    return _ScopeToken(scope_token=scope_token, auth_token=auth_token, snapshot=snapshot)


def exit_request_scope(token: _ScopeToken | None) -> None:
    """Снять request-скоуп и восстановить лог-контекст из snapshot."""
    if token is not None:
        _LOG_SCOPE.reset(token.scope_token)
        _LOG_SCOPE_REQUIRES_USER.reset(token.auth_token)
        restore_log_context(token.snapshot)
    else:
        clear_log_context()


class RequestLogScope:
    """
    Контекстный менеджер: вход в request-скоуп с обязательными полями.

    Использование:
        async with RequestLogScope(request_id=..., trace_id=..., service_name="flows",
                                   user_id=..., company_id=..., requires_user=True):
            await handler(...)
    """

    def __init__(
        self,
        *,
        request_id: str,
        trace_id: str,
        service_name: str,
        user_id: str | None = None,
        company_id: str | None = None,
        requires_user: bool = False,
        **extra: Any,
    ) -> None:
        self._request_id = request_id
        self._trace_id = trace_id
        self._service_name = service_name
        self._user_id = user_id
        self._company_id = company_id
        self._requires_user = requires_user
        self._extra = extra
        self._token: _ScopeToken | None = None

    def __enter__(self) -> "RequestLogScope":
        self._token = enter_request_scope(
            request_id=self._request_id,
            trace_id=self._trace_id,
            service_name=self._service_name,
            user_id=self._user_id,
            company_id=self._company_id,
            requires_user=self._requires_user,
            **self._extra,
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        exit_request_scope(self._token)
        self._token = None

    async def __aenter__(self) -> "RequestLogScope":
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.__exit__(exc_type, exc, tb)


class SystemLogScope:
    """
    Явный системный скоуп: lifecycle и фоновые ticks без привязки к запросу.

    Используется в startup/shutdown lifespan, в стартовых хуках воркеров и
    в тех местах, где сознательно нет request_id/trace_id.
    """

    def __init__(self, **extra: Any) -> None:
        self._extra = {k: v for k, v in extra.items() if v not in (None, "")}
        self._scope_token: Token[LogScope] | None = None
        self._auth_token: Token[bool] | None = None
        self._snapshot: dict[str, Any] = {}

    def __enter__(self) -> "SystemLogScope":
        self._snapshot = get_log_context()
        if self._extra:
            bind_log_context(**self._extra)
        self._scope_token = _LOG_SCOPE.set("system")
        self._auth_token = _LOG_SCOPE_REQUIRES_USER.set(False)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._auth_token is not None:
            _LOG_SCOPE_REQUIRES_USER.reset(self._auth_token)
        if self._scope_token is not None:
            _LOG_SCOPE.reset(self._scope_token)
        restore_log_context(self._snapshot)

    async def __aenter__(self) -> "SystemLogScope":
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.__exit__(exc_type, exc, tb)


__all__ = [
    "LogContractViolation",
    "LogScope",
    "REQUIRED_AUTHENTICATED_REQUEST_KEYS",
    "REQUIRED_REQUEST_KEYS",
    "RequestLogScope",
    "SystemLogScope",
    "enter_request_scope",
    "exit_request_scope",
    "get_log_scope",
    "get_log_scope_requires_user",
]
