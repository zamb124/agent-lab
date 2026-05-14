"""
Интеграционные тесты для внешних агентов.

Запускаются с реальным Docker контейнером тестового агента.
"""

import os

import pytest
from httpx import ASGITransport, AsyncClient

from apps.flows.src.container import get_container
from apps.flows.src.models import ExternalAgentStatus, FlowConfig, FlowType
from tests.flows.fixtures.external_agent.main import external_agent_app


@pytest.fixture
async def external_agent_url():
    """
    URL тестового внешнего агента.

    В docker-compose: http://external-agent-test:8080
    Локально через ASGI: используем ASGITransport
    """
    return os.getenv("EXTERNAL_AGENT_TEST_URL", "http://test-agent")


@pytest.fixture
async def asgi_external_agent():
    """ASGI клиент для тестового агента (без реального HTTP)."""
    transport = ASGITransport(app=external_agent_app)
    async with AsyncClient(transport=transport, base_url="http://test-agent") as client:
        yield client


class TestFlowDiscoveryService:
    """Тесты FlowDiscoveryService."""

    @pytest.mark.asyncio
    async def test_register_agent_via_asgi(self, app, asgi_external_agent):
        """Регистрация агента через ASGI (без реального контейнера)."""
        response = await asgi_external_agent.get("/.well-known/agent-card.json")
        assert response.status_code == 200

        agent_card = response.json()
        assert agent_card["name"] == "Test External Agent"

    @pytest.mark.asyncio
    async def test_register_and_list_agents(self, app):
        """Регистрация и получение списка агентов."""
        container = get_container()

        agent = FlowConfig(
            flow_id="test_agent_1",
            type=FlowType.EXTERNAL,
            url="http://test-agent:8080",
            name="Test Agent 1",
            status=ExternalAgentStatus.ACTIVE,
            headers={"X-API-Key": "test-key"},
        )

        await container.flow_repository.set(agent)

        all_agents = await container.flow_repository.list(limit=10000)
        assert len(all_agents) >= 1

        found = await container.flow_repository.get("test_agent_1")
        assert found is not None
        assert found.name == "Test Agent 1"
        assert found.headers == {"X-API-Key": "test-key"}

    @pytest.mark.asyncio
    async def test_list_active_agents(self, app):
        """Только активные агенты."""
        container = get_container()

        agent_active = FlowConfig(
            flow_id="active_agent",
            type=FlowType.EXTERNAL,
            url="http://active:8080",
            name="Active Agent",
            status=ExternalAgentStatus.ACTIVE,
        )
        agent_inactive = FlowConfig(
            flow_id="inactive_agent",
            type=FlowType.EXTERNAL,
            url="http://inactive:8080",
            name="Inactive Agent",
            status=ExternalAgentStatus.INACTIVE,
        )

        await container.flow_repository.set(agent_active)
        await container.flow_repository.set(agent_inactive)

        # Фильтруем external агентов по статусу
        all_agents = await container.flow_repository.list(limit=10000)
        active_agents = [a for a in all_agents if a.type == FlowType.EXTERNAL and a.status == ExternalAgentStatus.ACTIVE]
        agent_ids = [a.flow_id for a in active_agents]

        assert "active_agent" in agent_ids
        assert "inactive_agent" not in agent_ids

    @pytest.mark.asyncio
    async def test_get_agent_by_url(self, app, unique_id):
        """Получение агента по URL."""
        container = get_container()

        flow_id = f"url_test_agent_{unique_id}"
        url = f"http://unique-url-{unique_id}:9000"

        agent = FlowConfig(
            flow_id=flow_id,
            type=FlowType.EXTERNAL,
            url=url,
            name="URL Test Agent",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.flow_repository.set(agent)

        # Ищем агента по URL
        all_agents = await container.flow_repository.list(limit=10000)
        found = None
        for a in all_agents:
            if a.type == FlowType.EXTERNAL and a.url == url:
                found = a
                break
        assert found is not None
        assert found.flow_id == flow_id

    @pytest.mark.asyncio
    async def test_update_health_check(self, app):
        """Обновление статуса после health check."""
        container = get_container()

        agent = FlowConfig(
            flow_id="health_test_agent",
            type=FlowType.EXTERNAL,
            url="http://health-test:8080",
            name="Health Test Agent",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.flow_repository.set(agent)

        # Обновляем health check
        agent = await container.flow_repository.get("health_test_agent")
        agent.status = ExternalAgentStatus.UNHEALTHY
        agent.agent_card = {"name": "Updated Card"}
        from datetime import datetime
        from datetime import timezone as tz
        agent.last_health_check = datetime.now(tz.utc)
        await container.flow_repository.set(agent)

        updated = await container.flow_repository.get("health_test_agent")
        assert updated.status == ExternalAgentStatus.UNHEALTHY
        assert updated.agent_card == {"name": "Updated Card"}
        assert updated.last_health_check is not None


class TestA2AClientWithRealAgent:
    """
    Тесты A2AClient с реальным тестовым агентом.

    Эти тесты используют ASGI transport для тестирования
    без реального Docker контейнера.
    """

    @pytest.mark.asyncio
    async def test_get_agent_card_asgi(self, asgi_external_agent):
        """Получение agent-card через ASGI."""
        response = await asgi_external_agent.get("/.well-known/agent-card.json")
        assert response.status_code == 200

        card = response.json()
        assert card["name"] == "Test External Agent"
        assert "branches" in card
        assert len(card["branches"]) > 0

    @pytest.mark.asyncio
    async def test_health_check_asgi(self, asgi_external_agent):
        """Health check через ASGI."""
        response = await asgi_external_agent.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_send_task_asgi(self, asgi_external_agent):
        """Отправка задачи через ASGI."""
        import uuid

        task_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": task_id,
            "method": "tasks/send",
            "params": {
                "id": task_id,
                "sessionId": "test-session",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Hello, agent!"}],
                },
                "skillId": "default",
            },
        }

        response = await asgi_external_agent.post("/", json=payload)
        assert response.status_code == 200

        result = response.json()
        assert "result" in result
        assert result["result"]["status"]["state"] == "completed"

        response_text = ""
        for part in result["result"]["status"]["message"]["parts"]:
            if part["type"] == "text":
                response_text += part["text"]

        assert "Echo: Hello, agent!" in response_text


class TestExternalAgentsAPI:
    """Тесты API endpoints для внешних агентов."""

    @pytest.mark.asyncio
    async def test_list_external_agents_empty(self, client):
        """Пустой список внешних агентов."""
        from apps.flows.src.models import FlowType
        response = await client.get("/flows/api/v1/flows/", params={"type": FlowType.EXTERNAL.value})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_register_and_get_external_agent(self, app, client, asgi_external_agent):
        """Регистрация и получение внешнего агента через API."""
        container = get_container()

        agent = FlowConfig(
            flow_id="api_test_agent",
            type=FlowType.EXTERNAL,
            url="http://api-test:8080",
            name="API Test Agent",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.flow_repository.set(agent)

        # API для external agents теперь объединен с основным agents API
        response = await client.get("/flows/api/v1/flows/api_test_agent")
        assert response.status_code == 200

        data = response.json()
        assert data["flow_id"] == "api_test_agent"
        assert data["name"] == "API Test Agent"

    @pytest.mark.asyncio
    async def test_delete_external_agent(self, app, client):
        """Удаление внешнего агента через API."""
        container = get_container()

        agent = FlowConfig(
            flow_id="delete_test_agent",
            type=FlowType.EXTERNAL,
            url="http://delete-test:8080",
            name="Delete Test Agent",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.flow_repository.set(agent)

        # API для external agents теперь объединен с основным agents API
        response = await client.delete("/flows/api/v1/flows/delete_test_agent")
        assert response.status_code == 200

        deleted = await container.flow_repository.get("delete_test_agent")
        assert deleted is None

    @pytest.mark.asyncio
    async def test_get_nonexistent_agent(self, client):
        """404 для несуществующего агента."""
        response = await client.get("/flows/api/v1/flows/external/nonexistent")
        assert response.status_code == 404

