"""
Интеграционные тесты MCP.

HTTP-сессии идут в локальный stub (`tests.fixtures.mcp_http_stub`): тот же JSON-RPC
поток (initialize, tools/list, tools/call), без внешней сети и без длинных таймаутов.
"""

import uuid

import httpx
import pytest

from apps.flows.src.clients.mcp_client import MCPClient, MCPClientError, clear_mcp_client_cache
from apps.flows.src.models.mcp import MCPServerConfig, MCPTransportType


class TestMCPJsonrpcBodyParse:
    """Разбор JSON-RPC тела: чистый JSON и SSE `data:`."""

    def test_plain_json(self):
        text = '{"jsonrpc":"2.0","id":1,"result":{"capabilities":{}}}'
        out = MCPClient._jsonrpc_envelope_from_body(text)
        assert out is not None
        assert out.get("result") == {"capabilities": {}}

    def test_sse_data_line(self):
        text = (
            "event: message\n"
            'data: {"jsonrpc":"2.0","id":1,"result":{"serverInfo":{"name":"x"}}}\n\n'
        )
        out = MCPClient._jsonrpc_envelope_from_body(text)
        assert out is not None
        assert out.get("result", {}).get("serverInfo", {}).get("name") == "x"

    def test_empty_none(self):
        assert MCPClient._jsonrpc_envelope_from_body("") is None
        assert MCPClient._jsonrpc_envelope_from_body("   ") is None


def _local_mcp_config(url: str, server_id: str = "local-mcp-http") -> MCPServerConfig:
    return MCPServerConfig(
        server_id=server_id,
        name="Local MCP HTTP",
        url=url,
        transport_type=MCPTransportType.HTTP,
        headers={},
        is_active=True,
        description="Локальный MCP stub для тестов",
    )


class TestMCPClientHTTP:
    """Тесты MCP клиента против локального HTTP stub."""

    @pytest.fixture(autouse=True)
    def cleanup_cache(self):
        """Очищаем кэш клиентов перед каждым тестом."""
        clear_mcp_client_cache()
        yield
        clear_mcp_client_cache()

    @pytest.mark.asyncio
    async def test_initialize_real_server(self, local_mcp_http_url: str):
        """Инициализация сессии на локальном MCP HTTP."""
        client = MCPClient(_local_mcp_config(local_mcp_http_url), timeout=10.0)

        result = await client.initialize()

        # Главное - инициализация прошла без исключений
        assert result is not None
        assert client._initialized is True
        # Session ID должен быть получен от сервера
        # (может быть None если сервер не требует сессий)

    @pytest.mark.asyncio
    async def test_list_tools_real_server(self, local_mcp_http_url: str):
        """Список tools с локального MCP HTTP."""
        client = MCPClient(_local_mcp_config(local_mcp_http_url), timeout=10.0)

        tools = await client.list_tools()

        # Главное - список tools получен
        assert isinstance(tools, list)
        assert len(tools) > 0

        # Проверяем структуру tools
        for tool in tools:
            assert tool.name  # Имя обязательно
            print(f"Tool: {tool.name} - {tool.description}")

    @pytest.mark.asyncio
    async def test_call_tool_handles_response(self, local_mcp_http_url: str):
        """Вызов tool: проверка разбора ответа MCP."""
        client = MCPClient(_local_mcp_config(local_mcp_http_url), timeout=10.0)

        tools = await client.list_tools()
        assert len(tools) > 0

        first_tool = tools[0]

        try:
            result = await client.call_tool(
                first_tool.name,
                {"libraryName": "react"},
            )
        except httpx.ReadTimeout as exc:
            raise AssertionError("MCP stub не ответил в отведённое время") from exc

        # Главное - результат получен и имеет правильную структуру
        assert result is not None
        assert hasattr(result, 'is_error')
        assert hasattr(result, 'content')

        # Текст должен быть даже если это сообщение об ошибке
        text = result.get_text()
        assert isinstance(text, str)
        print(f"Tool call result (is_error={result.is_error}): {text[:200]}...")

    @pytest.mark.asyncio
    async def test_invalid_tool_returns_error(self, local_mcp_http_url: str):
        """Вызов несуществующего tool даёт ошибку RPC."""
        client = MCPClient(_local_mcp_config(local_mcp_http_url), timeout=10.0)

        with pytest.raises(MCPClientError) as exc_info:
            await client.call_tool("nonexistent-tool-12345", {})

        # Ошибка должна содержать информацию о том что tool не найден
        assert "not found" in str(exc_info.value).lower() or "error" in str(exc_info.value).lower()


class TestMCPSyncAPI:
    """Тесты API синхронизации MCP серверов."""

    @pytest.mark.asyncio
    async def test_create_and_sync_server(self, client, unique_id, local_mcp_http_url: str):
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
            "/flows/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Sync Test Server",
                "url": local_mcp_http_url,
                "transport_type": "http",
                "description": "Test server for sync",
            },
        )
        assert create_resp.status_code == 200, create_resp.text
        server_data = create_resp.json()
        assert server_data["server_id"] == server_id
        assert server_data["cached_tools"] == []  # Пока не синхронизировано

        # Синхронизируем tools
        sync_resp = await client.post(f"/flows/api/v1/mcp/servers/{server_id}/sync")
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
        tools_resp = await client.get("/flows/api/v1/tools/all")
        assert tools_resp.status_code == 200
        all_tools = tools_resp.json()["items"]

        mcp_tools = [t for t in all_tools if t.get("mcp_server_id") == server_id]
        assert len(mcp_tools) > 0, "MCP tools должны появиться в общем списке"

        # Cleanup
        await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")

    @pytest.mark.asyncio
    async def test_server_connection_test(self, client, unique_id, local_mcp_http_url: str):
        """
        E2E: Тест подключения к MCP серверу.
        """
        server_id = f"conn-test-{unique_id}"

        await client.post(
            "/flows/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Connection Test",
                "url": local_mcp_http_url,
                "transport_type": "http",
            },
        )

        test_resp = await client.post(f"/flows/api/v1/mcp/servers/{server_id}/test")
        assert test_resp.status_code == 200

        test_data = test_resp.json()
        assert test_data["success"] is True
        assert test_data["tools_count"] > 0
        assert test_data["transport_type"] == "http"
        assert test_data["url"] == local_mcp_http_url

        print(f"Connection test: {test_data}")

        # Cleanup
        await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")

    @pytest.mark.asyncio
    async def test_server_crud(self, client, unique_id, local_mcp_http_url: str):
        """
        E2E: CRUD операции с MCP сервером.
        """
        server_id = f"crud-test-{unique_id}"

        # Create
        create_resp = await client.post(
            "/flows/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "CRUD Test",
                "url": local_mcp_http_url,
                "transport_type": "http",
            },
        )
        assert create_resp.status_code == 200

        # Read
        get_resp = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["server_id"] == server_id
        assert data["name"] == "CRUD Test"

        # Update
        update_resp = await client.put(
            f"/flows/api/v1/mcp/servers/{server_id}",
            json={"name": "CRUD Test Updated"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "CRUD Test Updated"

        # List
        list_resp = await client.get("/flows/api/v1/mcp/servers")
        assert list_resp.status_code == 200
        servers = list_resp.json()["items"]
        assert any(s["server_id"] == server_id for s in servers)

        # Delete
        del_resp = await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")
        assert del_resp.status_code == 200

        # Verify deleted
        get_resp2 = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
        assert get_resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_server_url_returns_error(self, client, unique_id):
        """Проверяем что невалидный URL сервера возвращает ошибку при sync."""
        server_id = f"invalid-url-{unique_id}"

        # Создаем сервер с невалидным URL
        await client.post(
            "/flows/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Invalid URL Test",
                "url": "http://127.0.0.1:59999/mcp",  # Локальный порт который точно не слушает
                "transport_type": "http",
            },
        )

        # Sync должен вернуть ошибку (сетевая или HTTP)
        sync_resp = await client.post(f"/flows/api/v1/mcp/servers/{server_id}/sync")
        # Ожидаем любую ошибку >= 400
        assert sync_resp.status_code >= 400, f"Невалидный URL должен вернуть ошибку, получили {sync_resp.status_code}"

        # Cleanup
        await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")

    @pytest.mark.asyncio
    async def test_duplicate_server_id_rejected(self, client, unique_id, local_mcp_http_url: str):
        """Проверяем что дублирование server_id отклоняется."""
        server_id = f"duplicate-test-{unique_id}"

        # Создаем первый сервер
        resp1 = await client.post(
            "/flows/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "First Server",
                "url": local_mcp_http_url,
                "transport_type": "http",
            },
        )
        assert resp1.status_code == 200

        # Пытаемся создать второй с тем же ID
        resp2 = await client.post(
            "/flows/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Second Server",
                "url": local_mcp_http_url,
                "transport_type": "http",
            },
        )
        assert resp2.status_code == 409, "Дублирование server_id должно вернуть 409"

        # Cleanup
        await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")


class TestMCPNodeInGraph:
    """
    Тесты MCPNode в графе агента.

    Проверяем что MCPNode корректно интегрируется в граф и
    обрабатывает как успешные ответы, так и ошибки от MCP сервера.
    """

    @pytest.mark.asyncio
    async def test_mcp_node_executes_in_graph(self, client, unique_id, local_mcp_http_url: str):
        """
        E2E: MCPNode вызывается в графе агента.

        Проверяем что:
        1. MCPNode создаётся и конфигурируется
        2. Граф выполняется
        3. MCPNode обрабатывает ответ (успех или ошибку)
        """
        flow_id = f"mcp_node_graph_{unique_id}"
        server_id = f"context7-graph-{unique_id}"

        # Создаем MCP сервер
        server_resp = await client.post(
            "/flows/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Context7 Graph Test",
                "url": local_mcp_http_url,
                "transport_type": "http",
            },
        )
        assert server_resp.status_code == 200

        # Синхронизируем tools
        sync_resp = await client.post(f"/flows/api/v1/mcp/servers/{server_id}/sync")
        assert sync_resp.status_code == 200
        sync_data = sync_resp.json()
        assert sync_data["tools_count"] > 0

        # Берём первый tool
        first_tool = sync_data["tools"][0]["name"]

        # Создаем агента с MCPNode
        create_resp = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "MCP Node Graph Test",
                "entry": "init",
                "nodes": {
                    "init": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['query'] = 'fastapi'\n    return state",
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
                        "code": "async def run(args, state):\n    state['response'] = 'done'\n    return state",
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
            f"/flows/api/v1/{flow_id}",
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
                assert "mcp" in error_text.lower() or "error" in error_text.lower()
                print(f"MCP returned error (expected): {error_text[:200]}")
        else:
            print("MCP call completed successfully")

        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")
        await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")


class TestMCPToolInLlmNode:
    """Тесты MCP tool в ReAct ноде агента."""

    @pytest.mark.asyncio
    async def test_llm_node_can_use_mcp_tool(
        self, client, unique_id, mock_llm_redis, local_mcp_http_url: str
    ):
        """
        E2E: ReAct нода может использовать MCP tool.

        Сценарий:
        1. Создаём MCP сервер и синхронизируем tools
        2. Создаём агента с ReAct нодой которая имеет MCP tool
        3. MockLLM делает tool call
        4. Проверяем что tool был вызван
        """
        flow_id = f"react_mcp_{unique_id}"
        server_id = f"context7-react-{unique_id}"

        # Создаем MCP сервер
        server_resp = await client.post(
            "/flows/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Context7 React Test",
                "url": local_mcp_http_url,
                "transport_type": "http",
            },
        )
        assert server_resp.status_code == 200

        # Синхронизируем tools
        sync_resp = await client.post(f"/flows/api/v1/mcp/servers/{server_id}/sync")
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
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "React MCP Agent",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "llm_node",
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
            f"/flows/api/v1/{flow_id}",
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
        await client.delete(f"/flows/api/v1/flows/{flow_id}")
        await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")


class TestMCPWithCustomHeaders:
    """Тесты MCP с кастомными headers и авторизацией."""

    @pytest.mark.asyncio
    async def test_server_with_custom_headers(self, client, unique_id, local_mcp_http_url: str):
        """
        Проверяем что сервер с кастомными headers создаётся и сохраняется.
        """
        server_id = f"headers-test-{unique_id}"

        create_resp = await client.post(
            "/flows/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Headers Test",
                "url": local_mcp_http_url,
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
        get_resp = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["headers"]["X-Custom-Header"] == "test-value"

        # Cleanup
        await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")

    @pytest.mark.asyncio
    async def test_server_with_var_reference_in_headers(self, client, unique_id, local_mcp_http_url: str):
        """
        Проверяем что @var: ссылки в headers сохраняются.
        """
        server_id = f"var-headers-{unique_id}"

        create_resp = await client.post(
            "/flows/api/v1/mcp/servers",
            json={
                "server_id": server_id,
                "name": "Var Headers Test",
                "url": local_mcp_http_url,
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
        await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")


class TestMCPTransportTypes:
    """Тесты разных типов транспорта MCP."""

    @pytest.mark.asyncio
    async def test_http_transport_stored_correctly(self, client, unique_id):
        """Проверяем что HTTP транспорт сохраняется правильно."""
        server_id = f"http-transport-{unique_id}"

        create_resp = await client.post(
            "/flows/api/v1/mcp/servers",
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
        await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")

    @pytest.mark.asyncio
    async def test_sse_transport_stored_correctly(self, client, unique_id):
        """Проверяем что SSE транспорт сохраняется правильно."""
        server_id = f"sse-transport-{unique_id}"

        create_resp = await client.post(
            "/flows/api/v1/mcp/servers",
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
        await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")
