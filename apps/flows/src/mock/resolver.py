"""
MockResolver - резолвер mock конфигурации.

Мержит mock конфиги из всех уровней иерархии.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from apps.flows.config import get_settings
from core.config.testing import is_testing as is_testing_env
from core.logging import get_logger
from core.types import JsonObject, JsonValue, require_json_object

from .config import MockConfig

if TYPE_CHECKING:
    from core.state import ExecutionState

logger = get_logger(__name__)


def _mock_mapping_section(mock_config: Mapping[str, JsonValue], key: str) -> Mapping[str, JsonValue]:
    section = mock_config.get(key, {})
    return cast(Mapping[str, JsonValue], section) if isinstance(section, Mapping) else {}


def resolve_mock_config(
    global_mock: JsonObject | None = None,
    flow_mock: JsonObject | None = None,
    skill_mock: JsonObject | None = None,
    request_mock: JsonObject | None = None,
) -> MockConfig:
    """
    Резолвит итоговый mock конфиг с учётом иерархии.

    Приоритет (от низшего к высшему):
    1. global_mock (conf.json)
    2. flow_mock (уровень flow в flow.json / состоянии)
    3. skill_mock (skill во flow)
    4. request_mock (metadata.mock)

    Args:
        global_mock: Mock из глобального конфига
        flow_mock: Mock уровня flow (flow.json / состояние)
        skill_mock: Mock из skill конфига
        request_mock: Mock из metadata запроса

    Returns:
        Итоговый MockConfig
    """
    result: JsonObject = {
        "enabled": False,
        "llm": None,
        "tools": {},
        "flows": {},
        "nodes": {},
        "permission_groups": ["admin", "developers"],
    }

    # Мерж в порядке приоритета
    for mock_dict in [global_mock, flow_mock, skill_mock, request_mock]:
        if mock_dict:
            _merge_mock(result, mock_dict)

    return MockConfig.model_validate(result)


def _merge_mock(target: JsonObject, source: JsonObject) -> None:
    """
    Мержит source mock в target.

    - enabled: замена
    - llm: замена целиком (не мерж)
    - tools/flows/nodes: update (мерж); устаревший ключ agents мержится в flows
    - permission_groups: замена
    """
    if "enabled" in source:
        target["enabled"] = source["enabled"]

    # LLM: полная замена если указан
    if "llm" in source and source["llm"] is not None:
        target["llm"] = source["llm"]

    # Tools: мерж
    if "tools" in source and source["tools"]:
        tools = require_json_object(target["tools"], "mock.tools")
        tools.update(require_json_object(source["tools"], "mock.tools"))
        target["tools"] = tools

    if "flows" in source and source["flows"]:
        flows = require_json_object(target["flows"], "mock.flows")
        flows.update(require_json_object(source["flows"], "mock.flows"))
        target["flows"] = flows
    if "agents" in source and source["agents"]:
        flows = require_json_object(target["flows"], "mock.flows")
        flows.update(require_json_object(source["agents"], "mock.agents"))
        target["flows"] = flows

    # Nodes: мерж
    if "nodes" in source and source["nodes"]:
        nodes = require_json_object(target["nodes"], "mock.nodes")
        nodes.update(require_json_object(source["nodes"], "mock.nodes"))
        target["nodes"] = nodes

    # Замена групп разрешений
    if "permission_groups" in source:
        target["permission_groups"] = source["permission_groups"]


def is_mock_enabled(state_dict: JsonObject | None = None) -> bool:
    """
    Проверяет включен ли mock режим.

    Args:
        state_dict: State dict (from ExecutionState.model_dump(exclude_none=False))

    Returns:
        True если mock режим включен
    """
    if state_dict:
        raw_mock_config = state_dict.get("mock")
        mock_config = (
            require_json_object(raw_mock_config, "state.mock")
            if raw_mock_config is not None
            else None
        )
        if mock_config and mock_config.get("enabled"):
            return True

    return is_testing_env()


def get_mock_for_tool(state: ExecutionState | None, tool_id: str) -> JsonValue | None:
    """
    Получает mock ответ для tool.

    Args:
        state: ExecutionState
        tool_id: ID инструмента

    Returns:
        Mock ответ или None
    """
    if not state:
        return None

    mock_config = require_json_object(state.mock, "state.mock") if state.mock else None
    if not mock_config or not mock_config.get("enabled"):
        return None

    tools = _mock_mapping_section(mock_config, "tools")
    if tool_id in tools:
        logger.debug(f"Mock для tool '{tool_id}' найден")
        return tools[tool_id]

    return None


def get_mock_for_flow(state: ExecutionState | None, flow_id: str) -> JsonValue | None:
    """
    Получает mock ответ для вложенного flow.

    Args:
        state: ExecutionState
        flow_id: ID flow

    Returns:
        Mock ответ или None
    """
    if not state:
        return None

    mock_config = require_json_object(state.mock, "state.mock") if state.mock else None
    if not mock_config or not mock_config.get("enabled"):
        return None

    flows = _mock_mapping_section(mock_config, "flows")
    if flow_id in flows:
        logger.debug(f"Mock для flow '{flow_id}' найден")
        return flows[flow_id]

    return None


def get_mock_for_node(state: ExecutionState | None, node_id: str) -> JsonObject | None:
    """
    Получает mock данные для ноды.

    Args:
        state: ExecutionState
        node_id: ID ноды

    Returns:
        Dict или None
    """
    if not state:
        return None

    mock_config = require_json_object(state.mock, "state.mock") if state.mock else None
    if not mock_config or not mock_config.get("enabled"):
        return None

    nodes = _mock_mapping_section(mock_config, "nodes")
    if node_id in nodes:
        logger.debug(f"Mock для node '{node_id}' найден")
        node_mock = nodes[node_id]
        return require_json_object(node_mock, f"mock.nodes.{node_id}")

    return None


def get_mock_for_llm(state: ExecutionState | None) -> list[JsonObject] | None:
    """
    Получает mock ответы для LLM.

    Args:
        state: ExecutionState

    Returns:
        Список mock ответов или None
    """
    if not state:
        logger.debug("[mock] get_mock_for_llm: state is None")
        return None

    mock_config = require_json_object(state.mock, "state.mock") if state.mock else None
    if not mock_config:
        logger.debug("[mock] get_mock_for_llm: no mock in state")
        return None

    enabled = mock_config.get("enabled")
    if not enabled:
        logger.debug("[mock] get_mock_for_llm: mock disabled")
        return None

    llm_responses = mock_config.get("llm")
    if isinstance(llm_responses, list) and llm_responses:
        logger.info(f"[mock] Mock для LLM найден: {len(llm_responses)} ответов")
        responses: list[JsonObject] = []
        for index, item in enumerate(llm_responses):
            if not isinstance(item, Mapping):
                raise ValueError(f"mock.llm[{index}] must be an object")
            responses.append(require_json_object(item, f"mock.llm[{index}]"))
        return responses

    return None


def check_mock_permission(user_groups: list[str], mock_config: MockConfig) -> bool:
    """
    Проверяет есть ли у пользователя право использовать mock через request metadata.

    Если auth.permissions_enabled=false, mock разрешён всем.

    Args:
        user_groups: Группы пользователя
        mock_config: Mock конфигурация

    Returns:
        True если есть право
    """
    config = get_settings()
    if not config.auth.permissions_enabled:
        return True

    if not user_groups:
        return False

    permission_groups = mock_config.permission_groups or ["admin", "developers"]

    for group in user_groups:
        if group in permission_groups:
            return True

    return False
