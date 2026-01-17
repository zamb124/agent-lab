"""
Интеграционные тесты для ExternalAPINode и ExternalAPITool.

Тестируют:
- ExternalAPIClient - HTTP вызовы
- ExternalAPINode - нода flow
- ExternalAPITool - tool для react агентов
- @var: резолвинг
- Протокол ответа (completed/waiting_input)
"""

import pytest
from httpx import ASGITransport, AsyncClient

from apps.agents.src.clients.external_api_client import ExternalAPIClient, ExternalAPIError
from apps.agents.src.agent.nodes import ExternalAPINode, create_node
from apps.agents.src.models import Edge, AgentConfig
from apps.agents.src.models.external_api import (
    ExternalAPIConfig,
    HTTPMethod,
    ParameterLocation,
    ParameterSchema,
    ResponseSchema,
)
from apps.agents.src.tools import ExternalAPITool
from core.state import ExecutionState
from tests.agents.fixtures.external_api.main import external_api_app


@pytest.fixture
async def asgi_api_client():
    """ASGI клиент для тестового API."""
    transport = ASGITransport(app=external_api_app)
    async with AsyncClient(transport=transport, base_url="http://test-api") as client:
        yield client


class TestExternalAPIClient:
    """Тесты ExternalAPIClient."""

    @pytest.mark.asyncio
    async def test_simple_post_request(self, asgi_api_client):
        """Простой POST запрос."""
        response = await asgi_api_client.post(
            "/echo",
            json={"message": "Hello", "uppercase": False}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["data"]["result"] == "Hello"

    @pytest.mark.asyncio
    async def test_echo_uppercase(self, asgi_api_client):
        """Echo с uppercase."""
        response = await asgi_api_client.post(
            "/echo",
            json={"message": "hello world", "uppercase": True}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["result"] == "HELLO WORLD"

    @pytest.mark.asyncio
    async def test_calculator_add(self, asgi_api_client):
        """Калькулятор - сложение."""
        response = await asgi_api_client.post(
            "/calculate",
            json={"a": 10, "b": 5, "operation": "add"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["result"] == 15

    @pytest.mark.asyncio
    async def test_calculator_divide_by_zero(self, asgi_api_client):
        """Калькулятор - деление на ноль."""
        response = await asgi_api_client.post(
            "/calculate",
            json={"a": 10, "b": 0, "operation": "divide"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "Division by zero" in data["error"]

    @pytest.mark.asyncio
    async def test_interrupt_response(self, asgi_api_client):
        """Ответ с interrupt."""
        response = await asgi_api_client.post(
            "/ask-clarification",
            json={"message": "short"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "waiting_input"
        assert "interrupt" in data
        assert "question" in data["interrupt"]


class TestExternalAPIClientWithConfig:
    """Тесты ExternalAPIClient с конфигурацией."""

    @pytest.mark.asyncio
    async def test_client_call_echo(self, monkeypatch):
        """Вызов echo через клиент."""
        import httpx

        async def mock_request(*args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "data": {"result": "test message"}
                }
            )

        monkeypatch.setattr(httpx.AsyncClient, "request", mock_request)

        config = ExternalAPIConfig(
            api_id="echo",
            name="Echo API",
            url="http://test/echo",
            method=HTTPMethod.POST,
            parameters=[
                ParameterSchema(name="message", location=ParameterLocation.BODY, required=True),
            ]
        )

        client = ExternalAPIClient()
        result = await client.call(config, {"message": "test message"})

        assert result["status"] == "completed"
        assert result["data"]["result"] == "test message"

    @pytest.mark.asyncio
    async def test_var_resolution_in_url(self):
        """Резолвинг @var: в URL."""
        client = ExternalAPIClient()

        url = "@var:base_url/api/test"
        variables = {"base_url": "http://example.com"}

        resolved = client._resolve_value(url, variables)
        assert resolved == "http://example.com/api/test"

    @pytest.mark.asyncio
    async def test_var_resolution_in_headers(self):
        """Резолвинг @var: в headers."""
        client = ExternalAPIClient()

        config = ExternalAPIConfig(
            api_id="test",
            name="Test",
            url="http://test",
            auth_headers={"Authorization": "@var:api_token"}
        )

        variables = {"api_token": "Bearer secret123"}
        headers = client._build_headers(config, variables)

        assert headers["Authorization"] == "Bearer secret123"


class TestExternalAPINode:
    """Тесты ExternalAPINode."""

    @pytest.mark.asyncio
    async def test_create_external_api_node(self):
        """Создание ExternalAPINode."""
        node_config = {
            "type": "external_api",
            "name": "Echo API",
            "url": "http://test/echo",
            "method": "POST",
            "parameters": [
                {"name": "message", "location": "body", "required": True},
            ]
        }

        node = await create_node("echo_node", node_config)
        assert isinstance(node, ExternalAPINode)
        assert node.node_id == "echo_node"

    @pytest.mark.asyncio
    async def test_external_api_node_with_asgi(self, asgi_api_client, monkeypatch):
        """ExternalAPINode с ASGI транспортом."""
        import httpx

        async def mock_request(self, *args, **kwargs):
            url = kwargs.get("url", args[1] if len(args) > 1 else "")
            if "/echo" in str(url):
                return httpx.Response(
                    200,
                    json={
                        "status": "completed",
                        "data": {"result": "Hello from API"}
                    }
                )
            raise httpx.RequestError("Unknown URL")

        monkeypatch.setattr(httpx.AsyncClient, "request", mock_request)

        node = ExternalAPINode(
            node_id="echo_node",
            config={
                "url": "http://test/echo",
                "method": "POST",
                "parameters": [
                    {"name": "message", "location": "body", "required": True},
                ]
            }
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            message="Hello"
        )
        result = await node.run(state)

        assert result["api_status"] == "completed"
        assert result["api_response"]["result"] == "Hello from API"

    @pytest.mark.asyncio
    async def test_external_api_node_interrupt(self, monkeypatch):
        """ExternalAPINode с interrupt."""
        import httpx

        async def mock_request(self, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "status": "waiting_input",
                    "interrupt": {"question": "Need more info"}
                }
            )

        monkeypatch.setattr(httpx.AsyncClient, "request", mock_request)

        node = ExternalAPINode(
            node_id="clarify_node",
            config={
                "url": "http://test/clarify",
                "method": "POST",
                "parameters": [],
            }
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)

        assert result.interrupt is not None
        assert result.interrupt.question == "Need more info"

    @pytest.mark.asyncio
    async def test_external_api_node_with_var(self, monkeypatch):
        """ExternalAPINode с @var: переменными."""
        import httpx

        captured_headers = {}

        async def mock_request(self, *args, **kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return httpx.Response(
                200,
                json={"status": "completed", "data": {"ok": True}}
            )

        monkeypatch.setattr(httpx.AsyncClient, "request", mock_request)

        node = ExternalAPINode(
            node_id="auth_node",
            config={
                "url": "http://test/auth",
                "method": "POST",
                "auth_headers": {"Authorization": "@var:auth_token"},
                "parameters": [],
            }
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            variables={"auth_token": "Bearer secret123"}
        )
        await node.run(state)

        assert captured_headers.get("Authorization") == "Bearer secret123"


class TestExternalAPITool:
    """Тесты ExternalAPITool."""

    @pytest.mark.asyncio
    async def test_create_external_api_tool(self):
        """Создание ExternalAPITool."""
        tool = ExternalAPITool(
            api_id="echo_tool",
            url="http://test/echo",
            method="POST",
            description="Echo API tool",
            parameters=[
                {"name": "message", "type": "string", "required": True},
            ]
        )

        assert tool.name == "echo_tool"
        assert "message" in tool.parameters["properties"]
        assert "message" in tool.parameters["required"]

    @pytest.mark.asyncio
    async def test_external_api_tool_execute(self, monkeypatch):
        """Выполнение ExternalAPITool."""
        import httpx

        async def mock_request(self, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "data": {"result": "processed"}
                }
            )

        monkeypatch.setattr(httpx.AsyncClient, "request", mock_request)

        tool = ExternalAPITool(
            api_id="process_tool",
            url="http://test/process",
            method="POST",
            parameters=[
                {"name": "input", "type": "string", "required": True},
            ]
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await tool.run({"input": "test data"}, state)
        assert result["result"] == "processed"

    @pytest.mark.asyncio
    async def test_external_api_tool_openai_schema(self):
        """Схема для OpenAI."""
        tool = ExternalAPITool(
            api_id="calc_tool",
            url="http://test/calc",
            description="Calculator tool",
            parameters=[
                {"name": "a", "type": "number", "description": "First number", "required": True},
                {"name": "b", "type": "number", "description": "Second number", "required": True},
            ]
        )

        schema = tool.to_openai_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "calc_tool"
        assert "a" in schema["function"]["parameters"]["properties"]
        assert "b" in schema["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_external_api_tool_with_response_mapping(self, monkeypatch):
        """ExternalAPITool с маппингом ответа."""
        import httpx

        async def mock_request(self, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "data": {
                        "calculation_result": 42,
                        "details": "some info"
                    }
                }
            )

        monkeypatch.setattr(httpx.AsyncClient, "request", mock_request)

        tool = ExternalAPITool(
            api_id="calc",
            url="http://test/calc",
            parameters=[],
            response_mapping={"calculation_result": "answer"}
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await tool.run({}, state)
        assert result == {"answer": 42}


class TestFlowWithExternalAPI:
    """Тесты Agent с ExternalAPINode."""

    @pytest.mark.asyncio
    async def test_flow_with_external_api_node(self, app, monkeypatch):
        """Agent с ExternalAPINode."""
        import httpx
        from apps.agents.src.container import get_container

        async def mock_request(self, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "data": {"processed": True}
                }
            )

        monkeypatch.setattr(httpx.AsyncClient, "request", mock_request)

        container = get_container()

        agent_config = AgentConfig(
            agent_id="external_api_flow",
            name="External API Agent",
            entry="api_call",
            nodes={
                "api_call": {
                    "type": "external_api",
                    "url": "http://test/process",
                    "method": "POST",
                    "parameters": [],
                }
            },
            edges=[Edge(from_node="api_call", to_node=None)]
        )

        await container.agent_repository.set(agent_config)

        flow = await container.agent_factory.get_flow("external_api_flow")
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await flow.run(state)

        assert result["api_status"] == "completed"
        assert result["api_response"]["processed"] is True

