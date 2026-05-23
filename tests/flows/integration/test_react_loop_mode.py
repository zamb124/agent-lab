"""
Тесты для ReactLoopMode: AUTO и EXPLICIT.

Проверяем поведение ReAct цикла:
- AUTO: текстовый ответ без tool_calls завершает агента
- EXPLICIT: выход только через exit_tool (finish по умолчанию)

ПРАВИЛО: Мок только LLM. Tools, state, flow - реальные.
"""

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.models import FlowConfig
from core.errors import FlowExecutionError
from core.state import ExecutionState

# Inline tool конфиги для тестов
INLINE_CALCULATOR = {
    "tool_id": "calculator",
    "description": "Вычисляет математические выражения",
    "args_schema": {"expression": {"type": "string"}},
    "code": """async def execute(args: dict, state: dict = None):
    import ast
    import operator
    expr = args.get('expression', '0')
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
    def _eval(node):
        if isinstance(node, ast.Expression): return _eval(node.body)
        if isinstance(node, ast.Constant): return node.value
        if isinstance(node, ast.BinOp): return ops[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub): return -_eval(node.operand)
        raise ValueError(f"Unsupported: {type(node)}")
    return f"Результат: {_eval(ast.parse(expr, mode='eval'))}"
"""
}

INLINE_FINISH = {
    "tool_id": "finish",
    "description": "Завершает агента",
    "args_schema": {"answer": {"type": "string"}},
    "code": "async def execute(args: dict, state: dict = None):\n    return args.get('answer', '')",
    "react_role": "exit"
}

INLINE_ASK_USER = {
    "tool_id": "ask_user",
    "description": "Задает вопрос пользователю",
    "args_schema": {"question": {"type": "string"}},
    "code": """async def execute(args: dict, state: dict = None):
    from apps.flows.src.runtime.exceptions import FlowInterrupt
    q = args.get("question")
    if not q or not str(q).strip():
        raise ValueError("ask_user: question обязателен")
    raise FlowInterrupt(question=str(q).strip())
"""
}


class TestReactLoopModeAuto:
    """
    Тесты режима AUTO (по умолчанию).
    Агент завершается когда LLM возвращает текст без tool_calls.
    """

    async def test_auto_mode_text_response_exits(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        В режиме AUTO текстовый ответ сразу завершает агента.
        """
        flow_id = f"test_auto_text_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Auto Mode Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Ты помощник. Отвечай на вопросы.",
                    "tools": [INLINE_CALCULATOR]
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        # LLM сразу возвращает текст - агент завершается
        mock_llm_with_queue([
            {"type": "text", "content": "Привет! Чем могу помочь?"},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Привет"
        )
        result = await flow.run(state)

        assert "response" in result
        assert result["response"] == "Привет! Чем могу помочь?"

        await container.flow_repository.delete(flow_id)

    async def test_auto_mode_tool_then_text_exits(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        В режиме AUTO: tool_call -> result -> текст = завершение.
        """
        flow_id = f"test_auto_tool_text_{unique_id}"
        container = get_container()

        calc_code = """
async def execute(args: dict, state: dict = None):
    import ast
    import operator
    expr = args.get('expression', '0')
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
    def _eval(node):
        if isinstance(node, ast.Expression): return _eval(node.body)
        if isinstance(node, ast.Constant): return node.value
        if isinstance(node, ast.BinOp): return ops[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub): return -_eval(node.operand)
        raise ValueError(f"Unsupported: {type(node)}")
    return str(_eval(ast.parse(expr, mode='eval')))
"""

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Auto Mode Tool Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй калькулятор для вычислений.",
                    "tools": [{
                        "tool_id": "calc",
                        "description": "Калькулятор",
                        "code": calc_code,
                        "args_schema": {"expression": {"type": "string"}}
                    }]
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        # LLM вызывает tool, потом возвращает текст
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "calc", "args": {"expression": "5+3"}},
            {"type": "text", "content": "Результат: 8"},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="5+3?"
        )
        result = await flow.run(state)

        assert "response" in result
        assert "8" in result["response"]

        await container.flow_repository.delete(flow_id)

    async def test_auto_mode_no_react_config_defaults_to_auto(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        Без react конфига используется AUTO режим по умолчанию.
        """
        flow_id = f"test_default_auto_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Default Auto Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Просто отвечай.",
                    "tools": []
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {"type": "text", "content": "Ответ по умолчанию"},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test"
        )
        result = await flow.run(state)

        assert result["response"] == "Ответ по умолчанию"

        await container.flow_repository.delete(flow_id)


class TestReactLoopModeExplicit:
    """
    Тесты режима EXPLICIT.
    Агент завершается ТОЛЬКО при вызове exit_tool (finish).
    """

    async def test_explicit_mode_finish_tool_exits(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        В режиме EXPLICIT вызов finish завершает агента.
        """
        flow_id = f"test_explicit_finish_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Explicit Mode Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Отвечай через finish tool.",
                    "tools": [INLINE_FINISH],
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "finish"
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        # LLM вызывает finish - агент завершается
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Готово!"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Завершись"
        )
        result = await flow.run(state)

        assert "response" in result
        assert result["response"] == "Готово!"

        await container.flow_repository.delete(flow_id)

    async def test_explicit_mode_tool_then_finish_exits(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        В режиме EXPLICIT: tool -> finish = завершение с результатом.
        """
        flow_id = f"test_explicit_tool_finish_{unique_id}"
        container = get_container()

        calc_code = """
async def execute(args: dict, state: dict = None):
    import ast
    import operator
    expr = args.get('expression', '0')
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
    def _eval(node):
        if isinstance(node, ast.Expression): return _eval(node.body)
        if isinstance(node, ast.Constant): return node.value
        if isinstance(node, ast.BinOp): return ops[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub): return -_eval(node.operand)
        raise ValueError(f"Unsupported: {type(node)}")
    return str(_eval(ast.parse(expr, mode='eval')))
"""

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Explicit Tool Finish Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Вычисли и верни результат через finish.",
                    "tools": [
                        {
                            "tool_id": "calc",
                            "description": "Калькулятор",
                            "code": calc_code,
                            "args_schema": {"expression": {"type": "string"}}
                        },
                        INLINE_FINISH
                    ],
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "finish"
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "calc", "args": {"expression": "10*5"}},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "10*5 = 50"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="10*5?"
        )
        result = await flow.run(state)

        assert "response" in result
        assert "50" in result["response"]

        await container.flow_repository.delete(flow_id)

    async def test_explicit_mode_text_without_finish_continues(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        В режиме EXPLICIT текст без finish НЕ завершает - добавляется reminder.
        """
        flow_id = f"test_explicit_text_continues_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Explicit Text Continue Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Отвечай только через finish.",
                    "tools": [INLINE_FINISH],
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "finish"
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        # LLM сначала возвращает текст (ошибка), получает reminder, потом вызывает finish
        mock_llm_with_queue([
            {"type": "text", "content": "Просто текст"},  # Ошибка - нет finish
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Теперь правильно!"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test"
        )
        result = await flow.run(state)

        assert "response" in result
        assert result["response"] == "Теперь правильно!"

        await container.flow_repository.delete(flow_id)

    async def test_explicit_mode_auto_adds_finish_tool(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        В режиме EXPLICIT finish tool добавляется автоматически если его нет.
        """
        flow_id = f"test_explicit_auto_finish_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Explicit Auto Finish Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Завершайся через finish.",
                    "tools": [],  # finish не указан, но должен добавиться автоматически
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "finish"
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Finish добавлен автоматически!"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test"
        )
        result = await flow.run(state)

        assert "response" in result
        assert "автоматически" in result["response"]

        await container.flow_repository.delete(flow_id)

    async def test_explicit_mode_with_ask_user_interrupt(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        В режиме EXPLICIT ask_user работает корректно - interrupt и resume.
        """
        flow_id = f"test_explicit_ask_user_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Explicit Ask User Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Спроси имя у пользователя и поприветствуй через finish.",
                    "tools": [INLINE_ASK_USER, INLINE_FINISH],
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "finish"
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        # Первый запрос - агент спрашивает имя
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Как тебя зовут?"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Привет"
        )
        result = await flow.run(state)

        # Проверяем что произошел interrupt
        assert "interrupt" in result or result.get("interrupt") is not None

        await container.flow_repository.delete(flow_id)

    async def test_explicit_mode_multiple_tools_before_finish(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        В режиме EXPLICIT агент может вызвать несколько tools перед finish.
        """
        flow_id = f"test_explicit_multi_tools_{unique_id}"
        container = get_container()

        step1_code = "async def run(args, state): return 'step1_done'"
        step2_code = "async def run(args, state): return 'step2_done'"

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Explicit Multi Tools Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Выполни шаги и заверши через finish.",
                    "tools": [
                        {"tool_id": "step1", "description": "Шаг 1", "code": step1_code},
                        {"tool_id": "step2", "description": "Шаг 2", "code": step2_code},
                        INLINE_FINISH
                    ],
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "finish"
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "step1", "args": {}},
            {"type": "tool_call", "tool": "step2", "args": {}},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Все шаги выполнены!"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Выполни"
        )
        result = await flow.run(state)

        assert "response" in result
        assert "выполнены" in result["response"]

        await container.flow_repository.delete(flow_id)


class TestReactLoopModeStrictAndReminder:
    """
    Тесты для strict режима и кастомного reminder.
    """

    async def test_explicit_strict_true_sends_reminder(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        strict=True (по умолчанию): текст без finish вызывает reminder.
        """
        flow_id = f"test_strict_true_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Strict True Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Отвечай через finish.",
                    "tools": [INLINE_FINISH],
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "finish",
                        "strict": True
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        # LLM сначала текст (ошибка), потом finish
        mock_llm_with_queue([
            {"type": "text", "content": "Неправильный текстовый ответ"},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Правильный ответ через finish"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test"
        )
        result = await flow.run(state)

        assert "response" in result
        assert result["response"] == "Правильный ответ через finish"

        await container.flow_repository.delete(flow_id)

    async def test_explicit_strict_false_text_exits(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        strict=False: текст без finish сразу завершает агента.
        """
        flow_id = f"test_strict_false_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Strict False Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Можешь отвечать текстом.",
                    "tools": [INLINE_FINISH],
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "finish",
                        "strict": False
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        # LLM возвращает текст - в нестрогом режиме это OK
        mock_llm_with_queue([
            {"type": "text", "content": "Текстовый ответ без finish"},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test"
        )
        result = await flow.run(state)

        assert "response" in result
        assert result["response"] == "Текстовый ответ без finish"

        await container.flow_repository.delete(flow_id)

    async def test_explicit_custom_reminder_message(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        Кастомный reminder_message используется вместо дефолтного.
        """
        flow_id = f"test_custom_reminder_{unique_id}"
        container = get_container()

        custom_reminder = "ВНИМАНИЕ! Используй finish для ответа!"

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Custom Reminder Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Отвечай через finish.",
                    "tools": [INLINE_FINISH],
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "finish",
                        "strict": True,
                        "reminder_message": custom_reminder
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        # LLM сначала текст, потом finish
        mock_llm_with_queue([
            {"type": "text", "content": "Текст"},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "OK"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test"
        )
        result = await flow.run(state)

        # Проверяем что агент завершился
        assert "response" in result
        assert result["response"] == "OK"

        # Проверяем что в messages есть кастомный reminder
        messages = result.get("messages", [])
        reminder_found = any(
            custom_reminder in str(msg) for msg in messages
        )
        assert reminder_found, f"Кастомный reminder не найден в messages: {messages}"

        await container.flow_repository.delete(flow_id)

    async def test_strict_false_with_tool_still_works(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        strict=False: агент всё равно может использовать tools и finish.
        """
        flow_id = f"test_strict_false_tools_{unique_id}"
        container = get_container()

        calc_code = """
async def run(args, state):
    import ast, operator
    expr = args.get('expr', '0')
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul}
    def _e(n):
        if isinstance(n, ast.Expression): return _e(n.body)
        if isinstance(n, ast.Constant): return n.value
        if isinstance(n, ast.BinOp): return ops[type(n.op)](_e(n.left), _e(n.right))
        raise ValueError(str(type(n)))
    return str(_e(ast.parse(expr, mode='eval')))
"""

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Strict False Tools Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Вычисли и ответь.",
                    "tools": [
                        {"tool_id": "calc", "description": "Calc", "code": calc_code},
                        INLINE_FINISH
                    ],
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "finish",
                        "strict": False
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        # LLM вызывает tool, потом finish (как и должно)
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "calc", "args": {"expr": "2*3"}},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "2*3 = 6"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="2*3?"
        )
        result = await flow.run(state)

        assert "response" in result
        assert "6" in result["response"]

        await container.flow_repository.delete(flow_id)


class TestReactLoopModeMaxIterations:
    """
    Тесты ограничения итераций в ReAct цикле.
    """

    async def test_max_iterations_limit(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        Агент падает явно при достижении max_iterations без exit tool.
        """
        flow_id = f"test_max_iter_{unique_id}"
        container = get_container()

        loop_code = "async def run(args, state): return 'loop'"

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Max Iterations Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Вызывай tool пока не закончатся итерации.",
                    "tools": [
                        {"tool_id": "loop_tool", "description": "Loop", "code": loop_code},
                        INLINE_FINISH
                    ],
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "finish",
                        "max_iterations": 3
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        # LLM вызывает tool 3 раза - достигнут лимит
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "loop_tool", "args": {}},
            {"type": "tool_call", "tool": "loop_tool", "args": {}},
            {"type": "tool_call", "tool": "loop_tool", "args": {}},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Завершено после лимита"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Loop"
        )
        with pytest.raises(FlowExecutionError):
            await flow.run(state)

        await container.flow_repository.delete(flow_id)


class TestExampleReactExplicitMode:
    """
    Тесты для example_react агента с explicit режимом.
    Проверяем что пример из agents/example_react работает.
    """

    async def test_example_explicit_loop_loads(self, app):
        """
        Агент explicit_finish_agent из example_react загружается.
        """
        container = get_container()

        # Загружаем flow с skill explicit_mode
        flow = await container.flow_factory.get_flow("example_react", branch_id="explicit_mode")

        assert flow is not None

    async def test_example_explicit_loop_executes_calculator_and_finish(
        self, app, mock_llm_with_queue
    ):
        """
        Агент вычисляет через calculator и завершается через finish.
        """
        container = get_container()

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "7+8"}},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "7+8 = 15"}},
        ])

        flow = await container.flow_factory.get_flow("example_react", branch_id="explicit_mode")
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Сколько будет 7+8?"
        )
        result = await flow.run(state)

        assert "response" in result
        assert "15" in result["response"]

    async def test_example_explicit_loop_asks_user_when_unclear(
        self, app, mock_llm_with_queue
    ):
        """
        Агент использует ask_user для уточнения и interrupt происходит.
        """
        container = get_container()

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Что именно посчитать?"}},
        ])

        flow = await container.flow_factory.get_flow("example_react", branch_id="explicit_mode")
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Посчитай"
        )
        result = await flow.run(state)

        # Проверяем interrupt
        assert result.interrupt is not None

    async def test_example_test_explicit_skill_with_mock(self, app, mock_llm_with_queue):
        """
        Skill test_explicit с предустановленными mock ответами работает.
        """
        container = get_container()

        # Этот skill имеет mock.enabled=true и предустановленные LLM ответы
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "10+5"}},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Результат: 10+5 = 15"}},
        ])

        flow = await container.flow_factory.get_flow("example_react", branch_id="test_explicit")
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="10+5"
        )
        result = await flow.run(state)

        assert "response" in result
        assert "15" in result["response"]

    async def test_example_relaxed_mode_loads(self, app):
        """
        Агент explicit_relaxed_agent из example_react загружается.
        """
        container = get_container()

        flow = await container.flow_factory.get_flow("example_react", branch_id="explicit_relaxed_mode")

        assert flow is not None

    async def test_example_relaxed_mode_text_exits(self, app, mock_llm_with_queue):
        """
        В relaxed режиме текстовый ответ принимается.
        """
        container = get_container()

        mock_llm_with_queue([
            {"type": "text", "content": "Простой текстовый ответ"},
        ])

        flow = await container.flow_factory.get_flow("example_react", branch_id="explicit_relaxed_mode")
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Привет"
        )
        result = await flow.run(state)

        assert "response" in result
        assert result["response"] == "Простой текстовый ответ"


class TestReactLoopModeEdgeCases:
    """
    Edge cases и граничные условия.
    """

    async def test_explicit_mode_with_empty_content(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        Explicit режим корректно обрабатывает пустой content.
        """
        flow_id = f"test_empty_content_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Empty Content Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Отвечай через finish.",
                    "tools": [INLINE_FINISH],
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "finish"
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Нет данных"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content=""
        )
        result = await flow.run(state)

        assert "response" in result

        await container.flow_repository.delete(flow_id)

    async def test_finish_tool_auto_added_in_explicit_mode(
        self, app, unique_id, mock_llm_with_queue, make_test_state
    ):
        """
        Finish tool автоматически добавляется если его нет в списке tools.
        """
        flow_id = f"test_auto_finish_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Auto Finish Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Завершайся через finish.",
                    "tools": [],  # finish не указан!
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "finish"
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Finish был добавлен автоматически"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        result = await flow.run(make_test_state(content="test"))

        assert result.response is not None
        assert "автоматически" in result.response

        await container.flow_repository.delete(flow_id)

    async def test_multiple_text_responses_with_strict_mode(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        В strict режиме агент получает reminder после каждого текстового ответа.
        """
        flow_id = f"test_multi_text_strict_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Multi Text Strict Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Отвечай через finish.",
                    "tools": [INLINE_FINISH],
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "finish",
                        "strict": True
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        # LLM возвращает текст 2 раза, потом finish
        mock_llm_with_queue([
            {"type": "text", "content": "Первый текст"},
            {"type": "text", "content": "Второй текст"},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Наконец finish!"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test"
        )
        result = await flow.run(state)

        assert "response" in result
        assert result["response"] == "Наконец finish!"

        await container.flow_repository.delete(flow_id)

    async def test_explicit_mode_custom_exit_tool(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        Можно указать кастомный exit_tool вместо finish.
        """
        flow_id = f"test_custom_exit_{unique_id}"
        container = get_container()

        complete_code = """
async def execute(args: dict, state: dict = None):
    return args.get('result', 'completed')
"""

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Custom Exit Tool Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Завершайся через complete tool.",
                    "tools": [
                        {
                            "tool_id": "complete",
                            "description": "Завершает работу",
                            "code": complete_code,
                            "args_schema": {"result": {"type": "string"}}
                        }
                    ],
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "complete"  # Кастомный exit tool
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "complete", "args": {"result": "Задача выполнена"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test"
        )
        result = await flow.run(state)

        assert "response" in result
        assert "Задача выполнена" in result["response"]

        await container.flow_repository.delete(flow_id)

    async def test_auto_mode_still_works_with_react_config(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        Если react.loop_mode = auto, поведение как без react конфига.
        """
        flow_id = f"test_auto_with_config_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Auto Mode With Config Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Просто отвечай.",
                    "tools": [INLINE_FINISH],
                    "react": {
                        "loop_mode": "auto",  # Явно указан auto
                        "max_iterations": 5
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {"type": "text", "content": "Текстовый ответ в auto режиме"},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test"
        )
        result = await flow.run(state)

        assert "response" in result
        assert result["response"] == "Текстовый ответ в auto режиме"

        await container.flow_repository.delete(flow_id)
