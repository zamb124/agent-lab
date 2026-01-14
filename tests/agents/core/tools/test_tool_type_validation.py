"""
Тесты валидации ToolType - проверка уникальности reason/exit tools.
"""

import pytest

from apps.agents.src.tools.base import ToolType
from apps.agents.src.services.agents_loader import AgentsLoader
from apps.agents.src.services.agent_validator import AgentValidator, AgentValidationResult


class TestToolTypeEnum:
    """Тесты ToolType enum."""

    def test_tool_type_values(self):
        """ToolType имеет правильные значения."""
        assert ToolType.TOOL == "tool"
        assert ToolType.REASON == "reason"
        assert ToolType.EXIT == "exit"

    def test_builtin_tools_have_correct_types(self):
        """Встроенные tools имеют правильные типы."""
        from apps.agents.tools import reason, finish, final_answer, calculator

        assert reason.tool_type == ToolType.REASON
        assert finish.tool_type == ToolType.EXIT
        assert final_answer.tool_type == ToolType.EXIT
        assert calculator.tool_type == ToolType.TOOL


class TestAgentValidatorToolType:
    """Тесты валидации tool_type в AgentValidator."""

    @pytest.fixture
    def validator(self) -> AgentValidator:
        return AgentValidator()

    def test_single_reason_tool_valid(self, validator):
        """Один reasoning tool - валидно."""
        tools = [
            {"tool_id": "reason", "tool_type": "reason", "code": "..."},
            {"tool_id": "calc", "tool_type": "tool", "code": "..."},
        ]
        result = AgentValidationResult(valid=True)

        validator._validate_tool_type_uniqueness("test_node", tools, result)

        assert result.valid
        assert len(result.errors) == 0

    def test_single_exit_tool_valid(self, validator):
        """Один exit tool - валидно."""
        tools = [
            {"tool_id": "finish", "tool_type": "exit", "code": "..."},
            {"tool_id": "calc", "tool_type": "tool", "code": "..."},
        ]
        result = AgentValidationResult(valid=True)

        validator._validate_tool_type_uniqueness("test_node", tools, result)

        assert result.valid
        assert len(result.errors) == 0

    def test_duplicate_reason_tools_invalid(self, validator):
        """Два reasoning tools - невалидно."""
        tools = [
            {"tool_id": "reason", "tool_type": "reason", "code": "..."},
            {"tool_id": "custom_reason", "tool_type": "reason", "code": "..."},
        ]
        result = AgentValidationResult(valid=True)

        validator._validate_tool_type_uniqueness("test_node", tools, result)

        assert not result.valid
        assert len(result.errors) == 1
        assert result.errors[0].code == "duplicate_reason_tool"

    def test_duplicate_exit_tools_invalid(self, validator):
        """Два exit tools - невалидно."""
        tools = [
            {"tool_id": "finish", "tool_type": "exit", "code": "..."},
            {"tool_id": "final_answer", "tool_type": "exit", "code": "..."},
        ]
        result = AgentValidationResult(valid=True)

        validator._validate_tool_type_uniqueness("test_node", tools, result)

        assert not result.valid
        assert len(result.errors) == 1
        assert result.errors[0].code == "duplicate_exit_tool"

    def test_reason_and_exit_together_valid(self, validator):
        """Один reasoning + один exit - валидно."""
        tools = [
            {"tool_id": "reason", "tool_type": "reason", "code": "..."},
            {"tool_id": "finish", "tool_type": "exit", "code": "..."},
        ]
        result = AgentValidationResult(valid=True)

        validator._validate_tool_type_uniqueness("test_node", tools, result)

        assert result.valid
        assert len(result.errors) == 0

    def test_no_special_tools_valid(self, validator):
        """Без специальных tools - валидно."""
        tools = [
            {"tool_id": "calc", "tool_type": "tool", "code": "..."},
            {"tool_id": "search", "tool_type": "tool", "code": "..."},
        ]
        result = AgentValidationResult(valid=True)

        validator._validate_tool_type_uniqueness("test_node", tools, result)

        assert result.valid
        assert len(result.errors) == 0

    def test_tools_without_type_valid(self, validator):
        """Tools без tool_type - валидно (считаются обычными)."""
        tools = [
            {"tool_id": "calc", "code": "..."},
            {"tool_id": "search", "code": "..."},
        ]
        result = AgentValidationResult(valid=True)

        validator._validate_tool_type_uniqueness("test_node", tools, result)

        assert result.valid
        assert len(result.errors) == 0


class TestAgentsLoaderToolTypeValidation:
    """Тесты валидации tool_type в AgentsLoader."""

    def test_validate_react_node_tools_single_reason(self):
        """_validate_react_node_tools с одним reason - проходит."""
        loader = AgentsLoader.__new__(AgentsLoader)
        tools = [
            {"tool_id": "reason", "tool_type": "reason"},
            {"tool_id": "calc", "tool_type": "tool"},
        ]

        loader._validate_react_node_tools("test_node", tools)

    def test_validate_react_node_tools_duplicate_reason_raises(self):
        """_validate_react_node_tools с двумя reason - ошибка."""
        loader = AgentsLoader.__new__(AgentsLoader)
        tools = [
            {"tool_id": "reason", "tool_type": "reason"},
            {"tool_id": "my_reason", "tool_type": "reason"},
        ]

        with pytest.raises(ValueError, match="только 1 reasoning tool"):
            loader._validate_react_node_tools("test_node", tools)

    def test_validate_react_node_tools_duplicate_exit_raises(self):
        """_validate_react_node_tools с двумя exit - ошибка."""
        loader = AgentsLoader.__new__(AgentsLoader)
        tools = [
            {"tool_id": "finish", "tool_type": "exit"},
            {"tool_id": "final_answer", "tool_type": "exit"},
        ]

        with pytest.raises(ValueError, match="только 1 exit tool"):
            loader._validate_react_node_tools("test_node", tools)




