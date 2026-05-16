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
from typing import cast as type_cast

import httpx

from core.config import get_settings
from core.context import get_context
from core.http import get_httpx_client
from core.logging import get_log_context, get_logger

logger = get_logger(__name__)

TRACE_ID_HEADER = "X-Trace-Id"
REQUEST_ID_HEADER = "X-Request-Id"
COMPANY_ID_HEADER = "X-Company-Id"
USER_ID_HEADER = "X-User-Id"
NAMESPACE_HEADER = "X-Platform-Namespace"


class ServiceClientError(Exception):
    """Ошибка межсервисного взаимодействия"""

    pass


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

        Args:
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
            if context.active_company:
                headers[COMPANY_ID_HEADER] = context.active_company.company_id
            if context.user:
                headers[USER_ID_HEADER] = context.user.user_id
            if context.active_namespace and context.active_namespace != "default":
                headers[NAMESPACE_HEADER] = context.active_namespace

        if not trace_id:
            trace_id = log_ctx.get("trace_id")

        if trace_id:
            headers[TRACE_ID_HEADER] = trace_id
        if isinstance(request_id, str) and request_id:
            headers[REQUEST_ID_HEADER] = request_id

        return headers

    async def request(
        self,
        service: str,
        method: str,
        path: str,
        timeout: float = 30.0,
        **kwargs: object,
    ) -> object:
        """
        Выполняет HTTP запрос к сервису.

        Args:
            service: Имя сервиса (flows, crm, frontend)
            method: HTTP метод (GET, POST, PUT, DELETE)
            path: Путь запроса (без базового URL)
            timeout: Таймаут запроса
            **kwargs: Дополнительные параметры для httpx

        Returns:
            Ответ сервиса (JSON)

        Raises:
            ServiceClientError: если запрос не удался
        """

        base_url = self._get_service_url(service)
        url = f"{base_url}{path}"

        # Не устанавливаем Content-Type: application/json если передаются files
        # (httpx сам установит multipart/form-data)
        include_content_type = "files" not in kwargs
        headers = self._build_headers(include_content_type=include_content_type)
        extra_headers = kwargs.pop("headers", None)
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
                response = await client.request(method, url, headers=headers, **kwargs)
                response = response.raise_for_status()

                if response.content:
                    return type_cast(object, response.json())
                return None

        except httpx.HTTPStatusError as e:
            raise ServiceClientError(
                f"HTTP {e.response.status_code} при запросе к {service}: {e.response.text}"
            )
        except Exception as e:
            raise ServiceClientError(f"Ошибка запроса к {service}: {e}")

    async def get(self, service: str, path: str, timeout: float = 30.0, **kwargs: object) -> object:
        """GET запрос к сервису"""
        return await self.request(service, "GET", path, timeout=timeout, **kwargs)

    async def post(
        self, service: str, path: str, timeout: float = 30.0, **kwargs: object
    ) -> object:
        """POST запрос к сервису"""
        return await self.request(service, "POST", path, timeout=timeout, **kwargs)

    async def put(self, service: str, path: str, timeout: float = 30.0, **kwargs: object) -> object:
        """PUT запрос к сервису"""
        return await self.request(service, "PUT", path, timeout=timeout, **kwargs)

    async def patch(
        self, service: str, path: str, timeout: float = 30.0, **kwargs: object
    ) -> object:
        """PATCH запрос к сервису"""
        return await self.request(service, "PATCH", path, timeout=timeout, **kwargs)

    async def delete(
        self, service: str, path: str, timeout: float = 30.0, **kwargs: object
    ) -> object:
        """DELETE запрос к сервису"""
        return await self.request(service, "DELETE", path, timeout=timeout, **kwargs)
