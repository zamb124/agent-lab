"""
Тесты MockConfig и MockLLMResponse моделей.
"""

import pytest
from apps.agents.src.mock.config import MockConfig, MockLLMResponse


class TestMockLLMResponse:
    """Тесты MockLLMResponse."""

    def test_text_response(self):
        """Текстовый ответ LLM."""
        response = MockLLMResponse(type="text", content="Hello, world!")
        
        assert response.type == "text"
        assert response.content == "Hello, world!"
        assert response.tool is None
        assert response.args is None

    def test_tool_call_response(self):
        """Ответ с вызовом tool."""
        response = MockLLMResponse(
            type="tool_call",
            tool="calculator",
            args={"expression": "2+2"}
        )
        
        assert response.type == "tool_call"
        assert response.content is None
        assert response.tool == "calculator"
        assert response.args == {"expression": "2+2"}

    def test_from_dict(self):
        """Создание из словаря."""
        data = {
            "type": "text",
            "content": "Test content"
        }
        response = MockLLMResponse(**data)
        
        assert response.type == "text"
        assert response.content == "Test content"


class TestMockConfig:
    """Тесты MockConfig."""

    def test_default_values(self):
        """Значения по умолчанию."""
        config = MockConfig()
        
        assert config.enabled is False
        assert config.llm is None
        assert config.tools == {}
        assert config.agents == {}
        assert config.nodes == {}
        assert config.permission_groups == ["admin", "developers"]

    def test_enabled_mock(self):
        """Включенный mock режим."""
        config = MockConfig(enabled=True)
        
        assert config.enabled is True

    def test_with_tools(self):
        """Конфиг с mock для tools."""
        config = MockConfig(
            enabled=True,
            tools={
                "calculator": 42,
                "search": ["result1", "result2"]
            }
        )
        
        assert config.tools["calculator"] == 42
        assert config.tools["search"] == ["result1", "result2"]

    def test_with_agents(self):
        """Конфиг с mock для agents."""
        config = MockConfig(
            enabled=True,
            agents={
                "consultant": "Mock консультация",
                "analyzer": {"result": "analysis"}
            }
        )
        
        assert config.agents["consultant"] == "Mock консультация"
        assert config.agents["analyzer"] == {"result": "analysis"}

    def test_with_nodes(self):
        """Конфиг с mock для nodes."""
        config = MockConfig(
            enabled=True,
            nodes={
                "validator": {"valid": True},
                "formatter": {"response": "formatted"}
            }
        )
        
        assert config.nodes["validator"] == {"valid": True}
        assert config.nodes["formatter"] == {"response": "formatted"}

    def test_with_llm_responses(self):
        """Конфиг с mock ответами LLM."""
        llm_responses = [
            {"type": "text", "content": "First response"},
            {"type": "tool_call", "tool": "calc", "args": {"x": 1}},
            {"type": "text", "content": "Final response"}
        ]
        config = MockConfig(enabled=True, llm=llm_responses)
        
        assert len(config.llm) == 3
        # Pydantic конвертирует dict в MockLLMResponse
        assert config.llm[0].type == "text"
        assert config.llm[1].type == "tool_call"

    def test_custom_permission_groups(self):
        """Кастомные группы с правом mock."""
        config = MockConfig(
            enabled=True,
            permission_groups=["testers", "qa"]
        )
        
        assert config.permission_groups == ["testers", "qa"]

    def test_extra_fields_allowed(self):
        """Дополнительные поля разрешены."""
        config = MockConfig(
            enabled=True,
            custom_field="custom_value"
        )
        
        assert config.custom_field == "custom_value"

    def test_from_dict_full(self):
        """Создание из полного словаря."""
        data = {
            "enabled": True,
            "llm": [{"type": "text", "content": "Hello"}],
            "tools": {"tool1": "result1"},
            "agents": {"agent1": "result1"},
            "nodes": {"node1": {"key": "value"}},
            "permission_groups": ["admin"]
        }
        config = MockConfig(**data)
        
        assert config.enabled is True
        assert len(config.llm) == 1
        assert config.tools["tool1"] == "result1"
        assert config.agents["agent1"] == "result1"
        assert config.nodes["node1"]["key"] == "value"
        assert config.permission_groups == ["admin"]

    def test_model_dump(self):
        """Сериализация в словарь."""
        config = MockConfig(
            enabled=True,
            tools={"calc": 42}
        )
        data = config.model_dump()
        
        assert data["enabled"] is True
        assert data["tools"]["calc"] == 42

