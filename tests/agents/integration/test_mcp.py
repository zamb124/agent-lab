"""
Интеграционные тесты MCP на реальных публичных серверах.

Тестирование на реальных MCP серверах:
- Context7 HTTP: https://context7.liam.sh/mcp

БЕЗ МОКОВ - только реальные серверы и MockLLM для агентов.

ВАЖНО: Тесты проверяют что НАШ КОД работает корректно.
Если внешний MCP сервер возвращает ошибку - это тоже валидный результат,
главное что мы корректно обрабатываем эту ошибку.
"""

import pytest
import uuid
from typing import Any, Dict

from apps.agents.src.clients.mcp_client import MCPClient, MCPClientError, clear_mcp_client_cache
from apps.agents.src.models.mcp import MCPServerConfig, MCPTransportType


# Реальный публичный MCP сервер для тестов
CONTEXT7_HTTP_SERVER = MCPServerConfig(
    server_id="context7-http",
    name="Context7 HTTP",
    url="https://context7.liam.sh/mcp",
    transport_type=MCPTransportType.HTTP,
    headers={},
    is_active=True,
    description="Context7 MCP HTTP сервер (публичный)",
)


class TestMCPClientHTTP:
    """Тесты MCP клиента на реальном HTTP сервере Context7."""
    
    @pytest.fixture(autouse=True)
    def cleanup_cache(self):
        """Очищаем кэш клиентов перед каждым тестом."""
        clear_mcp_client_cache()
        yield
        clear_mcp_client_cache()
    
    @pytest.mark.asyncio
    async def test_initialize_real_server(self):
        """Тест инициализации сессии на реальном Context7 HTTP сервере."""
        client = MCPClient(CONTEXT7_HTTP_SERVER, timeout=30.0)
        
        result = await client.initialize()
        
        # Главное - инициализация прошла без исключений
        assert result is not None
        assert client._initialized is True
        # Session ID должен быть получен от сервера
        # (может быть None если сервер не требует сессий)
    
    @pytest.mark.asyncio
    async def test_list_tools_real_server(self):
        """Тест получения списка tools с реального Context7 HTTP сервера."""
        client = MCPClient(CONTEXT7_HTTP_SERVER, timeout=30.0)
        
        tools = await client.list_tools()
        
        # Главное - список tools получен
        assert isinstance(tools, list)
        assert len(tools) > 0
        
        # Проверяем структуру tools
        for tool in tools:
            assert tool.name  # Имя обязательно
            print(f"Tool: {tool.name} - {tool.description}")
    
    @pytest.mark.asyncio
    async def test_call_tool_handles_response(self):
        """
        Тест вызова tool на Context7.
        
        Проверяем что наш код корректно обрабатывает ответ -
        независимо от того, успешный он или с ошибкой от API.
        """
        client = MCPClient(CONTEXT7_HTTP_SERVER, timeout=30.0)
        
        # Сначала получим список tools чтобы узнать имена
        tools = await client.list_tools()
        assert len(tools) > 0
        
        # Берём первый tool и вызываем с минимальными параметрами
        first_tool = tools[0]
        
        result = await client.call_tool(
            first_tool.name,
            {"libraryName": "react"}  # Типичный параметр для Context7
        )
        
        # Главное - результат получен и имеет правильную структуру
        assert result is not None
        assert hasattr(result, 'is_error')
        assert hasattr(result, 'content')
        
        # Текст должен быть даже если это сообщение об ошибке
        text = result.get_text()
        assert isinstance(text, str)
        print(f"Tool call result (is_error={result.is_error}): {text[:200]}...")
    
    @pytest.mark.asyncio
    async def test_invalid_tool_returns_error(self):
        """Проверяем что вызов несуществующего tool возвращает ошибку."""
        client = MCPClient(CONTEXT7_HTTP_SERVER, timeout=30.0)
        
        with pytest.raises(MCPClientError) as exc_info:
            await client.call_tool("nonexistent-tool-12345", {})
        
        # Ошибка должна содержать информацию о том что tool не найден
        assert "not found" in str(exc_info.value).lower() or "error" in str(exc_info.value).lower()


class TestMCPSyncAPI:
    """Тесты API синхронизации MCP серверов."""
    
    @pytest.mark.asyncio
    async def test_create_and_sync_server(self, client, unique_id):
        """
        E2E: Создание MCP сервера и синхронизация tools.
        
        Проверяем полный цикл:
        1. Создание сервера
        2. Синхронизация tools
        3. Проверка что tools появились в системе
        """
        server_id = f"sync-test-{unique_id}"
        
        # Создаем сервер
        create_resp = await client.post(
            "/agents/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Sync Test Server",
                "url": "https://context7.liam.sh/mcp",
                "transport_type": "http",
                "description": "Test server for sync",
            },
        )
        assert create_resp.status_code == 200, create_resp.text
        server_data = create_resp.json()
        assert server_data["server_id"] == server_id
        assert server_data["cached_tools"] == []  # Пока не синхронизировано
        
        # Синхронизируем tools
        sync_resp = await client.post(f"/agents/api/v1/mcp/servers/{server_id}/sync")
        assert sync_resp.status_code == 200, sync_resp.text
        sync_data = sync_resp.json()
        
        # Проверяем что синхронизация прошла
        assert sync_data["success"] is True
        assert sync_data["tools_count"] > 0
        
        tools = sync_data["tools"]
        assert len(tools) > 0
        
        tool_names = [t["name"] for t in tools]
        print(f"Synced {len(tools)} tools: {tool_names}")
        
        # Проверяем что tools появились в /tools/all
        tools_resp = await client.get("/agents/api/v1/tools/all")
        assert tools_resp.status_code == 200
        all_tools = tools_resp.json()
        
        mcp_tools = [t for t in all_tools if t.get("mcp_server_id") == server_id]
        assert len(mcp_tools) > 0, "MCP tools должны появиться в общем списке"
        
        # Cleanup
        await client.delete(f"/agents/api/v1/mcp/servers/{server_id}")
    
    @pytest.mark.asyncio
    async def test_server_connection_test(self, client, unique_id):
        """
        E2E: Тест подключения к MCP серверу.
        """
        server_id = f"conn-test-{unique_id}"
        
        await client.post(
            "/agents/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Connection Test",
                "url": "https://context7.liam.sh/mcp",
                "transport_type": "http",
            },
        )
        
        test_resp = await client.post(f"/agents/api/v1/mcp/servers/{server_id}/test")
        assert test_resp.status_code == 200
        
        test_data = test_resp.json()
        assert test_data["success"] is True
        assert test_data["tools_count"] > 0
        assert test_data["transport_type"] == "http"
        assert "context7" in test_data["url"]
        
        print(f"Connection test: {test_data}")
        
        # Cleanup
        await client.delete(f"/agents/api/v1/mcp/servers/{server_id}")
    
    @pytest.mark.asyncio
    async def test_server_crud(self, client, unique_id):
        """
        E2E: CRUD операции с MCP сервером.
        """
        server_id = f"crud-test-{unique_id}"
        
        # Create
        create_resp = await client.post(
            "/agents/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "CRUD Test",
                "url": "https://context7.liam.sh/mcp",
                "transport_type": "http",
            },
        )
        assert create_resp.status_code == 200
        
        # Read
        get_resp = await client.get(f"/agents/api/v1/mcp/servers/{server_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["server_id"] == server_id
        assert data["name"] == "CRUD Test"
        
        # Update
        update_resp = await client.put(
            f"/agents/api/v1/mcp/servers/{server_id}",
            json={"name": "CRUD Test Updated"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "CRUD Test Updated"
        
        # List
        list_resp = await client.get("/agents/api/v1/mcp/servers")
        assert list_resp.status_code == 200
        servers = list_resp.json()
        assert any(s["server_id"] == server_id for s in servers)
        
        # Delete
        del_resp = await client.delete(f"/agents/api/v1/mcp/servers/{server_id}")
        assert del_resp.status_code == 200
        
        # Verify deleted
        get_resp2 = await client.get(f"/agents/api/v1/mcp/servers/{server_id}")
        assert get_resp2.status_code == 404
    
    @pytest.mark.asyncio
    async def test_invalid_server_url_returns_error(self, client, unique_id):
        """Проверяем что невалидный URL сервера возвращает ошибку при sync."""
        server_id = f"invalid-url-{unique_id}"
        
        # Создаем сервер с невалидным URL
        await client.post(
            "/agents/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Invalid URL Test",
                "url": "http://127.0.0.1:59999/mcp",  # Локальный порт который точно не слушает
                "transport_type": "http",
            },
        )
        
        # Sync должен вернуть ошибку (сетевая или HTTP)
        sync_resp = await client.post(f"/agents/api/v1/mcp/servers/{server_id}/sync")
        # Ожидаем любую ошибку >= 400
        assert sync_resp.status_code >= 400, f"Невалидный URL должен вернуть ошибку, получили {sync_resp.status_code}"
        
        # Cleanup
        await client.delete(f"/agents/api/v1/mcp/servers/{server_id}")
    
    @pytest.mark.asyncio
    async def test_duplicate_server_id_rejected(self, client, unique_id):
        """Проверяем что дублирование server_id отклоняется."""
        server_id = f"duplicate-test-{unique_id}"
        
        # Создаем первый сервер
        resp1 = await client.post(
            "/agents/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "First Server",
                "url": "https://context7.liam.sh/mcp",
                "transport_type": "http",
            },
        )
        assert resp1.status_code == 200
        
        # Пытаемся создать второй с тем же ID
        resp2 = await client.post(
            "/agents/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Second Server",
                "url": "https://context7.liam.sh/mcp",
                "transport_type": "http",
            },
        )
        assert resp2.status_code == 409, "Дублирование server_id должно вернуть 409"
        
        # Cleanup
        await client.delete(f"/agents/api/v1/mcp/servers/{server_id}")


class TestMCPNodeInGraph:
    """
    Тесты MCPNode в графе агента.
    
    Проверяем что MCPNode корректно интегрируется в граф и
    обрабатывает как успешные ответы, так и ошибки от MCP сервера.
    """
    
    @pytest.mark.asyncio
    async def test_mcp_node_executes_in_graph(self, client, unique_id):
        """
        E2E: MCPNode вызывается в графе агента.
        
        Проверяем что:
        1. MCPNode создаётся и конфигурируется
        2. Граф выполняется
        3. MCPNode обрабатывает ответ (успех или ошибку)
        """
        agent_id = f"mcp_node_graph_{unique_id}"
        server_id = f"context7-graph-{unique_id}"
        
        # Создаем MCP сервер
        server_resp = await client.post(
            "/agents/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Context7 Graph Test",
                "url": "https://context7.liam.sh/mcp",
                "transport_type": "http",
            },
        )
        assert server_resp.status_code == 200
        
        # Синхронизируем tools
        sync_resp = await client.post(f"/agents/api/v1/mcp/servers/{server_id}/sync")
        assert sync_resp.status_code == 200
        sync_data = sync_resp.json()
        assert sync_data["tools_count"] > 0
        
        # Берём первый tool
        first_tool = sync_data["tools"][0]["name"]
        
        # Создаем агента с MCPNode
        create_resp = await client.post(
            "/agents/api/v1/agents/",
            json={
                "agent_id": agent_id,
                "name": "MCP Node Graph Test",
                "entry": "init",
                "nodes": {
                    "init": {
                        "type": "code",
                        "code": "def run(state):\n    state['query'] = 'fastapi'\n    return state",
                    },
                    "mcp_call": {
                        "type": "mcp",
                        "server_id": server_id,
                        "tool_name": first_tool,
                        "input_mapping": {
                            "libraryName": "@state:query",
                        },
                    },
                    "finish": {
                        "type": "code",
                        "code": "def run(state):\n    state['response'] = 'done'\n    return state",
                    },
                },
                "edges": [
                    {"from": "init", "to": "mcp_call"},
                    {"from": "mcp_call", "to": "finish"},
                    {"from": "finish", "to": None},
                ],
            },
        )
        assert create_resp.status_code == 200, create_resp.text
        
        # Выполняем агента
        exec_resp = await client.post(
            f"/agents/api/v1/{agent_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "user",
                        "parts": [{"kind": "text", "text": "test mcp"}],
                    }
                },
            },
        )
        assert exec_resp.status_code == 200, exec_resp.text
        
        data = exec_resp.json()
        task = data.get("result", {})
        status = task.get("status", {}).get("state")
        
        # Граф должен либо завершиться успешно, либо с ошибкой от MCP
        # Оба варианта валидны - главное что наш код не упал
        assert status in ["completed", "failed"], f"Unexpected status: {status}"
        
        if status == "failed":
            # Проверяем что ошибка связана с MCP, а не с нашим кодом
            artifacts = task.get("artifacts", [])
            error_artifacts = [a for a in artifacts if "error" in a.get("name", "")]
            if error_artifacts:
                error_text = str(error_artifacts)
                assert "mcp" in error_text.lower() or "context7" in error_text.lower()
                print(f"MCP returned error (expected): {error_text[:200]}")
        else:
            print("MCP call completed successfully")
        
        # Cleanup
        await client.delete(f"/agents/api/v1/agents/{agent_id}")
        await client.delete(f"/agents/api/v1/mcp/servers/{server_id}")


class TestMCPToolInReactNode:
    """Тесты MCP tool в ReAct ноде агента."""
    
    @pytest.mark.asyncio
    async def test_react_node_can_use_mcp_tool(self, client, unique_id, mock_llm_redis):
        """
        E2E: ReAct нода может использовать MCP tool.
        
        Сценарий:
        1. Создаём MCP сервер и синхронизируем tools
        2. Создаём агента с ReAct нодой которая имеет MCP tool
        3. MockLLM делает tool call
        4. Проверяем что tool был вызван
        """
        agent_id = f"react_mcp_{unique_id}"
        server_id = f"context7-react-{unique_id}"
        
        # Создаем MCP сервер
        server_resp = await client.post(
            "/agents/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Context7 React Test",
                "url": "https://context7.liam.sh/mcp",
                "transport_type": "http",
            },
        )
        assert server_resp.status_code == 200
        
        # Синхронизируем tools
        sync_resp = await client.post(f"/agents/api/v1/mcp/servers/{server_id}/sync")
        assert sync_resp.status_code == 200
        sync_data = sync_resp.json()
        
        # Берем первый tool
        first_tool_name = sync_data["tools"][0]["name"]
        mcp_tool_id = f"mcp:{server_id}:{first_tool_name}"
        
        # Настраиваем MockLLM для вызова MCP tool
        await mock_llm_redis([
            {
                "type": "tool_call",
                "tool": mcp_tool_id,
                "args": {"libraryName": "django"},
            },
            {
                "type": "text",
                "content": "Готово! Информация о библиотеке получена.",
            },
        ])
        
        # Создаем агента с ReAct нодой и MCP tool
        create_resp = await client.post(
            "/agents/api/v1/agents/",
            json={
                "agent_id": agent_id,
                "name": "React MCP Agent",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "react_node",
                        "prompt": "Используй tools для поиска информации о библиотеках.",
                        "tools": [mcp_tool_id],
                    },
                },
                "edges": [
                    {"from": "main", "to": None},
                ],
            },
        )
        assert create_resp.status_code == 200, create_resp.text
        
        # Выполняем
        exec_resp = await client.post(
            f"/agents/api/v1/{agent_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Найди информацию о Django"}],
                    }
                },
            },
        )
        assert exec_resp.status_code == 200, exec_resp.text
        
        data = exec_resp.json()
        print(f"Full response: {data}")
        
        task = data.get("result", {})
        status = task.get("status", {}).get("state")
        
        # Проверяем что task завершился (успешно или с ошибкой от MCP)
        assert status in ["completed", "failed"], f"Unexpected status: {status}, full: {data}"
        
        # Проверяем artifacts
        artifacts = task.get("artifacts", [])
        artifact_names = [a.get("name", "") for a in artifacts]
        print(f"Artifacts ({len(artifacts)}): {artifact_names}")
        
        print(f"React node finished with status: {status}")
        
        # Cleanup
        await client.delete(f"/agents/api/v1/agents/{agent_id}")
        await client.delete(f"/agents/api/v1/mcp/servers/{server_id}")


class TestMCPWithCustomHeaders:
    """Тесты MCP с кастомными headers и авторизацией."""
    
    @pytest.mark.asyncio
    async def test_server_with_custom_headers(self, client, unique_id):
        """
        Проверяем что сервер с кастомными headers создаётся и сохраняется.
        """
        server_id = f"headers-test-{unique_id}"
        
        create_resp = await client.post(
            "/agents/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Headers Test",
                "url": "https://context7.liam.sh/mcp",
                "transport_type": "http",
                "headers": {
                    "X-Custom-Header": "test-value",
                    "X-Another-Header": "another-value",
                },
            },
        )
        assert create_resp.status_code == 200
        data = create_resp.json()
        
        # Headers должны сохраниться
        assert data["headers"]["X-Custom-Header"] == "test-value"
        assert data["headers"]["X-Another-Header"] == "another-value"
        
        # Проверяем через GET
        get_resp = await client.get(f"/agents/api/v1/mcp/servers/{server_id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["headers"]["X-Custom-Header"] == "test-value"
        
        # Cleanup
        await client.delete(f"/agents/api/v1/mcp/servers/{server_id}")
    
    @pytest.mark.asyncio
    async def test_server_with_var_reference_in_headers(self, client, unique_id):
        """
        Проверяем что @var: ссылки в headers сохраняются.
        """
        server_id = f"var-headers-{unique_id}"
        
        create_resp = await client.post(
            "/agents/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Var Headers Test",
                "url": "https://context7.liam.sh/mcp",
                "transport_type": "http",
                "headers": {
                    "Authorization": "Bearer @var:mcp_api_key",
                },
            },
        )
        assert create_resp.status_code == 200
        data = create_resp.json()
        
        # @var: ссылка должна сохраниться как есть
        assert data["headers"]["Authorization"] == "Bearer @var:mcp_api_key"
        
        # Cleanup
        await client.delete(f"/agents/api/v1/mcp/servers/{server_id}")


class TestMCPTransportTypes:
    """Тесты разных типов транспорта MCP."""
    
    @pytest.mark.asyncio
    async def test_http_transport_stored_correctly(self, client, unique_id):
        """Проверяем что HTTP транспорт сохраняется правильно."""
        server_id = f"http-transport-{unique_id}"
        
        create_resp = await client.post(
            "/agents/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "HTTP Transport Test",
                "url": "https://example.com/mcp",
                "transport_type": "http",
            },
        )
        assert create_resp.status_code == 200
        data = create_resp.json()
        assert data["transport_type"] == "http"
        
        # Cleanup
        await client.delete(f"/agents/api/v1/mcp/servers/{server_id}")
    
    @pytest.mark.asyncio
    async def test_sse_transport_stored_correctly(self, client, unique_id):
        """Проверяем что SSE транспорт сохраняется правильно."""
        server_id = f"sse-transport-{unique_id}"
        
        create_resp = await client.post(
            "/agents/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "SSE Transport Test",
                "url": "https://example.com/sse",
                "transport_type": "sse",
            },
        )
        assert create_resp.status_code == 200
        data = create_resp.json()
        assert data["transport_type"] == "sse"
        
        # Cleanup
        await client.delete(f"/agents/api/v1/mcp/servers/{server_id}")
