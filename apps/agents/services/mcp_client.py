"""
HTTP/SSE клиент для работы с MCP серверами.
"""

import asyncio
import base64
import httpx
import json
import logging
import uuid
from typing import Dict, Any, List, Optional, Tuple

from apps.agents.models.mcp_models import MCPTransportType
from core.config import get_settings
from apps.agents.container import get_agents_container
from core.context import get_context

logger = logging.getLogger(__name__)


class MCPHttpClient:
    """HTTP/SSE клиент для MCP серверов по протоколу JSON-RPC 2.0"""

    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        transport_type: MCPTransportType = MCPTransportType.HTTP,
        use_proxy: bool = True
    ):
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout
        self.transport_type = transport_type
        self.use_proxy = use_proxy
        self._client: Optional[httpx.AsyncClient] = None
        self._session_id: Optional[str] = None
        self._request_id = 0

    async def _get_client(self) -> httpx.AsyncClient:
        """Получить или создать HTTP клиент с инициализацией сессии"""
        if self._client is None:
            base_headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            base_headers.update(self.headers)

            proxy_url = None

            if self.use_proxy:
                settings = get_settings()
                proxy_url = settings.proxy.get_proxy_url("https")

                if proxy_url:
                    logger.info(f"🌐 Используем прокси для MCP клиента: {proxy_url}")
            else:
                logger.info(f"🚫 Прокси отключен для MCP сервера: {self.url}")

            self._client = httpx.AsyncClient(
                headers=base_headers,
                timeout=self.timeout,
                proxy=proxy_url,
                follow_redirects=True
            )

            # Инициализация сессии опциональна - не падаем, если не получилось
            # Для SSE транспорта инициализация происходит при первом запросе через /message
            if self.transport_type == MCPTransportType.HTTP:
                await self._initialize_session()
            elif self.transport_type == MCPTransportType.SSE:
                # Для SSE просто создаем session_id, инициализация будет при первом запросе
                self._session_id = str(uuid.uuid4())
                logger.debug(f"📝 Session ID для SSE: {self._session_id}")

        return self._client

    def _next_request_id(self) -> int:
        """Получить следующий ID запроса"""
        self._request_id += 1
        return self._request_id

    async def _initialize_session(self):
        """Инициализирует MCP сессию через JSON-RPC"""
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
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            data = self._parse_sse_text(response.text)
        else:
            data = response.json()

        # Проверяем наличие ошибки в JSON-RPC
        if "error" in data:
            raise ValueError(f"MCP ошибка: {data['error']['message']}")

        # Извлекаем результат
        result = data.get("result", {})
        tools = result.get("tools", [])

        logger.info(f"Получено {len(tools)} тулов от {self.url} (HTTP)")
        return tools

    def _parse_sse_text(self, text: str) -> Dict[str, Any]:
        """Парсит SSE ответ из строки в JSON-RPC формат"""
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                try:
                    return json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
        return {}

    async def _sse_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Выполняет JSON-RPC запрос через SSE транспорт"""
        client = await self._get_client()
        base_url = self.url.rstrip("/")
        if base_url.endswith("/sse"):
            base_url = base_url[:-4]
        sse_url = f"{base_url}/sse"
        message_url = f"{base_url}/message?sessionId={self._session_id}"

        request_data = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": method
        }
        if params:
            request_data["params"] = params

        async with client.stream(
            "GET",
            sse_url,
            headers={"Accept": "text/event-stream", "Mcp-Session-Id": self._session_id}
        ) as sse_response:
            sse_response.raise_for_status()
            iterator = sse_response.aiter_lines()

            # Читаем endpoint из потока (если есть)
            try:
                async for line in iterator:
                    if line.startswith("data: ") and "/message" in line:
                        message_url = f"{base_url}{line[6:].strip()}"
                        break
            except StopAsyncIteration:
                pass

            # Отправляем запрос
            await client.post(
                message_url,
                json=request_data,
                headers={"Content-Type": "application/json", "Mcp-Session-Id": self._session_id},
                timeout=self.timeout
            )

            # Читаем ответ из того же потока
            async for line in iterator:
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if data.get("id") == request_data["id"]:
                            if "error" in data:
                                error_msg = data["error"].get("message", str(data["error"]))
                                return {
                                    "isError": True,
                                    "content": [{"type": "text", "text": error_msg}]
                                }
                            return data.get("result", {})
                    except json.JSONDecodeError:
                        continue

        raise ValueError("Не получен ответ от MCP сервера")

    async def _list_tools_sse(self) -> List[Dict[str, Any]]:
        """JSON-RPC запрос tools/list для SSE транспорта"""
        result = await self._sse_request("tools/list")
        if result.get("isError"):
            error_msg = result.get("content", [{}])[0].get("text", "Неизвестная ошибка")
            raise ValueError(f"MCP ошибка: {error_msg}")
        return result.get("tools", [])

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

        if response.headers.get("content-type", "").startswith("text/event-stream"):
            data = self._parse_sse_text(response.text)
        else:
            data = response.json()

        # Проверяем JSON-RPC ошибку
        if "error" in data:
            error_msg = data["error"].get("message", str(data["error"]))
            logger.warning(f"MCP JSON-RPC ошибка: {error_msg}")
            return {
                "isError": True,
                "content": [{"type": "text", "text": error_msg}]
            }

        # Извлекаем результат
        result = data.get("result", {})

        # MCP возвращает content напрямую
        return {
            "isError": result.get("isError", False),
            "content": result.get("content", [])
        }

    async def _call_tool_sse(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-RPC запрос tools/call для SSE транспорта"""
        result = await self._sse_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        return {
            "isError": result.get("isError", False),
            "content": result.get("content", [])
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
    if company_id is None:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Не удалось определить company_id из контекста")
        company_id = context.active_company.company_id

    # Ключ для кэша
    cache_key = f"{company_id}:{server_id}"

    if cache_key in _mcp_clients:
        return _mcp_clients[cache_key]

    mcp_repo = get_agents_container().mcp_server_repository

    server_config = await mcp_repo.get(server_id)
    if not server_config:
        raise ValueError(f"MCP сервер {server_id} не найден для компании {company_id}")

    if not server_config.is_active:
        raise ValueError(f"MCP сервер {server_id} неактивен")

    variables_service = get_agents_container().variables_service
    resolved_headers = await variables_service.resolve(server_config.headers)

    # Отключаем прокси для localhost автоматически
    is_localhost = "localhost" in server_config.url or "127.0.0.1" in server_config.url
    use_proxy = server_config.use_proxy and not is_localhost
    if is_localhost and server_config.use_proxy:
        logger.info(f"🚫 Прокси отключен для localhost сервера: {server_config.url}")

    client = MCPHttpClient(
        url=server_config.url,
        headers=resolved_headers,
        timeout=server_config.timeout,
        transport_type=server_config.transport_type,
        use_proxy=use_proxy
    )

    _mcp_clients[cache_key] = client
    logger.info(f"✅ Создан MCP клиент для {company_id}:{server_id} ({server_config.transport_type})")

    return client


async def process_mcp_images(
    content: List[Dict[str, Any]],
    save_to_s3: bool = False
) -> Tuple[str, List[str]]:
    """
    Обрабатывает изображения из MCP результата, опционально сохраняет их и возвращает текстовое описание.

    Args:
        content: Массив content items от MCP сервера
        save_to_s3: Сохранять ли изображения на S3 (по умолчанию True).
                   Если False, изображения обрабатываются, но не сохраняются.

    Returns:
        Tuple[текстовое описание, список file_id сохраненных изображений (пустой если save_to_s3=False)]
    """
    if not content:
        return "Выполнено успешно", []

    text_parts = []
    image_file_ids = []

    for item in content:
        item_type = item.get("type")

        if item_type == "text":
            text_parts.append(item.get("text", ""))
        elif item_type == "image":
            try:
                # Извлекаем данные изображения
                data = item.get("data", "")
                mime_type = item.get("mimeType", "image/png")

                # Парсим data URL или base64
                if data.startswith("data:"):
                    # Формат: data:image/png;base64,iVBORw0KGgo...
                    base64_data = data.split(",", 1)[1] if "," in data else data
                else:
                    base64_data = data

                if not base64_data:
                    text_parts.append(f"📎 Изображение получено, но данные пусты ({mime_type})")
                    continue

                # Декодируем base64
                try:
                    image_bytes = base64.b64decode(base64_data)
                except Exception as e:
                    logger.warning(f"Не удалось декодировать base64 изображение: {e}")
                    text_parts.append(f"📎 Изображение получено, но не удалось декодировать ({mime_type})")
                    continue

                if save_to_s3:
                    # Сохраняем через FileProcessor
                    from app.core.file_processor import FileProcessor
                    file_processor = FileProcessor()

                    # Определяем расширение
                    ext = "png"
                    if "jpeg" in mime_type or "jpg" in mime_type:
                        ext = "jpg"
                    elif "webp" in mime_type:
                        ext = "webp"

                    record = await file_processor.process_file_from_bytes(
                        data=image_bytes,
                        original_name=f"figma_export_{uuid.uuid4().hex[:8]}.{ext}",
                        content_type=mime_type,
                        uploaded_by="figma_mcp",
                        public=True  # Делаем публичным для доступа LLM
                    )

                    image_file_ids.append(record.file_id)
                    text_parts.append(
                        f"📎 Изображение сохранено: {record.file_id}\n"
                        f"   URL: {record.url}\n"
                        f"   Размер: {len(image_bytes)} байт\n"
                        f"   Тип: {mime_type}"
                    )
                    logger.info(f"✅ Изображение из MCP сохранено: {record.file_id}")
                else:
                    # Не сохраняем, только сообщаем о получении
                    text_parts.append(
                        f"📎 Изображение получено (не сохранено)\n"
                        f"   Размер: {len(image_bytes)} байт\n"
                        f"   Тип: {mime_type}"
                    )
                    logger.debug("📎 Изображение из MCP получено, но не сохранено (save_to_s3=False)")

            except Exception as e:
                logger.error(f"Ошибка обработки изображения из MCP: {e}", exc_info=True)
                text_parts.append(f"📎 Изображение получено, но не удалось обработать: {str(e)}")
        elif item_type == "resource":
            uri = item.get("uri", "unknown")
            text_parts.append(f"📎 Ресурс: {uri}")
        else:
            text_parts.append(f"[{item_type}]")

    return "\n".join(text_parts), image_file_ids


def format_mcp_result(content: List[Dict[str, Any]]) -> str:
    """
    Форматирует результат MCP тула в строку (синхронная версия без обработки изображений).

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
            parts.append(f"📎 Изображение получено: {mime_type} (будет обработано)")
        elif item_type == "resource":
            uri = item.get("uri", "unknown")
            parts.append(f"📎 Ресурс: {uri}")
        else:
            parts.append(f"[{item_type}]")

    return "\n".join(parts)

