"""
Тесты для tasks.

Используется реальный Redis (через docker-compose-test.yaml).
"""

import pytest

from apps.broker.broker import broker
from apps.agents.src.tasks.agent_tasks import process_agent_task
from apps.agents.src.tasks.eval_task import execute_inline_code
from apps.agents.src.tasks.tool_tasks import execute_tool


class TestBroker:
    """Тесты broker."""

    def test_broker_is_redis(self):
        """Broker использует Redis."""
        from taskiq_redis import RedisStreamBroker

        assert isinstance(broker, RedisStreamBroker)


class TestProcessAgentTask:
    """Тесты process_agent_task."""

    @pytest.fixture
    async def setup_flow(self, app, container):
        """Создает flow для тестов."""
        from apps.agents.src.models import AgentConfig

        agent_config = AgentConfig(
            agent_id="task_test_flow",
            name="Task Test Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "function",
                    "code": "def run(state):\n    state['response'] = 'Initialized'\n    return state",
                }
            },
            edges=[{"from": "main", "to": None}],
        )
        await container.agent_repository.set(agent_config)

    @pytest.mark.asyncio
    async def test_process_agent_task_executes_flow(self, app, container, setup_flow, unique_id, mock_context):
        """process_agent_task выполняет flow."""
        session_id = f"task_test_flow:test-session-{unique_id}"
        mock_context.session_id = session_id
        mock_context.agent_id = "task_test_flow"
        mock_context.user.user_id = "test-user-1"
        result = await process_agent_task(
            agent_id="task_test_flow",
            session_id=session_id,
            user_id="test-user-1",
            content="Test message",
            context_data=mock_context.model_dump(),
        )

        assert result is not None
        assert "response" in result
        assert "status" in result

    @pytest.mark.asyncio
    async def test_process_agent_task_returns_completed_status(
        self, app, container, setup_flow, unique_id, mock_context
    ):
        """process_agent_task возвращает status=completed."""
        session_id = f"task_test_flow:test-session-{unique_id}"
        mock_context.session_id = session_id
        mock_context.agent_id = "task_test_flow"
        mock_context.user.user_id = "test-user-1"
        result = await process_agent_task(
            agent_id="task_test_flow",
            session_id=session_id,
            user_id="test-user-1",
            content="Hello",
            context_data=mock_context.model_dump(),
        )

        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_process_agent_task_raises_on_unknown_flow(self, app, container, unique_id, mock_context):
        """process_agent_task выбрасывает ошибку для несуществующего flow."""
        session_id = f"nonexistent_flow:test-session-{unique_id}"
        mock_context.session_id = session_id
        mock_context.agent_id = "nonexistent_flow"
        with pytest.raises(ValueError, match="Agent.*не найден|Agent.*not found"):
            await process_agent_task(
                agent_id="nonexistent_flow",
                session_id=session_id,
                user_id="test-user",
                content="Test",
                context_data=mock_context.model_dump(),
            )


class TestProcessAgentTaskResume:
    """Тесты resume через process_agent_task."""

    @pytest.fixture
    async def setup_flow_with_state(self, app, container, unique_id):
        """Создает flow и state для тестов resume."""
        from apps.agents.src.models import AgentConfig
        from apps.agents.src.container import get_container

        agent_config = AgentConfig(
            agent_id="interrupt_test_flow",
            name="Interrupt Test Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "function",
                    "code": "def run(state):\n    state['response'] = 'Resumed'\n    return state",
                }
            },
            edges=[{"from": "main", "to": None}],
        )
        await container.agent_repository.set(agent_config)

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
    async def test_process_agent_task_resumes_flow(
        self, app, container, setup_flow_with_state, mock_context
    ):
        """process_agent_task с is_resume=True продолжает flow."""
        session_id = setup_flow_with_state
        mock_context.session_id = session_id
        mock_context.agent_id = "interrupt_test_flow"
        result = await process_agent_task(
            agent_id="interrupt_test_flow",
            session_id=session_id,
            user_id="test-user",
            content="My name is Test",
            is_resume=True,
            context_data=mock_context.model_dump(),
        )

        assert result is not None
        assert "status" in result

    @pytest.mark.asyncio
    async def test_process_agent_task_resume_raises_on_unknown_flow(
        self, app, container, unique_id, mock_context
    ):
        """process_agent_task с is_resume выбрасывает ошибку для несуществующего flow."""
        session_id = f"nonexistent_flow:test-session-{unique_id}"
        mock_context.session_id = session_id
        mock_context.agent_id = "nonexistent_flow"
        with pytest.raises(ValueError, match="Agent.*не найден|Agent.*not found"):
            await process_agent_task(
                agent_id="nonexistent_flow",
                session_id=session_id,
                user_id="test-user",
                content="Test answer",
                is_resume=True,
                context_data=mock_context.model_dump(),
            )


class TestExecuteInlineCode:
    """Тесты execute_inline_code."""

    @pytest.mark.asyncio
    async def test_execute_inline_code_simple(self):
        """execute_inline_code выполняет простой код."""
        from core.state import ExecutionState
        
        code = """
def run(state):
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

def run(state):
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
def run(state):
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
def execute(args, state):
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
        """execute_tool обрабатывает AgentInterrupt."""
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
from apps.agents.src.agent.exceptions import AgentInterrupt

def execute(args, state):
    question = args.get("question", "")
    raise AgentInterrupt(question)
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
