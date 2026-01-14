"""
Тесты mock для NodeAsToolWrapper.

Mock через state.mock["agents"].
"""

import pytest
from typing import Any, Dict

from apps.agents.src.models import NodeConfig, LLMConfig
from apps.agents.src.models.node_config import NodeLLMOverride
from apps.agents.src.tools.node_wrapper import NodeAsToolWrapper
from core.state import ExecutionState


@pytest.fixture
def simple_node_config():
    """Конфигурация простой ноды."""
    return NodeConfig(
        node_id="test_node",
        type="react_node",
        name="Test Node",
        description="Test node for mocking",
        prompt="You are a test agent.",
        tools=[],
        llm_override=NodeLLMOverride(model="gpt-4o", temperature=0.1),
    )


class TestNodeAsToolWrapperMock:
    """Тесты mock для NodeAsToolWrapper."""

    @pytest.mark.asyncio
    async def test_mock_from_state_returns_string(self, simple_node_config):
        """Mock возвращает строку без вызова ноды."""
        wrapper = NodeAsToolWrapper(node_config=simple_node_config)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "agents": {
                    "test_node": "Mock response from node"
                }
            }
        )
        
        result = await wrapper.execute({"query": "test query"}, state)
        
        assert result == "Mock response from node"

    @pytest.mark.asyncio
    async def test_mock_from_state_returns_dict(self, simple_node_config):
        """Mock возвращает словарь без вызова ноды."""
        wrapper = NodeAsToolWrapper(node_config=simple_node_config)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "agents": {
                    "test_node": {
                        "result": "analysis complete",
                        "confidence": 0.95,
                        "details": ["item1", "item2"]
                    }
                }
            }
        )
        
        result = await wrapper.execute({"query": "analyze something"}, state)
        
        assert result["result"] == "analysis complete"
        assert result["confidence"] == 0.95
        assert result["details"] == ["item1", "item2"]

    @pytest.mark.asyncio
    async def test_mock_disabled_calls_real_node(self, simple_node_config, mock_llm):
        """Mock выключен - вызывается реальная нода."""
        wrapper = NodeAsToolWrapper(node_config=simple_node_config)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": False,
                "agents": {
                    "test_node": "should_not_be_used"
                }
            }
        )
        
        # mock_llm установлен в conftest, нода выполнится с mock LLM
        result = await wrapper.execute({"query": "test"}, state)
        
        # Должен быть результат от реальной ноды (с mock LLM)
        assert result != "should_not_be_used"

    @pytest.mark.asyncio
    async def test_no_mock_for_this_node_calls_real(self, simple_node_config, mock_llm):
        """Нет mock для этой ноды - вызывается реальная."""
        wrapper = NodeAsToolWrapper(node_config=simple_node_config)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "agents": {
                    "other_node": "mock for other"
                }
            }
        )
        
        # Нет mock для test_node, вызовется реальная нода
        result = await wrapper.execute({"query": "test"}, state)
        
        assert result != "mock for other"

    @pytest.mark.asyncio
    async def test_mock_with_empty_string(self, simple_node_config):
        """Mock с пустой строкой - валидно."""
        wrapper = NodeAsToolWrapper(node_config=simple_node_config)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "agents": {
                    "test_node": ""
                }
            }
        )
        
        result = await wrapper.execute({"query": "test"}, state)
        
        assert result == ""

    @pytest.mark.asyncio
    async def test_mock_with_list(self, simple_node_config):
        """Mock со списком - валидно."""
        wrapper = NodeAsToolWrapper(node_config=simple_node_config)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "agents": {
                    "test_node": ["item1", "item2", "item3"]
                }
            }
        )
        
        result = await wrapper.execute({"query": "test"}, state)
        
        assert result == ["item1", "item2", "item3"]

    @pytest.mark.asyncio
    async def test_mock_with_nested_structure(self, simple_node_config):
        """Mock с вложенной структурой."""
        wrapper = NodeAsToolWrapper(node_config=simple_node_config)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "agents": {
                    "test_node": {
                        "response": "Main response",
                        "metadata": {
                            "source": "database",
                            "confidence": 0.9,
                            "tags": ["urgent", "verified"]
                        },
                        "items": [
                            {"id": 1, "name": "Item 1"},
                            {"id": 2, "name": "Item 2"}
                        ]
                    }
                }
            }
        )
        
        result = await wrapper.execute({"query": "test"}, state)
        
        assert result["response"] == "Main response"
        assert result["metadata"]["source"] == "database"
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_multiple_nodes_mock(self):
        """Mock для нескольких нод."""
        node1_config = NodeConfig(
            node_id="node1",
            type="react_node",
            name="Node 1",
            description="First node",
            prompt="Prompt 1",
            tools=[],
        )
        node2_config = NodeConfig(
            node_id="node2",
            type="react_node",
            name="Node 2",
            description="Second node",
            prompt="Prompt 2",
            tools=[],
        )
        
        wrapper1 = NodeAsToolWrapper(node_config=node1_config)
        wrapper2 = NodeAsToolWrapper(node_config=node2_config)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "agents": {
                    "node1": "Response from node 1",
                    "node2": "Response from node 2"
                }
            }
        )
        
        result1 = await wrapper1.execute({"query": "test"}, state)
        result2 = await wrapper2.execute({"query": "test"}, state)
        
        assert result1 == "Response from node 1"
        assert result2 == "Response from node 2"

    @pytest.mark.asyncio
    async def test_mock_preserves_state(self, simple_node_config):
        """Mock не модифицирует state (кроме nested states)."""
        wrapper = NodeAsToolWrapper(node_config=simple_node_config)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "agents": {
                    "test_node": "mock response"
                }
            },
            existing_key="existing_value"
        )
        
        await wrapper.execute({"query": "test"}, state)
        
        # State не должен быть модифицирован (mock не вызывает ноду)
        assert state.existing_key == "existing_value"
        assert not hasattr(state, "__nested_states__")  # Нода не вызывалась

    @pytest.mark.asyncio
    async def test_wrapper_name_matches_node_id(self, simple_node_config):
        """Имя wrapper соответствует node_id."""
        wrapper = NodeAsToolWrapper(node_config=simple_node_config)
        
        assert wrapper.name == "test_node"

    @pytest.mark.asyncio
    async def test_wrapper_description(self, simple_node_config):
        """Description wrapper соответствует ноде."""
        wrapper = NodeAsToolWrapper(node_config=simple_node_config)
        
        # Description берётся из node_config.description или генерируется
        # simple_node_config.description = "Test node for mocking"
        assert wrapper.description == "Test node for mocking"


class TestNodeMockIntegration:
    """Интеграционные тесты mock нод."""

    @pytest.mark.asyncio
    async def test_mock_node_in_tools_chain(self, simple_node_config):
        """Mock нода в цепочке tools."""
        wrapper = NodeAsToolWrapper(node_config=simple_node_config)
        
        # Эмулируем вызов через ToolFactory (как это делает ReactNode)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "agents": {"test_node": "Mock response"}
            },
            content="User input"
        )
        
        # Прямой вызов wrapper как tool
        args = {"query": "process this"}
        result = await wrapper.run(args, state)
        
        assert result == "Mock response"
