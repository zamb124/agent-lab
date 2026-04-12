"""
Тесты для safe_eval.
"""

import asyncio

import pytest
from apps.flows.src.eval import (
    safe_eval,
    SafeEvalError,
    deep_copy_state,
    merge_state,
    get_nested,
    set_nested,
    SafeContext,
    compile_function,
    PythonCompiler,
)
from core.state import ExecutionState
from core.context import Context, User


class TestCompileFunction:
    """Тесты компиляции функций."""

    def test_compile_simple_function(self):
        """Компиляция простой функции."""
        code = """
async def run(state):
    state['result'] = state.get('x', 0) * 2
    return state
"""
        func = compile_function(code)
        result = asyncio.run(func({"x": 5}))
        assert result["result"] == 10

    def test_compile_async_function(self):
        """Компиляция async функции."""
        code = """
async def run(state):
    state['result'] = 'async_ok'
    return state
"""
        func = compile_function(code)
        import inspect
        assert inspect.iscoroutinefunction(func)

    def test_compile_with_allowed_import(self):
        """Компиляция с разрешённым импортом."""
        code = """
import json

async def run(state):
    state['result'] = json.dumps({'key': 'value'})
    return state
"""
        func = compile_function(code)
        result = asyncio.run(func({}))
        assert result["result"] == '{"key": "value"}'

    def test_compile_with_math(self):
        """Компиляция с math модулем."""
        code = """
import math

async def run(state):
    state['result'] = math.sqrt(16)
    return state
"""
        func = compile_function(code)
        result = asyncio.run(func({}))
        assert result["result"] == 4.0

    def test_compile_function_not_found(self):
        """Функция не найдена в коде."""
        code = """
def other_func(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="Function 'run' not found"):
            compile_function(code)

    def test_compile_syntax_error(self):
        """Синтаксическая ошибка в коде."""
        code = """
def run(state
    return state
"""
        with pytest.raises(SafeEvalError, match="Syntax error"):
            compile_function(code)


class TestBlockedImports:
    """Тесты блокировки опасных импортов."""

    def test_block_os_import(self):
        """Блокировка import os."""
        code = """
import os

async def run(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="Import of 'os' is not allowed"):
            compile_function(code)

    def test_block_sys_import(self):
        """Блокировка import sys."""
        code = """
import sys

async def run(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="Import of 'sys' is not allowed"):
            compile_function(code)

    def test_block_subprocess_import(self):
        """Блокировка import subprocess."""
        code = """
import subprocess

async def run(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="Import of 'subprocess' is not allowed"):
            compile_function(code)

    def test_block_builtins_import(self):
        """Блокировка import builtins."""
        code = """
import builtins

async def run(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="Import of 'builtins' is not allowed"):
            compile_function(code)

    def test_block_socket_import(self):
        """Блокировка import socket."""
        code = """
import socket

async def run(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="Import of 'socket' is not allowed"):
            compile_function(code)

    def test_block_from_os_import(self):
        """Блокировка from os import."""
        code = """
from os import path

async def run(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="Import of 'os' is not allowed"):
            compile_function(code)

    def test_block_apps_import(self):
        code = """
from apps.flows.src.container import get_container

async def run(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="нельзя подключать внутренние модули платформы"):
            compile_function(code)

    def test_block_core_import(self):
        code = """
import core.config

async def run(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="нельзя подключать внутренние модули платформы"):
            compile_function(code)

    def test_block_pathlib_import(self):
        code = """
import pathlib

async def run(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="Import of 'pathlib' is not allowed"):
            compile_function(code)


class TestBlockedBuiltins:
    """Тесты блокировки опасных builtins."""

    def test_block_eval(self):
        """Блокировка eval."""
        code = """
async def run(state):
    result = eval("1+1")
    return state
"""
        func = compile_function(code)
        with pytest.raises(NameError):
            asyncio.run(func({}))

    def test_block_exec(self):
        """Блокировка exec."""
        code = """
async def run(state):
    exec("x = 1")
    return state
"""
        func = compile_function(code)
        with pytest.raises(NameError):
            asyncio.run(func({}))

    def test_block_open(self):
        """Блокировка open."""
        code = """
async def run(state):
    f = open("/etc/passwd")
    return state
"""
        func = compile_function(code)
        with pytest.raises(NameError):
            asyncio.run(func({}))

    def test_block_dunder_import(self):
        """Блокировка __import__."""
        code = """
async def run(state):
    os = __import__("os")
    return state
"""
        func = compile_function(code)
        with pytest.raises(SafeEvalError, match="Import of 'os' is not allowed"):
            asyncio.run(func({}))


class TestBlockedDunderAccess:
    """Тесты блокировки доступа к dunder атрибутам."""

    def test_block_class_access(self):
        """Блокировка __class__."""
        code = """
async def run(state):
    x = "".__class__
    return state
"""
        with pytest.raises(SafeEvalError, match="Access to '__class__' is not allowed"):
            compile_function(code)

    def test_block_bases_access(self):
        """Блокировка __bases__."""
        code = """
async def run(state):
    x = str.__bases__
    return state
"""
        with pytest.raises(SafeEvalError, match="Access to '__bases__' is not allowed"):
            compile_function(code)

    def test_block_subclasses_access(self):
        """Блокировка __subclasses__."""
        code = """
async def run(state):
    x = str.__subclasses__()
    return state
"""
        with pytest.raises(SafeEvalError, match="Access to '__subclasses__' is not allowed"):
            compile_function(code)


class TestSafeEval:
    """Тесты safe_eval."""

    @pytest.mark.asyncio
    async def test_safe_eval_simple(self):
        """Простое выполнение."""
        code = """
async def run(state):
    state['doubled'] = state.get('value', 0) * 2
    return state
"""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test",
            value=21
        )
        result = await safe_eval(code, state)
        assert result.value == 21
        assert result.__pydantic_extra__["doubled"] == 42

    @pytest.mark.asyncio
    async def test_safe_eval_sync_run(self):
        code = """
def run(state):
    state['sum'] = state.get('a', 0) + state.get('b', 0)
    return state
"""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test",
            a=10,
            b=5,
        )
        result = await safe_eval(code, state)
        assert result.__pydantic_extra__["sum"] == 15

    @pytest.mark.asyncio
    async def test_safe_eval_accepts_any_return_type(self):
        """Функция может возвращать любой тип - он записывается в state.result."""
        code = """
async def run(state):
    return "string result"
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test"
        )
        result = await safe_eval(code, state)
        # Скалярный результат записывается в state
        assert result is not None

    @pytest.mark.asyncio
    async def test_safe_eval_with_json(self):
        """Использование json модуля."""
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
        result = await safe_eval(code, state)
        assert result.parsed == {"name": "test"}

    @pytest.mark.asyncio
    async def test_safe_eval_reader_read_path(self, tmp_path) -> None:
        path = tmp_path / "se.txt"
        path.write_text("safe_eval_reader", encoding="utf-8")
        code = f"""
async def run(state):
    res = await reader.read({repr(str(path))})
    state['first_page'] = res.pages[0].text if res.pages else ''
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test",
        )
        result = await safe_eval(code, state)
        assert result.__pydantic_extra__["first_page"] == "safe_eval_reader"

    @pytest.mark.asyncio
    async def test_safe_eval_reader_text_file_from_path_string(self, tmp_path) -> None:
        path = tmp_path / "note.txt"
        path.write_text("inline_reader_ok", encoding="utf-8")
        code = f"""
async def run(state):
    res = await reader.read({repr(str(path))})
    state['text'] = res.pages[0].text if res.pages else ''
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test",
        )
        result = await safe_eval(code, state)
        assert "inline_reader_ok" in (result.__pydantic_extra__ or {}).get("text", "")

    @pytest.mark.asyncio
    async def test_safe_eval_with_datetime(self):
        """Использование datetime модуля."""
        code = """
from datetime import datetime

async def run(state):
    state.year = datetime.now().year
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test"
        )
        result = await safe_eval(code, state)
        assert result.year >= 2024

    @pytest.mark.asyncio
    async def test_safe_eval_preserves_state(self):
        """State сохраняется между операциями."""
        code = """
async def run(state):
    state['new_key'] = 'added'
    return state
"""
        original_state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            existing="value"
        )
        result = await safe_eval(code, original_state)
        assert result["existing"] == "value"
        assert result["new_key"] == "added"


class TestAllowedModules:
    """Тесты разрешённых модулей."""

    @pytest.mark.asyncio
    async def test_allowed_re(self):
        """Модуль re разрешён."""
        code = """
import re

async def run(state):
    match = re.search(r'\\d+', state.text)
    state.number = match.group() if match else None
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test",
            text="price: 123 dollars"
        )
        result = await safe_eval(code, state)
        assert result.number == "123"

    @pytest.mark.asyncio
    async def test_allowed_uuid(self):
        """Модуль uuid разрешён."""
        code = """
import uuid

async def run(state):
    state.uuid_str = str(uuid.uuid4())
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test"
        )
        result = await safe_eval(code, state)
        assert len(result.uuid_str) == 36

    @pytest.mark.asyncio
    async def test_allowed_base64(self):
        """Модуль base64 разрешён."""
        code = """
import base64

async def run(state):
    encoded = base64.b64encode(b'hello').decode()
    state.encoded = encoded
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test"
        )
        result = await safe_eval(code, state)
        assert result.encoded == "aGVsbG8="

    @pytest.mark.asyncio
    async def test_allowed_collections(self):
        """Модуль collections разрешён."""
        code = """
from collections import Counter

async def run(state):
    c = Counter(state.items)
    state.counts = dict(c)
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test",
            items=["a", "b", "a", "a"]
        )
        result = await safe_eval(code, state)
        assert result.counts == {"a": 3, "b": 1}

    @pytest.mark.asyncio
    async def test_allowed_random(self):
        """Модуль random разрешён."""
        code = """
import random

async def run(state):
    items = state.items
    state.choice = random.choice(items) if items else None
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test",
            items=["a", "b", "c"]
        )
        result = await safe_eval(code, state)
        assert result.choice in ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_allowed_decimal(self):
        """Модуль decimal разрешён."""
        code = """
from decimal import Decimal, ROUND_HALF_UP

async def run(state):
    price = Decimal(str(state.price))
    tax = price * Decimal('0.2')
    state.total = str((price + tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test",
            price="100.00"
        )
        result = await safe_eval(code, state)
        assert result.total == "120.00"

    @pytest.mark.asyncio
    async def test_allowed_string(self):
        """Модуль string разрешён."""
        code = """
import string

async def run(state):
    state.letters = string.ascii_lowercase[:5]
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test"
        )
        result = await safe_eval(code, state)
        assert result.letters == "abcde"


class TestStateUtilities:
    """Тесты утилит для state."""

    def test_deep_copy_state(self):
        """Глубокое копирование state."""
        original = {"a": 1, "nested": {"b": 2, "list": [1, 2, 3]}}
        copied = deep_copy_state(original)
        
        copied["a"] = 100
        copied["nested"]["b"] = 200
        copied["nested"]["list"].append(4)
        
        assert original["a"] == 1
        assert original["nested"]["b"] == 2
        assert len(original["nested"]["list"]) == 3

    def test_deep_copy_state_invalid_type(self):
        """deep_copy_state требует ExecutionState или dict."""
        with pytest.raises(SafeEvalError, match="state must be ExecutionState or dict"):
            deep_copy_state("not a dict")

    def test_merge_state_simple(self):
        """Простой merge."""
        base = {"a": 1, "b": 2}
        updates = {"b": 3, "c": 4}
        result = merge_state(base, updates)
        
        assert result == {"a": 1, "b": 3, "c": 4}
        assert base == {"a": 1, "b": 2}

    def test_merge_state_nested(self):
        """Merge с вложенными словарями."""
        base = {"config": {"x": 1, "y": 2}}
        updates = {"config": {"y": 3, "z": 4}}
        result = merge_state(base, updates)
        
        assert result == {"config": {"x": 1, "y": 3, "z": 4}}

    def test_merge_state_invalid_base(self):
        """merge_state требует ExecutionState или dict для base."""
        with pytest.raises(SafeEvalError, match="base must be ExecutionState or dict"):
            merge_state("not a dict", {})

    def test_merge_state_invalid_updates(self):
        """merge_state требует dict для updates."""
        with pytest.raises(SafeEvalError, match="updates must be a dict"):
            merge_state({}, "not a dict")

    def test_get_nested_simple(self):
        """Получение вложенного значения."""
        data = {"user": {"profile": {"name": "John"}}}
        result = get_nested(data, "user.profile.name")
        assert result == "John"

    def test_get_nested_default(self):
        """Получение default при отсутствии пути."""
        data = {"user": {"profile": {}}}
        result = get_nested(data, "user.profile.name", "Unknown")
        assert result == "Unknown"

    def test_get_nested_invalid_path(self):
        """Получение default при невалидном пути."""
        data = {"user": "not a dict"}
        result = get_nested(data, "user.profile.name", "Unknown")
        assert result == "Unknown"

    def test_set_nested_simple(self):
        """Установка вложенного значения."""
        data = {}
        set_nested(data, "user.profile.name", "John")
        assert data == {"user": {"profile": {"name": "John"}}}

    def test_set_nested_existing(self):
        """Установка в существующую структуру."""
        data = {"user": {"profile": {"age": 30}}}
        set_nested(data, "user.profile.name", "John")
        assert data["user"]["profile"]["name"] == "John"
        assert data["user"]["profile"]["age"] == 30

    def test_set_nested_invalid_data(self):
        """set_nested требует ExecutionState или dict."""
        with pytest.raises(SafeEvalError, match="data must be ExecutionState or dict"):
            set_nested("not a dict", "key", "value")


class TestSafeContext:
    """Тесты SafeContext."""

    def test_safe_context_with_none(self):
        """SafeContext с None контекстом."""
        ctx = SafeContext(None)
        assert ctx.channel == "unknown"
        assert ctx.user_id is None
        assert ctx.session_id is None
        assert ctx.flow_id is None
        assert ctx.metadata == {}

    def test_safe_context_with_context(self):
        """SafeContext с реальным контекстом."""
        context = Context(
            user=User(user_id="user123", name="Test User"),
            session_id="session456",
            channel="telegram",
            flow_id="my_flow",
            metadata={"key": "value"}
        )
        ctx = SafeContext(context)
        
        assert ctx.channel == "telegram"
        assert ctx.user_id == "user123"
        assert ctx.session_id == "session456"
        assert ctx.flow_id == "my_flow"
        assert ctx.metadata == {"key": "value"}

    def test_safe_context_metadata_is_copy(self):
        """Metadata возвращается как копия."""
        from core.models.identity_models import User
        context = Context(
            user=User(user_id="test", name="Test"),
            channel="test",
            metadata={"key": "value"}
        )
        ctx = SafeContext(context)
        
        metadata = ctx.metadata
        metadata["new_key"] = "new_value"
        
        assert "new_key" not in ctx.metadata


class TestContextInSafeEval:
    """Тесты доступа к контексту в safe_eval."""

    @pytest.mark.asyncio
    async def test_access_context_channel(self):
        """Доступ к каналу из inline кода."""
        code = """
async def run(state):
    state.channel = context.channel
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test"
        )
        context = Context(
            user=User(user_id="test", name="Test"),
            channel="telegram"
        )
        result = await safe_eval(code, state, context=context)
        assert result.channel == "telegram"

    @pytest.mark.asyncio
    async def test_access_context_user_id(self):
        """Доступ к user_id из inline кода."""
        code = """
async def run(state):
    state.user_id_from_ctx = context.user_id
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test"
        )
        context = Context(
            user=User(user_id="user123", name="Test"),
            channel="test"
        )
        result = await safe_eval(code, state, context=context)
        assert result.user_id_from_ctx == "user123"

    @pytest.mark.asyncio
    async def test_access_variables(self):
        """Доступ к переменным flow."""
        code = """
async def run(state):
    state['company'] = variables.get('company_name', 'Default')
    return state
"""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            variables={"company_name": "Acme Corp"}
        )
        result = await safe_eval(code, state)
        assert result["company"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_utilities_in_inline_code(self):
        """Использование утилит в inline коде."""
        code = """
async def run(state):
    backup = deep_copy_state(state)
    
    set_nested(state, 'result.value', 42)
    
    name = get_nested(state, 'user.name', 'Unknown')
    state['name'] = name
    
    return state
"""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            user={"name": "John"}
        )
        result = await safe_eval(code, state)
        
        assert result["result"]["value"] == 42
        assert result["name"] == "John"


class TestLLMInSafeEval:
    """Тесты LLM клиента в safe_eval."""

    @pytest.mark.asyncio
    async def test_llm_object_available(self):
        """LLM объект доступен в коде."""
        code = """
async def run(state):
    state.llm_available = llm is not None
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test"
        )
        result = await safe_eval(code, state)
        assert result.llm_available is True

    @pytest.mark.asyncio
    async def test_llm_chat_mock(self):
        """Вызов LLM через mock с A2A типами."""
        code = """
from a2a.types import Message, Part, Role, TextPart
from a2a.utils.message import get_message_text
import uuid

async def run(state):
    messages = [
        Message(
            messageId=str(uuid.uuid4()),
            role=Role.user,
            parts=[Part(root=TextPart(text=state.question))]
        )
    ]
    
    result = await llm.chat(messages)
    state.answer = get_message_text(result)
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test",
            question="Привет"
        )
        result = await safe_eval(code, state)
        assert hasattr(result, 'answer')
        assert result.answer is not None

    @pytest.mark.asyncio
    async def test_llm_chat_accepts_tool_decorator_instance(self) -> None:
        code = """
@tool(name="double_n", description="Удваивает целое", tags=["test"])
def double_n(x: int) -> int:
    return x * 2

async def run(state):
    msg = await llm.chat("ignore", tools=[double_n])
    state["got_message"] = msg is not None
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test",
        )
        result = await safe_eval(code, state)
        assert result.__pydantic_extra__["got_message"] is True

    @pytest.mark.asyncio
    async def test_llm_chat_rejects_raw_callable_in_tools(self) -> None:
        code = """
async def run(state):
    def inner(v: int) -> int:
        return v
    await llm.chat("x", tools=[inner])
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test",
        )
        with pytest.raises(SafeEvalError, match="tools\\[0\\]"):
            await safe_eval(code, state)

    @pytest.mark.asyncio
    async def test_inline_node_tool_llm_returns_tool_call_then_run_executes(
        self,
        mock_llm_with_queue,
    ) -> None:
        """
        В коде ноды: @tool + llm.chat(..., tools=[fn]). Mock LLM отдаёт tool_call;
        аргументы парсятся, tool.run выполняется на реальном FunctionTool.
        """
        mock_llm_with_queue(
            [
                {
                    "type": "tool_call",
                    "tool": "node_inline_multiply",
                    "args": {"a": 6, "b": 7},
                },
            ]
        )
        code = """
import json

@tool(
    name="node_inline_multiply",
    description="Умножает целое a на целое b",
    tags=["test"],
)
def node_inline_multiply(a: int, b: int) -> int:
    return a * b

async def run(state):
    schema = node_inline_multiply.to_openai_schema()
    fn = schema.get("function") or {}
    state["schema_ok"] = (
        schema.get("type") == "function"
        and fn.get("name") == "node_inline_multiply"
    )
    state["schema_name"] = fn.get("name")
    props = (fn.get("parameters") or {}).get("properties") or {}
    state["schema_has_a"] = "a" in props and "b" in props

    msg = await llm.chat("Посчитай произведение через tool", tools=[node_inline_multiply])
    calls = (msg.metadata or {}).get("tool_calls") or []
    if not calls:
        raise ValueError("mock должен вернуть tool_calls")
    entry = calls[0]
    name = entry.get("name")
    if name is None and isinstance(entry.get("function"), dict):
        name = entry["function"].get("name")
    args = entry.get("arguments")
    if args is None and isinstance(entry.get("function"), dict):
        args = entry["function"].get("arguments")
    if isinstance(args, str):
        args = json.loads(args)
    state["parsed_tool_name"] = name
    state["parsed_args"] = dict(args)
    state["product"] = await node_inline_multiply.run(args, state)
    return state
"""
        state = ExecutionState(
            task_id="test",
            context_id="test",
            user_id="test",
            session_id="test:test",
        )
        result = await safe_eval(code, state)
        assert result["schema_ok"] is True
        assert result["schema_name"] == "node_inline_multiply"
        assert result["schema_has_a"] is True
        assert result["parsed_tool_name"] == "node_inline_multiply"
        assert result["parsed_args"] == {"a": 6, "b": 7}
        assert result["product"] == 42


def test_python_namespace_has_no_get_container() -> None:
    """В inline namespace нет DI, произвольного FS и настроек сервиса."""
    from apps.flows.src.eval.namespace import PythonNamespaceBuilder

    ns = PythonNamespaceBuilder().build()
    assert "get_container" not in ns
    assert "get_settings" not in ns
    assert "Path" not in ns
    assert "read_path_bytes" not in ns
    assert "read_path_base64" not in ns
    assert "ReadOptions" not in ns
    assert "writer" in ns
    assert callable(getattr(ns["writer"], "write", None))
    assert callable(getattr(ns["writer"], "create_file", None))
    assert "calculator" in ns
    assert "read_file" in ns
    assert "create_file" in ns
    assert "ask_user_tool" in ns
    assert ns["ask_user_tool"] is not ns["ask_user"]


def test_compile_rejects_container_import_in_source() -> None:
    code = """
import apps.flows.src.container as c

async def run(state):
    return state
"""
    with pytest.raises(SafeEvalError, match="нельзя подключать внутренние модули платформы"):
        compile_function(code)

