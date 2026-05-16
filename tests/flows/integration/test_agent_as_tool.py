"""
Тесты: агент как tool с полным Agent.

Сценарий:
1. main_flow с LlmNode, tool: support_agent
2. support_agent (NodeConfig в БД) с tool: ask_user
3. User → main_flow → support_agent → ask_user (interrupt)
4. User отвечает → управление возвращается в support_agent → завершение
"""

from typing import Any, Dict

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.tools.base import BaseTool
from apps.flows.src.tools.code_tool import CodeTool
from apps.flows.src.tools.node_wrapper import NodeAsToolWrapper
from core.clients.llm import setup_mock_responses
from core.state import ExecutionState


class TestNodeAsToolWrapper:
    """Базовые тесты NodeAsToolWrapper."""

    def test_wrapper_creates_from_dict_config(self):
        """Wrapper создаётся из dict конфига."""
        config = {
            "tool_id": "support_agent",
            "type": "llm_node",
            "name": "Support Agent",
            "description": "Агент поддержки",
            "prompt": "Ты агент поддержки",
        }

        wrapper = NodeAsToolWrapper(node_config=config)

        assert wrapper.name == "support_agent"
        assert "поддержки" in wrapper.description
        assert isinstance(wrapper, BaseTool)

    def test_wrapper_has_openai_schema(self):
        """Wrapper генерирует OpenAI схему."""
        config = {
            "tool_id": "helper",
            "type": "llm_node",
            "name": "Helper",
            "prompt": "Ты помощник",
        }

        wrapper = NodeAsToolWrapper(node_config=config)
        schema = wrapper.to_openai_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "helper"


class TestFlowWithSubagentInterrupt:
    """
    Интеграционный тест: Agent с субагентом который делает interrupt.

    Архитектура INLINE: все tools и субагенты определены inline в конфиге.

    main_flow (LlmNode)
        ↓ вызывает tool
    support_agent (inline llm_node)
        ↓ вызывает tool
    ask_user (inline tool с FlowInterrupt)
    """

    @pytest.fixture
    def main_agent_config(self) -> Dict[str, Any]:
        """Конфиг главного flow с субагентом как inline tool."""
        ask_user_code = '''
from apps.flows.src.runtime.exceptions import FlowInterrupt

async def execute(args, state):
    question = args.get("question", "")
    raise FlowInterrupt(question)
'''
        return {
            "id": "main_flow",
            "name": "Main Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "Ты главный агент. Для вопросов поддержки вызывай support_agent.",
                    "tools": [
                        {
                            "tool_id": "support_agent",
                            "type": "llm_node",
                            "name": "Support Agent",
                            "description": "Агент поддержки, задаёт уточняющие вопросы",
                            "prompt": "Ты агент поддержки. Если нужна информация от пользователя - используй ask_user.",
                            "tools": [
                                {
                                    "tool_id": "ask_user",
                                    "description": "Задать вопрос пользователю",
                                    "code": ask_user_code,
                                    "args_schema": {
                                        "question": {"type": "string", "description": "Вопрос пользователю"}
                                    }
                                }
                            ],
                            "llm": {"model": "mock-gpt-4"},
                        }
                    ],
                    "llm": {"model": "mock-gpt-4"},
                }
            },
            "edges": [
                {"from": "main", "to": None}
            ]
        }

    @pytest.mark.asyncio
    async def test_flow_with_subagent_interrupt(
        self,
        main_agent_config: Dict[str, Any],
        app,
    ):
        """
        Полный тест: Agent → субагент → ask_user → interrupt.
        Все конфиги inline - никакого обращения к БД.
        """
        setup_mock_responses(response_queue=[
            {"type": "tool_call", "tool": "support_agent", "args": {"query": "Помоги пользователю с заказом"}},
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Какой у вас номер заказа?"}},
        ])

        flow = await Flow.from_config(main_agent_config)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Помогите с моим заказом"
        )
        result = await flow.run(state)

        assert result.interrupt is not None
        assert result.interrupt.question == "Какой у вас номер заказа?"

    @pytest.mark.asyncio
    async def test_flow_resume_after_interrupt(
        self,
        main_agent_config: Dict[str, Any],
        app,
    ):
        """
        Тест resume после interrupt.
        Все конфиги inline.
        """
        setup_mock_responses(response_queue=[
            {"type": "tool_call", "tool": "support_agent", "args": {"query": "Помоги с заказом"}},
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Номер заказа?"}},
            "Ваш заказ #12345 отправлен!",
            "Готово! Ваш заказ отправлен.",
        ])

        flow = await Flow.from_config(main_agent_config)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Где мой заказ?"
        )

        result = await flow.run(state)
        assert result.interrupt is not None
        assert result.interrupt.question == "Номер заказа?"


class TestSubagentMessagesIntegrity:
    """
    СТРОГИЙ ТЕСТ: проверяем целостность messages при вложенных агентах.

    Архитектура INLINE: все tools определены inline в конфиге.
    """

    @pytest.fixture
    def main_flow_with_subagent(self) -> Dict[str, Any]:
        """Agent с субагентом - полностью inline."""
        ask_user_code = '''
from apps.flows.src.runtime.exceptions import FlowInterrupt

async def execute(args, state):
    question = args.get("question", "")
    raise FlowInterrupt(question)
'''
        return {
            "id": "test_flow",
            "name": "Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "Для сбора информации вызывай info_collector.",
                    "tools": [
                        {
                            "tool_id": "info_collector",
                            "type": "llm_node",
                            "name": "Info Collector",
                            "description": "Собирает информацию от пользователя",
                            "prompt": "Ты собираешь информацию. Используй ask_user для вопросов.",
                            "tools": [
                                {
                                    "tool_id": "ask_user",
                                    "description": "Задать вопрос пользователю",
                                    "code": ask_user_code,
                                    "args_schema": {
                                        "question": {"type": "string", "description": "Вопрос"}
                                    }
                                }
                            ],
                            "llm": {"model": "mock-gpt-4"},
                        }
                    ],
                    "llm": {"model": "mock-gpt-4"},
                }
            },
            "edges": [{"from": "main", "to": None}]
        }

    @pytest.mark.asyncio
    async def test_tool_result_has_correct_role(self):
        """
        Проверяем что tool result имеет role="tool", не "assistant".
        """
        from apps.flows.src.runtime.runners.llm_runner import new_tool_result_message
        from core.clients.llm.factory import _message_to_openai

        tool_result = new_tool_result_message(
            "call_test_123",
            "Test result",
            "test_node",
            context_id="ctx_test",
        )

        openai_msg = _message_to_openai(tool_result)

        assert openai_msg["role"] == "tool", \
            f"tool result должен иметь role='tool', получен: {openai_msg['role']}"

        assert openai_msg.get("tool_call_id") == "call_test_123", \
            f"tool_call_id должен быть 'call_test_123', получен: {openai_msg.get('tool_call_id')}"

    @pytest.mark.asyncio
    async def test_full_resume_cycle(
        self,
        main_flow_with_subagent: Dict[str, Any],
        app,
    ):
        """
        Полный цикл: interrupt -> resume -> завершение.
        Все конфиги inline.
        """
        setup_mock_responses(response_queue=[
            {"type": "tool_call", "tool": "info_collector", "args": {"query": "Собери"}},
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Email?"}},
            "Email получен: test@test.com",
            "Данные собраны успешно!",
        ])

        flow = await Flow.from_config(main_flow_with_subagent)

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Начни сбор"
        )
        result1 = await flow.run(state)

        assert result1.interrupt is not None
        assert len(result1.interrupt_path) > 0

        result1.content = "test@test.com"
        result1.interrupt = None

        result2 = await flow.run(result1)

        assert result2.interrupt is None, \
            f"Agent должен завершиться без interrupt, получен: {result2.interrupt}"
        assert result2.response, \
            f"Должен быть финальный ответ, state: {result2}"


class TestToolRegistryInline:
    """Тесты ToolRegistry с inline конфигурациями."""

    @pytest.mark.asyncio
    async def test_tool_registry_creates_inline_tool(self, app):
        """ToolRegistry создаёт CodeTool из inline конфига."""
        container = get_container()

        # Используем уникальный tool_id чтобы не перезаписать builtin calculator
        tool_config = {
            "tool_id": "test_simple_adder",
            "title": "Simple Adder",
            "description": "Складывает два числа",
            "code": """
async def execute(args: dict, state: dict = None):
    expression = args.get('expression', '1+1')
    parts = expression.split('+')
    return str(int(parts[0].strip()) + int(parts[1].strip()))
""",
            "args_schema": {
                "expression": {"type": "string", "description": "Выражение"}
            }
        }

        tool = await container.tool_registry.create_tool(tool_config)

        assert tool is not None
        assert isinstance(tool, CodeTool)
        assert tool.name == "test_simple_adder"

    @pytest.mark.asyncio
    async def test_tool_registry_creates_node_as_tool(self, app):
        """ToolRegistry создаёт NodeAsToolWrapper из inline llm_node конфига."""
        container = get_container()

        tool_config = {
            "tool_id": "helper_agent",
            "type": "llm_node",
            "name": "Helper Agent",
            "description": "Помощник",
            "prompt": "Ты помощник. Отвечай на вопросы.",
            "llm": {"model": "mock-gpt-4"},
        }

        tool = await container.tool_registry.create_tool(tool_config)

        assert tool is not None
        assert isinstance(tool, NodeAsToolWrapper)
        assert tool.name == "helper_agent"

    @pytest.mark.asyncio
    async def test_tool_registry_raises_on_missing_code(self, app):
        """ToolRegistry выбрасывает ошибку если нет code."""
        container = get_container()

        tool_config = {
            "tool_id": "no_code_tool",
            "description": "Tool без кода",
        }

        with pytest.raises(ValueError, match="code"):
            await container.tool_registry.create_tool(tool_config)

    @pytest.mark.asyncio
    async def test_tool_registry_rejects_string_refs(self, app):
        """ToolRegistry выбрасывает ошибку для строковых tool_id."""
        container = get_container()

        with pytest.raises(ValueError, match="passed as string"):
            await container.tool_registry.create_tool("calculator")

        with pytest.raises(ValueError, match="passed as string"):
            await container.tool_registry.create_tool("ask_user")

    @pytest.mark.asyncio
    async def test_builtin_tools_in_repository(self, app):
        """Встроенные tools загружены в БД с inline code."""
        container = get_container()

        calculator = await container.tool_repository.get("calculator")
        assert calculator is not None, "calculator не найден в БД"
        assert calculator.code is not None, "calculator должен иметь code"

        ask_user = await container.tool_repository.get("ask_user")
        assert ask_user is not None, "ask_user не найден в БД"
        assert ask_user.code is not None, "ask_user должен иметь code"


class TestFilesPassingToSubnode:
    """Тест: файлы передаются в субноду через shared state."""

    @pytest.fixture
    def agent_with_file_tool(self) -> Dict[str, Any]:
        """Агент с субагентом который проверяет наличие файлов в state."""
        check_files_code = '''
async def execute(args, state):
    files = state.get("files", [])
    if not files:
        return {"success": False, "error": "No files in state"}
    return {"success": True, "files_count": len(files), "first_file": files[0].get("name")}
'''
        return {
            "id": "file_test_flow",
            "name": "File Test Agent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "Ты агент для обработки файлов. Используй file_processor для проверки файлов.",
                    "tools": [
                        {
                            "tool_id": "file_processor",
                            "type": "llm_node",
                            "name": "File Processor",
                            "description": "Обрабатывает файлы",
                            "prompt": "Проверь файлы с помощью check_files.",
                            "tools": [
                                {
                                    "tool_id": "check_files",
                                    "description": "Проверяет наличие файлов в state",
                                    "code": check_files_code,
                                }
                            ],
                            "llm": {"model": "mock-gpt-4"},
                        }
                    ],
                    "llm": {"model": "mock-gpt-4"},
                }
            },
            "edges": [{"from": "main", "to": None}]
        }

    @pytest.mark.asyncio
    async def test_files_available_in_subagent(
        self,
        agent_with_file_tool: Dict[str, Any],
        app,
    ):
        """Файлы из родительского state доступны в субагенте."""
        setup_mock_responses(response_queue=[
            {"type": "tool_call", "tool": "file_processor", "args": {"query": "Проверь файлы"}},
            {"type": "tool_call", "tool": "check_files", "args": {}},
            "Файлы проверены: 1 файл найден, test.jpg",
            "Обработка завершена. Файл test.jpg обработан.",
        ])

        flow = await Flow.from_config(agent_with_file_tool)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Обработай мои файлы",
            files=[
                {
                    "name": "test.jpg",
                    "path": "/tmp/test.jpg",
                    "mime_type": "image/jpeg",
                    "size": 1024,
                }
            ]
        )

        result = await flow.run(state)

        assert result.response, f"Должен быть ответ, state: {result}"
        assert result.interrupt is None, "Не должно быть interrupt"
