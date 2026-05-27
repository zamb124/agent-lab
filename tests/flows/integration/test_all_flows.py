"""
Тесты для всех flows (агентов) в системе.

Каждый flow тестируется с mock LLM:
1. Загружается конфиг из БД (после инлайнинга через FlowsLoader)
2. Создаётся Agent
3. Выполняется с mock ответом
"""

import uuid
from pathlib import Path

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.runtime.flow import Flow
from core.clients.llm import setup_mock_responses
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object
from tests.flows.durable_runtime_harness import run_flow, workflow_state

# Базовая директория агентов
AGENTS_DIR = Path(__file__).parent.parent.parent.parent / "apps" / "flows" / "bundles"

# Agents с особой логикой - тестируются отдельно
SKIP_FLOWS = {"example_external"}
SIDE_EFFECT_NODE_TYPES = {"channel", "external_api", "flow", "mcp", "remote_flow"}
EXTERNAL_TOOL_PREFIXES = (
    "browser_",
    "crm_",
    "gdocs_",
    "mcp:",
    "pravo_",
    "rag_",
    "schedule_",
)
EXTERNAL_TOOL_IDS = {"send_telegram"}
EXTERNAL_CODE_TOKENS = (
    "tools.browser_",
    "tools.rag_",
    "tools.pravo_",
    "tools.gdocs_",
    "tools.crm_",
    "tools.schedule_",
    "platform.request",
    "http.request",
    "channel.send",
)
FORBIDDEN_SANDBOX_CODE_TOKENS = (
    "from core.",
    "import core",
    "from apps.",
    "import apps",
    "RagClient",
    "BrowserSnapshotDescribe",
    "DuckDuckGoBrowserSearch",
    "getattr(",
)


def _get_flow_id(config: JsonObject) -> str | None:
    """Возвращает flow_id из строгого bundle config."""
    flow_id = config.get("flow_id")
    return flow_id if isinstance(flow_id, str) and flow_id else None


def _load_flow_json(flow_json: Path) -> JsonObject:
    return parse_json_object(flow_json.read_text(encoding="utf-8"), str(flow_json))


def get_all_flow_ids() -> list[str]:
    """Получает список ID всех flows из файлов flow.json."""
    flow_ids: list[str] = []
    for flow_dir in AGENTS_DIR.iterdir():
        if flow_dir.is_dir() and not flow_dir.name.startswith("_"):
            flow_json = flow_dir / "flow.json"
            if flow_json.exists():
                config = _load_flow_json(flow_json)
                flow_id = _get_flow_id(config)
                if flow_id and flow_id not in SKIP_FLOWS:
                    flow_ids.append(flow_id)
    return flow_ids


def get_all_agent_configs_from_files() -> list[JsonObject]:
    """Загружает все flow.json напрямую из файлов."""
    configs: list[JsonObject] = []
    for flow_dir in AGENTS_DIR.iterdir():
        if flow_dir.is_dir() and not flow_dir.name.startswith("_"):
            flow_json = flow_dir / "flow.json"
            if flow_json.exists():
                config = _load_flow_json(flow_json)
                flow_id = _get_flow_id(config)
                if flow_id and flow_id not in SKIP_FLOWS:
                    config["_path"] = str(flow_json)
                    configs.append(config)
    return configs


FLOW_IDS = get_all_flow_ids()
ALL_FLOWS_FROM_FILES = get_all_agent_configs_from_files()


def _tool_id(raw_tool: JsonValue) -> str | None:
    if isinstance(raw_tool, str):
        return raw_tool
    if isinstance(raw_tool, dict):
        raw_tool_id = raw_tool.get("tool_id") or raw_tool.get("name")
        return raw_tool_id if isinstance(raw_tool_id, str) else None
    return None


def _tool_requires_external_runtime(tool_id: str) -> bool:
    return tool_id in EXTERNAL_TOOL_IDS or any(
        tool_id.startswith(prefix) for prefix in EXTERNAL_TOOL_PREFIXES
    )


def _flow_nodes(config: JsonObject) -> JsonObject:
    nodes = config.get("nodes")
    if not isinstance(nodes, dict):
        raise AssertionError("flow.nodes must be an object")
    return require_json_object(nodes, "flow.nodes")


def _flow_external_requirements(config: JsonObject) -> list[str]:
    try:
        nodes = _flow_nodes(config)
    except AssertionError:
        return ["nodes:missing"]

    requirements: set[str] = set()
    for node_id, raw_node in nodes.items():
        if not isinstance(raw_node, dict):
            requirements.add(f"{node_id}:invalid_node")
            continue
        node_type = raw_node.get("type")
        if isinstance(node_type, str) and node_type in SIDE_EFFECT_NODE_TYPES:
            requirements.add(f"{node_id}:node:{node_type}")

        code = raw_node.get("code")
        if isinstance(code, str) and any(token in code for token in EXTERNAL_CODE_TOKENS):
            requirements.add(f"{node_id}:code_capability")

        raw_tools = raw_node.get("tools")
        if isinstance(raw_tools, list):
            for raw_tool in raw_tools:
                tool_id = _tool_id(raw_tool)
                if tool_id is not None and _tool_requires_external_runtime(tool_id):
                    requirements.add(f"{node_id}:tool:{tool_id}")
                if isinstance(raw_tool, dict):
                    tool_code = raw_tool.get("code")
                    if isinstance(tool_code, str) and any(
                        token in tool_code for token in EXTERNAL_CODE_TOKENS
                    ):
                        requirements.add(f"{node_id}:tool_code_capability:{tool_id}")
    return sorted(requirements)


EXTERNAL_REQUIREMENTS_BY_FLOW = {
    flow_id: requirements
    for config in ALL_FLOWS_FROM_FILES
    if (flow_id := _get_flow_id(config)) is not None
    if (requirements := _flow_external_requirements(config))
}
EXECUTABLE_FLOW_IDS = [
    flow_id for flow_id in FLOW_IDS if flow_id not in EXTERNAL_REQUIREMENTS_BY_FLOW
]


def _iter_sandbox_code(config: JsonObject) -> list[tuple[str, str]]:
    try:
        nodes = _flow_nodes(config)
    except AssertionError:
        return []

    snippets: list[tuple[str, str]] = []
    for node_id, raw_node in nodes.items():
        if not isinstance(raw_node, dict):
            continue
        code = raw_node.get("code")
        if isinstance(code, str):
            snippets.append((node_id, code))
        raw_tools = raw_node.get("tools")
        if isinstance(raw_tools, list):
            for raw_tool in raw_tools:
                if not isinstance(raw_tool, dict):
                    continue
                tool_id = _tool_id(raw_tool) or "<unknown>"
                tool_code = raw_tool.get("code")
                if isinstance(tool_code, str):
                    snippets.append((f"{node_id}.tool.{tool_id}", tool_code))
    return snippets


class TestAllFlowConfigs:
    """Тесты конфигурации всех flows из БД (с инлайнингом)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("flow_id", FLOW_IDS)
    async def test_flow_creates_from_config(self, flow_id: str, app: object):
        """Agent создаётся из конфига в БД без ошибок."""
        _ = app
        container = get_container()
        config = await container.flow_repository.get(flow_id)

        assert config is not None, f"Agent {flow_id} не загружен в БД"

        # Конвертируем FlowConfig в dict для Flow.from_config
        config_dict = {
            "flow_id": config.flow_id,
            "name": config.name,
            "description": config.description or "",
            "tags": config.tags,
            "entry": config.entry,
            "nodes": config.nodes,
            "edges": [
                {
                    "from_node": e.from_node,
                    "to_node": e.to_node,
                    "condition": (
                        e.condition.model_dump(mode="json") if e.condition is not None else None
                    ),
                }
                for e in config.edges
            ],
        }

        flow = await Flow.from_config(config_dict, container=container)
        assert flow.flow_id == config.flow_id
        assert flow.name == config.name

    @pytest.mark.asyncio
    @pytest.mark.parametrize("flow_id", FLOW_IDS)
    async def test_flow_nodes_have_valid_types(self, flow_id: str, app: object):
        """Все ноды имеют валидный тип."""
        _ = app
        container = get_container()
        config = await container.flow_repository.get(flow_id)

        assert config is not None, f"Agent {flow_id} не загружен в БД"
        assert config.nodes is not None, f"Agent {flow_id} must define nodes"

        from apps.flows.src.models.enums import NodeType
        valid_types = {t.value for t in NodeType}
        for node_id, node_config in config.nodes.items():
            node_type = node_config.get("type")
            assert isinstance(node_type, str), f"Node '{node_id}' must define type"
            assert node_type in valid_types, f"Invalid type '{node_type}' in node '{node_id}'"


class TestAllFlowsExecution:
    """Тесты выполнения самодостаточных flows с test LLM."""

    def test_external_execution_contract_is_explicit(self):
        """Flows с внешними side effects не попадают в generic execution smoke."""
        assert EXECUTABLE_FLOW_IDS
        assert "psychologist_assistant" in EXTERNAL_REQUIREMENTS_BY_FLOW
        assert "simple_crawler" in EXTERNAL_REQUIREMENTS_BY_FLOW

    @pytest.mark.asyncio
    @pytest.mark.parametrize("flow_id", EXECUTABLE_FLOW_IDS)
    async def test_flow_executes_with_mock_llm(self, flow_id: str, app: object):
        """Самодостаточный flow выполняется с test LLM и возвращает ответ."""
        _ = app
        container = get_container()
        config = await container.flow_repository.get(flow_id)

        assert config is not None, f"Agent {flow_id} не загружен в БД"

        # Настраиваем mock LLM
        expected_response = f"Mock response for {config.name}"
        _ = setup_mock_responses(default_response=expected_response)

        # Получаем flow из БД (где уже загружены промпты и инлайнены tools)
        flow = await container.flow_factory.get_flow(flow_id)

        assert flow is not None, f"Agent {flow_id} не загружен в БД (flow_factory.get_flow)"

        state = workflow_state(
            flow_id=flow_id,
            unique_id=uuid.uuid4().hex,
            content="Тестовый запрос",
            messages=[],
        )
        result = await run_flow(container=container, flow=flow, state=state)

        # Проверяем что flow завершился
        assert result is not None
        assert result.get("current_node") is not None or result.get("node_history")
        # Agent с llm_node должен вернуть response
        if "response" in result:
            assert result["response"] is not None


class TestFlowPromptContract:
    """Тесты строгого inline prompt-контракта."""

    @pytest.mark.parametrize("config", ALL_FLOWS_FROM_FILES, ids=FLOW_IDS)
    def test_sandbox_code_uses_capability_sdk(self, config: JsonObject):
        """Inline sandbox code не импортирует platform internals."""
        for code_id, code in _iter_sandbox_code(config):
            for token in FORBIDDEN_SANDBOX_CODE_TOKENS:
                assert token not in code, f"{code_id}: forbidden sandbox token {token!r}"

    @pytest.mark.parametrize("config", ALL_FLOWS_FROM_FILES, ids=FLOW_IDS)
    def test_prompt_file_is_forbidden(self, config: JsonObject):
        """node.prompt_file запрещен; bundle хранит готовый node.prompt."""
        for node_id, node_config in _flow_nodes(config).items():
            assert isinstance(node_config, dict), f"{node_id}: node config must be object"
            assert "prompt_file" not in node_config, f"{node_id}: prompt_file is forbidden"

    @pytest.mark.parametrize("config", ALL_FLOWS_FROM_FILES, ids=FLOW_IDS)
    def test_inline_prompts_not_empty(self, config: JsonObject):
        """Inline prompt не пустой у prompt-driven нод."""
        for node_id, node_config in _flow_nodes(config).items():
            assert isinstance(node_config, dict), f"{node_id}: node config must be object"
            prompt = node_config.get("prompt")
            if prompt is not None:
                assert isinstance(prompt, str)
                assert len(prompt.strip()) > 0, f"{node_id}: empty inline prompt"
