"""
AccessLogMiddleware: внешний middleware. Гарантирует request_id/trace_id для
каждого HTTP-запроса (включая static/openapi/docs), переводит логирование в
request-скоуп, пишет одну итоговую запись `http.request` со схемой
OTel-полей.

Это единственная точка генерации request_id для HTTP-фронта — внутренние
middleware (AuthMiddleware, бизнес-handler'ы) только дополняют скоуп
полями user.id/company.id/...
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import override

import structlog
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.types import ASGIApp

from core.logging import (
    bind_log_context,
    enter_request_scope,
    exit_request_scope,
    get_logger,
)
from core.logging.attributes import (
    EVENT_HTTP_REQUEST,
    EVENT_HTTP_REQUEST_FAILED,
    LOG_HTTP_CLIENT_IP,
    LOG_HTTP_DURATION_MS,
    LOG_HTTP_METHOD,
    LOG_HTTP_PATH,
    LOG_HTTP_REQUEST_SIZE,
    LOG_HTTP_RESPONSE_SIZE,
    LOG_HTTP_ROUTE,
    LOG_HTTP_STATUS_CODE,
    LOG_HTTP_USER_AGENT,
    LOG_REQUEST_ID,
)
from core.types import JsonObject

REQUEST_ID_HEADER = "X-Request-Id"
TRACE_ID_HEADER = "X-Trace-Id"


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Структурированный access-log + единая точка входа в request-скоуп."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        service_name: str,
    ) -> None:
        super().__init__(app)
        if not service_name.strip():
            raise ValueError("AccessLogMiddleware: service_name обязателен")
        self._service_name: str = service_name
        self._logger: structlog.stdlib.BoundLogger = get_logger("platform.http")

    @override
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        method = request.method

        request_id = self._resolve_request_id(request)
        trace_id = self._resolve_trace_id(request)

        client_host = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        request.state.request_id = request_id
        request.state.trace_id = trace_id

        scope_extra: JsonObject = {
            LOG_HTTP_METHOD: method,
            LOG_HTTP_PATH: path,
            LOG_HTTP_USER_AGENT: user_agent,
            LOG_HTTP_CLIENT_IP: client_host,
        }
        scope_token = enter_request_scope(
            request_id=request_id,
            trace_id=trace_id,
            service_name=self._service_name,
        )
        bind_log_context(**scope_extra)

        start = time.perf_counter()
        status_code: int | None = None
        response_size: int | None = None
        request_size: int | None = self._content_length(request.headers)
        try:
            response = await call_next(request)
            status_code = response.status_code
            response_size = self._content_length(response.headers)
            response.headers[REQUEST_ID_HEADER] = request_id
            response.headers[TRACE_ID_HEADER] = trace_id
            return response
        except Exception:
            status_code = 500
            self._logger.exception(
                EVENT_HTTP_REQUEST_FAILED,
                **{
                    LOG_HTTP_METHOD: method,
                    LOG_HTTP_ROUTE: self._route_pattern(request, path),
                    LOG_HTTP_PATH: path,
                    LOG_HTTP_STATUS_CODE: status_code,
                    LOG_HTTP_DURATION_MS: round((time.perf_counter() - start) * 1000.0, 3),
                    LOG_REQUEST_ID: request_id,
                },
            )
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000.0, 3)
            if status_code is not None and status_code != 500:
                self._logger.log(
                    self._level_for_status(status_code, path),
                    EVENT_HTTP_REQUEST,
                    **self._compose_fields(
                        method=method,
                        path=path,
                        route=self._route_pattern(request, path),
                        status_code=status_code,
                        duration_ms=duration_ms,
                        request_size=request_size,
                        response_size=response_size,
                        request_id=request_id,
                    ),
                )
            exit_request_scope(scope_token)

    def _resolve_request_id(self, request: Request) -> str:
        raw = request.headers.get(REQUEST_ID_HEADER)
        if raw is not None:
            value = raw.strip()
            if value:
                return value
        return uuid.uuid4().hex

    def _resolve_trace_id(self, request: Request) -> str:
        raw = request.headers.get(TRACE_ID_HEADER)
        if raw is not None:
            value = raw.strip()
            if value:
                return value
        return f"{self._service_name}:{uuid.uuid4().hex}"

    @staticmethod
    def _content_length(headers: Headers) -> int | None:
        raw = headers.get("content-length")
        if not raw:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _route_pattern(request: Request, path: str) -> str:
        route = request.scope.get("route")
        if isinstance(route, Route):
            pattern = route.path
            if pattern:
                return pattern
        return path

    @staticmethod
    def _level_for_status(status_code: int, path: str) -> int:
        if status_code >= 500:
            return logging.ERROR
        if status_code in (401, 404) and path.startswith(("/openapi", "/docs", "/static")):
            return logging.DEBUG
        if status_code >= 400:
            return logging.WARNING
        return logging.INFO

    @staticmethod
    def _compose_fields(
        *,
        method: str,
        path: str,
        route: str,
        status_code: int,
        duration_ms: float,
        request_size: int | None,
        response_size: int | None,
        request_id: str,
    ) -> JsonObject:
        fields: JsonObject = {
            LOG_HTTP_METHOD: method,
            LOG_HTTP_ROUTE: route,
            LOG_HTTP_PATH: path,
            LOG_HTTP_STATUS_CODE: status_code,
            LOG_HTTP_DURATION_MS: duration_ms,
            LOG_REQUEST_ID: request_id,
        }
        if request_size is not None:
            fields[LOG_HTTP_REQUEST_SIZE] = request_size
        if response_size is not None:
            fields[LOG_HTTP_RESPONSE_SIZE] = response_size
        return fields
