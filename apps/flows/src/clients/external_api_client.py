"""
ExternalAPIClient - HTTP клиент для вызова внешних API.

Поддерживает:
- @var: / @state: в URL, headers; JSON body_template с рекурсивным резолвом
- Подстановка {key} в URL значениями из args (inputs / input_mapping)
- Протокол ответа с interrupt
- Умная логика прокси: сначала без, при 401/403 - с прокси
"""

from typing import Any
from urllib.parse import urlparse

import httpx

from apps.flows.src.mapping import MappingResolver
from apps.flows.src.models.external_api import (
    ExternalAPIConfig,
    ResponseStatus,
    ResponseType,
)
from core.errors import ExternalAPIError
from core.http import ProxyStrategy, get_httpx_client
from core.logging import get_logger
from core.tracing.operation_span import traced_operation

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
        args: dict[str, Any],
        variables: dict[str, Any] | None = None,
        state: Any | None = None,
    ) -> dict[str, Any]:
        """
        Выполняет вызов внешнего API.

        Логика прокси: сначала без прокси, при 401/403 пробуем с прокси.

        Args:
            config: Конфигурация API
            args: Результат input_mapping (подстановка {key} в url, merge в JSON body)
            variables: state.variables
            state: ExecutionState для резолва body_template (@state: / @var: в JSON)

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
        if state is None:
            raise ExternalAPIError(
                "execution state is required for external_api url, headers, and body_template"
            )

        url = self._resolve_url(config.url, args, variables, state)
        headers = self._build_headers(config, variables, state)

        request_kwargs: dict[str, Any] = {
            "method": config.method.value,
            "url": url,
            "headers": headers,
        }

        if config.method.value != "GET":
            body = self._build_json_body(config, state, variables, args)
            if config.request_content_type == "application/json":
                request_kwargs["json"] = body
            else:
                request_kwargs["data"] = body

        logger.debug(f"ExternalAPI call: {config.method.value} {url}")

        async with traced_operation(
            "flows.external_api.call",
            event_type="external_api.call",
            operation_category="external_api",
            extra_attributes={
                "platform.external_api.url": url,
                "platform.external_api.method": config.method.value,
            },
        ):
            response = await self._request_with_proxy_fallback(config.timeout, request_kwargs)

        if response.status_code >= 400:
            raise ExternalAPIError(f"HTTP {response.status_code}: {response.text}")

        return self._parse_response(config, response)

    async def _request_with_proxy_fallback(
        self,
        timeout: float,
        request_kwargs: dict[str, Any],
    ) -> httpx.Response:
        """
        Выполняет запрос: сначала без прокси, при 401/403 - с прокси.
        Для локальных хостов прокси не используется.
        """
        async with get_httpx_client(timeout=timeout, strategy=ProxyStrategy.DIRECT_ONLY) as client:
            response = await client.request(**request_kwargs)

        url = request_kwargs.get("url", "")
        if response.status_code in PROXY_RETRY_STATUS_CODES and not self._is_local_url(url):
            logger.debug(f"Got {response.status_code}, retrying with proxy")
            async with get_httpx_client(timeout=timeout, strategy=ProxyStrategy.PROXY_ONLY) as client:
                response = await client.request(**request_kwargs)

        return response

    def _is_local_url(self, url: str) -> bool:
        """Проверяет, является ли URL локальным."""
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        return hostname in LOCAL_HOSTS

    def _resolve_url(
        self,
        url: str,
        args: dict[str, Any],
        variables: dict[str, Any],
        state: Any,
    ) -> str:
        """Резолвит URL с path параметрами и шаблонами в строке."""
        resolved = MappingResolver.resolve_http_header_value(url, state, variables)

        for key, value in args.items():
            resolved = resolved.replace(f"{{{key}}}", str(value))

        return resolved

    def _build_headers(
        self,
        config: ExternalAPIConfig,
        variables: dict[str, Any],
        state: Any,
    ) -> dict[str, str]:
        """Собирает headers с резолвингом @state: / @var:."""
        headers: dict[str, str] = {}

        for key, value in config.headers.items():
            headers[key] = MappingResolver.resolve_http_header_value(value, state, variables)

        if config.request_content_type and "Content-Type" not in headers:
            headers["Content-Type"] = config.request_content_type

        return headers

    def _build_json_body(
        self,
        config: ExternalAPIConfig,
        state: Any,
        variables: dict[str, Any],
        args: dict[str, Any],
    ) -> dict[str, Any]:
        merged = MappingResolver.parse_and_resolve_body_template(
            config.body_template, state, variables
        )
        if not isinstance(merged, dict):
            raise ExternalAPIError("body_template must resolve to a JSON object at the root")
        if not args:
            return merged
        return {**merged, **args}

    def _parse_response(
        self,
        config: ExternalAPIConfig,
        response: httpx.Response,
    ) -> dict[str, Any]:
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
