"""
Тесты для services (AgentFactory, agents_loader, AgentDiscoveryService).
"""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core.clients import A2AClient
from apps.agents.config import ExternalAgentConfig
from apps.agents.src.container import get_container
from core.db.repositories import Variable
from apps.agents.src.agent.agent import Agent
from apps.agents.src.models import ExternalAgentStatus, AgentConfig, AgentType
from apps.agents.src.services.agent_discovery import AgentDiscoveryService
from apps.agents.src.services.agent_factory import AgentFactory


class TestAgentFactory:
    """Тесты AgentFactory."""

    @pytest.mark.asyncio
    async def test_get_flow_from_db(self, app):
        """AgentFactory загружает flow из БД."""
        container = get_container()
        factory = container.agent_factory

        # Сохраняем flow в БД
        agent_config = AgentConfig(
            agent_id="test_factory_flow",
            name="Test Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "react_node",
                    "prompt": "Test prompt",
                    "next": None
                }
            },
        )
        await container.agent_repository.set(agent_config)

        # Получаем через factory
        flow = await factory.get_flow("test_factory_flow")

        assert flow is not None
        assert isinstance(flow, Agent)
        assert flow.agent_id == "test_factory_flow"

        # Cleanup
        await container.agent_repository.delete("test_factory_flow")

    @pytest.mark.asyncio
    async def test_get_flow_returns_none_for_missing(self, app):
        """AgentFactory возвращает None для несуществующего flow."""
        container = get_container()
        factory = container.agent_factory

        flow = await factory.get_flow("nonexistent_flow_xyz")

        assert flow is None

    @pytest.mark.asyncio
    async def test_agent_factory_resolves_variables(self, app):
        """AgentFactory резолвит @var:key в variables."""
        container = get_container()
        factory = container.agent_factory

        # Создаём переменную
        await container.variable_repository.set(
            Variable(key="factory_var", value="resolved!")
        )

        # Agent с @var:key
        agent_config = AgentConfig(
            agent_id="test_var_flow",
            name="Test Var Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "react_node",
                    "prompt": "Test",
                    "next": None
                }
            },
            variables={
                "test_var": "@var:factory_var",
                "static_var": "static_value"
            },
        )
        await container.agent_repository.set(agent_config)

        # Получаем flow - variables должны быть резолвнуты
        flow = await factory.get_flow("test_var_flow")

        assert flow.variables["test_var"] == "resolved!"
        assert flow.variables["static_var"] == "static_value"

        # Cleanup
        await container.agent_repository.delete("test_var_flow")
        await container.variable_repository.delete("factory_var")

    @pytest.mark.asyncio
    async def test_create_flow_saves_to_db(self, app):
        """AgentFactory.create_flow сохраняет в БД."""
        container = get_container()
        factory = container.agent_factory

        agent_config = AgentConfig(
            agent_id="created_flow",
            name="Created Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "react_node",
                    "prompt": "Created",
                    "next": None
                }
            },
        )

        flow = await factory.create_flow(agent_config)

        assert flow is not None

        # Проверяем что сохранилось в БД
        loaded = await container.agent_repository.get("created_flow")
        assert loaded is not None

        # Cleanup
        await container.agent_repository.delete("created_flow")


class TestAgentsLoader:
    """Тесты agents_loader."""

    @pytest.mark.asyncio
    async def test_load_flows_to_db(self, app):
        """load_flows_to_db загружает flows и agents из директории в БД."""
        from apps.agents.src.services.agents_loader import AgentsLoader

        container = get_container()
        agents_dir = Path(__file__).parent.parent.parent.parent.parent / "apps" / "agents" / "agents"
        registry_path = Path(__file__).parent.parent.parent.parent.parent / "apps" / "agents" / "registry.yaml"

        # Загружаем flows и nodes с явным указанием registry_path
        loader = AgentsLoader(
            agents_dir=agents_dir,
            agent_repository=container.agent_repository,
            node_repository=container.node_repository,
            tool_repository=container.tool_repository,
            registry_path=registry_path,
        )
        loaded_flows, loaded_nodes = await loader.load_all()

        assert len(loaded_flows) > 0
        assert isinstance(loaded_flows, list)

        # Проверяем что flows доступны в БД
        for agent_id in loaded_flows[:3]:  # Проверяем первые 3
            agent_config = await container.agent_repository.get(agent_id)
            assert agent_config is not None

        # Проверяем что nodes загружены (если есть nodes.json)
        if loaded_nodes:
            for node_id in loaded_nodes[:3]:
                node_config = await container.node_repository.get(node_id)
                assert node_config is not None

    @pytest.mark.asyncio
    async def test_load_tools_to_db(self, app):
        """load_tools_to_db загружает tools в БД."""
        from apps.agents.src.services.agents_loader import load_tools_to_db

        container = get_container()

        # Загружаем tools
        loaded = await load_tools_to_db(container.tool_repository)

        assert len(loaded) > 0

        # Проверяем calculator
        if "calculator" in loaded:
            tool = await container.tool_repository.get("calculator")
            assert tool is not None


class TestAgentDiscoveryService:
    """Тесты AgentDiscoveryService."""

    @pytest.fixture
    def mock_a2a_client(self):
        """Мок A2A клиента."""
        client = AsyncMock(spec=A2AClient)
        client.get_agent_card = AsyncMock(
            return_value={
                "name": "Test Agent",
                "description": "Test Description",
                "skills": [{"id": "default", "name": "Default Skill"}],
            }
        )
        return client

    @pytest.fixture
    async def discovery_service(self, app, mock_a2a_client):
        """AgentDiscoveryService с мок клиентом."""
        container = get_container()
        return AgentDiscoveryService(
            repository=container.agent_repository,
            a2a_client=mock_a2a_client,
        )

    @pytest.mark.asyncio
    async def test_register_agent(self, discovery_service, mock_a2a_client, unique_id):
        """Регистрация нового агента."""
        url = f"http://new-agent-{unique_id}:8080"
        agent = await discovery_service.register_agent(
            url=url,
            auth_headers={"Authorization": "Bearer token"},
            name="Custom Name",
        )

        assert agent is not None
        assert agent.name == "Custom Name"
        assert agent.url == url
        assert agent.auth_headers == {"Authorization": "Bearer token"}
        assert agent.status == ExternalAgentStatus.ACTIVE
        assert agent.agent_card["name"] == "Test Agent"

        mock_a2a_client.get_agent_card.assert_called_once_with(url, {"Authorization": "Bearer token"})

    @pytest.mark.asyncio
    async def test_register_agent_already_exists(self, discovery_service, mock_a2a_client, app, unique_id):
        """Регистрация уже существующего агента возвращает его."""
        container = get_container()
        agent_id = f"existing_{unique_id}"
        url = f"http://existing-{unique_id}:8080"
        existing = AgentConfig(
            agent_id=agent_id,
            type=AgentType.EXTERNAL,
            url=url,
            name="Existing",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.agent_repository.set(existing)

        agent = await discovery_service.register_agent(url=url)

        assert agent.agent_id == agent_id
        mock_a2a_client.get_agent_card.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_agent_uses_card_name(self, discovery_service, mock_a2a_client, unique_id):
        """Регистрация без имени использует имя из agent-card."""
        url = f"http://card-name-{unique_id}:8080"
        agent = await discovery_service.register_agent(url=url)

        assert agent.name == "Test Agent"

    @pytest.mark.asyncio
    async def test_unregister_agent(self, discovery_service, app, unique_id):
        """Удаление агента."""
        container = get_container()
        agent_id = f"unregister_{unique_id}"
        agent = AgentConfig(
            agent_id=agent_id,
            type=AgentType.EXTERNAL,
            url=f"http://unregister-{unique_id}:8080",
            name="To Unregister",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.agent_repository.set(agent)

        result = await discovery_service.unregister_agent(agent_id)
        assert result is True

        deleted = await container.agent_repository.get(agent_id)
        assert deleted is None

    @pytest.mark.asyncio
    async def test_get_agent(self, discovery_service, app, unique_id):
        """Получение агента по ID."""
        container = get_container()
        agent_id = f"get_{unique_id}"
        agent = AgentConfig(
            agent_id=agent_id,
            type=AgentType.EXTERNAL,
            url=f"http://get-{unique_id}:8080",
            name="Get Test",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.agent_repository.set(agent)

        found = await discovery_service.get_agent(agent_id)

        assert found is not None
        assert found.agent_id == agent_id

    @pytest.mark.asyncio
    async def test_get_agent_by_url(self, discovery_service, app, unique_id):
        """Получение агента по URL."""
        container = get_container()
        agent_id = f"url_{unique_id}"
        url = f"http://url-{unique_id}:8080"
        agent = AgentConfig(
            agent_id=agent_id,
            type=AgentType.EXTERNAL,
            url=url,
            name="URL Test",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.agent_repository.set(agent)

        found = await discovery_service.get_agent_by_url(f"{url}/")

        assert found is not None
        assert found.agent_id == agent_id

    @pytest.mark.asyncio
    async def test_list_agents_only_active(self, discovery_service, app, unique_id):
        """Список только активных агентов."""
        container = get_container()
        active_id = f"list_active_{unique_id}"
        inactive_id = f"list_inactive_{unique_id}"
        active = AgentConfig(
            agent_id=active_id,
            type=AgentType.EXTERNAL,
            url=f"http://list-active-{unique_id}:8080",
            name="Active",
            status=ExternalAgentStatus.ACTIVE,
        )
        inactive = AgentConfig(
            agent_id=inactive_id,
            type=AgentType.EXTERNAL,
            url=f"http://list-inactive-{unique_id}:8080",
            name="Inactive",
            status=ExternalAgentStatus.INACTIVE,
        )
        await container.agent_repository.set(active)
        await container.agent_repository.set(inactive)

        agents = await discovery_service.list_agents(only_active=True)
        agent_ids = [a.agent_id for a in agents]

        assert active_id in agent_ids
        assert inactive_id not in agent_ids

    @pytest.mark.asyncio
    async def test_list_agents_all(self, discovery_service, app, unique_id):
        """Список всех агентов."""
        container = get_container()
        active_id = f"all_active_{unique_id}"
        inactive_id = f"all_inactive_{unique_id}"
        active = AgentConfig(
            agent_id=active_id,
            type=AgentType.EXTERNAL,
            url=f"http://all-active-{unique_id}:8080",
            name="Active",
            status=ExternalAgentStatus.ACTIVE,
        )
        inactive = AgentConfig(
            agent_id=inactive_id,
            type=AgentType.EXTERNAL,
            url=f"http://all-inactive-{unique_id}:8080",
            name="Inactive",
            status=ExternalAgentStatus.INACTIVE,
        )
        await container.agent_repository.set(active)
        await container.agent_repository.set(inactive)

        agents = await discovery_service.list_agents(only_active=False)
        agent_ids = [a.agent_id for a in agents]

        assert active_id in agent_ids
        assert inactive_id in agent_ids

    @pytest.mark.asyncio
    async def test_health_check_agent_success(self, discovery_service, mock_a2a_client, app, unique_id):
        """Health check успешного агента."""
        container = get_container()
        agent_id = f"health_success_{unique_id}"
        agent = AgentConfig(
            agent_id=agent_id,
            type=AgentType.EXTERNAL,
            url=f"http://health-success-{unique_id}:8080",
            name="Health Success",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.agent_repository.set(agent)

        result = await discovery_service.health_check_agent(agent_id)

        assert result is True

        updated = await container.agent_repository.get(agent_id)
        assert updated.status == ExternalAgentStatus.ACTIVE
        assert updated.agent_card["name"] == "Test Agent"

    @pytest.mark.asyncio
    async def test_health_check_agent_failure(self, discovery_service, mock_a2a_client, app, unique_id):
        """Health check неудачного агента."""
        container = get_container()
        agent_id = f"health_fail_{unique_id}"
        agent = AgentConfig(
            agent_id=agent_id,
            type=AgentType.EXTERNAL,
            url=f"http://health-fail-{unique_id}:8080",
            name="Health Fail",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.agent_repository.set(agent)

        mock_a2a_client.get_agent_card.side_effect = Exception("Connection refused")

        result = await discovery_service.health_check_agent(agent_id)

        assert result is False

        updated = await container.agent_repository.get(agent_id)
        assert updated.status == ExternalAgentStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_health_check_agent_not_found(self, discovery_service, unique_id):
        """Health check несуществующего агента."""
        result = await discovery_service.health_check_agent(f"nonexistent_{unique_id}")
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_all(self, discovery_service, mock_a2a_client, app, unique_id):
        """Health check всех агентов."""
        # Используем короткие ID чтобы попасть в limit=100 при сортировке по алфавиту
        agent1_id = f"a_check_1_{unique_id}"
        agent2_id = f"a_check_2_{unique_id}"
        agent1 = AgentConfig(
            agent_id=agent1_id,
            type=AgentType.EXTERNAL,
            url=f"http://check-all-1-{unique_id}:8080",
            name="Check All 1",
            status=ExternalAgentStatus.ACTIVE,
        )
        agent2 = AgentConfig(
            agent_id=agent2_id,
            type=AgentType.EXTERNAL,
            url=f"http://check-all-2-{unique_id}:8080",
            name="Check All 2",
            status=ExternalAgentStatus.ACTIVE,
        )
        # Используем тот же репозиторий что и в discovery_service
        await discovery_service._repository.set(agent1)
        await discovery_service._repository.set(agent2)

        results = await discovery_service.health_check_all()

        assert agent1_id in results, f"Agent {agent1_id} not in results: {list(results.keys())[:10]}..."
        assert agent2_id in results, f"Agent {agent2_id} not in results: {list(results.keys())[:10]}..."
        assert results[agent1_id] is True
        assert results[agent2_id] is True

    @pytest.mark.asyncio
    async def test_init_from_config(self, discovery_service, mock_a2a_client, unique_id):
        """Инициализация из конфига."""
        url1 = f"http://config-agent-1-{unique_id}:8080"
        url2 = f"http://config-agent-2-{unique_id}:8080"
        configs = [
            ExternalAgentConfig(
                url=url1,
                auth_headers={"X-Key": "key1"},
                name="Config Agent 1",
            ),
            ExternalAgentConfig(
                url=url2,
                auth_headers={"X-Key": "key2"},
            ),
        ]

        count = await discovery_service.init_from_config(configs)

        assert count == 2

        agent1 = await discovery_service.get_agent_by_url(url1)
        assert agent1 is not None
        assert agent1.name == "Config Agent 1"

        agent2 = await discovery_service.get_agent_by_url(url2)
        assert agent2 is not None
        assert agent2.name == "Test Agent"

    @pytest.mark.asyncio
    async def test_init_from_config_partial_failure(self, discovery_service, mock_a2a_client, unique_id):
        """Инициализация из конфига с частичной ошибкой."""
        mock_a2a_client.get_agent_card.side_effect = [
            {"name": "OK Agent", "description": "OK"},
            Exception("Connection refused"),
        ]

        configs = [
            ExternalAgentConfig(url=f"http://ok-agent-{unique_id}:8080"),
            ExternalAgentConfig(url=f"http://fail-agent-{unique_id}:8080"),
        ]

        count = await discovery_service.init_from_config(configs)

        assert count == 1

    @pytest.mark.asyncio
    async def test_generate_agent_id(self, discovery_service):
        """Генерация ID агента из URL."""
        assert discovery_service._generate_agent_id("http://localhost:8080") == "localhost_8080"
        assert discovery_service._generate_agent_id("http://my-agent.local:9000") == "my_agent_local_9000"
        assert discovery_service._generate_agent_id("http://192.168.1.100:8080") == "192_168_1_100_8080"
        assert discovery_service._generate_agent_id("http://simple-host") == "simple_host_80"

