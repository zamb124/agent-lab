"""
HTTP/SSE клиент для работы с MCP серверами.
"""

import httpx
import json
import logging
from typing import Dict, Any, List, Optional

from app.models.mcp_models import MCPTransportType

logger = logging.getLogger(__name__)


class MCPHttpClient:
    """HTTP/SSE клиент для MCP серверов по протоколу JSON-RPC 2.0"""
    
    def __init__(
        self, 
        url: str, 
        headers: Optional[Dict[str, str]] = None, 
        timeout: int = 30,
        transport_type: MCPTransportType = MCPTransportType.HTTP
    ):
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout
        self.transport_type = transport_type
        self._client: Optional[httpx.AsyncClient] = None
        self._session_id: Optional[str] = None
        self._request_id = 0
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Получить или создать HTTP клиент с инициализацией сессии"""
        if self._client is None:
            # Базовые заголовки для MCP
            base_headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            base_headers.update(self.headers)
            
            self._client = httpx.AsyncClient(
                headers=base_headers,
                timeout=self.timeout
            )
            
            # Инициализируем MCP сессию
            await self._initialize_session()
        
        return self._client
    
    def _next_request_id(self) -> int:
        """Получить следующий ID запроса"""
        self._request_id += 1
        return self._request_id
    
    async def _initialize_session(self):
        """Инициализирует MCP сессию через JSON-RPC"""
        import uuid
        
        self._session_id = str(uuid.uuid4())
        
        request_data = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "agent-lab",
                    "version": "1.0.0"
                }
            }
        }
        
        try:
            response = await self._client.post(
                self.url,
                json=request_data,
                headers={"Mcp-Session-Id": self._session_id}
            )
            
            response.raise_for_status()
            
            # Проверяем session ID в response headers (GitHub Copilot возвращает его)
            session_from_response = response.headers.get("mcp-session-id") or response.headers.get("Mcp-Session-Id")
            if session_from_response:
                self._session_id = session_from_response
                logger.info(f"✅ MCP сессия получена от сервера: {self._session_id}")
            
            # Для SSE читаем event stream
            if self.transport_type == MCPTransportType.SSE:
                lines = response.text.split("\n")
                for line in lines:
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if "result" in data:
                            logger.info(f"✅ MCP сессия инициализирована (SSE): {self._session_id}")
                            return
            else:
                data = response.json()
                if "result" in data:
                    logger.info(f"✅ MCP сессия инициализирована (HTTP): {self._session_id}")
                elif "error" in data:
                    logger.warning(f"⚠️ Ошибка инициализации MCP: {data['error']}")
        
        except Exception as e:
            logger.warning(f"⚠️ Не удалось инициализировать MCP сессию: {e}")
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        Получить список доступных тулов от MCP сервера.
        
        HTTP: POST /list_tools
        SSE: GET /list_tools (читаем SSE stream)
        
        Returns:
            Список тулов с описаниями и схемами
        """
        try:
            if self.transport_type == MCPTransportType.HTTP:
                return await self._list_tools_http()
            elif self.transport_type == MCPTransportType.SSE:
                return await self._list_tools_sse()
            else:
                raise ValueError(f"Неподдерживаемый тип транспорта: {self.transport_type}")
        except Exception as e:
            logger.error(f"Ошибка получения списка тулов от {self.url}: {e}", exc_info=True)
            raise
    
    async def _list_tools_http(self) -> List[Dict[str, Any]]:
        """JSON-RPC запрос tools/list для HTTP транспорта"""
        client = await self._get_client()
        
        request_data = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": "tools/list"
        }
        
        response = await client.post(
            self.url,
            json=request_data,
            headers={"Mcp-Session-Id": self._session_id}
        )
        response.raise_for_status()
        
        # Некоторые MCP серверы возвращают SSE даже для HTTP
        response_text = response.text
        
        # Проверяем формат ответа
        if response_text.startswith("event:"):
            # SSE формат - парсим
            data = self._parse_sse_response(response_text)
        else:
            # Обычный JSON
            data = response.json()
        
        # Проверяем наличие ошибки в JSON-RPC
        if "error" in data:
            raise ValueError(f"MCP ошибка: {data['error']['message']}")
        
        # Извлекаем результат
        result = data.get("result", {})
        tools = result.get("tools", [])
        
        logger.info(f"Получено {len(tools)} тулов от {self.url} (HTTP)")
        return tools
    
    def _parse_sse_response(self, text: str) -> Dict[str, Any]:
        """Парсит SSE ответ и извлекает JSON-RPC данные"""
        lines = text.split("\n")
        for line in lines:
            if line.startswith("data: "):
                try:
                    return json.loads(line[6:])
                except json.JSONDecodeError as e:
                    logger.warning(f"Ошибка парсинга SSE data: {e}")
                    continue
        return {}
    
    async def _list_tools_sse(self) -> List[Dict[str, Any]]:
        """JSON-RPC запрос tools/list для SSE транспорта"""
        client = await self._get_client()
        
        request_data = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": "tools/list"
        }
        
        async with client.stream(
            "POST",
            self.url,
            json=request_data,
            headers={"Mcp-Session-Id": self._session_id}
        ) as response:
            response.raise_for_status()
            
            tools = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        
                        # Проверяем ошибку
                        if "error" in data:
                            raise ValueError(f"MCP ошибка: {data['error']['message']}")
                        
                        # Извлекаем результат
                        if "result" in data:
                            result = data["result"]
                            tools = result.get("tools", [])
                            break
                    except json.JSONDecodeError as e:
                        logger.warning(f"Ошибка парсинга SSE: {e}")
                        continue
            
            logger.info(f"Получено {len(tools)} тулов от {self.url} (SSE)")
            return tools
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Вызвать MCP тул.
        
        HTTP: POST /call_tool (обычный JSON ответ)
        SSE: POST /call_tool (streaming ответ)
        
        Args:
            tool_name: Имя тула
            arguments: Аргументы для тула
            
        Returns:
            Результат выполнения тула
        """
        try:
            if self.transport_type == MCPTransportType.HTTP:
                return await self._call_tool_http(tool_name, arguments)
            elif self.transport_type == MCPTransportType.SSE:
                return await self._call_tool_sse(tool_name, arguments)
            else:
                raise ValueError(f"Неподдерживаемый тип транспорта: {self.transport_type}")
        except Exception as e:
            logger.error(f"Ошибка вызова MCP тула {tool_name}: {e}", exc_info=True)
            raise
    
    async def _call_tool_http(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-RPC запрос tools/call для HTTP транспорта"""
        client = await self._get_client()
        
        logger.info(f"🔧 MCP вызов (HTTP): {tool_name}")
        
        request_data = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        response = await client.post(
            self.url,
            json=request_data,
            headers={"Mcp-Session-Id": self._session_id}
        )
        response.raise_for_status()
        
        # Парсим ответ (может быть SSE или JSON)
        response_text = response.text
        
        if response_text.startswith("event:"):
            data = self._parse_sse_response(response_text)
        else:
            data = response.json()
        
        # Проверяем JSON-RPC ошибку
        if "error" in data:
            logger.warning(f"MCP JSON-RPC ошибка: {data['error']}")
            return {
                "isError": True,
                "content": [{"type": "text", "text": data['error']['message']}]
            }
        
        # Извлекаем результат
        result = data.get("result", {})
        
        # MCP возвращает content напрямую
        return {
            "isError": result.get("isError", False),
            "content": result.get("content", [])
        }
    
    async def _call_tool_sse(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-RPC запрос tools/call для SSE транспорта (streaming)"""
        client = await self._get_client()
        
        logger.info(f"🔧 MCP вызов (SSE): {tool_name}")
        
        request_data = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        async with client.stream(
            "POST",
            self.url,
            json=request_data,
            headers={"Mcp-Session-Id": self._session_id}
        ) as response:
            response.raise_for_status()
            
            result_data = None
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        
                        # Проверяем ошибку
                        if "error" in data:
                            logger.warning(f"MCP JSON-RPC ошибка: {data['error']}")
                            return {
                                "isError": True,
                                "content": [{"type": "text", "text": data['error']['message']}]
                            }
                        
                        # Собираем результат
                        if "result" in data:
                            result_data = data["result"]
                    except json.JSONDecodeError as e:
                        logger.warning(f"Ошибка парсинга SSE: {e}")
                        continue
            
            if result_data is None:
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "No response from MCP server"}]
                }
            
            return {
                "isError": result_data.get("isError", False),
                "content": result_data.get("content", [])
            }
    
    async def close(self):
        """Закрыть HTTP клиент"""
        if self._client:
            await self._client.aclose()
            self._client = None


# Глобальный кэш клиентов по {company_id}:{server_id}
_mcp_clients: Dict[str, MCPHttpClient] = {}


async def get_mcp_client(server_id: str, company_id: Optional[str] = None) -> MCPHttpClient:
    """
    Получить HTTP клиент для MCP сервера компании.
    Кэширует клиенты по ключу {company_id}:{server_id}
    
    Args:
        server_id: ID MCP сервера
        company_id: ID компании (опционально, берется из контекста)
        
    Returns:
        MCPHttpClient для работы с сервером
    """
    from app.db.repositories.mcp_repository import MCPServerRepository
    from app.core.container import get_container
    from app.core.context import get_context
    
    # Определяем company_id
    if company_id is None:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Не удалось определить company_id из контекста")
        company_id = context.active_company.company_id
    
    # Ключ для кэша
    cache_key = f"{company_id}:{server_id}"
    
    if cache_key in _mcp_clients:
        return _mcp_clients[cache_key]
    
    # Загружаем конфиг сервера
    storage = get_container().get_storage()
    mcp_repo = MCPServerRepository(storage)
    
    server_config = await mcp_repo.get(server_id, company_id)
    if not server_config:
        raise ValueError(f"MCP сервер {server_id} не найден для компании {company_id}")
    
    if not server_config.is_active:
        raise ValueError(f"MCP сервер {server_id} неактивен")
    
    # Резолвим переменные в headers (переменные берутся из scope компании)
    from app.services.variables_service import get_variables_service
    variables_service = get_variables_service()
    resolved_headers = await variables_service.resolve(server_config.headers)
    
    # Создаем и кэшируем клиент
    client = MCPHttpClient(
        url=server_config.url,
        headers=resolved_headers,
        timeout=server_config.timeout,
        transport_type=server_config.transport_type
    )
    
    _mcp_clients[cache_key] = client
    logger.info(f"✅ Создан MCP клиент для {company_id}:{server_id} ({server_config.transport_type})")
    
    return client


def format_mcp_result(content: List[Dict[str, Any]]) -> str:
    """
    Форматирует результат MCP тула в строку.
    
    Args:
        content: Массив content items от MCP сервера
        
    Returns:
        Отформатированная строка
    """
    if not content:
        return "Выполнено успешно"
    
    parts = []
    for item in content:
        item_type = item.get("type")
        
        if item_type == "text":
            parts.append(item.get("text", ""))
        elif item_type == "image":
            mime_type = item.get("mimeType", "unknown")
            parts.append(f"📎 Изображение: {mime_type}")
        elif item_type == "resource":
            uri = item.get("uri", "unknown")
            parts.append(f"📎 Ресурс: {uri}")
        else:
            parts.append(f"[{item_type}]")
    
    return "\n".join(parts)

