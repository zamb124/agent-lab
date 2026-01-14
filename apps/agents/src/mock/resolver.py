"""
MockResolver - резолвер mock конфигурации.

Мержит mock конфиги из всех уровней иерархии.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from apps.agents.config import get_settings
from core.logging import get_logger

from .config import MockConfig

if TYPE_CHECKING:
    from core.state import ExecutionState

logger = get_logger(__name__)


def resolve_mock_config(
    global_mock: Optional[Dict[str, Any]] = None,
    agent_mock: Optional[Dict[str, Any]] = None,
    skill_mock: Optional[Dict[str, Any]] = None,
    request_mock: Optional[Dict[str, Any]] = None,
) -> MockConfig:
    """
    Резолвит итоговый mock конфиг с учётом иерархии.
    
    Приоритет (от низшего к высшему):
    1. global_mock (conf.json)
    2. agent_mock (agent.json)
    3. skill_mock (skill в agent.json)
    4. request_mock (metadata.mock)
    
    Args:
        global_mock: Mock из глобального конфига
        agent_mock: Mock из конфига агента
        skill_mock: Mock из skill конфига
        request_mock: Mock из metadata запроса
        
    Returns:
        Итоговый MockConfig
    """
    result: Dict[str, Any] = {
        "enabled": False,
        "llm": None,
        "tools": {},
        "agents": {},
        "nodes": {},
        "permission_groups": ["admin", "developers"],
    }
    
    # Мерж в порядке приоритета
    for mock_dict in [global_mock, agent_mock, skill_mock, request_mock]:
        if mock_dict:
            _merge_mock(result, mock_dict)
    
    return MockConfig(**result)


def _merge_mock(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    """
    Мержит source mock в target.
    
    - enabled: замена
    - llm: замена целиком (не мерж)
    - tools/agents/nodes: update (мерж)
    - permission_groups: замена
    """
    if "enabled" in source:
        target["enabled"] = source["enabled"]
    
    # LLM: полная замена если указан
    if "llm" in source and source["llm"] is not None:
        target["llm"] = source["llm"]
    
    # Tools: мерж
    if "tools" in source and source["tools"]:
        target["tools"].update(source["tools"])
    
    # Agents: мерж
    if "agents" in source and source["agents"]:
        target["agents"].update(source["agents"])
    
    # Nodes: мерж
    if "nodes" in source and source["nodes"]:
        target["nodes"].update(source["nodes"])
    
    # Замена групп разрешений
    if "permission_groups" in source:
        target["permission_groups"] = source["permission_groups"]


def is_mock_enabled(state_dict: Optional[Dict[str, Any]] = None) -> bool:
    """
    Проверяет включен ли mock режим.
    
    Args:
        state_dict: State dict (from ExecutionState.model_dump(exclude_none=False))
        
    Returns:
        True если mock режим включен
    """
    if state_dict:
        mock_config = state_dict.get("mock")
        if mock_config and mock_config.get("enabled"):
            return True
    
    return os.environ.get("TESTING", "").lower() in ("true", "1", "yes")


def get_mock_for_tool(state: Optional["ExecutionState"], tool_id: str) -> Optional[Any]:
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
    
    mock_config = state.mock
    if not mock_config or not mock_config.get("enabled"):
        return None
    
    tools = mock_config.get("tools", {})
    if tool_id in tools:
        logger.debug(f"Mock для tool '{tool_id}' найден")
        return tools[tool_id]
    
    return None


def get_mock_for_agent(state: Optional["ExecutionState"], agent_id: str) -> Optional[Any]:
    """
    Получает mock ответ для агента.
    
    Args:
        state: ExecutionState
        agent_id: ID агента
        
    Returns:
        Mock ответ или None
    """
    if not state:
        return None
    
    mock_config = state.mock
    if not mock_config or not mock_config.get("enabled"):
        return None
    
    agents = mock_config.get("agents", {})
    if agent_id in agents:
        logger.debug(f"Mock для agent '{agent_id}' найден")
        return agents[agent_id]
    
    return None


def get_mock_for_node(state: Optional["ExecutionState"], node_id: str) -> Optional[Dict[str, Any]]:
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
    
    mock_config = state.mock
    if not mock_config or not mock_config.get("enabled"):
        return None
    
    nodes = mock_config.get("nodes", {})
    if node_id in nodes:
        logger.debug(f"Mock для node '{node_id}' найден")
        return nodes[node_id]
    
    return None


def get_mock_for_llm(state: Optional["ExecutionState"]) -> Optional[List[Dict[str, Any]]]:
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
    
    mock_config = state.mock
    if not mock_config:
        logger.debug("[mock] get_mock_for_llm: no mock in state")
        return None
    
    enabled = mock_config.get("enabled")
    if not enabled:
        logger.debug(f"[mock] get_mock_for_llm: mock disabled")
        return None
    
    llm_responses = mock_config.get("llm")
    if llm_responses:
        logger.info(f"[mock] Mock для LLM найден: {len(llm_responses)} ответов")
        return llm_responses
    
    return None


def check_mock_permission(user_groups: List[str], mock_config: MockConfig) -> bool:
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

