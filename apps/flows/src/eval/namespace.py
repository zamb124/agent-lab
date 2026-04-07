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
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union
from urllib.parse import quote

from core.clients.service_client import ServiceClient, ServiceClientError
from core.context import get_context

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
from apps.flows.src.eval.platform_services import (
    get_file_bytes,
    get_oauth_service,
    get_operator_handoff_service,
    get_schedule_service,
)
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
from core.state.interrupt import (
    HandoffMode,
    InterruptKind,
    OperatorTaskInterrupt,
    UserMessageInterrupt,
)
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.scheduling import _extract_ids_from_state
from core.files.models import FileResponse
from core.files.reader import FileReadError, FileReader
from core.files.writer import FileWriteError, FileWriter
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


def _inline_require_context_namespace() -> str:
    """Совпадает с lara_crm._require_context_namespace; код тулов в БД без импортов core.*."""
    ctx = get_context()
    if ctx is None:
        raise RuntimeError("Context is not set")
    return ctx.active_namespace or "default"


def _inline_compact_entity_hit(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Совпадает с lara_crm._compact_entity_hit."""
    desc = raw.get("description")
    if isinstance(desc, str) and len(desc) > 400:
        desc = desc[:400] + "…"
    return {
        "entity_id": raw.get("entity_id"),
        "name": raw.get("name"),
        "entity_type": raw.get("entity_type"),
        "entity_subtype": raw.get("entity_subtype"),
        "description": desc,
        "namespace": raw.get("namespace"),
    }


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
        namespace["Literal"] = Literal

        namespace["FlowInterrupt"] = FlowInterrupt
        namespace["InterruptKind"] = InterruptKind
        namespace["HandoffMode"] = HandoffMode
        namespace["UserMessageInterrupt"] = UserMessageInterrupt
        namespace["OperatorTaskInterrupt"] = OperatorTaskInterrupt

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

        namespace["FileReader"] = FileReader
        namespace["FileReadError"] = FileReadError
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

        namespace["ServiceClient"] = ServiceClient
        namespace["ServiceClientError"] = ServiceClientError
        namespace["get_context"] = get_context
        namespace["get_operator_handoff_service"] = get_operator_handoff_service
        namespace["get_schedule_service"] = get_schedule_service
        namespace["get_oauth_service"] = get_oauth_service
        namespace["get_file_bytes"] = get_file_bytes
        namespace["quote"] = quote
        namespace["_require_context_namespace"] = _inline_require_context_namespace
        namespace["_compact_entity_hit"] = _inline_compact_entity_hit

        namespace["datetime"] = stdlib_datetime.datetime
        namespace["ContentType"] = ContentType
        namespace["_extract_ids_from_state"] = _extract_ids_from_state

        namespace["FileWriter"] = FileWriter
        namespace["FileWriteError"] = FileWriteError
        namespace["FileResponse"] = FileResponse
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
