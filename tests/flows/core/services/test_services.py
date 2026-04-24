"""
Тесты для services (FlowFactory, flows_loader, FlowDiscoveryService).
"""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core.clients import A2AClient
from apps.flows.config import ExternalFlowConfig
from apps.flows.src.container import get_container
from core.db.repositories import Variable
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.models import ExternalAgentStatus, FlowConfig, FlowType
from apps.flows.src.services.flow_discovery import FlowDiscoveryService
from apps.flows.src.services.flow_factory import FlowFactory


class TestFlowFactory:
    """Тесты FlowFactory."""

    @pytest.mark.asyncio
    async def test_get_flow_from_db(self, app):
        """FlowFactory загружает flow из БД."""
        container = get_container()
        factory = container.flow_factory

        # Сохраняем flow в БД
        flow_config = FlowConfig(
            flow_id="test_factory_flow",
            name="Test Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Test prompt",
                    "next": None
                }
            },
        )
        await container.flow_repository.set(flow_config)

        # Получаем через factory
        flow = await factory.get_flow("test_factory_flow")

        assert flow is not None
        assert isinstance(flow, Flow)
        assert flow.flow_id == "test_factory_flow"

        # Cleanup
        await container.flow_repository.delete("test_factory_flow")

    @pytest.mark.asyncio
    async def test_get_flow_returns_none_for_missing(self, app):
        """FlowFactory возвращает None для несуществующего flow."""
        container = get_container()
        factory = container.flow_factory

        flow = await factory.get_flow("nonexistent_flow_xyz")

        assert flow is None

    @pytest.mark.asyncio
    async def test_flow_factory_resolves_variables(self, app):
        """FlowFactory резолвит @var:key в variables."""
        container = get_container()
        factory = container.flow_factory

        # Создаём переменную
        await container.variable_repository.set(
            Variable(key="factory_var", value="resolved!")
        )

        # Agent с @var:key
        flow_config = FlowConfig(
            flow_id="test_var_flow",
            name="Test Var Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Test",
                    "next": None
                }
            },
            variables={
                "test_var": "@var:factory_var",
                "static_var": "static_value"
            },
        )
        await container.flow_repository.set(flow_config)

        # Получаем flow - variables должны быть резолвнуты
        flow = await factory.get_flow("test_var_flow")

        assert flow.variables["test_var"] == "resolved!"
        assert flow.variables["static_var"] == "static_value"

        # Cleanup
        await container.flow_repository.delete("test_var_flow")
        await container.variable_repository.delete("factory_var")

    @pytest.mark.asyncio
    async def test_flow_factory_unresolved_var_is_none(self, app):
        """Нет company variable — в runtime variables попадает None, не строка @var:..."""
        container = get_container()
        factory = container.flow_factory

        flow_config = FlowConfig(
            flow_id="test_unresolved_var_flow",
            name="Test unresolved @var",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Test",
                    "next": None,
                }
            },
            variables={
                "only_ref": "@var:factory_nonexistent_key_xyz",
                "composite": "Bearer @var:factory_nonexistent_token_xyz",
                "literal": "ok",
            },
        )
        await container.flow_repository.set(flow_config)

        flow = await factory.get_flow("test_unresolved_var_flow")

        assert flow.variables["only_ref"] is None
        assert flow.variables["composite"] is None
        assert flow.variables["literal"] == "ok"

        await container.flow_repository.delete("test_unresolved_var_flow")

    @pytest.mark.asyncio
    async def test_create_flow_saves_to_db(self, app):
        """FlowFactory.create_flow сохраняет в БД."""
        container = get_container()
        factory = container.flow_factory

        flow_config = FlowConfig(
            flow_id="created_flow",
            name="Created Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Created",
                    "next": None
                }
            },
        )

        flow = await factory.create_flow(flow_config)

        assert flow is not None

        # Проверяем что сохранилось в БД
        loaded = await container.flow_repository.get("created_flow")
        assert loaded is not None

        # Cleanup
        await container.flow_repository.delete("created_flow")


class TestFlowsLoader:
    """Тесты flows_loader."""

    @pytest.mark.asyncio
    async def test_load_flows_to_db(self, app):
        """load_flows_to_db загружает flows и nodes из каталога bundles в БД."""
        from apps.flows.src.services.flows_loader import FlowsLoader

        container = get_container()
        repo_root = Path(__file__).parent.parent.parent.parent.parent
        bundles_dir = repo_root / "apps" / "flows" / "bundles"
        registry_path = repo_root / "apps" / "flows" / "registry.yaml"

        # Загружаем flows и nodes с явным указанием registry_path
        loader = FlowsLoader(
            bundles_dir=bundles_dir,
            flow_repository=container.flow_repository,
            node_repository=container.node_repository,
            tool_repository=container.tool_repository,
            registry_path=registry_path,
        )
        loaded_flows, loaded_nodes = await loader.load_all()

        assert len(loaded_flows) > 0
        assert isinstance(loaded_flows, list)

        # Проверяем что flows доступны в БД
        for flow_id in loaded_flows[:3]:  # Проверяем первые 3
            flow_config = await container.flow_repository.get(flow_id)
            assert flow_config is not None

        # Проверяем что nodes загружены (если есть nodes.json)
        if loaded_nodes:
            for node_id in loaded_nodes[:3]:
                node_config = await container.node_repository.get(node_id)
                assert node_config is not None

        if "telegram_demo" in loaded_flows:
            tg_flow = await container.flow_repository.get("telegram_demo")
            assert tg_flow is not None
            assert "tg_react" in tg_flow.triggers
            assert "tg_echo" in tg_flow.triggers
            assert tg_flow.triggers["tg_react"].skill_id == "react_skill"
            assert tg_flow.triggers["tg_echo"].skill_id == "echo_skill"

    @pytest.mark.asyncio
    async def test_load_tools_to_db(self, app):
        """load_tools_to_db загружает tools в БД."""
        from apps.flows.src.services.flows_loader import load_tools_to_db

        container = get_container()

        # Загружаем tools
        loaded = await load_tools_to_db(container.tool_repository)

        assert len(loaded) > 0

        # Проверяем calculator
        if "calculator" in loaded:
            tool = await container.tool_repository.get("calculator")
            assert tool is not None
            assert tool.parameters_schema is not None
            assert tool.parameters_schema.get("type") == "object"
            assert "properties" in tool.parameters_schema

        if "crm_search_entities" in loaded:
            crm_tool = await container.tool_repository.get("crm_search_entities")
            assert crm_tool is not None
            assert crm_tool.parameters_schema is not None
            props = crm_tool.parameters_schema.get("properties") or {}
            assert "query" in props
            assert "minimum" in props.get("limit", {})


class TestFlowDiscoveryService:
    """Тесты FlowDiscoveryService."""

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
        """FlowDiscoveryService с мок клиентом."""
        container = get_container()
        return FlowDiscoveryService(
            repository=container.flow_repository,
            a2a_client=mock_a2a_client,
        )

    @pytest.mark.asyncio
    async def test_register_agent(self, discovery_service, mock_a2a_client, unique_id):
        """Регистрация нового агента."""
        url = f"http://new-agent-{unique_id}:8080"
        registered = await discovery_service.register_agent(
            url=url,
            auth_headers={"Authorization": "Bearer token"},
            name="Custom Name",
        )

        assert registered is not None
        assert registered.name == "Custom Name"
        assert registered.url == url
        assert registered.auth_headers == {"Authorization": "Bearer token"}
        assert registered.status == ExternalAgentStatus.ACTIVE
        assert registered.agent_card["name"] == "Test Agent"

        mock_a2a_client.get_agent_card.assert_called_once_with(url, {"Authorization": "Bearer token"})

    @pytest.mark.asyncio
    async def test_register_agent_already_exists(self, discovery_service, mock_a2a_client, app, unique_id):
        """Регистрация уже существующего агента возвращает его."""
        container = get_container()
        flow_id = f"existing_{unique_id}"
        url = f"http://existing-{unique_id}:8080"
        existing = FlowConfig(
            flow_id=flow_id,
            type=FlowType.EXTERNAL,
            url=url,
            name="Existing",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.flow_repository.set(existing)

        same = await discovery_service.register_agent(url=url)

        assert same.flow_id == flow_id
        mock_a2a_client.get_agent_card.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_agent_uses_card_name(self, discovery_service, mock_a2a_client, unique_id):
        """Регистрация без имени использует имя из agent-card."""
        url = f"http://card-name-{unique_id}:8080"
        from_card = await discovery_service.register_agent(url=url)

        assert from_card.name == "Test Agent"

    @pytest.mark.asyncio
    async def test_unregister_agent(self, discovery_service, app, unique_id):
        """Удаление агента."""
        container = get_container()
        flow_id = f"unregister_{unique_id}"
        record = FlowConfig(
            flow_id=flow_id,
            type=FlowType.EXTERNAL,
            url=f"http://unregister-{unique_id}:8080",
            name="To Unregister",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.flow_repository.set(record)

        result = await discovery_service.unregister_agent(flow_id)
        assert result is True

        deleted = await container.flow_repository.get(flow_id)
        assert deleted is None

    @pytest.mark.asyncio
    async def test_get_agent(self, discovery_service, app, unique_id):
        """Получение агента по ID."""
        container = get_container()
        flow_id = f"get_{unique_id}"
        record = FlowConfig(
            flow_id=flow_id,
            type=FlowType.EXTERNAL,
            url=f"http://get-{unique_id}:8080",
            name="Get Test",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.flow_repository.set(record)

        found = await discovery_service.get_flow(flow_id)

        assert found is not None
        assert found.flow_id == flow_id

    @pytest.mark.asyncio
    async def test_get_agent_by_url(self, discovery_service, app, unique_id):
        """Получение агента по URL."""
        container = get_container()
        flow_id = f"url_{unique_id}"
        url = f"http://url-{unique_id}:8080"
        record = FlowConfig(
            flow_id=flow_id,
            type=FlowType.EXTERNAL,
            url=url,
            name="URL Test",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.flow_repository.set(record)

        found = await discovery_service.get_flow_by_url(f"{url}/")

        assert found is not None
        assert found.flow_id == flow_id

    @pytest.mark.asyncio
    async def test_list_agents_only_active(self, discovery_service, app, unique_id):
        """Список только активных агентов."""
        container = get_container()
        active_id = f"list_active_{unique_id}"
        inactive_id = f"list_inactive_{unique_id}"
        active = FlowConfig(
            flow_id=active_id,
            type=FlowType.EXTERNAL,
            url=f"http://list-active-{unique_id}:8080",
            name="Active",
            status=ExternalAgentStatus.ACTIVE,
        )
        inactive = FlowConfig(
            flow_id=inactive_id,
            type=FlowType.EXTERNAL,
            url=f"http://list-inactive-{unique_id}:8080",
            name="Inactive",
            status=ExternalAgentStatus.INACTIVE,
        )
        await container.flow_repository.set(active)
        await container.flow_repository.set(inactive)

        external_rows = await discovery_service.list_agents(only_active=True)
        flow_ids = [row.flow_id for row in external_rows]

        assert active_id in flow_ids
        assert inactive_id not in flow_ids

    @pytest.mark.asyncio
    async def test_list_agents_all(self, discovery_service, app, unique_id):
        """Список всех агентов."""
        container = get_container()
        active_id = f"all_active_{unique_id}"
        inactive_id = f"all_inactive_{unique_id}"
        active = FlowConfig(
            flow_id=active_id,
            type=FlowType.EXTERNAL,
            url=f"http://all-active-{unique_id}:8080",
            name="Active",
            status=ExternalAgentStatus.ACTIVE,
        )
        inactive = FlowConfig(
            flow_id=inactive_id,
            type=FlowType.EXTERNAL,
            url=f"http://all-inactive-{unique_id}:8080",
            name="Inactive",
            status=ExternalAgentStatus.INACTIVE,
        )
        await container.flow_repository.set(active)
        await container.flow_repository.set(inactive)

        external_rows = await discovery_service.list_agents(only_active=False)
        flow_ids = [row.flow_id for row in external_rows]

        assert active_id in flow_ids
        assert inactive_id in flow_ids

    @pytest.mark.asyncio
    async def test_health_check_agent_success(self, discovery_service, mock_a2a_client, app, unique_id):
        """Health check успешного агента."""
        container = get_container()
        flow_id = f"health_success_{unique_id}"
        record = FlowConfig(
            flow_id=flow_id,
            type=FlowType.EXTERNAL,
            url=f"http://health-success-{unique_id}:8080",
            name="Health Success",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.flow_repository.set(record)

        result = await discovery_service.health_check_agent(flow_id)

        assert result is True

        updated = await container.flow_repository.get(flow_id)
        assert updated.status == ExternalAgentStatus.ACTIVE
        assert updated.agent_card["name"] == "Test Agent"

    @pytest.mark.asyncio
    async def test_health_check_agent_failure(self, discovery_service, mock_a2a_client, app, unique_id):
        """Health check неудачного агента."""
        container = get_container()
        flow_id = f"health_fail_{unique_id}"
        record = FlowConfig(
            flow_id=flow_id,
            type=FlowType.EXTERNAL,
            url=f"http://health-fail-{unique_id}:8080",
            name="Health Fail",
            status=ExternalAgentStatus.ACTIVE,
        )
        await container.flow_repository.set(record)

        mock_a2a_client.get_agent_card.side_effect = Exception("Connection refused")

        result = await discovery_service.health_check_agent(flow_id)

        assert result is False

        updated = await container.flow_repository.get(flow_id)
        assert updated.status == ExternalAgentStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_health_check_agent_not_found(self, discovery_service, unique_id):
        """Health check несуществующего агента."""
        result = await discovery_service.health_check_agent(f"nonexistent_{unique_id}")
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_all(
        self, discovery_service, mock_a2a_client, app, unique_id, monkeypatch
    ):
        """Health check всех агентов."""
        # Используем короткие ID чтобы попасть в limit=100 при сортировке по алфавиту
        ext_id_a = f"a_check_1_{unique_id}"
        ext_id_b = f"a_check_2_{unique_id}"
        row_a = FlowConfig(
            flow_id=ext_id_a,
            type=FlowType.EXTERNAL,
            url=f"http://check-all-1-{unique_id}:8080",
            name="Check All 1",
            status=ExternalAgentStatus.ACTIVE,
        )
        row_b = FlowConfig(
            flow_id=ext_id_b,
            type=FlowType.EXTERNAL,
            url=f"http://check-all-2-{unique_id}:8080",
            name="Check All 2",
            status=ExternalAgentStatus.ACTIVE,
        )
        await discovery_service._repository.set(row_a)
        await discovery_service._repository.set(row_b)

        async def _list_only_test_flows(limit: int = 100):
            _ = limit
            persisted_a = await discovery_service._repository.get(ext_id_a)
            persisted_b = await discovery_service._repository.get(ext_id_b)
            if persisted_a is None or persisted_b is None:
                raise AssertionError("тестовые external flow не найдены в репозитории")
            return [persisted_a, persisted_b]

        monkeypatch.setattr(discovery_service._repository, "list", _list_only_test_flows)

        results = await discovery_service.health_check_all()

        assert ext_id_a in results, f"flow {ext_id_a} not in results: {list(results.keys())[:10]}..."
        assert ext_id_b in results, f"flow {ext_id_b} not in results: {list(results.keys())[:10]}..."
        assert results[ext_id_a] is True
        assert results[ext_id_b] is True

    @pytest.mark.asyncio
    async def test_init_from_config(self, discovery_service, mock_a2a_client, unique_id):
        """Инициализация из конфига."""
        url1 = f"http://config-agent-1-{unique_id}:8080"
        url2 = f"http://config-agent-2-{unique_id}:8080"
        configs = [
            ExternalFlowConfig(
                url=url1,
                auth_headers={"X-Key": "key1"},
                name="Config Agent 1",
            ),
            ExternalFlowConfig(
                url=url2,
                auth_headers={"X-Key": "key2"},
            ),
        ]

        count = await discovery_service.init_from_config(configs)

        assert count == 2

        first_registered = await discovery_service.get_flow_by_url(url1)
        assert first_registered is not None
        assert first_registered.name == "Config Agent 1"

        second_registered = await discovery_service.get_flow_by_url(url2)
        assert second_registered is not None
        assert second_registered.name == "Test Agent"

    @pytest.mark.asyncio
    async def test_init_from_config_partial_failure(self, discovery_service, mock_a2a_client, unique_id):
        """Инициализация из конфига с частичной ошибкой."""
        mock_a2a_client.get_agent_card.side_effect = [
            {"name": "OK Agent", "description": "OK"},
            Exception("Connection refused"),
        ]

        configs = [
            ExternalFlowConfig(url=f"http://ok-agent-{unique_id}:8080"),
            ExternalFlowConfig(url=f"http://fail-agent-{unique_id}:8080"),
        ]

        count = await discovery_service.init_from_config(configs)

        assert count == 1

    @pytest.mark.asyncio
    async def test_generate_flow_id(self, discovery_service):
        """Генерация flow_id из URL."""
        assert discovery_service._generate_flow_id("http://localhost:8080") == "localhost_8080"
        assert discovery_service._generate_flow_id("http://my-agent.local:9000") == "my_agent_local_9000"
        assert discovery_service._generate_flow_id("http://192.168.1.100:8080") == "192_168_1_100_8080"
        assert discovery_service._generate_flow_id("http://simple-host") == "simple_host_80"

