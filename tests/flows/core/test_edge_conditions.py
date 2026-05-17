"""
Тесты вычисления условий переходов (edge conditions).

Три формата условий:
1. Legacy строка: "route == 'order'"
2. Simple объект: {"type": "simple", "variable": "route", "operator": "==", "value": "order"}
3. Code runner условие: {"type": "code", "language": "python|javascript|typescript|go|csharp", "code": "..."}
"""

import pytest

from apps.flows.src.runtime.flow import Flow
from core.errors import FlowPrematureCompletionError
from core.state import ExecutionState


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
                "start": {"type": "code", "code": "async def run(args, state): state.route = 'order'; return state"},
                "order": {"type": "code", "code": "async def run(args, state): state.result = 'order_node'; return state"},
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
                "start": {"type": "code", "code": "async def run(args, state): state.count = 5; return state"},
                "five": {"type": "code", "code": "async def run(args, state): state.result = 'five'; return state"},
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
                "start": {"type": "code", "code": "async def run(args, state): state.status = 'ok'; return state"},
                "proceed": {"type": "code", "code": "async def run(args, state): state.result = 'proceeded'; return state"},
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
                "start": {"type": "code", "code": "async def run(args, state): state.score = 85; return state"},
                "pass": {"type": "code", "code": "async def run(args, state): state.result = 'passed'; return state"},
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
                "start": {"type": "code", "code": "async def run(args, state): state.user = {'role': 'admin'}; return state"},
                "admin": {"type": "code", "code": "async def run(args, state): state.result = 'admin_access'; return state"},
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
        """Если условие false — единственный исход условный: FlowPrematureCompletionError."""
        agent = await Flow.from_config({
            "id": "test",
            "name": "Test",
            "entry": "start",
            "nodes": {
                "start": {"type": "code", "code": "async def run(args, state): state.route = 'other'; return state"},
                "order": {"type": "code", "code": "async def run(args, state): state.result = 'order_node'; return state"},
            },
            "edges": [
                {"from": "start", "to": "order", "condition": "route == 'order'"}
            ]
        })

        state = make_state()
        with pytest.raises(FlowPrematureCompletionError) as exc_info:
            await agent.run(state)
        assert exc_info.value.payload.get("reason") == "no_conditional_match"


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
                "start": {"type": "code", "code": "async def run(args, state): state.route = 'complaint'; return state"},
                "complaint": {"type": "code", "code": "async def run(args, state): state.result = 'complaint_handler'; return state"},
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
                "start": {"type": "code", "code": "async def run(args, state): state.status = 'active'; return state"},
                "proceed": {"type": "code", "code": "async def run(args, state): state.result = 'ok'; return state"},
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
                "start": {"type": "code", "code": "async def run(args, state): state.priority = 10; return state"},
                "high": {"type": "code", "code": "async def run(args, state): state.result = 'high_priority'; return state"},
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
                "start": {"type": "code", "code": "async def run(args, state): state.count = 2; return state"},
                "few": {"type": "code", "code": "async def run(args, state): state.result = 'few_items'; return state"},
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
                "start": {"type": "code", "code": "async def run(args, state): return state"},
                "next": {"type": "code", "code": "async def run(args, state): state.result = 'next_executed'; return state"},
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
                "start": {"type": "code", "code": "async def run(args, state): return state"},
                "next": {"type": "code", "code": "async def run(args, state): state.result = 'executed'; return state"},
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
                "start": {"type": "code", "code": "async def run(args, state): state.route = 'order'; return state"},
                "order": {"type": "code", "code": "async def run(args, state): state.result = 'order_handler'; return state"},
                "complaint": {"type": "code", "code": "async def run(args, state): state.result = 'complaint_handler'; return state"},
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
                "start": {"type": "code", "code": "async def run(args, state): state.route = 'unknown'; return state"},
                "known": {"type": "code", "code": "async def run(args, state): state.result = 'known'; return state"},
                "fallback": {"type": "code", "code": "async def run(args, state): state.result = 'fallback'; return state"},
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
