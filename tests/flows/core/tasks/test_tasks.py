"""
Тесты для tasks.

Используется реальный Redis (через docker-compose-test.yaml).
"""

from datetime import datetime, timezone

import pytest

from core.context import set_context

from apps.flows_worker.broker import broker
from apps.flows.src.tasks.flow_tasks import process_flow_task
from apps.flows.src.tasks.eval_task import execute_inline_code
from apps.flows.src.tasks.tool_tasks import execute_tool
import apps.idle_worker.tasks.calendar_sync_tasks as calendar_sync_tasks
from core.models import (
    CalendarEventSource,
    CalendarIntegration,
    CalendarIntegrationCredentials,
    CalendarIntegrationSettings,
    CalendarProvider,
)


class TestBroker:
    """Тесты broker."""

    def test_broker_is_redis(self):
        """Broker использует Redis."""
        from taskiq_redis import RedisStreamBroker

        assert isinstance(broker, RedisStreamBroker)


@pytest.mark.asyncio
async def test_calendar_sync_tick_returns_zero_when_disabled(monkeypatch):
    class _FakeCalendarSync:
        enabled = False

    class _FakeDatabase:
        shared_url = "postgresql://test"

    class _FakeSettings:
        calendar_sync = _FakeCalendarSync()
        database = _FakeDatabase()

    async def _list_sync_enabled(self, *, limit: int):
        _ = (self, limit)
        raise AssertionError("list_sync_enabled must not be called when task is disabled")

    monkeypatch.setattr(calendar_sync_tasks, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(calendar_sync_tasks.CalendarIntegrationSqlRepository, "list_sync_enabled", _list_sync_enabled)

    result = await calendar_sync_tasks.calendar_sync_tick()
    assert result["integrations_total"] == 0
    assert result["notifications_sent"] == 0


@pytest.mark.asyncio
async def test_calendar_sync_tick_detects_new_events_and_sends_notification(monkeypatch):
    class _FakeCalendarSync:
        enabled = True
        lookback_days = 7
        lookahead_months = 3
        batch_size = 100
        max_integrations_per_tick = 1000
        max_parallel_integrations = 2
        notification_dedup_ttl_seconds = 86400

    class _FakeDatabase:
        shared_url = "postgresql://test"

    class _FakeSettings:
        calendar_sync = _FakeCalendarSync()
        database = _FakeDatabase()

    integration = CalendarIntegration(
        integration_id="integration-1",
        company_id="company-1",
        user_id="user-1",
        provider=CalendarProvider.GOOGLE,
        credentials=CalendarIntegrationCredentials(access_token="token", refresh_token="refresh"),
        settings=CalendarIntegrationSettings(
            default_calendar_id="primary",
            sync_enabled=True,
            sync_inbound_enabled=True,
            sync_outbound_enabled=False,
            notifications_enabled=True,
        ),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    async def _list_sync_enabled(self, *, limit: int):
        _ = (self, limit)
        return [integration]

    class _FakeEvent:
        def __init__(self, event_id: str):
            self.event_id = event_id

    class _FakeCalendarService:
        def __init__(self) -> None:
            self._list_calls = 0

        async def run_sync(self, **kwargs):
            _ = kwargs
            return {"imported": 1, "exported": 0}

        async def list_events(self, **kwargs):
            _ = kwargs
            self._list_calls += 1
            if self._list_calls == 1:
                return [_FakeEvent("existing-event")]
            return [_FakeEvent("existing-event"), _FakeEvent("new-event")]

    class _FakeStorage:
        def __init__(self) -> None:
            self._data = {}

        async def get(self, key: str, force_global: bool = False):
            _ = force_global
            return self._data.get(key)

        async def set(self, key: str, value: str, ttl: int, force_global: bool = False):
            _ = (ttl, force_global)
            self._data[key] = value
            return True

    sent_notifications = {"count": 0}

    async def _notify_user(user_id, notification):
        _ = (user_id, notification)
        sent_notifications["count"] += 1

    fake_container = type(
        "Container",
        (),
        {
            "calendar_service": _FakeCalendarService(),
            "shared_storage": _FakeStorage(),
        },
    )()

    monkeypatch.setattr(calendar_sync_tasks, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(calendar_sync_tasks.CalendarIntegrationSqlRepository, "list_sync_enabled", _list_sync_enabled)
    monkeypatch.setattr(calendar_sync_tasks, "get_container", lambda: fake_container)
    monkeypatch.setattr(calendar_sync_tasks, "notify_user", _notify_user)

    first = await calendar_sync_tasks.calendar_sync_tick()
    second = await calendar_sync_tasks.calendar_sync_tick()

    assert first["integrations_total"] == 1
    assert first["events_new"] == 1
    assert first["notifications_sent"] == 1
    assert second["notifications_sent"] == 0
    assert sent_notifications["count"] == 1


class TestProcessAgentTask:
    """Тесты process_flow_task."""

    @pytest.fixture
    async def setup_flow(self, app, container):
        """Создает flow для тестов."""
        from apps.flows.src.models import FlowConfig

        flow_config = FlowConfig(
            flow_id="task_test_flow",
            name="Task Test Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "code",
                    "code": "async def run(state):\n    state['response'] = 'Initialized'\n    return state",
                }
            },
            edges=[{"from": "main", "to": None}],
        )
        await container.flow_repository.set(flow_config)

    @pytest.mark.asyncio
    async def test_process_flow_task_executes_flow(self, app, container, setup_flow, unique_id, mock_context):
        """process_flow_task выполняет flow."""
        session_id = f"task_test_flow:test-session-{unique_id}"
        mock_context.session_id = session_id
        mock_context.flow_id = "task_test_flow"
        mock_context.user.user_id = "test-user-1"
        result = await process_flow_task(
            flow_id="task_test_flow",
            session_id=session_id,
            user_id="test-user-1",
            content="Test message",
            context_data=mock_context.model_dump(),
        )

        assert result is not None
        assert "response" in result
        assert "status" in result

    @pytest.mark.asyncio
    async def test_process_flow_task_returns_completed_status(
        self, app, container, setup_flow, unique_id, mock_context
    ):
        """process_flow_task возвращает status=completed."""
        session_id = f"task_test_flow:test-session-{unique_id}"
        mock_context.session_id = session_id
        mock_context.flow_id = "task_test_flow"
        mock_context.user.user_id = "test-user-1"
        result = await process_flow_task(
            flow_id="task_test_flow",
            session_id=session_id,
            user_id="test-user-1",
            content="Hello",
            context_data=mock_context.model_dump(),
        )

        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_process_flow_task_raises_on_unknown_flow(self, app, container, unique_id, mock_context):
        """process_flow_task выбрасывает ошибку для несуществующего flow."""
        session_id = f"nonexistent_flow:test-session-{unique_id}"
        mock_context.session_id = session_id
        mock_context.flow_id = "nonexistent_flow"
        with pytest.raises(ValueError, match="Flow.*не найден|Agent.*не найден|not found"):
            await process_flow_task(
                flow_id="nonexistent_flow",
                session_id=session_id,
                user_id="test-user",
                content="Test",
                context_data=mock_context.model_dump(),
            )


class TestProcessAgentTaskResume:
    """Тесты resume через process_flow_task."""

    @pytest.fixture
    async def setup_flow_with_state(self, app, container, unique_id):
        """Создает flow и state для тестов resume."""
        from apps.flows.src.models import FlowConfig
        from apps.flows.src.container import get_container

        flow_config = FlowConfig(
            flow_id="interrupt_test_flow",
            name="Interrupt Test Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "code",
                    "code": "async def run(state):\n    state['response'] = 'Resumed'\n    return state",
                }
            },
            edges=[{"from": "main", "to": None}],
        )
        await container.flow_repository.set(flow_config)

        session_id = f"interrupt_test_flow:interrupt-session-{unique_id}"
        state_manager = get_container().state_manager
        await state_manager.save_state(
            session_id,
            {
                "task_id": "test-task",
                "context_id": "test-context",
                "user_id": "test-user",
                "session_id": session_id,
                "current_node": "main",
                "interrupt": {"question": "What is your name?"},
                "skill_id": "default",
                "content": "Hello",
            },
        )
        return session_id

    @pytest.mark.asyncio
    async def test_process_flow_task_resumes_flow(
        self, app, container, setup_flow_with_state, mock_context
    ):
        """process_flow_task с is_resume=True продолжает flow."""
        session_id = setup_flow_with_state
        mock_context.session_id = session_id
        mock_context.flow_id = "interrupt_test_flow"
        result = await process_flow_task(
            flow_id="interrupt_test_flow",
            session_id=session_id,
            user_id="test-user",
            content="My name is Test",
            is_resume=True,
            context_data=mock_context.model_dump(),
        )

        assert result is not None
        assert "status" in result

    @pytest.mark.asyncio
    async def test_process_flow_task_resume_raises_on_unknown_flow(
        self, app, container, unique_id, mock_context
    ):
        """process_flow_task с is_resume выбрасывает ошибку для несуществующего flow."""
        session_id = f"nonexistent_flow:test-session-{unique_id}"
        mock_context.session_id = session_id
        mock_context.flow_id = "nonexistent_flow"
        with pytest.raises(ValueError, match="Flow.*не найден|Agent.*не найден|not found"):
            await process_flow_task(
                flow_id="nonexistent_flow",
                session_id=session_id,
                user_id="test-user",
                content="Test answer",
                is_resume=True,
                context_data=mock_context.model_dump(),
            )


class TestProcessFlowTaskSequentialLlmNodes:
    """process_flow_task обходит граф: несколько llm_node подряд по рёбрам."""

    @pytest.fixture
    async def two_llm_flow_id(self, app, container, unique_id):
        from apps.flows.src.models import FlowConfig

        flow_id = f"two_llm_seq_{unique_id}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Two LLM sequential",
            entry="first",
            nodes={
                "first": {
                    "type": "llm_node",
                    "prompt": "Reply exactly: FIRST_OK",
                    "tools": [],
                },
                "second": {
                    "type": "llm_node",
                    "prompt": "Reply exactly: SECOND_OK",
                    "tools": [],
                },
            },
            edges=[{"from": "first", "to": "second"}],
        )
        await container.flow_repository.set(flow_config)
        return flow_id

    @pytest.mark.asyncio
    async def test_both_llm_nodes_run_via_process_task(
        self,
        app,
        container,
        two_llm_flow_id,
        unique_id,
        mock_context,
        mock_llm_with_queue,
    ):
        mock_llm_with_queue(["FIRST_OK", "SECOND_OK"])
        flow_id = two_llm_flow_id
        ctx = f"ctx-{unique_id}"
        session_id = f"{flow_id}:{ctx}"
        mock_context.session_id = session_id
        mock_context.flow_id = flow_id
        mock_context.user.user_id = "test-user-1"

        result = await process_flow_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id="test-user-1",
            content="hello",
            context_data=mock_context.model_dump(),
        )

        assert result["status"] == "completed"
        assert result["response"] == "SECOND_OK"

        set_context(mock_context)
        saved = await container.state_manager.get_state(session_id)
        assert saved is not None
        assert "first" in saved.node_history
        assert "second" in saved.node_history


class TestExecuteInlineCode:
    """Тесты execute_inline_code."""

    @pytest.mark.asyncio
    async def test_execute_inline_code_simple(self):
        """execute_inline_code выполняет простой код."""
        from core.state import ExecutionState
        
        code = """
async def run(state):
    state.result = state.x * 2
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test",
            x=21
        )
        result_dict = await execute_inline_code(code, state.model_dump(exclude_none=False))
        assert result_dict["result"] == 42

    @pytest.mark.asyncio
    async def test_execute_inline_code_async(self):
        """execute_inline_code выполняет async код."""
        from core.state import ExecutionState
        
        code = """
async def run(state):
    state.async_done = True
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test"
        )
        result_dict = await execute_inline_code(code, state.model_dump(exclude_none=False))
        assert result_dict["async_done"] is True

    @pytest.mark.asyncio
    async def test_execute_inline_code_with_json(self):
        """execute_inline_code с json модулем."""
        from core.state import ExecutionState
        
        code = """
import json

async def run(state):
    data = json.loads(state.json_str)
    state.parsed = data
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test",
            json_str='{"name": "test"}'
        )
        result_dict = await execute_inline_code(code, state.model_dump(exclude_none=False))
        assert result_dict["parsed"]["name"] == "test"

    @pytest.mark.asyncio
    async def test_execute_inline_code_preserves_state(self):
        """execute_inline_code сохраняет state."""
        from core.state import ExecutionState
        
        code = """
async def run(state):
    state.new_key = 'added'
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test",
            existing="value"
        )
        result_dict = await execute_inline_code(code, state.model_dump(exclude_none=False))
        assert result_dict["existing"] == "value"
        assert result_dict["new_key"] == "added"


class TestExecuteTool:
    """Тесты execute_tool."""

    @pytest.fixture
    def calculator_config(self):
        """Inline конфиг calculator tool."""
        return {
            "tool_id": "test_calculator",
            "description": "Calculator for tests",
            "code": """
async def execute(args, state):
    import re
    
    expr = args.get("expression", "0")
    
    # Простой калькулятор без eval/ast
    # Поддерживает +, -, *, / с учётом приоритета
    def parse_expr(s):
        s = s.replace(" ", "")
        return parse_add_sub(s, 0)[0]
    
    def parse_add_sub(s, i):
        left, i = parse_mul_div(s, i)
        while i < len(s) and s[i] in "+-":
            op = s[i]
            right, i = parse_mul_div(s, i + 1)
            left = left + right if op == "+" else left - right
        return left, i
    
    def parse_mul_div(s, i):
        left, i = parse_atom(s, i)
        while i < len(s) and s[i] in "*/":
            op = s[i]
            right, i = parse_atom(s, i + 1)
            left = left * right if op == "*" else left / right
        return left, i
    
    def parse_atom(s, i):
        if s[i] == "(":
            val, i = parse_add_sub(s, i + 1)
            return val, i + 1  # skip )
        # parse number
        j = i
        while j < len(s) and (s[j].isdigit() or s[j] == "."):
            j += 1
        return float(s[i:j]), j
    
    result = parse_expr(expr)
    return str(int(result) if result == int(result) else result)
""",
        }

    @pytest.mark.asyncio
    async def test_execute_tool_calculator(self, app, calculator_config):
        """execute_tool выполняет calculator tool."""
        from core.state import ExecutionState
        
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test"
        )
        
        result = await execute_tool(
            calculator_config,
            {"expression": "2 + 2"},
            state.model_dump(exclude_none=False)
        )
        
        assert result["tool_id"] == "test_calculator"
        assert "4" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_tool_returns_result_structure(self, app, calculator_config):
        """execute_tool возвращает структуру с tool_id и result."""
        from core.state import ExecutionState
        
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test"
        )
        
        result = await execute_tool(
            calculator_config,
            {"expression": "10 * 5"},
            state.model_dump(exclude_none=False)
        )
        
        assert "tool_id" in result
        assert "result" in result
        assert result["tool_id"] == "test_calculator"
        assert "50" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_tool_with_state(self, app, calculator_config):
        """execute_tool получает state."""
        from core.state import ExecutionState
        
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test",
            some_context="value"
        )
        
        result = await execute_tool(
            calculator_config,
            {"expression": "7 - 3"},
            state.model_dump(exclude_none=False)
        )
        
        assert "4" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_tool_raises_on_unknown_tool(self, app):
        """execute_tool выбрасывает ошибку для tool без code."""
        from core.state import ExecutionState
        
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test"
        )
        
        with pytest.raises(ValueError, match="code"):
            await execute_tool(
                {"tool_id": "no_code_tool"},
                {},
                state.model_dump(exclude_none=False)
            )

    @pytest.mark.asyncio
    async def test_execute_tool_handles_interrupt(self, app):
        """execute_tool обрабатывает FlowInterrupt."""
        from core.state import ExecutionState
        
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test"
        )
        
        ask_user_config = {
            "tool_id": "test_ask_user",
            "description": "Ask user question",
            "code": """
async def execute(args, state):
    question = args.get("question", "")
    raise FlowInterrupt(question=question)
""",
        }
        result = await execute_tool(
            ask_user_config,
            {"question": "What is your name?"},
            state.model_dump(exclude_none=False)
        )
        
        assert result["tool_id"] == "test_ask_user"
        assert result["result"] is None
        assert "interrupt" in result
        assert result["interrupt"]["question"] == "What is your name?"

    @pytest.mark.asyncio
    async def test_execute_tool_complex_expression(self, app, calculator_config):
        """execute_tool с комплексным выражением."""
        from core.state import ExecutionState
        
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test"
        )
        
        result = await execute_tool(
            calculator_config,
            {"expression": "(10 + 5) * 2 - 8 / 4"},
            state.model_dump(exclude_none=False)
        )
        
        assert result["tool_id"] == "test_calculator"
        assert "28" in result["result"]
