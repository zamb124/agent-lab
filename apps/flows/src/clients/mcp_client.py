"""
MCP клиент - поддержка HTTP и SSE транспортов.

MCP (Model Context Protocol) использует JSON-RPC 2.0.
Поддерживаемые транспорты:
- HTTP (Streamable HTTP) - POST запросы с JSON ответами
- SSE (Server-Sent Events) - POST запросы с event stream ответами
"""

import json
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from apps.flows.src.models.mcp import (
    MCPCallResult,
    MCPServerConfig,
    MCPToolInfo,
    MCPTransportType,
)
from core.http import get_httpx_client
from core.logging import get_logger
from core.tracing.operation_span import traced_operation
from core.variables import VarResolver

logger = get_logger(__name__)

MCP_PROTOCOL_VERSION = "2024-11-05"


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
        variables: Optional[Dict[str, Any]] = None,
        timeout: float = 60.0,
    ):
        self.config = config
        self.variables = variables or {}
        self.timeout = timeout
        self.session_id: Optional[str] = None  # Получаем от сервера
        self._request_id = 0
        self._initialized = False
    
    def _next_request_id(self) -> int:
        """Генерирует следующий ID запроса."""
        self._request_id += 1
        return self._request_id
    
    def _resolve_headers(self, include_session: bool = True) -> Dict[str, str]:
        """Резолвит headers с @var: ссылками."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        
        # Session ID добавляется только после инициализации
        if include_session and self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        
        for key, value in self.config.headers.items():
            if isinstance(value, str) and "@var:" in value:
                headers[key] = VarResolver.resolve_text(value, self.variables)
            else:
                headers[key] = value
        
        return headers
    
    @staticmethod
    def _jsonrpc_envelope_from_body(text: str) -> Optional[Dict[str, Any]]:
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
                o = json.loads(s)
            except json.JSONDecodeError:
                o = None
            else:
                if isinstance(o, dict) and (
                    o.get("jsonrpc") == "2.0" or "result" in o or "error" in o
                ):
                    return o
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
                o = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(o, dict) and (
                o.get("jsonrpc") == "2.0" or "result" in o or "error" in o
            ):
                return o
        return None

    async def _read_response_text(self, response: httpx.Response) -> str:
        await response.aread()
        return response.text
    
    async def _rpc_call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        include_session: bool = True,
    ) -> tuple[Any, httpx.Headers]:
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
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params:
            payload["params"] = params
        
        headers = self._resolve_headers(include_session=include_session)
        
        logger.debug(f"MCP RPC call: {method} to {self.config.url}")
        
        async with get_httpx_client(timeout=self.timeout, proxy=False) as client:
            response = await client.post(
                self.config.url,
                json=payload,
                headers=headers,
            )
            
            response_headers = response.headers
            text = await self._read_response_text(response)
            
            if response.status_code >= 400:
                raise MCPClientError(
                    f"MCP HTTP error: {response.status_code} {text}"
                )
            
            result = self._jsonrpc_envelope_from_body(text)
            if result is None:
                snippet = text[:500] if text else ""
                ct = response.headers.get("content-type", "")
                raise MCPClientError(
                    f"MCP: empty response for {method} (content-type={ct!r}, body={snippet!r})"
                )
        
        if "error" in result:
            error = result["error"]
            raise MCPClientError(
                f"MCP RPC error: {error.get('code')} - {error.get('message')}"
            )
        
        return result.get("result"), response_headers
    
    async def initialize(self) -> Dict[str, Any]:
        """
        Инициализирует MCP сессию.
        
        После initialize сервер возвращает Mcp-Session-Id в headers,
        который нужно использовать для последующих запросов.
        
        Returns:
            Информация о сервере (capabilities, serverInfo)
        """
        if self._initialized:
            return {}
        
        result, headers = await self._rpc_call(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "agent-lab",
                    "version": "1.0.0",
                },
            },
            include_session=False,  # Первый запрос без session
        )
        
        # Получаем session_id из response headers
        self.session_id = headers.get("mcp-session-id") or headers.get("Mcp-Session-Id")
        
        self._initialized = True
        logger.info(f"MCP session initialized: {self.session_id}")
        
        return result
    
    async def list_tools(self) -> List[MCPToolInfo]:
        """
        Получает список доступных tools с MCP сервера.
        
        Returns:
            Список MCPToolInfo
        """
        if not self._initialized:
            await self.initialize()
        
        result, _ = await self._rpc_call("tools/list")
        
        tools = []
        for tool_data in result.get("tools", []):
            tools.append(MCPToolInfo(
                name=tool_data.get("name", ""),
                description=tool_data.get("description"),
                input_schema=tool_data.get("inputSchema"),
            ))
        
        logger.info(f"MCP server {self.config.server_id}: {len(tools)} tools available")
        return tools
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
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
            await self.initialize()
        
        logger.debug(f"MCP tool call: {tool_name}")

        async with traced_operation(
            "flows.mcp.call_tool",
            event_type="mcp.call_tool",
            operation_category="mcp",
            extra_attributes={
                "platform.mcp.server_id": self.config.server_id,
                "platform.mcp.tool_name": tool_name,
            },
        ):
            result, _ = await self._rpc_call(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": arguments or {},
                },
            )

        return MCPCallResult(
            is_error=result.get("isError", False),
            content=result.get("content", []),
        )


# Алиас для обратной совместимости
MCPHttpClient = MCPClient


# Кэш клиентов по server_id
_client_cache: Dict[str, MCPClient] = {}


async def get_mcp_client(
    config: MCPServerConfig,
    variables: Optional[Dict[str, Any]] = None,
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
        client.variables = variables or {}
        return client
    
    client = MCPClient(config, variables, timeout)
    await client.initialize()
    
    _client_cache[cache_key] = client
    return client


def clear_mcp_client_cache(server_id: Optional[str] = None) -> None:
    """
    Очищает кэш MCP клиентов.
    
    Args:
        server_id: ID сервера для очистки. None = очистить всё.
    """
    if server_id:
        _client_cache.pop(server_id, None)
    else:
        _client_cache.clear()
