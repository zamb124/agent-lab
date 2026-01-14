"""
Тесты mock для BaseTool и InlineTool.

Mock через state.mock["tools"].
"""

import pytest
from typing import Any, Dict, Optional

from apps.agents.src.tools.base import BaseTool, InlineTool
from core.state import ExecutionState


class SimpleTool(BaseTool):
    """Простой tool для тестов."""
    
    name = "simple_tool"
    description = "Simple test tool"
    
    async def execute(self, args: Dict[str, Any], state: Optional[Dict[str, Any]] = None) -> Any:
        return f"real_result_{args.get('input', 'default')}"


class ToolWithCustomMock(BaseTool):
    """Tool с переопределённым execute_mock."""
    
    name = "tool_with_custom_mock"
    description = "Tool with custom mock"
    
    async def execute(self, args: Dict[str, Any], state: Optional[Dict[str, Any]] = None) -> Any:
        return "real_result"
    
    async def execute_mock(self, args: Dict[str, Any], state: Optional[Dict[str, Any]] = None) -> Any:
        return f"custom_mock_{args.get('value', 0)}"


class TestBaseToolMockFromState:
    """Тесты mock через state.mock["tools"]."""

    @pytest.mark.asyncio
    async def test_mock_from_state_has_priority(self):
        """Mock из state имеет приоритет над TESTING env."""
        tool = SimpleTool()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {
                    "simple_tool": "mock_from_state"
                }
            }
        )
        
        result = await tool.run({"input": "test"}, state)
        
        assert result == "mock_from_state"

    @pytest.mark.asyncio
    async def test_mock_from_state_complex_value(self):
        """Mock из state с сложным значением."""
        tool = SimpleTool()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {
                    "simple_tool": {
                        "status": "success",
                        "data": [1, 2, 3],
                        "nested": {"key": "value"}
                    }
                }
            }
        )
        
        result = await tool.run({}, state)
        
        assert result["status"] == "success"
        assert result["data"] == [1, 2, 3]
        assert result["nested"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_mock_disabled_in_state_uses_real(self):
        """Mock выключен в state - используется реальный execute."""
        tool = SimpleTool()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": False,  # Mock выключен
                "tools": {
                    "simple_tool": "should_not_be_used"
                }
            }
        )
        
        result = await tool.run({"input": "test"}, state)
        
        # Реальный результат, не mock
        assert result == "real_result_test"

    @pytest.mark.asyncio
    async def test_no_mock_for_this_tool_uses_real(self):
        """Нет mock для этого tool - используется реальный execute."""
        tool = SimpleTool()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {
                    "other_tool": "mock_for_other"
                }
            }
        )
        
        result = await tool.run({"input": "test"}, state)
        
        # Реальный результат
        assert result == "real_result_test"

    @pytest.mark.asyncio
    async def test_empty_mock_config_uses_testing_env(self):
        """Пустой mock - fallback на TESTING env + execute_mock."""
        tool = ToolWithCustomMock()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={}  # Пустой конфиг
        )
        
        result = await tool.run({"value": 42}, state)
        
        # TESTING=true установлен в conftest, должен использовать execute_mock
        assert result == "custom_mock_42"

    @pytest.mark.asyncio
    async def test_no_state_uses_testing_env(self):
        """Без mock в state - fallback на TESTING env."""
        tool = ToolWithCustomMock()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        
        result = await tool.run({"value": 123}, state)
        
        # TESTING=true, используется execute_mock
        assert result == "custom_mock_123"

    @pytest.mark.asyncio
    async def test_mock_value_none_uses_real(self):
        """Mock значение None в tools - используется реальный execute."""
        tool = SimpleTool()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {
                    "simple_tool": None  # Явно None
                }
            }
        )
        
        result = await tool.run({"input": "test"}, state)
        
        # None не является валидным mock, используется real
        # Но get_mock_for_tool возвращает None если tools[id] is None
        # так что реальный execute вызовется
        assert result == "real_result_test"

    @pytest.mark.asyncio
    async def test_mock_value_zero_is_valid(self):
        """Mock значение 0 - валидно."""
        tool = SimpleTool()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {
                    "simple_tool": 0
                }
            }
        )
        
        result = await tool.run({}, state)
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_mock_value_empty_string_is_valid(self):
        """Mock значение пустая строка - валидно."""
        tool = SimpleTool()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {
                    "simple_tool": ""
                }
            }
        )
        
        result = await tool.run({}, state)
        
        assert result == ""

    @pytest.mark.asyncio
    async def test_mock_value_false_is_valid(self):
        """Mock значение False - валидно."""
        tool = SimpleTool()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {
                    "simple_tool": False
                }
            }
        )
        
        result = await tool.run({}, state)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_mock_value_empty_list_is_valid(self):
        """Mock значение пустой список - валидно."""
        tool = SimpleTool()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {
                    "simple_tool": []
                }
            }
        )
        
        result = await tool.run({}, state)
        
        assert result == []


class TestInlineToolMock:
    """Тесты mock для InlineTool."""

    @pytest.mark.asyncio
    async def test_inline_tool_mock_from_state(self):
        """InlineTool использует mock из state."""
        code = """
def execute(args, state):
    return f"inline_result_{args.get('x', 0)}"
"""
        tool = InlineTool(tool_id="inline_test", code=code)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {
                    "inline_test": "mock_inline_result"
                }
            }
        )
        
        result = await tool.run({"x": 5}, state)
        
        assert result == "mock_inline_result"

    @pytest.mark.asyncio
    async def test_inline_tool_real_execution(self):
        """InlineTool выполняет реальный код когда mock нет."""
        code = """
def execute(args, state):
    return f"inline_result_{args.get('x', 0)}"
"""
        tool = InlineTool(tool_id="inline_test", code=code)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {}  # Нет mock для inline_test
            }
        )
        
        result = await tool.run({"x": 42}, state)
        
        assert result == "inline_result_42"


class TestToolMockWithPermissions:
    """Тесты mock с проверкой permissions."""

    @pytest.mark.asyncio
    async def test_mock_respects_permissions(self, monkeypatch):
        """Mock работает с включенными permissions."""
        from core.config.base import BaseSettings
        
        monkeypatch.setenv("AUTH__PERMISSIONS_ENABLED", "true")
        new_settings = BaseSettings()
        
        import apps.agents.config
        monkeypatch.setattr(apps.agents.config, "_settings", new_settings)
        
        class ProtectedTool(BaseTool):
            name = "protected_tool"
            description = "Protected tool"
            permission = "admin"
            
            async def execute(self, args, state=None):
                return "real_result"
        
        tool = ProtectedTool()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {"protected_tool": "mock_result"}
            },
            user={"grps": ["admin"]}  # Пользователь с правами
        )
        
        result = await tool.run({}, state)
        
        # Mock должен работать для пользователя с правами
        assert result == "mock_result"

    @pytest.mark.asyncio
    async def test_permission_denied_before_mock(self, monkeypatch):
        """Permission проверяется до mock."""
        from core.config.base import BaseSettings
        
        monkeypatch.setenv("AUTH__PERMISSIONS_ENABLED", "true")
        new_settings = BaseSettings()
        
        import apps.agents.config
        monkeypatch.setattr(apps.agents.config, "_settings", new_settings)
        
        class ProtectedTool(BaseTool):
            name = "protected_tool"
            description = "Protected tool"
            permission = "admin"
            
            async def execute(self, args, state=None):
                return "real_result"
        
        tool = ProtectedTool()
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {"protected_tool": "mock_result"}
            },
            user={"grps": ["users"]}  # Нет прав
        )
        
        result = await tool.run({}, state)
        
        # Должно вернуть сообщение об ошибке, не mock
        assert "нет прав" in result


