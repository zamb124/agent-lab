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

import apps.flows.tools as flows_tools
from apps.flows.src.eval.import_policy import safe_inline_import
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
    set_nested,
)
from apps.flows.src.eval.wrappers import (
    HttpxModule,
    SafeChannel,
    SafeContext,
    SafeLLMClient,
)
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.scheduling import _extract_ids_from_state
from core.files.reader import FileReader
from core.files.writer import FileWriter
from core.inline_python_eval_policy import ALLOWED_BUILTINS
from core.logging import get_logger
from core.scheduler.models import ContentType


def _create_safe_builtins() -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for name in ALLOWED_BUILTINS:
        if hasattr(b, name):
            safe[name] = getattr(b, name)
    safe["__import__"] = safe_inline_import
    safe["__build_class__"] = b.__build_class__
    return safe


def _get_inline_logger(name: str = "inline_code"):
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
        base_tool_class: Optional[type] = None,
    ):
        self.context = context
        self.variables = variables or {}
        self.resources = resources or {}
        if base_tool_class is None:
            from apps.flows.src.tools.base import BaseTool

            base_tool_class = BaseTool
        self.base_tool_class = base_tool_class

    def build(self) -> Dict[str, Any]:
        safe_builtins = _create_safe_builtins()

        namespace: Dict[str, Any] = {
            "__builtins__": safe_builtins,
            "__name__": "__inline__",
            "__doc__": None,
        }

        namespace["Optional"] = Optional
        namespace["List"] = List
        namespace["Dict"] = Dict
        namespace["Any"] = Any
        namespace["Union"] = Union
        namespace["Tuple"] = Tuple
        namespace["Callable"] = Callable

        namespace["FlowInterrupt"] = FlowInterrupt

        if "math" not in self.resources:
            namespace["math"] = math
        namespace["ast"] = ast
        namespace["operator"] = operator
        namespace["json"] = importlib.import_module("json")
        namespace["mimetypes"] = importlib.import_module("mimetypes")
        namespace["base64"] = importlib.import_module("base64")

        namespace["llm"] = SafeLLMClient()

        namespace["deep_copy_state"] = deep_copy_state
        namespace["merge_state"] = merge_state
        namespace["get_nested"] = get_nested
        namespace["set_nested"] = set_nested

        namespace["get_files"] = get_files
        namespace["get_user"] = get_user
        namespace["get_tool_result"] = get_tool_result
        namespace["get_messages"] = get_messages
        namespace["add_user_message"] = add_user_message
        namespace["add_agent_message"] = add_agent_message

        namespace["reader"] = FileReader()

        namespace["extract_json"] = extract_json

        namespace["logger"] = _get_inline_logger("inline")

        namespace["context"] = SafeContext(self.context)

        namespace["channel"] = SafeChannel(self.context)

        namespace["variables"] = dict(self.variables)

        namespace["Message"] = Message
        namespace["Part"] = Part
        namespace["TextPart"] = TextPart
        namespace["FilePart"] = FilePart
        namespace["DataPart"] = DataPart
        namespace["Role"] = Role
        namespace["Artifact"] = Artifact

        namespace["httpx"] = HttpxModule()

        namespace["datetime"] = stdlib_datetime.datetime
        namespace["ContentType"] = ContentType
        namespace["_extract_ids_from_state"] = _extract_ids_from_state

        namespace["writer"] = FileWriter()
        namespace["BaseTool"] = self.base_tool_class
        namespace["tool"] = tool

        for _tool_name in flows_tools.__all__:
            namespace[_tool_name] = getattr(flows_tools, _tool_name)
        namespace["ask_user_tool"] = namespace["ask_user"]
        namespace["ask_user"] = ask_user

        for resource_id, resource in self.resources.items():
            namespace[resource_id] = resource

        return namespace
