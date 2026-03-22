"""
Тесты MockResolver - резолвер mock конфигурации.
"""

import os
import pytest
from apps.flows.src.mock.config import MockConfig
from apps.flows.src.mock.resolver import (
    resolve_mock_config,
    is_mock_enabled,
    get_mock_for_tool,
    get_mock_for_flow,
    get_mock_for_node,
    get_mock_for_llm,
    check_mock_permission,
)
from core.state import ExecutionState


class TestResolveMockConfig:
    """Тесты resolve_mock_config() - мерж конфигов по иерархии."""

    def test_empty_configs_returns_defaults(self):
        """Пустые конфиги возвращают дефолты."""
        result = resolve_mock_config()
        
        assert result.enabled is False
        assert result.llm is None
        assert result.tools == {}
        assert result.flows == {}
        assert result.nodes == {}
        assert result.permission_groups == ["admin", "developers"]

    def test_global_config_only(self):
        """Только глобальный конфиг."""
        global_mock = {
            "enabled": True,
            "tools": {"calc": 100}
        }
        result = resolve_mock_config(global_mock=global_mock)
        
        assert result.enabled is True
        assert result.tools["calc"] == 100

    def test_flow_overrides_global(self):
        """Agent конфиг переопределяет глобальный."""
        global_mock = {
            "enabled": False,
            "tools": {"calc": 100, "search": "global"}
        }
        flow_mock = {
            "enabled": True,
            "tools": {"calc": 200}  # Переопределяет calc
        }
        result = resolve_mock_config(global_mock=global_mock, flow_mock=flow_mock)
        
        assert result.enabled is True  # Переопределено flow
        assert result.tools["calc"] == 200  # Переопределено flow
        assert result.tools["search"] == "global"  # Осталось от global

    def test_skill_overrides_flow(self):
        """Skill конфиг переопределяет flow."""
        flow_mock = {
            "enabled": True,
            "tools": {"tool1": "flow_value"}
        }
        skill_mock = {
            "enabled": False,
            "tools": {"tool1": "skill_value", "tool2": "skill_only"}
        }
        result = resolve_mock_config(flow_mock=flow_mock, skill_mock=skill_mock)
        
        assert result.enabled is False  # Переопределено skill
        assert result.tools["tool1"] == "skill_value"  # Переопределено skill
        assert result.tools["tool2"] == "skill_only"  # Добавлено skill

    def test_request_overrides_all(self):
        """Request metadata переопределяет всё."""
        global_mock = {"enabled": False, "tools": {"t1": "g"}}
        flow_mock = {"enabled": True, "tools": {"t1": "f"}}
        skill_mock = {"tools": {"t2": "s"}}
        request_mock = {
            "enabled": True,
            "tools": {"t1": "r", "t3": "request_only"}
        }
        
        result = resolve_mock_config(
            global_mock=global_mock,
            flow_mock=flow_mock,
            skill_mock=skill_mock,
            request_mock=request_mock
        )
        
        assert result.enabled is True
        assert result.tools["t1"] == "r"  # request переопределил
        assert result.tools["t2"] == "s"  # от skill
        assert result.tools["t3"] == "request_only"  # от request

    def test_llm_full_replace(self):
        """LLM конфиг полностью заменяется, не мержится."""
        global_mock = {
            "llm": [{"type": "text", "content": "global response"}]
        }
        flow_mock = {
            "llm": [
                {"type": "text", "content": "flow response 1"},
                {"type": "text", "content": "flow response 2"}
            ]
        }
        result = resolve_mock_config(global_mock=global_mock, flow_mock=flow_mock)
        
        # LLM полностью заменён flow конфигом
        assert len(result.llm) == 2
        # Pydantic конвертирует в MockLLMResponse
        assert result.llm[0].content == "flow response 1"
        assert result.llm[1].content == "flow response 2"

    def test_flows_mock_merge(self):
        """Ключ mock.flows мержится между уровнями."""
        global_mock = {"flows": {"flow1": "g1"}}
        flow_mock = {"flows": {"flow2": "f2"}}
        skill_mock = {"flows": {"flow1": "s1", "flow3": "s3"}}
        
        result = resolve_mock_config(
            global_mock=global_mock,
            flow_mock=flow_mock,
            skill_mock=skill_mock
        )
        
        assert result.flows["flow1"] == "s1"  # skill переопределил
        assert result.flows["flow2"] == "f2"  # от flow
        assert result.flows["flow3"] == "s3"  # от skill

    def test_nodes_merge(self):
        """Nodes мержатся между уровнями."""
        global_mock = {"nodes": {"node1": {"key1": "g1"}}}
        flow_mock = {"nodes": {"node2": {"key2": "f2"}}}
        request_mock = {"nodes": {"node1": {"key1": "r1"}, "node3": {"key3": "r3"}}}
        
        result = resolve_mock_config(
            global_mock=global_mock,
            flow_mock=flow_mock,
            request_mock=request_mock
        )
        
        assert result.nodes["node1"]["key1"] == "r1"  # request переопределил
        assert result.nodes["node2"]["key2"] == "f2"  # от flow
        assert result.nodes["node3"]["key3"] == "r3"  # от request

    def test_permission_groups_full_replace(self):
        """Permission groups полностью заменяются."""
        global_mock = {"permission_groups": ["admin"]}
        flow_mock = {"permission_groups": ["testers", "qa"]}
        
        result = resolve_mock_config(global_mock=global_mock, flow_mock=flow_mock)
        
        assert result.permission_groups == ["testers", "qa"]

    def test_none_llm_does_not_replace(self):
        """None в llm не заменяет предыдущее значение."""
        global_mock = {"llm": [{"type": "text", "content": "global"}]}
        flow_mock = {"llm": None}  # Явный None
        
        result = resolve_mock_config(global_mock=global_mock, flow_mock=flow_mock)
        
        # llm остался от global, т.к. flow передал None
        # Pydantic конвертирует в MockLLMResponse
        assert result.llm[0].content == "global"

    def test_legacy_agents_key_merges_into_flows(self):
        """Устаревший ключ mock.agents мержится в flows."""
        result = resolve_mock_config(
            flow_mock={"agents": {"legacy_id": "x"}, "flows": {"new_id": "y"}}
        )
        assert result.flows["legacy_id"] == "x"
        assert result.flows["new_id"] == "y"


class TestIsMockEnabled:
    """Тесты is_mock_enabled()."""

    def test_mock_enabled_from_state(self):
        """Mock включен через state."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={"enabled": True}
        )
        assert is_mock_enabled(state) is True

    def test_mock_disabled_from_state(self):
        """Mock выключен через state, но fallback на TESTING env."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={"enabled": False}
        )
        # is_mock_enabled проверяет:
        # 1. state.mock["enabled"] == True -> True
        # 2. fallback на TESTING env -> True (если TESTING=true)
        # Так как enabled=False, проверка 1 не срабатывает, идём на fallback
        # TESTING=true установлен в conftest, поэтому вернёт True
        assert is_mock_enabled(state) is True

    def test_no_mock_in_state_uses_env(self):
        """Без __mock__ в state используется TESTING env."""
        # TESTING=true установлен в conftest.py
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        assert is_mock_enabled(state) is True

    def test_none_state_uses_env(self):
        """None state использует TESTING env."""
        assert is_mock_enabled(None) is True

    def test_empty_mock_config_in_state(self):
        """Пустой __mock__ в state - enabled=False."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={}
        )
        # Пустой конфиг = enabled=False, но TESTING=true даст True
        assert is_mock_enabled(state) is True  # fallback на TESTING env


class TestGetMockForTool:
    """Тесты get_mock_for_tool()."""

    def test_returns_mock_when_exists(self):
        """Возвращает mock когда он есть."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {
                    "calculator": 42,
                    "search": ["r1", "r2"]
                }
            }
        )
        
        assert get_mock_for_tool(state, "calculator") == 42
        assert get_mock_for_tool(state, "search") == ["r1", "r2"]

    def test_returns_none_when_not_exists(self):
        """Возвращает None когда mock нет."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {"calc": 42}
            }
        )
        
        assert get_mock_for_tool(state, "unknown_tool") is None

    def test_returns_none_when_mock_disabled(self):
        """Возвращает None когда mock выключен."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": False,
                "tools": {"calc": 42}
            }
        )
        
        assert get_mock_for_tool(state, "calc") is None

    def test_returns_none_when_no_mock_config(self):
        """Возвращает None когда нет __mock__ в state."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        assert get_mock_for_tool(state, "calc") is None

    def test_returns_none_when_state_is_none(self):
        """Возвращает None когда state is None."""
        assert get_mock_for_tool(None, "calc") is None

    def test_returns_complex_mock_value(self):
        """Возвращает сложные значения mock."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {
                    "api_call": {
                        "status": "success",
                        "data": [1, 2, 3],
                        "nested": {"key": "value"}
                    }
                }
            }
        )
        
        result = get_mock_for_tool(state, "api_call")
        assert result["status"] == "success"
        assert result["data"] == [1, 2, 3]
        assert result["nested"]["key"] == "value"


class TestGetMockForAgent:
    """Тесты get_mock_for_flow()."""

    def test_returns_mock_when_exists(self):
        """Возвращает mock когда он есть."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "flows": {
                    "consultant": "Mock консультация",
                    "analyzer": {"result": "analysis"}
                }
            }
        )
        
        assert get_mock_for_flow(state, "consultant") == "Mock консультация"
        assert get_mock_for_flow(state, "analyzer") == {"result": "analysis"}

    def test_returns_none_when_not_exists(self):
        """Возвращает None когда mock нет."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "flows": {"consultant": "mock"}
            }
        )
        
        assert get_mock_for_flow(state, "unknown_agent") is None

    def test_returns_none_when_mock_disabled(self):
        """Возвращает None когда mock выключен."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": False,
                "flows": {"consultant": "mock"}
            }
        )
        
        assert get_mock_for_flow(state, "consultant") is None

    def test_returns_none_when_no_mock_config(self):
        """Возвращает None когда нет __mock__ в state."""
        assert get_mock_for_flow({}, "consultant") is None

    def test_returns_none_when_state_is_none(self):
        """Возвращает None когда state is None."""
        assert get_mock_for_flow(None, "consultant") is None


class TestGetMockForNode:
    """Тесты get_mock_for_node()."""

    def test_returns_mock_when_exists(self):
        """Возвращает mock когда он есть."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "nodes": {
                    "validator": {"valid": True},
                    "formatter": {"response": "formatted", "extra": 123}
                }
            }
        )
        
        assert get_mock_for_node(state, "validator") == {"valid": True}
        assert get_mock_for_node(state, "formatter") == {"response": "formatted", "extra": 123}

    def test_returns_none_when_not_exists(self):
        """Возвращает None когда mock нет."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "nodes": {"validator": {"valid": True}}
            }
        )
        
        assert get_mock_for_node(state, "unknown_node") is None

    def test_returns_none_when_mock_disabled(self):
        """Возвращает None когда mock выключен."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": False,
                "nodes": {"validator": {"valid": True}}
            }
        )
        
        assert get_mock_for_node(state, "validator") is None

    def test_returns_none_when_no_mock_config(self):
        """Возвращает None когда нет __mock__ в state."""
        assert get_mock_for_node({}, "validator") is None

    def test_returns_none_when_state_is_none(self):
        """Возвращает None когда state is None."""
        assert get_mock_for_node(None, "validator") is None


class TestGetMockForLLM:
    """Тесты get_mock_for_llm()."""

    def test_returns_mock_when_exists(self):
        """Возвращает mock когда он есть."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "llm": [
                    {"type": "text", "content": "Response 1"},
                    {"type": "tool_call", "tool": "calc", "args": {"x": 1}},
                    {"type": "text", "content": "Final"}
                ]
            }
        )
        
        result = get_mock_for_llm(state)
        assert len(result) == 3
        assert result[0]["content"] == "Response 1"
        assert result[1]["tool"] == "calc"
        assert result[2]["content"] == "Final"

    def test_returns_none_when_not_exists(self):
        """Возвращает None когда llm mock нет."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": True,
                "tools": {"calc": 42}
                # llm отсутствует
            }
        )
        
        assert get_mock_for_llm(state) is None

    def test_returns_none_when_mock_disabled(self):
        """Возвращает None когда mock выключен."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            mock={
                "enabled": False,
                "llm": [{"type": "text", "content": "mock"}]
            }
        )
        
        assert get_mock_for_llm(state) is None

    def test_returns_none_when_no_mock_config(self):
        """Возвращает None когда нет __mock__ в state."""
        assert get_mock_for_llm({}) is None

    def test_returns_none_when_state_is_none(self):
        """Возвращает None когда state is None."""
        assert get_mock_for_llm(None) is None


class TestCheckMockPermission:
    """Тесты check_mock_permission()."""

    def test_permissions_disabled_allows_all(self):
        """Если permissions_enabled=false, mock разрешён всем."""
        # В тестах AUTH__PERMISSIONS_ENABLED=false (conftest.py)
        mock_config = MockConfig()
        
        # Любой пользователь может использовать mock
        assert check_mock_permission([], mock_config) is True
        assert check_mock_permission(["users"], mock_config) is True

    def test_admin_has_permission(self, monkeypatch):
        """admin группа имеет доступ по умолчанию."""
        from core.config.base import BaseSettings
        
        monkeypatch.setenv("AUTH__PERMISSIONS_ENABLED", "true")
        new_settings = BaseSettings()
        
        # Патчим в apps.flows.config (там используется свой _settings)
        import apps.flows.config
        monkeypatch.setattr(apps.flows.config, "_settings", new_settings)
        
        mock_config = MockConfig()  # permission_groups = ["admin", "developers"]
        
        assert check_mock_permission(["admin"], mock_config) is True

    def test_developers_has_permission(self, monkeypatch):
        """developers группа имеет доступ по умолчанию."""
        from core.config.base import BaseSettings
        
        monkeypatch.setenv("AUTH__PERMISSIONS_ENABLED", "true")
        new_settings = BaseSettings()
        
        import apps.flows.config
        monkeypatch.setattr(apps.flows.config, "_settings", new_settings)
        
        mock_config = MockConfig()
        
        assert check_mock_permission(["developers"], mock_config) is True

    def test_user_without_permission(self, monkeypatch):
        """Обычный пользователь без доступа (если permissions включены)."""
        from core.config.base import BaseSettings
        
        monkeypatch.setenv("AUTH__PERMISSIONS_ENABLED", "true")
        new_settings = BaseSettings()
        
        import apps.flows.config
        monkeypatch.setattr(apps.flows.config, "_settings", new_settings)
        
        mock_config = MockConfig()
        
        assert check_mock_permission(["users", "readers"], mock_config) is False

    def test_custom_permission_groups(self, monkeypatch):
        """Кастомные группы с правом mock."""
        from core.config.base import BaseSettings
        
        monkeypatch.setenv("AUTH__PERMISSIONS_ENABLED", "true")
        new_settings = BaseSettings()
        
        import apps.flows.config
        monkeypatch.setattr(apps.flows.config, "_settings", new_settings)
        
        mock_config = MockConfig(permission_groups=["testers", "qa"])
        
        assert check_mock_permission(["testers"], mock_config) is True
        assert check_mock_permission(["qa"], mock_config) is True
        assert check_mock_permission(["admin"], mock_config) is False  # admin не в списке
        assert check_mock_permission(["developers"], mock_config) is False

    def test_empty_user_groups(self, monkeypatch):
        """Пустой список групп - нет доступа (если permissions включены)."""
        from core.config.base import BaseSettings
        
        monkeypatch.setenv("AUTH__PERMISSIONS_ENABLED", "true")
        new_settings = BaseSettings()
        
        import apps.flows.config
        monkeypatch.setattr(apps.flows.config, "_settings", new_settings)
        
        mock_config = MockConfig()
        
        assert check_mock_permission([], mock_config) is False

    def test_multiple_groups_one_match(self, monkeypatch):
        """Достаточно одного совпадения."""
        from core.config.base import BaseSettings
        
        monkeypatch.setenv("AUTH__PERMISSIONS_ENABLED", "true")
        new_settings = BaseSettings()
        
        import apps.flows.config
        monkeypatch.setattr(apps.flows.config, "_settings", new_settings)
        
        mock_config = MockConfig(permission_groups=["admin"])
        
        assert check_mock_permission(["users", "readers", "admin"], mock_config) is True

    def test_none_permission_groups_uses_default(self, monkeypatch):
        """None в permission_groups использует дефолт."""
        from core.config.base import BaseSettings
        
        monkeypatch.setenv("AUTH__PERMISSIONS_ENABLED", "true")
        new_settings = BaseSettings()
        
        import apps.flows.config
        monkeypatch.setattr(apps.flows.config, "_settings", new_settings)
        
        mock_config = MockConfig()
        mock_config.permission_groups = None
        
        assert check_mock_permission(["admin"], mock_config) is True


