"""
PythonNamespaceBuilder - построение namespace для выполнения Python кода.
"""

from __future__ import annotations

import ast
import builtins as b
import datetime as stdlib_datetime
import importlib
import math
import operator
import pathlib
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from a2a.types import (
    Artifact,
    DataPart,
    FilePart,
    Message,
    Part,
    Role,
    TextPart,
)

from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.eval.constants import BLOCKED_BUILTINS, BLOCKED_MODULES
from apps.flows.src.eval.state_utils import (
    add_agent_message,
    add_user_message,
    ask_user,
    deep_copy_state,
    extract_json,
    get_files,
    get_messages,
    get_nested,
    get_tool_result,
    get_user,
    merge_state,
    read_path_bytes,
    read_path_base64,
    set_nested,
)
from core.files.reader import FileReader
from core.files.writer import FileWriter
from apps.flows.src.tools.decorator import tool
from apps.flows.src.eval.wrappers import (
    HttpxModule,
    SafeChannel,
    SafeContext,
    SafeLLMClient,
)
from apps.flows.config import get_settings
from apps.flows.src.container import get_container
from apps.flows.tools.scheduling import _extract_ids_from_state
from core.errors import SafeEvalError
from core.scheduler.models import ContentType
from core.logging import get_logger


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


def _get_inline_logger(name: str = "inline_code"):
    """Возвращает логгер для inline кода."""
    return get_logger(name)


class PythonNamespaceBuilder:
    """
    Строит namespace для Python кода.
    Единственное место, где определяется что доступно в inline коде.
    """
    
    def __init__(
        self,
        context: Optional[Any] = None,
        variables: Optional[Dict[str, Any]] = None,
        resources: Optional[Dict[str, Any]] = None,
    ):
        self.context = context
        self.variables = variables or {}
        self.resources = resources or {}
    
    def build(self) -> Dict[str, Any]:
        """Возвращает полный namespace с builtins, типами, утилитами, wrappers."""
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
        namespace["Callable"] = Callable
        
        # FlowInterrupt для ask_user и interrupt
        namespace["FlowInterrupt"] = FlowInterrupt
        
        # Стандартный math только если ресурс flow не занял имя "math"
        if "math" not in self.resources:
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
        namespace["read_path_bytes"] = read_path_bytes
        namespace["read_path_base64"] = read_path_base64
        namespace["reader"] = FileReader()
        namespace["Path"] = pathlib.Path
        
        # Interrupt для запроса информации у пользователя
        namespace["ask_user"] = ask_user
        
        # JSON утилиты
        namespace["extract_json"] = extract_json
        
        # Логирование
        namespace["logger"] = _get_inline_logger("inline")
        
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

        # get_container в namespace не даём: inline-код не должен иметь доступ к DI и репозиториям.
        # Шаблоны из tool_repository часто без импортов; в исходниках было ``from datetime import datetime``.
        namespace["datetime"] = stdlib_datetime.datetime
        namespace["ContentType"] = ContentType
        namespace["_extract_ids_from_state"] = _extract_ids_from_state

        # BaseTool и @tool: функция из кода -> схема для llm.chat(..., tools=[...])
        container = get_container()
        namespace["writer"] = FileWriter()
        namespace["BaseTool"] = container.base_tool_class
        namespace["tool"] = tool
        
        # Ресурсы агента (code modules, llm, rag, http и др.)
        for resource_id, resource in self.resources.items():
            namespace[resource_id] = resource
        
        return namespace
