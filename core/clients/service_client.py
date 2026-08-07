"""
Простой HTTP клиент для межсервисного взаимодействия.

Автоматически добавляет заголовки из контекста:
- X-Trace-Id (обязателен; берётся из Context.trace_id, иначе из лог-контекста)
- X-Request-Id
- Authorization
- X-Company-Id
- X-User-Id
- X-Platform-Namespace (если не default)
"""

from collections.abc import Mapping
from typing import Unpack
from typing import cast as type_cast

import httpx

from core.config import get_settings
from core.context import get_context
from core.http import get_httpx_client
from core.http.client import HttpRequestKwargs
from core.internal_context_headers import build_internal_context_headers
from core.logging import get_log_context, get_logger
from core.test_scope import TEST_SCOPE_HEADER, resolve_test_scope
from core.types import JsonValue, parse_json_value, require_json_value

logger = get_logger(__name__)

TRACE_ID_HEADER = "X-Trace-Id"
REQUEST_ID_HEADER = "X-Request-Id"
COMPANY_ID_HEADER = "X-Company-Id"
USER_ID_HEADER = "X-User-Id"
NAMESPACE_HEADER = "X-Platform-Namespace"


class ServiceClientError(Exception):
    """Ошибка межсервисного взаимодействия."""

    status_code: int | None
    response_text: str | None

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_text: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

    @property
    def is_client_error(self) -> bool:
        return self.status_code is not None and 400 <= self.status_code < 500

    def http_detail(self) -> JsonValue | str:
        """Тело для HTTPException.detail: FastAPI `detail` из JSON peer-ответа, иначе текст."""
        if self.response_text is None:
            return str(self)
        response_text = self.response_text.strip()
        if response_text == "":
            return str(self)
        try:
            parsed = parse_json_value(response_text, "service_client.response")
        except ValueError:
            return self.response_text
        if isinstance(parsed, dict) and "detail" in parsed:
            return parsed["detail"]
        return parsed


class ServiceClient:
    """
    Простой клиент для межсервисного взаимодействия.

    Автоматически добавляет заголовки из контекста (trace_id, auth, company, user).
    Управляется через DI контейнер.
    """

    def _get_service_url(self, service: str) -> str:
        """Получает URL сервиса из конфигурации"""
        settings = get_settings()
        return settings.server.get_service_url(service)

    def _build_headers(self, include_content_type: bool = True) -> dict[str, str]:
        """
        Собирает заголовки из текущего контекста.

        Аргументы:
            include_content_type: Включать ли Content-Type: application/json
                                 (False для multipart/form-data запросов)
        """
        headers: dict[str, str] = {}

        if include_content_type:
            headers["Content-Type"] = "application/json"

        log_ctx = get_log_context()

        trace_id = None
        request_id = log_ctx.get("request_id")

        context = get_context()
        if context is not None:
            if context.trace_id:
                trace_id = context.trace_id
            if context.auth_token:
                headers["Authorization"] = f"Bearer {context.auth_token}"
            elif context.active_company is not None:
                headers.update(
                    build_internal_context_headers(
                        company_id=context.active_company.company_id,
                        user_id=context.user.user_id,
                    )
                )
            if context.active_company:
                headers[COMPANY_ID_HEADER] = context.active_company.company_id
            if context.user:
                headers[USER_ID_HEADER] = context.user.user_id
            if context.active_namespace and context.active_namespace != "default":
                headers[NAMESPACE_HEADER] = context.active_namespace

        if not trace_id:
            log_trace_id = log_ctx.get("trace_id")
            if isinstance(log_trace_id, str):
                trace_id = log_trace_id

        if trace_id:
            headers[TRACE_ID_HEADER] = trace_id
        if isinstance(request_id, str) and request_id:
            headers[REQUEST_ID_HEADER] = request_id

        test_scope = resolve_test_scope()
        if test_scope is not None:
            headers[TEST_SCOPE_HEADER] = test_scope

        return headers

    async def request(
        self,
        service: str,
        method: str,
        path: str,
        timeout: float = 30.0,
        **kwargs: Unpack[HttpRequestKwargs],
    ) -> JsonValue:
        """
        Выполняет HTTP запрос к сервису.

        Аргументы:
            service: Имя сервиса (flows, crm, frontend)
            method: HTTP метод (GET, POST, PUT, DELETE)
            path: Путь запроса (без базового URL)
            timeout: Таймаут запроса
            **kwargs: Дополнительные параметры для httpx

        Возвращает:
            Ответ сервиса (JSON)

        Исключения:
            ServiceClientError: если запрос не удался
        """

        base_url = self._get_service_url(service)
        url = f"{base_url}{path}"

        # Не устанавливаем Content-Type: application/json, если передаются files
        # (httpx сам установит multipart/form-data)
        include_content_type = (
            "files" not in kwargs and "content" not in kwargs and "data" not in kwargs
        )
        headers = self._build_headers(include_content_type=include_content_type)
        request_kwargs = dict(kwargs)
        extra_headers = request_kwargs.pop("headers", None)
        if extra_headers is not None:
            if not isinstance(extra_headers, Mapping):
                raise ServiceClientError("headers must be a mapping")
            extra_headers_map = type_cast(Mapping[object, object], extra_headers)
            for key, value in extra_headers_map.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise ServiceClientError("headers must contain only str keys and str values")
                headers[key] = value

        try:
            async with get_httpx_client(timeout=timeout) as client:
                typed_request_kwargs = type_cast(
                    HttpRequestKwargs,
                    type_cast(object, request_kwargs),
                )
                typed_request_kwargs["headers"] = headers
                response = await client.request(method, url, **typed_request_kwargs)
                response = response.raise_for_status()

                if response.content:
                    return require_json_value(
                        type_cast(object, response.json()),
                        f"{service} {method} {path} response",
                    )
                return None

        except httpx.HTTPStatusError as e:
            raise ServiceClientError(
                f"HTTP {e.response.status_code} при запросе к {service}: {e.response.text}",
                status_code=e.response.status_code,
                response_text=e.response.text,
            ) from e
        except Exception as e:
            detail = str(e).strip()
            if detail == "":
                detail = type(e).__name__
                cause = e.__cause__
                if cause is not None:
                    cause_detail = str(cause).strip()
                    detail = (
                        f"{detail} caused by {type(cause).__name__}"
                        + (f": {cause_detail}" if cause_detail else "")
                    )
            raise ServiceClientError(f"Ошибка запроса к {service}: {detail}") from e

    async def get(
        self,
        service: str,
        path: str,
        timeout: float = 30.0,
        **kwargs: Unpack[HttpRequestKwargs],
    ) -> JsonValue:
        """GET запрос к сервису"""
        return await self.request(service, "GET", path, timeout=timeout, **kwargs)

    async def post(
        self,
        service: str,
        path: str,
        timeout: float = 30.0,
        **kwargs: Unpack[HttpRequestKwargs],
    ) -> JsonValue:
        """POST запрос к сервису"""
        return await self.request(service, "POST", path, timeout=timeout, **kwargs)

    async def put(
        self,
        service: str,
        path: str,
        timeout: float = 30.0,
        **kwargs: Unpack[HttpRequestKwargs],
    ) -> JsonValue:
        """PUT запрос к сервису"""
        return await self.request(service, "PUT", path, timeout=timeout, **kwargs)

    async def patch(
        self,
        service: str,
        path: str,
        timeout: float = 30.0,
        **kwargs: Unpack[HttpRequestKwargs],
    ) -> JsonValue:
        """PATCH запрос к сервису"""
        return await self.request(service, "PATCH", path, timeout=timeout, **kwargs)

    async def delete(
        self,
        service: str,
        path: str,
        timeout: float = 30.0,
        **kwargs: Unpack[HttpRequestKwargs],
    ) -> JsonValue:
        """DELETE запрос к сервису"""
        return await self.request(service, "DELETE", path, timeout=timeout, **kwargs)
