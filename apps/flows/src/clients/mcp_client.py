"""
MCP клиент - поддержка HTTP и SSE транспортов.

MCP (Model Context Protocol) использует JSON-RPC 2.0.
Поддерживаемые транспорты:
- HTTP (Streamable HTTP) - POST запросы с JSON ответами
- SSE (Server-Sent Events) - POST запросы с event stream ответами
"""

import hashlib
import json
from collections.abc import Mapping
from typing import cast

import httpx

from apps.flows.src.models.mcp import (
    MCPCallResult,
    MCPServerConfig,
    MCPToolInfo,
)
from apps.flows.src.services.browser_preview import emit_browser_preview_mcp_event
from core.http import ProxyStrategy, get_httpx_client
from core.logging import get_logger
from core.tracing.operation_span import traced_operation
from core.types import JsonObject, JsonValue, require_json_object
from core.variables import VarResolver

logger = get_logger(__name__)

MCP_PROTOCOL_VERSION = "2024-11-05"
_TRACE_TEXT_LIMIT = 2000


class MCPClientError(Exception):
    """Ошибка MCP клиента."""
    pass


class MCPClient:
    """
    Универсальный MCP клиент с поддержкой HTTP и SSE транспортов.

    Поддерживает:
    - HTTP транспорт (JSON-RPC over HTTP POST)
    - SSE транспорт (JSON-RPC over Server-Sent Events)
    - Session management через Mcp-Session-Id header
    - Резолвинг @var: в headers
    """

    def __init__(
        self,
        config: MCPServerConfig,
        variables: Mapping[str, JsonValue] | None = None,
        timeout: float = 60.0,
    ):
        self.config: MCPServerConfig = config
        self.variables: JsonObject = dict(variables or {})
        self.timeout: float = timeout
        self.session_id: str | None = None  # Получаем от сервера
        self._request_id: int = 0
        self._initialized: bool = False

    def _next_request_id(self) -> int:
        """Генерирует следующий ID запроса."""
        self._request_id += 1
        return self._request_id

    def _resolve_headers(self, include_session: bool = True) -> dict[str, str]:
        """Резолвит headers с @var: ссылками."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        # Session ID добавляется только после инициализации
        if include_session and self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        for key, value in self.config.headers.items():
            if "@var:" in value:
                headers[key] = VarResolver.resolve_text(value, self.variables)
            else:
                headers[key] = value

        return headers

    @staticmethod
    def _jsonrpc_envelope_from_body(text: str) -> JsonObject | None:
        """
        Извлекает один JSON-RPC 2.0 envelope из тела ответа.

        Поддерживает:
        - целиком application/json;
        - SSE: строки `data: {...}` (Streamable HTTP / совместимые прокси);
        - несколько `data:` — берётся первое валидное с result/error/jsonrpc.
        """
        if not text or not str(text).strip():
            return None
        s = str(text).strip()
        if s.startswith("{"):
            try:
                envelope = require_json_object(
                    cast(JsonValue, json.loads(s)),
                    "MCP JSON-RPC envelope",
                )
            except (json.JSONDecodeError, ValueError):
                envelope = None
            else:
                if (
                    envelope.get("jsonrpc") == "2.0"
                    or "result" in envelope
                    or "error" in envelope
                ):
                    return envelope
        for line in str(text).splitlines():
            line = line.strip()
            if not line:
                continue
            low = line.lower()
            if not low.startswith("data:"):
                continue
            payload = line[5:].lstrip()
            if not payload or payload == "[DONE]":
                continue
            try:
                envelope = require_json_object(
                    cast(JsonValue, json.loads(payload)),
                    "MCP SSE JSON-RPC envelope",
                )
            except (json.JSONDecodeError, ValueError):
                continue
            if (
                envelope.get("jsonrpc") == "2.0"
                or "result" in envelope
                or "error" in envelope
            ):
                return envelope
        return None

    @staticmethod
    def _trace_text(value: JsonValue, *, limit: int = _TRACE_TEXT_LIMIT) -> str:
        """
        Trace attributes должны быть компактными и безопасными по кодировке.
        Возвращаем ASCII-строку: unicode будет экранирован как \\uXXXX.
        """
        if value is None:
            return ""
        if isinstance(value, str):
            raw = value.encode("unicode_escape", errors="backslashreplace").decode("ascii", errors="replace")
        else:
            raw = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        if len(raw) <= limit:
            return raw
        return raw[:limit] + "...[truncated]"

    @staticmethod
    def _sha256_hex(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

    async def _read_response_text(self, response: httpx.Response) -> str:
        _ = await response.aread()
        return response.text

    async def _rpc_call(
        self,
        method: str,
        params: JsonObject | None = None,
        include_session: bool = True,
    ) -> tuple[JsonValue, httpx.Headers]:
        """
        Выполняет JSON-RPC 2.0 вызов через HTTP или SSE.

        Args:
            method: Имя метода (initialize, tools/list, tools/call)
            params: Параметры метода
            include_session: Включать ли session_id в headers

        Returns:
            Кортеж (результат, response headers)

        Raises:
            MCPClientError: При ошибке вызова
        """
        request_id = self._next_request_id()
        payload: JsonObject = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        headers = self._resolve_headers(include_session=include_session)

        logger.debug(f"MCP RPC call: {method} to {self.config.url}")

        if method == "tools/call":
            operation_name = "flows.mcp.tool_call"
            event_type = "mcp.tool_call"
        else:
            operation_name = "flows.mcp.rpc_call"
            event_type = "mcp.rpc_call"

        async with traced_operation(
            operation_name,
            event_type=event_type,
            operation_category="mcp",
            extra_attributes={
                "platform.mcp.server_id": self.config.server_id,
                "platform.mcp.method": method,
                "platform.mcp.request_id": request_id,
                "platform.mcp.has_session": bool(self.session_id) if include_session else False,
                "platform.mcp.request_preview": MCPClient._trace_text(payload),
            },
        ) as span:
            # Удобные поля для tools/call: отдельно tool_name и ключи аргументов.
            if method == "tools/call" and params:
                raw_name = params.get("name")
                raw_args = params.get("arguments")
                if isinstance(raw_name, str) and raw_name.strip():
                    span.set_attribute("platform.mcp.tool_name", raw_name.strip())
                if isinstance(raw_args, dict):
                    keys = list(raw_args.keys())
                    keys.sort()
                    span.set_attribute("platform.mcp.tool_args_keys", ",".join(keys[:50]))

            async with get_httpx_client(timeout=self.timeout, strategy=ProxyStrategy.DIRECT_ONLY) as client:
                response = await client.post(
                    self.config.url,
                    json=payload,
                    headers=headers,
                )

                response_headers = response.headers
                text = await self._read_response_text(response)
                response_content_type = cast(
                    str,
                    response.headers.get("content-type", ""),
                )

                span.set_attribute("http.status_code", int(response.status_code))
                span.set_attribute(
                    "platform.mcp.response_content_type",
                    response_content_type.strip(),
                )
                span.set_attribute("platform.mcp.response_bytes", len(text.encode("utf-8", errors="replace")))
                span.set_attribute("platform.mcp.response_sha256", MCPClient._sha256_hex(text))
                span.set_attribute("platform.mcp.response_preview", MCPClient._trace_text(text))
                sid = cast(
                    str | None,
                    response_headers.get("mcp-session-id")
                    or response_headers.get("Mcp-Session-Id"),
                )
                if sid is not None and sid.strip():
                    span.set_attribute("platform.mcp.response_session_id", sid.strip())

                if response.status_code >= 400:
                    raise MCPClientError(
                        f"MCP HTTP error: {response.status_code} {text}"
                    )

                result = self._jsonrpc_envelope_from_body(text)
                if result is None:
                    snippet = text[:500] if text else ""
                    ct = response_content_type
                    raise MCPClientError(
                        f"MCP: empty response for {method} (content-type={ct!r}, body={snippet!r})"
                    )

        error_raw = result.get("error")
        if error_raw is not None:
            error = require_json_object(error_raw, "MCP RPC error")
            raise MCPClientError(
                f"MCP RPC error: {error.get('code')} - {error.get('message')}"
            )

        return result.get("result"), response_headers

    async def initialize(self) -> JsonObject:
        """
        Инициализирует MCP сессию.

        После initialize сервер возвращает Mcp-Session-Id в headers,
        который нужно использовать для последующих запросов.

        Returns:
            Информация о сервере (capabilities, serverInfo)
        """
        if self._initialized:
            return {}

        initialize_params: JsonObject = {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {
                "name": "agent-lab",
                "version": "1.0.0",
            },
        }
        result, headers = await self._rpc_call(
            "initialize",
            initialize_params,
            include_session=False,  # Первый запрос без session
        )

        # Получаем session_id из response headers
        self.session_id = headers.get("mcp-session-id") or headers.get("Mcp-Session-Id")

        self._initialized = True
        logger.info(f"MCP session initialized: {self.session_id}")

        return require_json_object(result, "MCP initialize result")

    async def list_tools(self) -> list[MCPToolInfo]:
        """
        Получает список доступных tools с MCP сервера.

        Returns:
            Список MCPToolInfo
        """
        if not self._initialized:
            _ = await self.initialize()

        raw_result, _ = await self._rpc_call("tools/list")
        result = require_json_object(raw_result, "MCP tools/list result")

        raw_tools = result.get("tools")
        if not isinstance(raw_tools, list):
            raise MCPClientError("MCP tools/list result.tools must be an array")
        tools: list[MCPToolInfo] = []
        for index, tool_data in enumerate(raw_tools):
            tools.append(
                MCPToolInfo.model_validate(
                    require_json_object(tool_data, f"MCP tools[{index}]")
                )
            )

        logger.info(f"MCP server {self.config.server_id}: {len(tools)} tools available")
        return tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: JsonObject | None = None,
    ) -> MCPCallResult:
        """
        Вызывает tool на MCP сервере.

        Args:
            tool_name: Имя tool
            arguments: Аргументы вызова

        Returns:
            MCPCallResult с результатом
        """
        if not self._initialized:
            _ = await self.initialize()

        logger.debug(f"MCP tool call: {tool_name}")
        args: JsonObject = arguments or {}
        await emit_browser_preview_mcp_event(
            config=self.config,
            tool_name=tool_name,
            arguments=args,
            phase="started",
        )

        try:
            raw_result, _ = await self._rpc_call(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": args,
                },
            )
        except Exception as exc:
            await emit_browser_preview_mcp_event(
                config=self.config,
                tool_name=tool_name,
                arguments=args,
                phase="failed",
                error=str(exc),
            )
            raise

        result = require_json_object(raw_result, "MCP tools/call result")
        call_result = MCPCallResult.model_validate(result)
        await emit_browser_preview_mcp_event(
            config=self.config,
            tool_name=tool_name,
            arguments=args,
            phase="failed" if call_result.is_error else "finished",
            result=call_result,
        )
        return call_result


# Алиас для обратной совместимости
MCPHttpClient = MCPClient


# Кэш клиентов по server_id
_client_cache: dict[str, MCPClient] = {}


async def get_mcp_client(
    config: MCPServerConfig,
    variables: Mapping[str, JsonValue] | None = None,
    timeout: float = 60.0,
) -> MCPClient:
    """
    Получает или создает MCP клиент для сервера.

    Args:
        config: Конфигурация MCP сервера
        variables: Переменные для резолвинга @var:
        timeout: Таймаут запросов

    Returns:
        Инициализированный MCPClient
    """
    cache_key = f"{config.server_id}"

    if cache_key in _client_cache:
        client = _client_cache[cache_key]
        client.variables = dict(variables or {})
        return client

    client = MCPClient(config, variables, timeout)
    _ = await client.initialize()

    _client_cache[cache_key] = client
    return client


def clear_mcp_client_cache(server_id: str | None = None) -> None:
    """
    Очищает кэш MCP клиентов.

    Args:
        server_id: ID сервера для очистки. None = очистить всё.
    """
    if server_id:
        _ = _client_cache.pop(server_id, None)
    else:
        _client_cache.clear()
