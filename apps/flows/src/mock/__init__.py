"""
Mock Control System.

Иерархическое управление моками для tools, flows, nodes и LLM.

Уровни (от низшего приоритета к высшему):
1. Global config (conf.json)
2. Flow bundle (flow.json)
3. Skill config (skill в flow.json)
4. Request metadata (metadata.mock)
"""

from .config import MockConfig, MockLLMResponse
from .resolver import (
    check_mock_permission,
    get_mock_for_flow,
    get_mock_for_llm,
    get_mock_for_node,
    get_mock_for_tool,
    is_mock_enabled,
    resolve_mock_config,
)

__all__ = [
    "MockConfig",
    "MockLLMResponse",
    "resolve_mock_config",
    "is_mock_enabled",
    "get_mock_for_tool",
    "get_mock_for_flow",
    "get_mock_for_node",
    "get_mock_for_llm",
    "check_mock_permission",
]

