"""
ExternalAPIClient - HTTP клиент для вызова внешних API.

Поддерживает:
- @var: переменные в URL, headers, параметрах (включая вложенные пути @var:config.api_key)
- OpenAPI-like параметры (query, path, header, body)
- Протокол ответа с interrupt
- Умная логика прокси: сначала без, при 401/403 - с прокси
"""

from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from apps.agents.src.mapping import MappingResolver
from core.http import get_httpx_client
from core.logging import get_logger
from apps.agents.src.models.external_api import (
    ExternalAPIConfig,
    ParameterLocation,
    ResponseStatus,
    ResponseType,
)
from core.errors import ExternalAPIError

logger = get_logger(__name__)

PROXY_RETRY_STATUS_CODES = frozenset([401, 403])
LOCAL_HOSTS = frozenset(["localhost", "127.0.0.1", "0.0.0.0", "::1"])


class ExternalAPIClient:
    """
    HTTP клиент для вызова внешних API.

    Поддерживает резолвинг @var: переменных через VariablesService.
    """

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def call(
        self,
        config: ExternalAPIConfig,
        args: Dict[str, Any],
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Выполняет вызов внешнего API.

        Логика прокси: сначала без прокси, при 401/403 пробуем с прокси.

        Args:
            config: Конфигурация API
            args: Аргументы вызова (от LLM или из state)
            variables: Резолвнутые переменные (state.variables)

        Returns:
            Результат в формате:
            {
                "status": "completed" | "waiting_input" | "error",
                "data": {...},
                "interrupt": {"question": "..."} | None,
                "error": "..." | None,
                "raw": {...}
            }
        """
        variables = variables or {}

        url = self._resolve_url(config.url, args, variables)
        headers = self._build_headers(config, variables)
        query_params, body = self._build_request(config, args, variables)

        logger.debug(f"ExternalAPI call: {config.method.value} {url}")

        request_kwargs = {
            "method": config.method.value,
            "url": url,
            "headers": headers,
        }
        if query_params:
            request_kwargs["params"] = query_params
        if body and config.method.value != "GET":
            if config.request_content_type == "application/json":
                request_kwargs["json"] = body
            else:
                request_kwargs["data"] = body

        response = await self._request_with_proxy_fallback(config.timeout, request_kwargs)

        if response.status_code >= 400:
            raise ExternalAPIError(f"HTTP {response.status_code}: {response.text}")

        return self._parse_response(config, response)

    async def _request_with_proxy_fallback(
        self,
        timeout: float,
        request_kwargs: Dict[str, Any],
    ) -> httpx.Response:
        """
        Выполняет запрос: сначала без прокси, при 401/403 - с прокси.
        Для локальных хостов прокси не используется.
        """
        async with get_httpx_client(timeout=timeout, proxy=False) as client:
            response = await client.request(**request_kwargs)

        url = request_kwargs.get("url", "")
        if response.status_code in PROXY_RETRY_STATUS_CODES and not self._is_local_url(url):
            logger.debug(f"Got {response.status_code}, retrying with proxy")
            async with get_httpx_client(timeout=timeout, proxy=True) as client:
                response = await client.request(**request_kwargs)

        return response

    def _is_local_url(self, url: str) -> bool:
        """Проверяет, является ли URL локальным."""
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        return hostname in LOCAL_HOSTS

    def _resolve_value(self, value: Any, variables: Dict[str, Any]) -> Any:
        """Резолвит @var: значения с поддержкой вложенных путей."""
        if not isinstance(value, str):
            return value
        return MappingResolver.resolve_vars_in_string(value, variables)

    def _resolve_url(
        self,
        url: str,
        args: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> str:
        """Резолвит URL с path параметрами и @var."""
        resolved = self._resolve_value(url, variables)

        for key, value in args.items():
            resolved = resolved.replace(f"{{{key}}}", str(value))

        return resolved

    def _build_headers(
        self,
        config: ExternalAPIConfig,
        variables: Dict[str, Any],
    ) -> Dict[str, str]:
        """Собирает headers с резолвингом @var."""
        headers = {}

        for key, value in config.headers.items():
            headers[key] = self._resolve_value(value, variables)

        for key, value in config.auth_headers.items():
            headers[key] = self._resolve_value(value, variables)

        if config.request_content_type and "Content-Type" not in headers:
            headers["Content-Type"] = config.request_content_type

        return headers

    def _build_request(
        self,
        config: ExternalAPIConfig,
        args: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Собирает query params и body из параметров.

        Returns:
            (query_params, body)
        """
        query_params = {}
        body = {}

        for param in config.parameters:
            value = args.get(param.name)

            if value is None and param.default is not None:
                value = self._resolve_value(param.default, variables)

            if value is None:
                if param.required:
                    raise ExternalAPIError(f"Required parameter '{param.name}' is missing")
                continue

            if param.location == ParameterLocation.QUERY:
                query_params[param.name] = value
            elif param.location == ParameterLocation.BODY:
                body[param.name] = value

        return query_params, body

    def _parse_response(
        self,
        config: ExternalAPIConfig,
        response: httpx.Response,
    ) -> Dict[str, Any]:
        """Парсит ответ согласно response_schema."""
        schema = config.response_schema
        raw = None

        if config.response_type == ResponseType.JSON:
            raw = response.json()
        else:
            raw = {"text": response.text}

        status = ResponseStatus.COMPLETED
        data = raw
        interrupt = None
        error = None

        if isinstance(raw, dict):
            status_value = raw.get(schema.status_field)
            if status_value == "waiting_input":
                status = ResponseStatus.WAITING_INPUT
            elif status_value == "error":
                status = ResponseStatus.ERROR

            if schema.data_field in raw:
                data = raw[schema.data_field]

            if schema.interrupt_field in raw:
                interrupt = raw[schema.interrupt_field]

            if schema.error_field in raw:
                error = raw[schema.error_field]

        return {
            "status": status.value,
            "data": data,
            "interrupt": interrupt,
            "error": error,
            "raw": raw,
        }
