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
import typing as typing_module
from collections.abc import Callable
from typing import Any, Literal
from urllib.parse import quote

from a2a.types import (
    Artifact,
    DataPart,
    FilePart,
    Message,
    Part,
    Role,
    TextPart,
)

from apps.flows.src.eval.import_policy import safe_inline_import
from apps.flows.src.eval.sandbox_codegen_namespace import register_sandbox_codegen_namespace
from apps.flows.src.eval.shim_registry import apply_inline_shims
from apps.flows.src.eval.state_utils import (
    add_agent_message,
    add_user_message,
    ask_user,
    deep_copy_state,
    extract_json,
    find_file,
    get_files,
    get_messages,
    get_nested,
    get_tool_result,
    get_user,
    merge_state,
    pop_ui_events,
    push_ui_event,
    push_ui_events,
    set_nested,
)
from apps.flows.src.eval.web_snapshot import (
    BrowserSnapshotDescribe,
    Describe,
    DuckDuckGoBrowserSearch,
    Search,
)
from apps.flows.src.eval.wrappers import (
    SafeChannel,
    SafeContext,
)
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.tools.base import BaseTool
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.builtin_specs import BUILTIN_TOOL_SPECS
from apps.flows.tools.scheduling_ids import extract_ids_from_state
from core.clients.google_docs_client import GoogleDocsClient
from core.clients.pravo import PravoClient, PravoClientError
from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClient, ServiceClientError
from core.context import get_context
from core.files import DocxTemplateError, DocxTemplater
from core.files.models import FileResponse
from core.files.reader import FileReader, FileReadError
from core.files.writer import FileWriteError, FileWriter
from core.inline_python_eval_policy import ALLOWED_BUILTINS
from core.logging import get_logger
from core.scheduler.models import ContentType
from core.state.interrupt import (
    HandoffMode,
    InterruptKind,
    OperatorTaskInterrupt,
    UserMessageInterrupt,
)


def _create_safe_builtins() -> dict[str, Any]:
    safe: dict[str, Any] = {}
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


def _inline_compact_entity_hit(raw: dict[str, Any]) -> dict[str, Any]:
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
        context: Any | None = None,
        variables: dict[str, Any] | None = None,
        resources: dict[str, Any] | None = None,
        base_tool_class: type | None = None,
    ):
        self.context = context
        self.variables = variables or {}
        self.resources = resources or {}
        if base_tool_class is None:
            base_tool_class = BaseTool
        self.base_tool_class = base_tool_class

    def build(self) -> dict[str, Any]:
        safe_builtins = _create_safe_builtins()

        namespace: dict[str, Any] = {
            "__builtins__": safe_builtins,
            "__name__": "__inline__",
            "__doc__": None,
        }

        namespace["Optional"] = getattr(typing_module, "Optional")
        namespace["List"] = list
        namespace["Dict"] = dict
        namespace["Any"] = Any
        namespace["Union"] = getattr(typing_module, "Union")
        namespace["Tuple"] = tuple
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

        apply_inline_shims(self, namespace)

        namespace["deep_copy_state"] = deep_copy_state
        namespace["merge_state"] = merge_state
        namespace["get_nested"] = get_nested
        namespace["set_nested"] = set_nested

        namespace["get_files"] = get_files
        namespace["find_file"] = find_file
        namespace["get_user"] = get_user
        namespace["get_tool_result"] = get_tool_result
        namespace["get_messages"] = get_messages
        namespace["add_user_message"] = add_user_message
        namespace["add_agent_message"] = add_agent_message
        namespace["push_ui_event"] = push_ui_event
        namespace["push_ui_events"] = push_ui_events
        namespace["pop_ui_events"] = pop_ui_events

        namespace["FileReader"] = FileReader
        namespace["FileReadError"] = FileReadError
        namespace["reader"] = FileReader()

        namespace["DocxTemplater"] = DocxTemplater
        namespace["DocxTemplateError"] = DocxTemplateError

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

        namespace["ServiceClient"] = ServiceClient
        namespace["ServiceClientError"] = ServiceClientError
        namespace["RagClient"] = RagClient
        namespace["PravoClient"] = PravoClient
        namespace["PravoClientError"] = PravoClientError
        namespace["get_context"] = get_context
        platform_services = importlib.import_module("apps.flows.src.eval.platform_services")
        namespace["get_operator_handoff_service"] = platform_services.get_operator_handoff_service
        namespace["get_schedule_service"] = platform_services.get_schedule_service
        namespace["get_oauth_service"] = platform_services.get_oauth_service
        namespace["get_file_bytes"] = platform_services.get_file_bytes
        namespace["get_mcp_client"] = platform_services.get_mcp_client
        namespace["call_mcp_tool"] = platform_services.call_mcp_tool
        namespace["transcribe_audio"] = platform_services.transcribe_audio
        namespace["synthesize_speech"] = platform_services.synthesize_speech
        namespace["Search"] = Search
        namespace["Describe"] = Describe
        namespace["DuckDuckGoBrowserSearch"] = DuckDuckGoBrowserSearch
        namespace["BrowserSnapshotDescribe"] = BrowserSnapshotDescribe
        namespace["get_google_oauth_token"] = platform_services.get_google_oauth_token
        namespace["get_lara_facade"] = platform_services.get_lara_facade
        namespace["get_text_transform_service"] = platform_services.get_text_transform_service
        namespace["GoogleDocsClient"] = GoogleDocsClient
        namespace["quote"] = quote
        namespace["_require_context_namespace"] = _inline_require_context_namespace
        namespace["_compact_entity_hit"] = _inline_compact_entity_hit

        namespace["datetime"] = stdlib_datetime.datetime
        namespace["ContentType"] = ContentType
        namespace["_extract_ids_from_state"] = extract_ids_from_state

        namespace["FileWriter"] = FileWriter
        namespace["FileWriteError"] = FileWriteError
        namespace["FileResponse"] = FileResponse
        namespace["writer"] = FileWriter()
        namespace["BaseTool"] = self.base_tool_class
        namespace["tool"] = tool

        for module_name, attr_name in BUILTIN_TOOL_SPECS:
            namespace[attr_name] = getattr(importlib.import_module(module_name), attr_name)
        namespace["ask_user_tool"] = namespace["ask_user"]
        namespace["ask_user"] = ask_user

        for resource_id, resource in self.resources.items():
            namespace[resource_id] = resource

        register_sandbox_codegen_namespace(namespace)

        return namespace
