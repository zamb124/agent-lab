"""
Тесты для всех flows (агентов) в системе.

Каждый flow тестируется с mock LLM:
1. Загружается конфиг из БД (после инлайнинга через FlowsLoader)
2. Создаётся Agent
3. Выполняется с mock ответом
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.runtime.flow import Flow
from core.clients.llm import setup_mock_responses
from core.state import ExecutionState

# Базовая директория агентов
AGENTS_DIR = Path(__file__).parent.parent.parent.parent / "apps" / "flows" / "bundles"

# Agents с особой логикой - тестируются отдельно
SKIP_FLOWS = {"example_external"}


def _get_agent_id(config: Dict[str, Any]) -> Optional[str]:
    """Возвращает ID агента из конфига (поддерживает 'id' и 'flow_id')."""
    return config.get("id") or config.get("flow_id")


def get_all_flow_ids() -> List[str]:
    """Получает список ID всех flows из файлов agent.json."""
    flow_ids = []
    for flow_dir in AGENTS_DIR.iterdir():
        if flow_dir.is_dir() and not flow_dir.name.startswith("_"):
            flow_json = flow_dir / "agent.json"
            if flow_json.exists():
                with open(flow_json) as f:
                    config = json.load(f)
                    flow_id = _get_agent_id(config)
                    if flow_id and flow_id not in SKIP_FLOWS:
                        flow_ids.append(flow_id)
    return flow_ids


def get_all_agent_configs_from_files() -> List[Dict[str, Any]]:
    """Загружает все agent.json напрямую из файлов (для проверки prompt_file)."""
    configs = []
    for flow_dir in AGENTS_DIR.iterdir():
        if flow_dir.is_dir() and not flow_dir.name.startswith("_"):
            flow_json = flow_dir / "agent.json"
            if flow_json.exists():
                with open(flow_json) as f:
                    config = json.load(f)
                    flow_id = _get_agent_id(config)
                    if flow_id and flow_id not in SKIP_FLOWS:
                        config["_path"] = str(flow_json)
                        configs.append(config)
    return configs


FLOW_IDS = get_all_flow_ids()
ALL_FLOWS_FROM_FILES = get_all_agent_configs_from_files()


class TestAllFlowConfigs:
    """Тесты конфигурации всех flows из БД (с инлайнингом)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("flow_id", FLOW_IDS)
    async def test_flow_creates_from_config(self, flow_id: str, app):
        """Agent создаётся из конфига в БД без ошибок."""
        container = get_container()
        config = await container.flow_repository.get(flow_id)

        assert config is not None, f"Agent {flow_id} не загружен в БД"

        # Конвертируем FlowConfig в dict для Flow.from_config
        config_dict = {
            "id": config.flow_id,
            "name": config.name,
            "description": config.description or "",
            "tags": config.tags,
            "entry": config.entry,
            "nodes": config.nodes,
            "edges": [{"from": e.from_node, "to": e.to_node, "condition": e.condition} for e in config.edges],
        }

        flow = await Flow.from_config(config_dict)
        assert flow.flow_id == config.flow_id
        assert flow.name == config.name

    @pytest.mark.asyncio
    @pytest.mark.parametrize("flow_id", FLOW_IDS)
    async def test_flow_nodes_have_valid_types(self, flow_id: str, app):
        """Все ноды имеют валидный тип."""
        container = get_container()
        config = await container.flow_repository.get(flow_id)

        assert config is not None, f"Agent {flow_id} не загружен в БД"

        from apps.flows.src.models.enums import NodeType
        valid_types = {t.value for t in NodeType}
        for node_id, node_config in config.nodes.items():
            node_type = node_config.get("type", "llm_node")
            assert node_type in valid_types, f"Invalid type '{node_type}' in node '{node_id}'"


class TestAllFlowsExecution:
    """Тесты выполнения всех flows с mock LLM."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("flow_id", FLOW_IDS)
    async def test_flow_executes_with_mock_llm(self, flow_id: str, app):
        """Agent выполняется с mock LLM и возвращает ответ."""
        container = get_container()
        config = await container.flow_repository.get(flow_id)

        assert config is not None, f"Agent {flow_id} не загружен в БД"

        # Настраиваем mock LLM
        expected_response = f"Mock response for {config.name}"
        setup_mock_responses(default_response=expected_response)

        # Получаем flow из БД (где уже загружены промпты и инлайнены tools)
        flow = await container.flow_factory.get_flow(flow_id)

        assert flow is not None, f"Agent {flow_id} не загружен в БД (flow_factory.get_flow)"

        # Выполняем
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Тестовый запрос",
            messages=[]
        )
        result = await flow.run(state)

        # Проверяем что flow завершился
        assert result is not None
        assert result.get("current_node") is not None or result.get("node_history")
        # Agent с llm_node должен вернуть response
        if "response" in result:
            assert result["response"] is not None


class TestFlowPromptFiles:
    """Тесты что все prompt_file существуют."""

    @pytest.mark.parametrize("config", ALL_FLOWS_FROM_FILES, ids=FLOW_IDS)
    def test_prompt_files_exist(self, config: Dict[str, Any]):
        """Все prompt_file из конфига существуют."""
        flow_path = Path(config["_path"]).parent

        for node_id, node_config in config["nodes"].items():
            prompt_file = node_config.get("prompt_file")
            if prompt_file:
                full_path = flow_path / prompt_file
                assert full_path.exists(), f"Prompt file not found: {full_path}"

    @pytest.mark.parametrize("config", ALL_FLOWS_FROM_FILES, ids=FLOW_IDS)
    def test_prompt_files_not_empty(self, config: Dict[str, Any]):
        """Все prompt файлы не пустые."""
        flow_path = Path(config["_path"]).parent

        for node_id, node_config in config["nodes"].items():
            prompt_file = node_config.get("prompt_file")
            if prompt_file:
                full_path = flow_path / prompt_file
                content = full_path.read_text()
                assert len(content.strip()) > 0, f"Empty prompt file: {full_path}"

