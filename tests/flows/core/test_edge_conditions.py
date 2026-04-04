"""
Тесты вычисления условий переходов (edge conditions).

Три формата условий:
1. Legacy строка: "route == 'order'"
2. Simple объект: {"type": "simple", "variable": "route", "operator": "==", "value": "order"}
3. Python код: {"type": "python", "code": "def check(state): return state.get('route') == 'order'"}
"""

import pytest
from core.state import ExecutionState
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import create_node


def make_state(**kwargs) -> ExecutionState:
    """Хелпер для создания state."""
    defaults = {
        "task_id": "test-task",
        "context_id": "test-context",
        "user_id": "test-user",
        "session_id": "test-agent:test-context",
    }
    defaults.update(kwargs)
    return ExecutionState(**defaults)


class TestLegacyStringConditions:
    """Тесты legacy формата: строковые условия."""

    @pytest.mark.asyncio
    async def test_string_condition_equals_string(self, app):
        """Условие route == 'order'."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.route = 'order'; return state"},
                "order": {"type": "code", "code": "def run(state): state.result = 'order_node'; return state"},
            },
            "edges": [
                {"from": "start", "to": "order", "condition": "route == 'order'"}
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        assert result.result == "order_node"

    @pytest.mark.asyncio
    async def test_string_condition_equals_number(self, app):
        """Условие count == 5."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.count = 5; return state"},
                "five": {"type": "code", "code": "def run(state): state.result = 'five'; return state"},
            },
            "edges": [
                {"from": "start", "to": "five", "condition": "count == 5"}
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        assert result.result == "five"

    @pytest.mark.asyncio
    async def test_string_condition_not_equals(self, app):
        """Условие status != 'error'."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.status = 'ok'; return state"},
                "proceed": {"type": "code", "code": "def run(state): state.result = 'proceeded'; return state"},
            },
            "edges": [
                {"from": "start", "to": "proceed", "condition": "status != 'error'"}
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        assert result.result == "proceeded"

    @pytest.mark.asyncio
    async def test_string_condition_greater_than(self, app):
        """Условие score > 80."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.score = 85; return state"},
                "pass": {"type": "code", "code": "def run(state): state.result = 'passed'; return state"},
            },
            "edges": [
                {"from": "start", "to": "pass", "condition": "score > 80"}
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        assert result.result == "passed"

    @pytest.mark.asyncio
    async def test_string_condition_nested_field(self, app):
        """Условие user.role == 'admin'."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.user = {'role': 'admin'}; return state"},
                "admin": {"type": "code", "code": "def run(state): state.result = 'admin_access'; return state"},
            },
            "edges": [
                {"from": "start", "to": "admin", "condition": "user.role == 'admin'"}
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        assert result.result == "admin_access"

    @pytest.mark.asyncio
    async def test_string_condition_false_no_transition(self, app):
        """Если условие false - перехода нет."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.route = 'other'; return state"},
                "order": {"type": "code", "code": "def run(state): state.result = 'order_node'; return state"},
            },
            "edges": [
                {"from": "start", "to": "order", "condition": "route == 'order'"}
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        # order_node не выполнился - нет подходящего edge
        assert not hasattr(result, 'result') or result.result is None


class TestSimpleObjectConditions:
    """Тесты объектного формата: {"type": "simple", ...}."""

    @pytest.mark.asyncio
    async def test_simple_equals(self, app):
        """Simple условие: route == 'complaint'."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.route = 'complaint'; return state"},
                "complaint": {"type": "code", "code": "def run(state): state.result = 'complaint_handler'; return state"},
            },
            "edges": [
                {
                    "from": "start", 
                    "to": "complaint", 
                    "condition": {
                        "type": "simple",
                        "variable": "route",
                        "operator": "==",
                        "value": "complaint"
                    }
                }
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        assert result.result == "complaint_handler"

    @pytest.mark.asyncio
    async def test_simple_not_equals(self, app):
        """Simple условие: status != 'blocked'."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.status = 'active'; return state"},
                "proceed": {"type": "code", "code": "def run(state): state.result = 'ok'; return state"},
            },
            "edges": [
                {
                    "from": "start", 
                    "to": "proceed", 
                    "condition": {
                        "type": "simple",
                        "variable": "status",
                        "operator": "!=",
                        "value": "blocked"
                    }
                }
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        assert result.result == "ok"

    @pytest.mark.asyncio
    async def test_simple_greater_than(self, app):
        """Simple условие: priority > 5."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.priority = 10; return state"},
                "high": {"type": "code", "code": "def run(state): state.result = 'high_priority'; return state"},
            },
            "edges": [
                {
                    "from": "start", 
                    "to": "high", 
                    "condition": {
                        "type": "simple",
                        "variable": "priority",
                        "operator": ">",
                        "value": 5
                    }
                }
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        assert result.result == "high_priority"

    @pytest.mark.asyncio
    async def test_simple_less_or_equal(self, app):
        """Simple условие: count <= 3."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.count = 2; return state"},
                "few": {"type": "code", "code": "def run(state): state.result = 'few_items'; return state"},
            },
            "edges": [
                {
                    "from": "start", 
                    "to": "few", 
                    "condition": {
                        "type": "simple",
                        "variable": "count",
                        "operator": "<=",
                        "value": 3
                    }
                }
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        assert result.result == "few_items"


class TestPythonConditions:
    """Тесты Python условий: {"type": "python", "code": "..."}."""

    @pytest.mark.asyncio
    async def test_python_simple_check(self, app):
        """Python условие: простая проверка поля."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.category = 'urgent'; return state"},
                "urgent": {"type": "code", "code": "def run(state): state.result = 'urgent_handler'; return state"},
            },
            "edges": [
                {
                    "from": "start", 
                    "to": "urgent", 
                    "condition": {
                        "type": "python",
                        "code": "def check(state):\n    return state.get('category') == 'urgent'"
                    }
                }
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        assert result.result == "urgent_handler"

    @pytest.mark.asyncio
    async def test_python_complex_logic(self, app):
        """Python условие: сложная логика с несколькими условиями."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.score = 85; state.verified = True; return state"},
                "approved": {"type": "code", "code": "def run(state): state.result = 'approved'; return state"},
            },
            "edges": [
                {
                    "from": "start", 
                    "to": "approved", 
                    "condition": {
                        "type": "python",
                        "code": """def check(state):
    score = state.get('score', 0)
    verified = state.get('verified', False)
    return score >= 80 and verified
"""
                    }
                }
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        assert result.result == "approved"

    @pytest.mark.asyncio
    async def test_python_with_list_check(self, app):
        """Python условие: проверка элемента в списке."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.tags = ['vip', 'premium']; return state"},
                "vip": {"type": "code", "code": "def run(state): state.result = 'vip_treatment'; return state"},
            },
            "edges": [
                {
                    "from": "start", 
                    "to": "vip", 
                    "condition": {
                        "type": "python",
                        "code": "def check(state):\n    tags = state.get('tags', [])\n    return 'vip' in tags"
                    }
                }
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        assert result.result == "vip_treatment"

    @pytest.mark.asyncio
    async def test_python_condition_returns_false(self, app):
        """Python условие возвращает False - переход не происходит."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.value = 10; return state"},
                "target": {"type": "code", "code": "def run(state): state.result = 'reached'; return state"},
            },
            "edges": [
                {
                    "from": "start", 
                    "to": "target", 
                    "condition": {
                        "type": "python",
                        "code": "def check(state):\n    return state.get('value', 0) > 100"
                    }
                }
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        # target node не выполнился
        assert not hasattr(result, 'result') or result.result is None

    @pytest.mark.asyncio
    async def test_python_invalid_code_raises(self, app):
        """Python условие с ошибкой выполнения check — ValueError."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): return state"},
                "target": {"type": "code", "code": "def run(state): state.result = 'reached'; return state"},
            },
            "edges": [
                {
                    "from": "start",
                    "to": "target",
                    "condition": {
                        "type": "python",
                        "code": "def check(state):\n    return undefined_variable",
                    },
                }
            ],
        })

        state = make_state()
        with pytest.raises(ValueError, match="Python-условие ребра"):
            await agent.run(state)

    @pytest.mark.asyncio
    async def test_python_missing_check_function_raises(self, app):
        """Python условие без функции check — ValueError."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): return state"},
                "target": {"type": "code", "code": "def run(state): state.result = 'reached'; return state"},
            },
            "edges": [
                {
                    "from": "start",
                    "to": "target",
                    "condition": {
                        "type": "python",
                        "code": "def wrong_name(state):\n    return True",
                    },
                }
            ],
        })

        state = make_state()
        with pytest.raises(ValueError, match="функцией check"):
            await agent.run(state)


class TestUnconditionalEdges:
    """Тесты безусловных переходов (без condition)."""

    @pytest.mark.asyncio
    async def test_edge_without_condition(self, app):
        """Edge без condition - безусловный переход."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): return state"},
                "next": {"type": "code", "code": "def run(state): state.result = 'next_executed'; return state"},
            },
            "edges": [
                {"from": "start", "to": "next"}
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        assert result.result == "next_executed"

    @pytest.mark.asyncio
    async def test_edge_with_null_condition(self, app):
        """Edge с condition=None - безусловный переход."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): return state"},
                "next": {"type": "code", "code": "def run(state): state.result = 'executed'; return state"},
            },
            "edges": [
                {"from": "start", "to": "next", "condition": None}
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        assert result.result == "executed"


class TestMultipleEdges:
    """Тесты с несколькими edges от одной ноды."""

    @pytest.mark.asyncio
    async def test_first_matching_condition_wins(self, app):
        """Первый подходящий edge срабатывает."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.route = 'order'; return state"},
                "order": {"type": "code", "code": "def run(state): state.result = 'order_handler'; return state"},
                "complaint": {"type": "code", "code": "def run(state): state.result = 'complaint_handler'; return state"},
            },
            "edges": [
                {"from": "start", "to": "order", "condition": "route == 'order'"},
                {"from": "start", "to": "complaint", "condition": "route == 'complaint'"},
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        assert result.result == "order_handler"

    @pytest.mark.asyncio
    async def test_fallback_edge_without_condition(self, app):
        """Безусловный edge как fallback."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "def run(state): state.route = 'unknown'; return state"},
                "known": {"type": "code", "code": "def run(state): state.result = 'known'; return state"},
                "fallback": {"type": "code", "code": "def run(state): state.result = 'fallback'; return state"},
            },
            "edges": [
                {"from": "start", "to": "known", "condition": "route == 'order'"},
                {"from": "start", "to": "fallback"},
            ]
        })
        
        state = make_state()
        result = await agent.run(state)
        
        # Первое условие не сработало, но есть безусловный fallback
        assert result.result == "fallback"
