"""ExternalAPIClient - HTTP клиент для вызова внешних API."""

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
from core.http.client import HttpRequestKwargs
from core.logging import get_logger
from core.state import ExecutionState
from core.tracing.operation_span import traced_operation
from core.types import JsonObject, JsonValue, parse_json_value, require_json_object

logger = get_logger(__name__)

PROXY_RETRY_STATUS_CODES = frozenset([401, 403])
LOCAL_HOSTS = frozenset(["localhost", "127.0.0.1", "0.0.0.0", "::1"])


class ExternalAPIClient:
    """
    HTTP клиент для вызова внешних API.

    Поддерживает резолвинг @var: переменных через VariablesService.
    """

    def __init__(self, timeout: float = 30.0):
        self.timeout: float = timeout

    async def call(
        self,
        config: ExternalAPIConfig,
        args: JsonObject,
        variables: JsonObject | None = None,
        state: ExecutionState | None = None,
    ) -> JsonObject:
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

        json_body: JsonObject | None = None
        data_body: JsonObject | None = None
        if config.method.value != "GET":
            body = self._build_json_body(config, state, variables, args)
            if config.request_content_type == "application/json":
                json_body = body
            else:
                data_body = body

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
            response = await self._request_with_proxy_fallback(
                timeout=config.timeout,
                method=config.method.value,
                url=url,
                headers=headers,
                json_body=json_body,
                data_body=data_body,
            )

        if response.status_code >= 400:
            raise ExternalAPIError(f"HTTP {response.status_code}: {response.text}")

        return self._parse_response(config, response)

    async def _request_with_proxy_fallback(
        self,
        timeout: float,
        method: str,
        url: str,
        headers: dict[str, str],
        json_body: JsonObject | None = None,
        data_body: JsonObject | None = None,
    ) -> httpx.Response:
        """
        Выполняет запрос: сначала без прокси, при 401/403 - с прокси.
        Для локальных хостов прокси не используется.
        """
        request_kwargs: HttpRequestKwargs = {"headers": headers}
        if json_body is not None:
            request_kwargs["json"] = json_body
        if data_body is not None:
            request_kwargs["data"] = data_body

        async with get_httpx_client(timeout=timeout, strategy=ProxyStrategy.DIRECT_ONLY) as client:
            response = await client.request(method, url, **request_kwargs)

        if response.status_code in PROXY_RETRY_STATUS_CODES and not self._is_local_url(url):
            logger.debug(f"Got {response.status_code}, retrying with proxy")
            async with get_httpx_client(timeout=timeout, strategy=ProxyStrategy.PROXY_ONLY) as client:
                response = await client.request(method, url, **request_kwargs)

        return response

    def _is_local_url(self, url: str) -> bool:
        """Проверяет, является ли URL локальным."""
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        return hostname in LOCAL_HOSTS

    def _resolve_url(
        self,
        url: str,
        args: JsonObject,
        variables: JsonObject,
        state: ExecutionState,
    ) -> str:
        """Резолвит URL с path параметрами и шаблонами в строке."""
        resolved = MappingResolver.resolve_http_header_value(url, state, variables)

        for key, value in args.items():
            resolved = resolved.replace(f"{{{key}}}", str(value))

        return resolved

    def _build_headers(
        self,
        config: ExternalAPIConfig,
        variables: JsonObject,
        state: ExecutionState,
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
        state: ExecutionState,
        variables: JsonObject,
        args: JsonObject,
    ) -> JsonObject:
        merged = MappingResolver.parse_and_resolve_body_template(
            config.body_template, state, variables
        )
        body = require_json_object(merged, "external_api.body_template")
        if not args:
            return body
        return {**body, **args}

    def _parse_response(
        self,
        config: ExternalAPIConfig,
        response: httpx.Response,
    ) -> JsonObject:
        """Парсит ответ согласно response_schema."""
        schema = config.response_schema

        if config.response_type == ResponseType.JSON:
            raw = parse_json_value(response.content, "external_api.response")
        else:
            raw = {"text": response.text}

        status = ResponseStatus.COMPLETED
        data: JsonValue = raw
        interrupt: JsonValue = None
        error: JsonValue = None

        if isinstance(raw, dict):
            raw_obj = require_json_object(raw, "external_api.response")
            status_value = raw.get(schema.status_field)
            if status_value == "waiting_input":
                status = ResponseStatus.WAITING_INPUT
            elif status_value == "error":
                status = ResponseStatus.ERROR

            if schema.data_field in raw_obj:
                data = raw_obj[schema.data_field]

            if schema.interrupt_field in raw_obj:
                interrupt = raw_obj[schema.interrupt_field]

            if schema.error_field in raw_obj:
                error = raw_obj[schema.error_field]

        return {
            "status": status.value,
            "data": data,
            "interrupt": interrupt,
            "error": error,
            "raw": raw,
        }
