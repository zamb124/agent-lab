"""
СТРОГИЕ тесты комбинаций режимов LlmNode.

Проверяют ВСЕ возможные комбинации reason/exit tools и loop modes:
1. AUTO режим без reason - текст завершает
2. AUTO режим с reason - reason → текст завершает
3. EXPLICIT режим с exit - только exit tool завершает
4. EXPLICIT режим с reason + exit - reason → exit завершает
5. Кастомные reason/exit tools работают корректно

ПРАВИЛО: Мок только LLM. Tools, state, flow - реальные.
"""


from apps.flows.src.container import get_container
from apps.flows.src.models import FlowConfig
from core.state import ExecutionState

# ============================================================================
# INLINE TOOL DEFINITIONS
# ============================================================================

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
    return str(_eval(ast.parse(expr, mode='eval')))
"""
}

INLINE_FINISH = {
    "tool_id": "finish",
    "description": "Завершает агента и возвращает финальный ответ",
    "args_schema": {"answer": {"type": "string"}},
    "code": "async def execute(args: dict, state: dict = None):\n    return args.get('answer', '')",
    "react_role": "exit"
}

INLINE_REASON = {
    "tool_id": "reason",
    "description": "Инструмент для рассуждения. Используй для анализа ситуации.",
    "args_schema": {
        "observation": {"type": "string", "description": "Что ты наблюдаешь"},
        "analysis": {"type": "string", "description": "Анализ ситуации"},
        "plan": {"type": "string", "description": "План действий"},
        "next_action": {"type": "string", "description": "Следующее действие"}
    },
    "code": """async def execute(args: dict, state: dict = None):
    if state is not None:
        if "reasoning_history" not in state:
            state["reasoning_history"] = []
        state["reasoning_history"].append({
            "observation": args.get("observation", ""),
            "analysis": args.get("analysis", ""),
            "plan": args.get("plan", ""),
            "next_action": args.get("next_action", "")
        })
    return f"Reasoning recorded: {args.get('next_action', '')}"
""",
    "react_role": "reason"
}

INLINE_CUSTOM_THINK = {
    "tool_id": "think_step",
    "description": "Кастомный инструмент рассуждений",
    "args_schema": {"thought": {"type": "string"}},
    "code": """async def execute(args: dict, state: dict = None):
    if state is not None:
        if "reasoning_history" not in state:
            state["reasoning_history"] = []
        state["reasoning_history"].append({"thought": args.get("thought", "")})
    return f"Thought: {args.get('thought', '')}"
""",
    "react_role": "reason"
}

INLINE_CUSTOM_COMPLETE = {
    "tool_id": "complete",
    "description": "Кастомный завершающий инструмент",
    "args_schema": {"result": {"type": "string"}},
    "code": "async def execute(args: dict, state: dict = None):\n    return args.get('result', 'done')",
    "react_role": "exit"
}


# ============================================================================
# AUTO MODE TESTS
# ============================================================================

class TestAutoModeWithoutReason:
    """
    AUTO режим БЕЗ reason tool.
    Агент завершается когда LLM возвращает текст без tool_calls.
    """

    async def test_text_response_exits_immediately(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Текстовый ответ сразу завершает агента."""
        flow_id = f"auto_no_reason_text_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Auto No Reason Text",
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

        mock_llm_with_queue([
            {"type": "text", "content": "Привет! Я готов помочь."},
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

        assert result["response"] == "Привет! Я готов помочь."
        assert not result.reasoning_history

        await container.flow_repository.delete(flow_id)

    async def test_tool_then_text_exits(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Tool call → результат → текст = завершение."""
        flow_id = f"auto_no_reason_tool_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Auto No Reason Tool",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй калькулятор для вычислений.",
                    "tools": [INLINE_CALCULATOR]
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "7+3"}},
            {"type": "text", "content": "Результат: 10"},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="7+3?"
        )
        result = await flow.run(state)

        assert "10" in result["response"]
        assert not result.reasoning_history

        await container.flow_repository.delete(flow_id)

    async def test_multiple_tools_then_text_exits(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Несколько tool calls → текст = завершение."""
        flow_id = f"auto_no_reason_multi_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Auto No Reason Multi",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй калькулятор.",
                    "tools": [INLINE_CALCULATOR]
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "2+2"}},
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "4*3"}},
            {"type": "text", "content": "2+2=4, 4*3=12"},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Посчитай 2+2 и 4*3"
        )
        result = await flow.run(state)

        assert "12" in result["response"]

        await container.flow_repository.delete(flow_id)


class TestAutoModeWithReason:
    """
    AUTO режим С reason tool.
    Агент может использовать reason для рассуждений, завершается при текстовом ответе.
    """

    async def test_reason_then_text_exits(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Reason → текст = завершение + reasoning сохранен."""
        flow_id = f"auto_reason_text_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Auto Reason Text",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй reason для анализа, потом отвечай.",
                    "tools": [INLINE_REASON, INLINE_CALCULATOR]
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "reason",
                "args": {
                    "observation": "Пользователь спрашивает про вычисление",
                    "analysis": "Нужно использовать калькулятор",
                    "plan": "Вычислю и отвечу",
                    "next_action": "Вызову calculator"
                }
            },
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "5+5"}},
            {"type": "text", "content": "5+5 = 10"},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Сколько 5+5?"
        )
        result = await flow.run(state)

        assert "10" in result["response"]
        assert result.reasoning_history
        assert len(result.reasoning_history) == 1
        assert result.reasoning_history[0]["observation"] == "Пользователь спрашивает про вычисление"

        await container.flow_repository.delete(flow_id)

    async def test_multiple_reasons_then_text_exits(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Несколько reason → текст = завершение + все reasoning сохранены."""
        flow_id = f"auto_multi_reason_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Auto Multi Reason",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Рассуждай поэтапно.",
                    "tools": [INLINE_REASON, INLINE_CALCULATOR]
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "reason",
                "args": {
                    "observation": "Первое наблюдение",
                    "analysis": "Первый анализ",
                    "plan": "Первый план",
                    "next_action": "Посчитать"
                }
            },
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "10+10"}},
            {
                "type": "tool_call",
                "tool": "reason",
                "args": {
                    "observation": "Получил 20",
                    "analysis": "Результат правильный",
                    "plan": "Вернуть ответ",
                    "next_action": "Ответить пользователю"
                }
            },
            {"type": "text", "content": "10+10 = 20"},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="10+10?"
        )
        result = await flow.run(state)

        assert "20" in result["response"]
        assert result.reasoning_history
        assert len(result.reasoning_history) == 2
        assert result.reasoning_history[0]["observation"] == "Первое наблюдение"
        assert result.reasoning_history[1]["observation"] == "Получил 20"

        await container.flow_repository.delete(flow_id)

    async def test_reason_only_then_text_exits(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Reason без других tools → текст = завершение."""
        flow_id = f"auto_reason_only_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Auto Reason Only",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Рассуждай и отвечай.",
                    "tools": [INLINE_REASON]
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "reason",
                "args": {
                    "observation": "Простой вопрос",
                    "analysis": "Могу ответить сразу",
                    "plan": "Ответить",
                    "next_action": "Дать ответ"
                }
            },
            {"type": "text", "content": "Ответ на вопрос"},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Вопрос"
        )
        result = await flow.run(state)

        assert result["response"] == "Ответ на вопрос"
        assert result.reasoning_history
        assert len(result.reasoning_history) == 1

        await container.flow_repository.delete(flow_id)


# ============================================================================
# EXPLICIT MODE TESTS
# ============================================================================

class TestExplicitModeWithExitOnly:
    """
    EXPLICIT режим ТОЛЬКО с exit tool (без reason).
    Агент завершается ТОЛЬКО при вызове exit tool.
    """

    async def test_exit_tool_exits(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Exit tool сразу завершает агента."""
        flow_id = f"explicit_exit_only_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Explicit Exit Only",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Отвечай через finish.",
                    "tools": [INLINE_FINISH, INLINE_CALCULATOR],
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
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Готово!"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Сделай"
        )
        result = await flow.run(state)

        assert result["response"] == "Готово!"
        assert not result.reasoning_history

        await container.flow_repository.delete(flow_id)

    async def test_tool_then_exit_exits(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Tool → exit = завершение с результатом."""
        flow_id = f"explicit_tool_exit_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Explicit Tool Exit",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Вычисли и ответь через finish.",
                    "tools": [INLINE_CALCULATOR, INLINE_FINISH],
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
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "8*8"}},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "8*8 = 64"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="8*8?"
        )
        result = await flow.run(state)

        assert "64" in result["response"]
        assert not result.reasoning_history

        await container.flow_repository.delete(flow_id)

    async def test_text_without_exit_adds_reminder(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Текст без exit → reminder → exit = завершение."""
        flow_id = f"explicit_text_reminder_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Explicit Text Reminder",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Отвечай только через finish.",
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

        mock_llm_with_queue([
            {"type": "text", "content": "Неправильный текст"},
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

        assert result["response"] == "Теперь правильно!"

        await container.flow_repository.delete(flow_id)

    async def test_multiple_tools_then_exit(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Несколько tools → exit = завершение."""
        flow_id = f"explicit_multi_tool_exit_{unique_id}"
        container = get_container()

        step1 = {
            "tool_id": "step1",
            "description": "Шаг 1",
            "code": "async def execute(args, state): return 'step1_done'"
        }
        step2 = {
            "tool_id": "step2",
            "description": "Шаг 2",
            "code": "async def execute(args, state): return 'step2_done'"
        }

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Explicit Multi Tool Exit",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Выполни шаги и заверши.",
                    "tools": [step1, step2, INLINE_FINISH],
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
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Оба шага выполнены"}},
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

        assert "выполнены" in result["response"]

        await container.flow_repository.delete(flow_id)


class TestExplicitModeWithReasonAndExit:
    """
    EXPLICIT режим С reason И exit tools.
    Агент рассуждает через reason, завершается ТОЛЬКО через exit.
    """

    async def test_reason_then_exit_exits(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Reason → exit = завершение + reasoning сохранен."""
        flow_id = f"explicit_reason_exit_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Explicit Reason Exit",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Рассуждай через reason, отвечай через finish.",
                    "tools": [INLINE_REASON, INLINE_FINISH],
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
            {
                "type": "tool_call",
                "tool": "reason",
                "args": {
                    "observation": "Нужно ответить",
                    "analysis": "Простой запрос",
                    "plan": "Ответить сразу",
                    "next_action": "finish"
                }
            },
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Готово!"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Сделай"
        )
        result = await flow.run(state)

        assert result["response"] == "Готово!"
        assert result.reasoning_history
        assert len(result.reasoning_history) == 1
        assert result.reasoning_history[0]["observation"] == "Нужно ответить"

        await container.flow_repository.delete(flow_id)

    async def test_reason_tool_then_exit_exits(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Reason → tool → reason → exit = завершение + все reasoning."""
        flow_id = f"explicit_reason_tool_exit_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Explicit Reason Tool Exit",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Рассуждай, используй калькулятор, завершай через finish.",
                    "tools": [INLINE_REASON, INLINE_CALCULATOR, INLINE_FINISH],
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
            {
                "type": "tool_call",
                "tool": "reason",
                "args": {
                    "observation": "Нужно вычислить",
                    "analysis": "Использую калькулятор",
                    "plan": "Посчитать и вернуть",
                    "next_action": "calculator"
                }
            },
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "15-5"}},
            {
                "type": "tool_call",
                "tool": "reason",
                "args": {
                    "observation": "Получил 10",
                    "analysis": "Результат верный",
                    "plan": "Завершить",
                    "next_action": "finish"
                }
            },
            {"type": "tool_call", "tool": "finish", "args": {"answer": "15-5 = 10"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        context_id = f"reason-exit-{unique_id}"
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=context_id,
            user_id=f"test-user-{unique_id}",
            session_id=f"{flow_id}:{context_id}",
            content="15-5?"
        )
        result = await flow.run(state)

        assert "10" in result["response"]
        assert result.reasoning_history
        assert len(result.reasoning_history) == 2
        assert result.reasoning_history[0]["observation"] == "Нужно вычислить"
        assert result.reasoning_history[1]["observation"] == "Получил 10"

        await container.flow_repository.delete(flow_id)

    async def test_text_with_reason_still_needs_exit(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Reason → текст → reminder → exit = завершение (strict mode)."""
        flow_id = f"explicit_reason_text_exit_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Explicit Reason Text Exit",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Рассуждай и завершай через finish.",
                    "tools": [INLINE_REASON, INLINE_FINISH],
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

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "reason",
                "args": {
                    "observation": "Анализирую",
                    "analysis": "Понял",
                    "plan": "Ответить",
                    "next_action": "Отвечу текстом"
                }
            },
            {"type": "text", "content": "Текст без finish"},  # Ошибка в strict
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Правильный ответ"}},
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

        assert result["response"] == "Правильный ответ"
        assert result.reasoning_history
        assert len(result.reasoning_history) == 1

        await container.flow_repository.delete(flow_id)


# ============================================================================
# CUSTOM TOOLS TESTS
# ============================================================================

class TestCustomReasonAndExitTools:
    """
    Тесты с КАСТОМНЫМИ reason и exit tools (не стандартные reason/finish).
    Проверяет что react_role корректно определяется.
    """

    async def test_custom_reason_tool_works(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Кастомный reason tool (think_step) работает."""
        flow_id = f"custom_reason_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Custom Reason Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Используй think_step для рассуждений.",
                    "tools": [INLINE_CUSTOM_THINK, INLINE_CALCULATOR]
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "think_step", "args": {"thought": "Надо посчитать"}},
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "3*3"}},
            {"type": "text", "content": "3*3 = 9"},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        context_id = f"custom-reason-{unique_id}"
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=context_id,
            user_id=f"test-user-{unique_id}",
            session_id=f"{flow_id}:{context_id}",
            content="3*3?"
        )
        result = await flow.run(state)

        assert "9" in result["response"]
        assert result.reasoning_history
        assert len(result.reasoning_history) == 1
        assert result.reasoning_history[0]["thought"] == "Надо посчитать"

        await container.flow_repository.delete(flow_id)

    async def test_custom_exit_tool_works(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Кастомный exit tool (complete) работает."""
        flow_id = f"custom_exit_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Custom Exit Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Завершай через complete.",
                    "tools": [INLINE_CUSTOM_COMPLETE, INLINE_CALCULATOR],
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "complete"
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "6/2"}},
            {"type": "tool_call", "tool": "complete", "args": {"result": "6/2 = 3"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        context_id = f"custom-exit-{unique_id}"
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=context_id,
            user_id=f"test-user-{unique_id}",
            session_id=f"{flow_id}:{context_id}",
            content="6/2?"
        )
        result = await flow.run(state)

        assert "3" in result["response"]

        await container.flow_repository.delete(flow_id)

    async def test_custom_reason_and_exit_together(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Кастомные reason (think_step) + exit (complete) вместе."""
        flow_id = f"custom_both_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Custom Both Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Думай через think_step, завершай через complete.",
                    "tools": [INLINE_CUSTOM_THINK, INLINE_CUSTOM_COMPLETE, INLINE_CALCULATOR],
                    "react": {
                        "loop_mode": "explicit",
                        "exit_tool": "complete"
                    }
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "think_step", "args": {"thought": "Анализирую задачу"}},
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "100/4"}},
            {"type": "tool_call", "tool": "think_step", "args": {"thought": "Результат получен"}},
            {"type": "tool_call", "tool": "complete", "args": {"result": "100/4 = 25"}},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        context_id = f"custom-both-{unique_id}"
        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=context_id,
            user_id=f"test-user-{unique_id}",
            session_id=f"{flow_id}:{context_id}",
            content="100/4?"
        )
        result = await flow.run(state)

        assert "25" in result["response"]
        assert result.reasoning_history
        assert len(result.reasoning_history) == 2
        assert result.reasoning_history[0]["thought"] == "Анализирую задачу"
        assert result.reasoning_history[1]["thought"] == "Результат получен"

        await container.flow_repository.delete(flow_id)


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Граничные случаи и особые сценарии."""

    async def test_empty_tools_auto_mode(
        self, app, unique_id, mock_llm_with_queue
    ):
        """AUTO режим без tools - текст сразу завершает."""
        flow_id = f"edge_empty_tools_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Empty Tools Agent",
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
            {"type": "text", "content": "Простой ответ"},
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

        assert result["response"] == "Простой ответ"

        await container.flow_repository.delete(flow_id)

    async def test_exit_tool_auto_injected_in_explicit(
        self, app, unique_id, mock_llm_with_queue
    ):
        """В EXPLICIT режиме exit tool инъектируется автоматически если отсутствует."""
        flow_id = f"edge_auto_inject_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Auto Inject Exit Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Завершайся через finish.",
                    "tools": [],  # finish не указан
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
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Auto-injected finish работает"}},
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

        assert "Auto-injected" in result["response"]

        await container.flow_repository.delete(flow_id)

    async def test_strict_false_allows_text_exit(
        self, app, unique_id, mock_llm_with_queue
    ):
        """strict=False позволяет текстовый ответ в EXPLICIT режиме."""
        flow_id = f"edge_strict_false_{unique_id}"
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

        assert result["response"] == "Текстовый ответ без finish"

        await container.flow_repository.delete(flow_id)

    async def test_reason_without_other_actions_then_text(
        self, app, unique_id, mock_llm_with_queue
    ):
        """Reason tool используется только для рассуждений, без других actions."""
        flow_id = f"edge_reason_alone_{unique_id}"
        container = get_container()

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Reason Alone Agent",
            entry="agent",
            nodes={
                "agent": {
                    "type": "llm_node",
                    "prompt": "Рассуждай и отвечай.",
                    "tools": [INLINE_REASON]
                }
            },
            edges=[]
        )
        await container.flow_repository.set(flow_config)

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "reason",
                "args": {
                    "observation": "Получил вопрос",
                    "analysis": "Простой вопрос",
                    "plan": "Ответить напрямую",
                    "next_action": "text response"
                }
            },
            {"type": "text", "content": "Прямой ответ"},
        ])

        flow = await container.flow_factory.get_flow(flow_id)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Вопрос"
        )
        result = await flow.run(state)

        assert result["response"] == "Прямой ответ"
        assert result.reasoning_history
        assert len(result.reasoning_history) == 1

        await container.flow_repository.delete(flow_id)


# ============================================================================
# STREAMING TESTS
# ============================================================================

class TestExplicitModeStreaming:
    """
    Тесты стриминга в EXPLICIT режиме.

    В EXPLICIT режиме текстовые артефакты НЕ должны стримиться до вызова exit_tool.
    Это критически важно чтобы пользователь не видел промежуточные ответы LLM.
    """

    async def test_text_artifacts_not_streamed_before_exit_tool(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        Текстовые артефакты НЕ стримятся до вызова exit_tool.

        Сценарий:
        1. LLM отвечает текстом (без exit_tool) - reminder добавляется
        2. LLM вызывает exit_tool

        Ожидание: текстовые артефакты первого ответа НЕ должны быть в событиях.
        """
        from a2a.types import TaskArtifactUpdateEvent

        from apps.flows.src.models import ReactLoopMode
        from apps.flows.src.models.enums import ReactToolRole
        from apps.flows.src.models.node_config import NodeConfig, NodeLLMOverride, ReactConfig
        from apps.flows.src.models.tool_reference import CallParameter
        from apps.flows.src.runtime.runners.llm_runner import LlmNodeRunner
        from apps.flows.src.tools.code_tool import CodeTool

        flow_id = f"explicit_streaming_{unique_id}"
        get_container()

        finish_tool = CodeTool(
            tool_id="finish",
            code="async def execute(args: dict, state: dict = None):\n    return args.get('answer', '')",
            description="Завершает агента",
            parameters={"answer": CallParameter(type="string", description="Ответ")},
            react_role=ReactToolRole.EXIT,
        )

        node_config = NodeConfig(
            node_id=flow_id,
            type="llm_node",
            name="Explicit Streaming Test",
            description="Test agent for streaming",
            prompt="Отвечай через finish.",
            llm_override=NodeLLMOverride(model="mock-gpt-4", temperature=0.2),
            react=ReactConfig(
                loop_mode=ReactLoopMode.EXPLICIT,
                exit_tool="finish",
                strict=True,
            ),
        )

        mock_llm_with_queue([
            {"type": "text", "content": "Промежуточный текст который НЕ должен стримиться"},
            {"type": "tool_call", "tool": "finish", "args": {"answer": "Финальный ответ"}},
        ])

        runner = LlmNodeRunner(
            node_config=node_config,
            tools=[finish_tool],
            llm=None,
            prompt="Отвечай через finish.",
        )

        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test-user",
            session_id="test-agent:test",
            messages=[]
        )
        events = []

        async for event in runner.run({"content": "Привет"}, state):
            events.append(event)

        text_artifact_events = [
            e for e in events
            if isinstance(e, TaskArtifactUpdateEvent)
            and (e.artifact.name is None or e.artifact.name == "response")
        ]

        assert len(text_artifact_events) == 0, (
            f"В EXPLICIT режиме текстовые артефакты НЕ должны стримиться! "
            f"Найдено {len(text_artifact_events)} текстовых артефактов."
        )

        assert state["response"] == "Финальный ответ"

    async def test_auto_mode_streams_text_artifacts(
        self, app, unique_id, mock_llm_with_queue
    ):
        """
        В AUTO режиме текстовые артефакты ДОЛЖНЫ стримиться.

        Контрольный тест: AUTO режим работает как раньше.
        """
        from a2a.types import TaskArtifactUpdateEvent

        from apps.flows.src.models import ReactLoopMode
        from apps.flows.src.models.node_config import NodeConfig, NodeLLMOverride, ReactConfig
        from apps.flows.src.runtime.runners.llm_runner import LlmNodeRunner

        flow_id = f"auto_streaming_{unique_id}"

        node_config = NodeConfig(
            node_id=flow_id,
            type="llm_node",
            name="Auto Streaming Test",
            description="Test agent for streaming",
            prompt="Отвечай как хочешь.",
            llm_override=NodeLLMOverride(model="mock-gpt-4", temperature=0.2),
            react=ReactConfig(
                loop_mode=ReactLoopMode.AUTO,
            ),
        )

        mock_llm_with_queue([
            {"type": "text", "content": "Текстовый ответ"},
        ])

        runner = LlmNodeRunner(
            node_config=node_config,
            tools=[],
            llm=None,
            prompt="Отвечай как хочешь.",
        )

        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test-user",
            session_id="test-agent:test",
            messages=[]
        )
        events = []

        async for event in runner.run({"content": "Привет"}, state):
            events.append(event)

        text_artifact_events = [
            e for e in events
            if isinstance(e, TaskArtifactUpdateEvent)
            and (e.artifact.name is None or e.artifact.name == "response")
        ]

        assert len(text_artifact_events) > 0, (
            "В AUTO режиме текстовые артефакты ДОЛЖНЫ стримиться!"
        )

        assert state["response"] == "Текстовый ответ"

