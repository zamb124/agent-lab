"""
SafeEval - безопасное выполнение inline кода.
Ограничивает доступные модули и блокирует опасные операции.
Предоставляет доступ к LLM, переменным агента, контексту, A2A типам и утилитам.
"""

from __future__ import annotations

import ast
import base64
import builtins as b
import copy
import importlib
import inspect
import math
import operator
import pathlib
import re
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, TYPE_CHECKING

import httpx
from core.http import get_httpx_client
from a2a.types import (
    Artifact,
    DataPart,
    FilePart,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TextPart,
)

if TYPE_CHECKING:
    from core.state import ExecutionState

from apps.agents.src.agent.exceptions import AgentInterrupt
from core.clients.llm.factory import get_llm
from apps.agents.config import get_settings
from apps.agents.src.container import get_container
from core.context import get_current_channel
from core.logging import get_logger
from apps.agents.src.utils import extract_json_from_response
from core.errors import SafeEvalError

logger = get_logger(__name__)


BLOCKED_MODULES = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "shutil",
        "socket",
        "pickle",
        "marshal",
        "ctypes",
        "multiprocessing",
        "threading",
        "signal",
        "resource",
        "pty",
        "fcntl",
        "termios",
        "syslog",
        "posix",
        "nt",
        "_thread",
        "builtins",
        "__builtin__",
        "importlib",
        "code",
        "codeop",
        "compileall",
        "py_compile",
    }
)

BLOCKED_BUILTINS = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "open",
        "__import__",
        "globals",
        "locals",
        "vars",
        "dir",
        "getattr",
        "setattr",
        "delattr",
        "hasattr",
        "classmethod",
        "staticmethod",
        "property",
        "super",
        "object",
        "memoryview",
        "bytearray",
        "breakpoint",
        "input",
        "help",
        "exit",
        "quit",
    }
)


class SafeLLMClient:
    """
    Безопасная обертка над LLM клиентом для использования в inline коде.
    Использует stream() и собирает результат.
    """

    def _get_llm(self, model: Optional[str] = None, temperature: Optional[float] = None):
        """Получает LLM клиент."""
        return get_llm(model_name=model, temperature=temperature)

    async def chat(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Message:
        """
        Вызывает LLM и возвращает результат.

        Args:
            messages: История сообщений (List[Message] из a2a-sdk)
            model: Имя модели (опционально)
            temperature: Температура генерации (опционально)

        Returns:
            Message - ответ ассистента (a2a-sdk тип)
        """
        llm = self._get_llm(model, temperature)

        content_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []

        async for event in llm.stream(messages):
            if isinstance(event, TaskArtifactUpdateEvent):
                if event.artifact and event.artifact.parts:
                    for part in event.artifact.parts:
                        if hasattr(part, "root") and hasattr(part.root, "text"):
                            content_parts.append(part.root.text)

        content = "".join(content_parts)

        return Message(
            messageId="",
            role=Role.agent,
            parts=[Part(root=TextPart(text=content))],
            metadata={"tool_calls": tool_calls} if tool_calls else None,
        )

    async def chat_simple(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Простой вызов LLM - принимает строку, возвращает строку.

        Args:
            prompt: Текст запроса
            model: Имя модели (опционально)
            temperature: Температура генерации (опционально)

        Returns:
            Текст ответа
        """
        messages = [
            Message(
                messageId=str(uuid.uuid4()),
                role=Role.user,
                parts=[Part(root=TextPart(text=prompt))],
            )
        ]
        response = await self.chat(messages, model, temperature)

        for part in response.parts:
            if hasattr(part, "root") and hasattr(part.root, "text"):
                return part.root.text
        return ""

    async def chat_with_tools(
        self,
        messages: List[Message],
        tools: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Message:
        """
        Вызов LLM с tools.

        Args:
            messages: История сообщений
            tools: Список tools в OpenAI формате
            model: Имя модели (опционально)
            temperature: Температура генерации (опционально)

        Returns:
            Message с возможными tool_calls в metadata
        """
        llm = self._get_llm(model, temperature)

        content_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []

        async for event in llm.stream(messages, tools):
            if isinstance(event, TaskArtifactUpdateEvent):
                if event.artifact and event.artifact.parts:
                    for part in event.artifact.parts:
                        if hasattr(part, "root") and hasattr(part.root, "text"):
                            content_parts.append(part.root.text)
            if hasattr(event, "status") and event.status:
                if event.status.message and event.status.message.metadata:
                    tc = event.status.message.metadata.get("tool_calls")
                    if tc:
                        tool_calls = tc

        content = "".join(content_parts)

        return Message(
            messageId=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=content))],
            metadata={"tool_calls": tool_calls} if tool_calls else None,
        )


class SafeContext:
    """
    Безопасная обертка над контекстом выполнения.
    Предоставляет только чтение основных полей.
    """

    def __init__(self, context: Optional[Any] = None):
        self._context = context

    @property
    def channel(self) -> str:
        """Канал коммуникации: a2a, api, telegram, max, voip."""
        if self._context is None:
            return "unknown"
        return self._context.channel

    @property
    def user_id(self) -> Optional[str]:
        """ID пользователя."""
        if self._context is None or self._context.user is None:
            return None
        return self._context.user.user_id

    @property
    def session_id(self) -> Optional[str]:
        """ID сессии."""
        if self._context is None:
            return None
        return self._context.session_id

    @property
    def agent_id(self) -> Optional[str]:
        """ID агента."""
        if self._context is None:
            return None
        return self._context.agent_id

    @property
    def metadata(self) -> Dict[str, Any]:
        """Метаданные запроса (только для чтения)."""
        if self._context is None:
            return {}
        return dict(self._context.metadata)


def deep_copy_state(state: 'ExecutionState | dict') -> 'ExecutionState | dict':
    """
    Глубокое копирование state.

    Args:
        state: Исходный state (ExecutionState или dict)

    Returns:
        Копия state
    """
    from core.state import ExecutionState
    
    if isinstance(state, ExecutionState):
        return ExecutionState.model_validate(state.model_dump(exclude_none=False))
    elif isinstance(state, dict):
        return copy.deepcopy(state)
    else:
        raise SafeEvalError("state must be ExecutionState or dict")


def merge_state(base: 'ExecutionState | dict', updates: dict) -> 'ExecutionState | dict':
    """
    Безопасный merge двух state.

    Args:
        base: Базовый state (ExecutionState или dict)
        updates: Обновления (dict)

    Returns:
        Объединенный state
    """
    from core.state import ExecutionState
    
    if isinstance(base, ExecutionState):
        # Для ExecutionState обновляем атрибуты
        if not isinstance(updates, dict):
            raise SafeEvalError("updates must be a dict")
        for key, value in updates.items():
            setattr(base, key, value)
        return base
    elif isinstance(base, dict):
        if not isinstance(updates, dict):
            raise SafeEvalError("updates must be a dict")
    else:
        raise SafeEvalError("base must be ExecutionState or dict")

    result = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_state(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def get_nested(data: 'ExecutionState | dict', path: str, default: Any = None) -> Any:
    """
    Получение вложенного значения по пути.

    Args:
        data: ExecutionState или словарь
        path: Путь через точку (например, "user.name")
        default: Значение по умолчанию

    Returns:
        Значение по пути или default
    """
    from core.state import ExecutionState
    
    keys = path.split(".")
    result = data

    for key in keys:
        if isinstance(result, ExecutionState):
            result = getattr(result, key, None)
        elif isinstance(result, dict):
            result = result.get(key)
        else:
            return default
        
        if result is None:
            return default

    return result


def set_nested(data: 'ExecutionState | dict', path: str, value: Any) -> 'ExecutionState | dict':
    """
    Установка вложенного значения по пути.

    Args:
        data: ExecutionState или словарь
        path: Путь через точку (например, "user.name")
        value: Значение для установки

    Returns:
        Модифицированный data
    """
    from core.state import ExecutionState
    
    keys = path.split(".")
    
    if isinstance(data, ExecutionState):
        # Для ExecutionState устанавливаем атрибут напрямую
        if len(keys) == 1:
            setattr(data, keys[0], value)
        else:
            # Для вложенных путей работаем с variables или создаём структуру
            current = data
            for key in keys[:-1]:
                if not hasattr(current, key):
                    setattr(current, key, {})
                current = getattr(current, key)
                if not isinstance(current, dict):
                    raise SafeEvalError(f"Cannot set nested value: {key} is not a dict")
            current[keys[-1]] = value
        return data
    elif isinstance(data, dict):
        current = data
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            elif not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
        return data
    else:
        raise SafeEvalError("data must be ExecutionState or dict")


def get_files(state: 'ExecutionState | dict') -> List[Dict[str, Any]]:
    """
    Возвращает список файлов из state.

    Args:
        state: Текущий state (ExecutionState или dict)

    Returns:
        Список файлов [{name, path, mime_type, size}, ...]
    """
    from core.state import ExecutionState
    
    if isinstance(state, ExecutionState):
        return state.files or []
    elif isinstance(state, dict):
        return state.get("files", [])
    else:
        return []


def read_file(file_path: str, mode: str = "rb") -> bytes:
    """
    Безопасно читает файл по пути.
    
    Args:
        file_path: Путь к файлу
        mode: Режим чтения ("rb" для бинарного, "r" для текстового)
    
    Returns:
        Содержимое файла (bytes для "rb", str для "r")
    
    Raises:
        SafeEvalError: Если файл не найден или ошибка чтения
    """
    try:
        path = pathlib.Path(file_path)
        if not path.exists():
            raise SafeEvalError(f"File not found: {file_path}")
        
        if mode == "rb":
            return path.read_bytes()
        else:
            return path.read_text(encoding="utf-8")
    except Exception as e:
        raise SafeEvalError(f"Error reading file {file_path}: {e}")


def read_file_base64(file_path: str) -> str:
    """
    Читает файл и возвращает base64 строку.
    
    Args:
        file_path: Путь к файлу
    
    Returns:
        Base64 строка
    
    Raises:
        SafeEvalError: Если файл не найден или ошибка чтения
    """
    data = read_file(file_path, mode="rb")
    return base64.b64encode(data).decode("utf-8")


def get_user(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Возвращает информацию о пользователе из state.

    Args:
        state: Текущий state

    Returns:
        Информация о пользователе {id, email, grps}
    """
    return {"id": state.get("user_id", ""), "groups": state.get("user_groups", [])}


def get_tool_result(state: Dict[str, Any], tool_name: str) -> Any:
    """
    Возвращает результат выполнения tool.

    Args:
        state: Текущий state
        tool_name: Имя tool

    Returns:
        Результат tool или None
    """
    return state.get("tool_results", {}).get(tool_name)


def get_messages(state: Dict[str, Any]) -> List[Message]:
    """
    Возвращает историю сообщений из state.

    Args:
        state: Текущий state

    Returns:
        Список A2A Message
    """
    return state.get("messages", [])


def add_user_message(state: Dict[str, Any], content: str) -> Dict[str, Any]:
    """
    Добавляет сообщение пользователя в state.

    Args:
        state: Текущий state
        content: Текст сообщения

    Returns:
        Обновленный state
    """
    if "messages" not in state:
        state["messages"] = []

    task_id = state.get("task_id")
    message = Message(
        messageId=str(uuid.uuid4()),
        role=Role.user,
        parts=[Part(root=TextPart(text=content))],
        taskId=task_id,
    )
    state["messages"].append(message)
    return state


def add_agent_message(state: Dict[str, Any], content: str) -> Dict[str, Any]:
    """
    Добавляет сообщение агента в state.

    Args:
        state: Текущий state dict
        content: Текст сообщения

    Returns:
        Обновленный state dict
    """
    if "messages" not in state:
        state["messages"] = []

    task_id = state.get("task_id")
    message = Message(
        messageId=str(uuid.uuid4()),
        role=Role.agent,
        parts=[Part(root=TextPart(text=content))],
        taskId=task_id,
    )
    state["messages"].append(message)
    return state


def ask_user(question: str) -> None:
    """
    Запрашивает информацию у пользователя через interrupt.

    Args:
        question: Вопрос для пользователя

    Raises:
        AgentInterrupt: Всегда, для прерывания выполнения
    """
    raise AgentInterrupt(question=question)


def extract_json(text: str) -> Any:
    """
    Извлекает JSON из текста.

    Поддерживает:
    - JSON в markdown блоке ```json ... ```
    - Прямой JSON объект или массив

    Args:
        text: Текст с JSON

    Returns:
        Распарсенный JSON или None
    """
    return extract_json_from_response(text)


def get_inline_logger(name: str = "inline_code"):
    """
    Возвращает логгер для inline кода.

    Args:
        name: Имя логгера

    Returns:
        Logger
    """
    return get_logger(name)


class SafeChannel:
    """
    Безопасная обертка для отправки сообщений пользователю.
    """

    def __init__(self, context: Optional[Any] = None):
        self._context = context

    async def send(self, content: str) -> None:
        """
        Отправляет сообщение пользователю через текущий канал.

        Args:
            content: Текст сообщения
        """
        channel = get_current_channel()
        if channel is None:
            logger.warning("Cannot send message: no channel available")
            return

        await channel.send_to_user(content)

    async def send_with_buttons(
        self, content: str, buttons: List[str]
    ) -> None:
        """
        Отправляет сообщение с кнопками быстрого ответа.

        Args:
            content: Текст сообщения
            buttons: Список кнопок
        """
        channel = get_current_channel()
        if channel is None:
            logger.warning("Cannot send message: no channel available")
            return

        await channel.send_to_user(content, buttons=buttons)


class HttpxModule:
    """
    Модуль-обертка httpx с функциями верхнего уровня.
    Предоставляет простой API: httpx.get(), httpx.post() и т.д.
    """

    _default_timeout = 30.0

    @staticmethod
    async def get(
        url: Union[str, httpx.URL],
        *,
        params: Optional[Union[Dict[str, Any], httpx.QueryParams]] = None,
        headers: Optional[Union[Dict[str, str], httpx.Headers]] = None,
        cookies: Optional[Union[Dict[str, str], httpx.Cookies]] = None,
        auth: Optional[httpx.Auth] = None,
        follow_redirects: bool = False,
        timeout: Optional[Union[float, httpx.Timeout]] = None,
        **kwargs,
    ) -> httpx.Response:
        """GET запрос через прокси."""
        timeout = timeout or HttpxModule._default_timeout
        async with get_httpx_client(timeout=timeout, proxy=True) as client:
            return await client.get(
                url,
                params=params,
                headers=headers,
                cookies=cookies,
                auth=auth,
                follow_redirects=follow_redirects,
                **kwargs,
            )

    @staticmethod
    async def post(
        url: Union[str, httpx.URL],
        *,
        content: Optional[Union[str, bytes]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        params: Optional[Union[Dict[str, Any], httpx.QueryParams]] = None,
        headers: Optional[Union[Dict[str, str], httpx.Headers]] = None,
        cookies: Optional[Union[Dict[str, str], httpx.Cookies]] = None,
        auth: Optional[httpx.Auth] = None,
        follow_redirects: bool = False,
        timeout: Optional[Union[float, httpx.Timeout]] = None,
        **kwargs,
    ) -> httpx.Response:
        """POST запрос через прокси."""
        timeout = timeout or HttpxModule._default_timeout
        async with get_httpx_client(timeout=timeout, proxy=True) as client:
            return await client.post(
                url,
                content=content,
                data=data,
                files=files,
                json=json,
                params=params,
                headers=headers,
                cookies=cookies,
                auth=auth,
                follow_redirects=follow_redirects,
                **kwargs,
            )

    @staticmethod
    async def put(
        url: Union[str, httpx.URL],
        *,
        content: Optional[Union[str, bytes]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        params: Optional[Union[Dict[str, Any], httpx.QueryParams]] = None,
        headers: Optional[Union[Dict[str, str], httpx.Headers]] = None,
        cookies: Optional[Union[Dict[str, str], httpx.Cookies]] = None,
        auth: Optional[httpx.Auth] = None,
        follow_redirects: bool = False,
        timeout: Optional[Union[float, httpx.Timeout]] = None,
        **kwargs,
    ) -> httpx.Response:
        """PUT запрос через прокси."""
        timeout = timeout or HttpxModule._default_timeout
        async with get_httpx_client(timeout=timeout, proxy=True) as client:
            return await client.put(
                url,
                content=content,
                data=data,
                files=files,
                json=json,
                params=params,
                headers=headers,
                cookies=cookies,
                auth=auth,
                follow_redirects=follow_redirects,
                **kwargs,
            )

    @staticmethod
    async def patch(
        url: Union[str, httpx.URL],
        *,
        content: Optional[Union[str, bytes]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        params: Optional[Union[Dict[str, Any], httpx.QueryParams]] = None,
        headers: Optional[Union[Dict[str, str], httpx.Headers]] = None,
        cookies: Optional[Union[Dict[str, str], httpx.Cookies]] = None,
        auth: Optional[httpx.Auth] = None,
        follow_redirects: bool = False,
        timeout: Optional[Union[float, httpx.Timeout]] = None,
        **kwargs,
    ) -> httpx.Response:
        """PATCH запрос через прокси."""
        timeout = timeout or HttpxModule._default_timeout
        async with get_httpx_client(timeout=timeout, proxy=True) as client:
            return await client.patch(
                url,
                content=content,
                data=data,
                files=files,
                json=json,
                params=params,
                headers=headers,
                cookies=cookies,
                auth=auth,
                follow_redirects=follow_redirects,
                **kwargs,
            )

    @staticmethod
    async def delete(
        url: Union[str, httpx.URL],
        *,
        params: Optional[Union[Dict[str, Any], httpx.QueryParams]] = None,
        headers: Optional[Union[Dict[str, str], httpx.Headers]] = None,
        cookies: Optional[Union[Dict[str, str], httpx.Cookies]] = None,
        auth: Optional[httpx.Auth] = None,
        follow_redirects: bool = False,
        timeout: Optional[Union[float, httpx.Timeout]] = None,
        **kwargs,
    ) -> httpx.Response:
        """DELETE запрос через прокси."""
        timeout = timeout or HttpxModule._default_timeout
        async with get_httpx_client(timeout=timeout, proxy=True) as client:
            return await client.delete(
                url,
                params=params,
                headers=headers,
                cookies=cookies,
                auth=auth,
                follow_redirects=follow_redirects,
                **kwargs,
            )

    @staticmethod
    async def request(
        method: str,
        url: Union[str, httpx.URL],
        *,
        content: Optional[Union[str, bytes]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        params: Optional[Union[Dict[str, Any], httpx.QueryParams]] = None,
        headers: Optional[Union[Dict[str, str], httpx.Headers]] = None,
        cookies: Optional[Union[Dict[str, str], httpx.Cookies]] = None,
        auth: Optional[httpx.Auth] = None,
        follow_redirects: bool = False,
        timeout: Optional[Union[float, httpx.Timeout]] = None,
        **kwargs,
    ) -> httpx.Response:
        """Универсальный request через прокси."""
        timeout = timeout or HttpxModule._default_timeout
        async with get_httpx_client(timeout=timeout, proxy=True) as client:
            return await client.request(
                method,
                url,
                content=content,
                data=data,
                files=files,
                json=json,
                params=params,
                headers=headers,
                cookies=cookies,
                auth=auth,
                follow_redirects=follow_redirects,
                **kwargs,
            )


def _create_safe_builtins() -> Dict[str, Any]:
    """Создаёт безопасный набор builtins."""
    safe = {}
    for name in dir(b):
        if name.startswith("_"):
            continue
        if name in BLOCKED_BUILTINS:
            continue
        safe[name] = getattr(b, name)

    # __build_class__ нужен для определения классов в inline коде
    safe["__build_class__"] = b.__build_class__

    return safe


def _safe_import(name: str, *args, **kwargs):
    """Безопасный import - всё разрешено кроме опасных модулей."""
    base_module = name.split(".")[0]

    if name in BLOCKED_MODULES or base_module in BLOCKED_MODULES:
        raise SafeEvalError(f"Import of '{name}' is not allowed")

    return importlib.import_module(name)


def _validate_code(code: str) -> None:
    """Проверяет код на опасные конструкции."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SafeEvalError(f"Syntax error: {e}")

    for node in ast.walk(tree):
        # Блокируем import запрещенных модулей
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module_name = None
            if isinstance(node, ast.Import):
                module_name = node.names[0].name
            elif isinstance(node, ast.ImportFrom) and node.module:
                module_name = node.module

            if module_name:
                base = module_name.split(".")[0]
                if module_name in BLOCKED_MODULES or base in BLOCKED_MODULES:
                    raise SafeEvalError(f"Import of '{module_name}' is not allowed")

        # Блокируем доступ к dunder атрибутам
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                raise SafeEvalError(f"Access to '{node.attr}' is not allowed")


class SafeEval:
    """
    Единый класс для безопасного выполнения inline кода.
    
    Предоставляет общий namespace для tools и nodes с разными методами вызова:
    - execute_tool(code, args, state) - для tools (ищет execute, возвращает Any)
    - execute_node(code, state) - для nodes (ищет run, возвращает dict)
    """
    
    def __init__(self, context: Optional[Any] = None, variables: Optional[Dict[str, Any]] = None):
        self.context = context
        self.variables = variables or {}
    
    def _build_namespace(self) -> Dict[str, Any]:
        """Создаёт общий namespace для выполнения кода."""
        safe_builtins = _create_safe_builtins()
        safe_builtins["__import__"] = _safe_import
        
        namespace: Dict[str, Any] = {
            "__builtins__": safe_builtins,
            "__name__": "__inline__",
            "__doc__": None,
        }
        
        # Типы из typing для аннотаций
        namespace["Optional"] = Optional
        namespace["List"] = List
        namespace["Dict"] = Dict
        namespace["Any"] = Any
        namespace["Union"] = Union
        namespace["Tuple"] = Tuple
        
        # AgentInterrupt для ask_user и других tools
        namespace["AgentInterrupt"] = AgentInterrupt
        
        # Стандартные модули для tools
        namespace["math"] = math
        namespace["ast"] = ast
        namespace["operator"] = operator
        namespace["json"] = importlib.import_module("json")
        namespace["mimetypes"] = importlib.import_module("mimetypes")
        namespace["base64"] = importlib.import_module("base64")
        
        # LLM клиент
        namespace["llm"] = SafeLLMClient()
        
        # Утилиты для работы со state (базовые)
        namespace["deep_copy_state"] = deep_copy_state
        namespace["merge_state"] = merge_state
        namespace["get_nested"] = get_nested
        namespace["set_nested"] = set_nested
        
        # Утилиты для работы со state (расширенные)
        namespace["get_files"] = get_files
        namespace["get_user"] = get_user
        namespace["get_tool_result"] = get_tool_result
        namespace["get_messages"] = get_messages
        namespace["add_user_message"] = add_user_message
        namespace["add_agent_message"] = add_agent_message
        
        # Утилиты для работы с файлами
        namespace["read_file"] = read_file
        namespace["read_file_base64"] = read_file_base64
        namespace["Path"] = pathlib.Path
        
        # Interrupt для запроса информации у пользователя
        namespace["ask_user"] = ask_user
        
        # JSON утилиты
        namespace["extract_json"] = extract_json
        
        # Логирование
        namespace["logger"] = get_inline_logger("inline")
        
        # Контекст выполнения
        namespace["context"] = SafeContext(self.context)
        
        # Канал для отправки сообщений
        namespace["channel"] = SafeChannel(self.context)
        
        # Переменные агента (только для чтения)
        namespace["variables"] = dict(self.variables)
        
        # A2A типы для создания сообщений
        namespace["Message"] = Message
        namespace["Part"] = Part
        namespace["TextPart"] = TextPart
        namespace["FilePart"] = FilePart
        namespace["DataPart"] = DataPart
        namespace["Role"] = Role
        namespace["Artifact"] = Artifact
        
        # HTTP клиент
        namespace["httpx"] = HttpxModule()
        
        # Настройки
        namespace["get_settings"] = get_settings
        
        # BaseTool для создания инструментов в inline коде (через DI)
        container = get_container()
        namespace["BaseTool"] = container.base_tool_class
        
        return namespace
    
    def _compile(self, code: str, func_name: str, auto_find: bool = True) -> Callable:
        """Компилирует код и возвращает функцию."""
        _validate_code(code)
        
        namespace = self._build_namespace()
        
        try:
            exec(code, namespace)
        except Exception as e:
            raise SafeEvalError(f"Compilation error: {e}")
        
        if func_name not in namespace:
            # Автопоиск первой функции только для стандартных имен
            if auto_find and func_name in ("run", "execute"):
                match = re.search(r"(?:async\s+)?def\s+(\w+)\s*\(", code)
                if match:
                    found_func_name = match.group(1)
                    if found_func_name in namespace:
                        return namespace[found_func_name]
            raise SafeEvalError(f"Function '{func_name}' not found in code")
        
        return namespace[func_name]
    
    async def execute_node(self, code: str, state: 'ExecutionState') -> 'ExecutionState':
        """
        Выполняет код ноды (ищет функцию run).
        
        Контракт: функция ВСЕГДА должна возвращать ExecutionState.
        Поддержка dict для обратной совместимости со старым кодом.
        
        Args:
            code: Код функции
            state: ExecutionState для передачи
            
        Returns:
            ExecutionState
            
        Raises:
            TypeError: Если функция вернула не ExecutionState
        """
        from core.state import ExecutionState
        
        func = self._compile(code, "run", auto_find=True)
        
        if inspect.iscoroutinefunction(func):
            result = await func(state)
        else:
            result = func(state)
        
        # Возвращаем результат как есть - BaseNode._apply_output_mapping обработает
        return result
    
    async def execute_tool(self, code: str, args: Dict[str, Any], state: Optional['ExecutionState'] = None) -> Any:
        """
        Выполняет код tool.
        
        Поддерживает два формата:
        1. Функция: def execute(args, state) или async def execute(args, state)
        2. Класс: class MyTool(BaseTool) с методом execute
        
        Args:
            code: Код функции или класса
            args: Аргументы вызова tool
            state: State (опционально)
            
        Returns:
            Результат выполнения (Any)
        """
        _validate_code(code)
        namespace = self._build_namespace()
        
        try:
            exec(code, namespace)
        except Exception as e:
            raise SafeEvalError(f"Compilation error: {e}")
        
        # Ищем класс наследующий BaseTool
        base_tool_cls = namespace["BaseTool"]
        tool_class = None
        for name, obj in namespace.items():
            if isinstance(obj, type) and issubclass(obj, base_tool_cls) and obj is not base_tool_cls:
                tool_class = obj
                break
        
        if tool_class:
            tool_instance = tool_class()
            return await tool_instance.run(args, state)
        
        # Ищем функцию execute
        func = None
        if "execute" in namespace:
            func = namespace["execute"]
        else:
            # Автопоиск первой функции
            match = re.search(r"(?:async\s+)?def\s+(\w+)\s*\(", code)
            if match:
                found_func_name = match.group(1)
                if found_func_name in namespace:
                    func = namespace[found_func_name]
        
        if func is None:
            raise SafeEvalError("No 'execute' function or BaseTool class found in code")
        
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        
        # Если первый параметр - "args", передаём dict целиком
        if params and params[0] == "args":
            call_kwargs = {"args": args}
            if "state" in params:
                call_kwargs["state"] = state
            if inspect.iscoroutinefunction(func):
                return await func(**call_kwargs)
            return func(**call_kwargs)
        
        # Иначе распаковываем args в именованные параметры
        kwargs = dict(args)
        if "state" in params:
            kwargs["state"] = state
        
        if inspect.iscoroutinefunction(func):
            return await func(**kwargs)
        return func(**kwargs)


# Вспомогательные функции
def compile_function(
    code: str,
    func_name: str = "run",
    context: Optional[Any] = None,
    variables: Optional[Dict[str, Any]] = None,
    auto_find: bool = False,
) -> Callable:
    """Компилирует код и возвращает функцию."""
    evaluator = SafeEval(context=context, variables=variables)
    return evaluator._compile(code, func_name, auto_find=auto_find)


async def safe_eval(
    code: str,
    state: 'ExecutionState',
    context: Optional[Any] = None,
    func_name: str = "run",
) -> 'ExecutionState':
    """Безопасно выполняет inline код ноды."""
    variables = state.variables
    evaluator = SafeEval(context=context, variables=variables)
    return await evaluator.execute_node(code, state)
