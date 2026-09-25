"""
Тесты для services (FlowFactory, flows_loader, FlowDiscoveryService).
"""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from apps.flows.config import ExternalFlowConfig
from apps.flows.src.models import (
    ExternalAgentStatus,
    FlowConfig,
    FlowType,
    NodeConfig,
    ToolReference,
)
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.services.flow_discovery import FlowDiscoveryService
from core.clients.a2a_client import A2AClient
from tests.fixtures.variables_helpers import (
    delete_variable_via_service,
    upsert_static_variable_via_service,
)


class TestFlowFactory:
    """Тесты FlowFactory."""

    @pytest.mark.asyncio
    async def test_get_flow_from_db(self, app, di):
        """FlowFactory загружает flow из БД."""
        factory = di.flow_factory

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
        await FlowConfig.create_version(flow_config)

        # Получаем через factory
        flow = await factory.get_flow("test_factory_flow", tool_registry=di.tool_registry)

        assert flow is not None
        assert isinstance(flow, Flow)
        assert flow.flow_id == "test_factory_flow"

        # Cleanup
        await FlowConfig.delete_by_flow_id("test_factory_flow")

    @pytest.mark.asyncio
    async def test_get_flow_returns_none_for_missing(self, app, di):
        """FlowFactory возвращает None для несуществующего flow."""
        factory = di.flow_factory

        flow = await factory.get_flow("nonexistent_flow_xyz", tool_registry=di.tool_registry)

        assert flow is None

    @pytest.mark.asyncio
    async def test_flow_factory_resolves_variables(self, app, di):
        """FlowFactory резолвит @var:key в variables."""
        factory = di.flow_factory

        # Создаём переменную
        await upsert_static_variable_via_service(di, "factory_var", "resolved!")

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
        await FlowConfig.create_version(flow_config)

        # Получаем flow - variables должны быть резолвнуты
        flow = await factory.get_flow("test_var_flow", tool_registry=di.tool_registry)
        assert flow is not None

        assert flow.variables["test_var"] == "resolved!"
        assert flow.variables["static_var"] == "static_value"

        # Cleanup
        await FlowConfig.delete_by_flow_id("test_var_flow")
        await delete_variable_via_service(di, "factory_var")

    @pytest.mark.asyncio
    async def test_flow_factory_unresolved_var_is_none(self, app, di):
        """Нет company variable — в runtime variables попадает None, не строка @var:..."""
        factory = di.flow_factory

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
        await FlowConfig.create_version(flow_config)

        flow = await factory.get_flow(
            "test_unresolved_var_flow", tool_registry=di.tool_registry
        )
        assert flow is not None

        assert flow.variables["only_ref"] is None
        assert flow.variables["composite"] is None
        assert flow.variables["literal"] == "ok"

        await FlowConfig.delete_by_flow_id("test_unresolved_var_flow")

    @pytest.mark.asyncio
    async def test_create_flow_saves_to_db(self, app, di):
        """FlowFactory.create_flow сохраняет в БД."""
        factory = di.flow_factory

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

        flow = await factory.create_flow(flow_config, tool_registry=di.tool_registry)

        assert flow is not None

        # Проверяем что сохранилось в БД
        loaded = await FlowConfig.get_latest("created_flow")
        assert loaded is not None

        # Cleanup
        await FlowConfig.delete_by_flow_id("created_flow")


class TestFlowsLoader:
    """Тесты flows_loader."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_load_flows_to_db(self, app, di):
        """load_flows_to_db загружает flows и nodes из каталога bundles в БД."""
        from apps.flows.src.services.flows_loader import FlowsLoader

        repo_root = Path(__file__).parent.parent.parent.parent.parent
        bundles_dir = repo_root / "apps" / "flows" / "bundles"
        registry_path = repo_root / "apps" / "flows" / "registry.yaml"

        # Загружаем flows и nodes с явным указанием registry_path
        loader = FlowsLoader(
            bundles_dir=bundles_dir,
            registry_path=registry_path,
            flow_access_service=di.flow_access_service,
        )
        loaded_flows, loaded_nodes = await loader.load_all()

        assert len(loaded_flows) > 0
        assert isinstance(loaded_flows, list)

        # Проверяем что flows доступны в БД
        for flow_id in loaded_flows[:3]:  # Проверяем первые 3
            flow_config = await FlowConfig.get_latest(flow_id)
            assert flow_config is not None

        # Проверяем что nodes загружены (если есть nodes.json)
        if loaded_nodes:
            for node_id in loaded_nodes[:3]:
                node_config = await NodeConfig.get(NodeConfig.row_id(node_id))
                assert node_config is not None

        if "telegram_demo" in loaded_flows:
            tg_flow = await FlowConfig.get_latest("telegram_demo")
            assert tg_flow is not None
            assert "tg_react" in tg_flow.triggers
            assert "tg_echo" in tg_flow.triggers
            assert tg_flow.triggers["tg_react"].branch_id == "react_skill"
            assert tg_flow.triggers["tg_echo"].branch_id == "echo_skill"

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_load_tools_to_db(self, app, di):
        """load_tools_to_db загружает tools в БД."""
        from apps.flows.src.services.flows_loader import load_tools_to_db


        # Загружаем tools
        loaded = await load_tools_to_db(
            flow_access_service=di.flow_access_service,
        )

        assert len(loaded) > 0

        # Проверяем calculator
        if "calculator" in loaded:
            tool = await ToolReference.get(ToolReference.row_id("calculator"))
            assert tool is not None
            assert isinstance(tool.code, str) and "async def calculator" in tool.code
            assert tool.parameters_schema is not None
            assert tool.parameters_schema.get("type") == "object"
            assert "properties" in tool.parameters_schema

        if "crm_search_entities" in loaded:
            crm_tool = await ToolReference.get(ToolReference.row_id("crm_search_entities"))
            assert crm_tool is not None
            assert isinstance(crm_tool.code, str) and "async def crm_search_entities" in crm_tool.code
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
                "branches": [{"id": "default", "name": "Default Skill"}],
            }
        )
        return client

    @pytest.fixture
    async def discovery_service(self, app, mock_a2a_client):
        """FlowDiscoveryService с мок клиентом."""
        _ = app
        return FlowDiscoveryService(a2a_client=mock_a2a_client)

    @pytest.mark.asyncio
    async def test_register_agent(self, discovery_service, mock_a2a_client, unique_id):
        """Регистрация нового агента."""
        url = f"http://new-agent-{unique_id}:8080"
        registered = await discovery_service.register_agent(
            url=url,
            headers={"Authorization": "Bearer token"},
            name="Custom Name",
        )

        assert registered is not None
        assert registered.name == "Custom Name"
        assert registered.url == url
        assert registered.headers == {"Authorization": "Bearer token"}
        assert registered.status == ExternalAgentStatus.ACTIVE
        assert registered.agent_card["name"] == "Test Agent"

        mock_a2a_client.get_agent_card.assert_called_once_with(url, {"Authorization": "Bearer token"})

    @pytest.mark.asyncio
    async def test_register_agent_already_exists(self, discovery_service, mock_a2a_client, app, unique_id, di):
        """Регистрация уже существующего агента возвращает его."""
        flow_id = f"existing_{unique_id}"
        url = f"http://existing-{unique_id}:8080"
        existing = FlowConfig(
            flow_id=flow_id,
            type=FlowType.EXTERNAL,
            url=url,
            name="Existing",
            status=ExternalAgentStatus.ACTIVE,
        )
        await FlowConfig.create_version(existing)

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
    async def test_unregister_agent(self, discovery_service, app, unique_id, di):
        """Удаление агента."""
        flow_id = f"unregister_{unique_id}"
        record = FlowConfig(
            flow_id=flow_id,
            type=FlowType.EXTERNAL,
            url=f"http://unregister-{unique_id}:8080",
            name="To Unregister",
            status=ExternalAgentStatus.ACTIVE,
        )
        await FlowConfig.create_version(record)

        result = await discovery_service.unregister_agent(flow_id)
        assert result is True

        deleted = await FlowConfig.get_latest(flow_id)
        assert deleted is None

    @pytest.mark.asyncio
    async def test_get_agent(self, discovery_service, app, unique_id, di):
        """Получение агента по ID."""
        flow_id = f"get_{unique_id}"
        record = FlowConfig(
            flow_id=flow_id,
            type=FlowType.EXTERNAL,
            url=f"http://get-{unique_id}:8080",
            name="Get Test",
            status=ExternalAgentStatus.ACTIVE,
        )
        await FlowConfig.create_version(record)

        found = await discovery_service.get_flow(flow_id)

        assert found is not None
        assert found.flow_id == flow_id

    @pytest.mark.asyncio
    async def test_get_agent_by_url(self, discovery_service, app, unique_id, di):
        """Получение агента по URL."""
        flow_id = f"url_{unique_id}"
        url = f"http://url-{unique_id}:8080"
        record = FlowConfig(
            flow_id=flow_id,
            type=FlowType.EXTERNAL,
            url=url,
            name="URL Test",
            status=ExternalAgentStatus.ACTIVE,
        )
        await FlowConfig.create_version(record)

        found = await discovery_service.get_flow_by_url(f"{url}/")

        assert found is not None
        assert found.flow_id == flow_id

    @pytest.mark.asyncio
    async def test_list_agents_only_active(self, discovery_service, app, unique_id, di):
        """Список только активных агентов."""
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
        await FlowConfig.create_version(active)
        await FlowConfig.create_version(inactive)

        external_rows = await discovery_service.list_agents(only_active=True)
        flow_ids = [row.flow_id for row in external_rows]

        assert active_id in flow_ids
        assert inactive_id not in flow_ids

    @pytest.mark.asyncio
    async def test_list_agents_all(self, discovery_service, app, unique_id, di):
        """Список всех агентов."""
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
        await FlowConfig.create_version(active)
        await FlowConfig.create_version(inactive)

        external_rows = await discovery_service.list_agents(only_active=False)
        flow_ids = [row.flow_id for row in external_rows]

        assert active_id in flow_ids
        assert inactive_id in flow_ids

    @pytest.mark.asyncio
    async def test_health_check_agent_success(self, discovery_service, mock_a2a_client, app, unique_id, di):
        """Health check успешного агента."""
        flow_id = f"health_success_{unique_id}"
        record = FlowConfig(
            flow_id=flow_id,
            type=FlowType.EXTERNAL,
            url=f"http://health-success-{unique_id}:8080",
            name="Health Success",
            status=ExternalAgentStatus.ACTIVE,
        )
        await FlowConfig.create_version(record)

        result = await discovery_service.health_check_agent(flow_id)

        assert result is True

        updated = await FlowConfig.get_latest(flow_id)
        assert updated is not None
        assert updated.status == ExternalAgentStatus.ACTIVE
        assert updated.agent_card is not None
        assert updated.agent_card["name"] == "Test Agent"

    @pytest.mark.asyncio
    async def test_health_check_agent_failure(self, discovery_service, mock_a2a_client, app, unique_id, di):
        """Health check неудачного агента."""
        flow_id = f"health_fail_{unique_id}"
        record = FlowConfig(
            flow_id=flow_id,
            type=FlowType.EXTERNAL,
            url=f"http://health-fail-{unique_id}:8080",
            name="Health Fail",
            status=ExternalAgentStatus.ACTIVE,
        )
        await FlowConfig.create_version(record)

        mock_a2a_client.get_agent_card.side_effect = Exception("Connection refused")

        result = await discovery_service.health_check_agent(flow_id)

        assert result is False

        updated = await FlowConfig.get_latest(flow_id)
        assert updated is not None
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
        await FlowConfig.create_version(row_a)
        await FlowConfig.create_version(row_b)

        async def _list_only_test_flows(*, limit: int, offset: int = 0) -> list[FlowConfig]:
            _ = limit, offset
            persisted_a = await FlowConfig.get_latest(ext_id_a)
            persisted_b = await FlowConfig.get_latest(ext_id_b)
            if persisted_a is None or persisted_b is None:
                raise AssertionError("тестовые external flow не найдены")
            return [persisted_a, persisted_b]

        monkeypatch.setattr(FlowConfig, "list_current", _list_only_test_flows)

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
                headers={"X-Key": "key1"},
                name="Config Agent 1",
            ),
            ExternalFlowConfig(
                url=url2,
                headers={"X-Key": "key2"},
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
