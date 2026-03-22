"""
Тесты для safe_eval.
"""

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
def run(state):
    state['result'] = state.get('x', 0) * 2
    return state
"""
        func = compile_function(code)
        result = func({"x": 5})
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

def run(state):
    state['result'] = json.dumps({'key': 'value'})
    return state
"""
        func = compile_function(code)
        result = func({})
        assert result["result"] == '{"key": "value"}'

    def test_compile_with_math(self):
        """Компиляция с math модулем."""
        code = """
import math

def run(state):
    state['result'] = math.sqrt(16)
    return state
"""
        func = compile_function(code)
        result = func({})
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

def run(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="Import of 'os' is not allowed"):
            compile_function(code)

    def test_block_sys_import(self):
        """Блокировка import sys."""
        code = """
import sys

def run(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="Import of 'sys' is not allowed"):
            compile_function(code)

    def test_block_subprocess_import(self):
        """Блокировка import subprocess."""
        code = """
import subprocess

def run(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="Import of 'subprocess' is not allowed"):
            compile_function(code)

    def test_block_builtins_import(self):
        """Блокировка import builtins."""
        code = """
import builtins

def run(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="Import of 'builtins' is not allowed"):
            compile_function(code)

    def test_block_socket_import(self):
        """Блокировка import socket."""
        code = """
import socket

def run(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="Import of 'socket' is not allowed"):
            compile_function(code)

    def test_block_from_os_import(self):
        """Блокировка from os import."""
        code = """
from os import path

def run(state):
    return state
"""
        with pytest.raises(SafeEvalError, match="Import of 'os' is not allowed"):
            compile_function(code)


class TestBlockedBuiltins:
    """Тесты блокировки опасных builtins."""

    def test_block_eval(self):
        """Блокировка eval."""
        code = """
def run(state):
    result = eval("1+1")
    return state
"""
        func = compile_function(code)
        with pytest.raises(NameError):
            func({})

    def test_block_exec(self):
        """Блокировка exec."""
        code = """
def run(state):
    exec("x = 1")
    return state
"""
        func = compile_function(code)
        with pytest.raises(NameError):
            func({})

    def test_block_open(self):
        """Блокировка open."""
        code = """
def run(state):
    f = open("/etc/passwd")
    return state
"""
        func = compile_function(code)
        with pytest.raises(NameError):
            func({})

    def test_block_dunder_import(self):
        """Блокировка __import__."""
        code = """
def run(state):
    os = __import__("os")
    return state
"""
        func = compile_function(code)
        with pytest.raises(SafeEvalError, match="Import of 'os' is not allowed"):
            func({})


class TestBlockedDunderAccess:
    """Тесты блокировки доступа к dunder атрибутам."""

    def test_block_class_access(self):
        """Блокировка __class__."""
        code = """
def run(state):
    x = "".__class__
    return state
"""
        with pytest.raises(SafeEvalError, match="Access to '__class__' is not allowed"):
            compile_function(code)

    def test_block_bases_access(self):
        """Блокировка __bases__."""
        code = """
def run(state):
    x = str.__bases__
    return state
"""
        with pytest.raises(SafeEvalError, match="Access to '__bases__' is not allowed"):
            compile_function(code)

    def test_block_subclasses_access(self):
        """Блокировка __subclasses__."""
        code = """
def run(state):
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
    async def test_safe_eval_sync_function(self):
        """Синхронная функция."""
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
            b=5
        )
        result = await safe_eval(code, state)
        assert result.__pydantic_extra__["sum"] == 15

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_safe_eval_accepts_any_return_type(self):
        """Функция может возвращать любой тип - он записывается в state.result."""
        code = """
def run(state):
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
        result = await safe_eval(code, state)
        assert result.parsed == {"name": "test"}

    @pytest.mark.asyncio
    async def test_safe_eval_with_datetime(self):
        """Использование datetime модуля."""
        code = """
from datetime import datetime

def run(state):
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
def run(state):
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

def run(state):
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

def run(state):
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

def run(state):
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

def run(state):
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

def run(state):
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

def run(state):
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

def run(state):
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
def run(state):
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
def run(state):
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
def run(state):
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
def run(state):
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
def run(state):
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

