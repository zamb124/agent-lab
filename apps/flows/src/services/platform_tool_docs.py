"""
Сбор описаний platform tools для документации редактора кода.

Объединяет записи из БД компании (контекст) и тулы только из процессного ToolRegistry.
"""

from __future__ import annotations

import json
from enum import Enum

from apps.flows.src.container import FlowContainer
from core.context import get_context
from core.docs.models import PlatformToolDoc

_MAX_CODE_PREVIEW_CHARS = 4000


def _code_mode_str(value: object) -> str:
    if isinstance(value, Enum):
        return value.value
    return str(value)


async def collect_platform_tool_docs(container: FlowContainer) -> list[PlatformToolDoc]:
    """
    Все динамические / зарегистрированные tools: сначала из tool_repository текущей компании,
    затем дополняются экземплярами из ToolRegistry, которых нет в БД.
    """
    registry = container.tool_registry
    registry.register_builtin_tools()

    merged: dict[str, PlatformToolDoc] = {}

    ctx = get_context()
    if ctx and ctx.active_company:
        refs = await container.tool_repository.list(limit=5000)
        for ref in refs:
            effective = ref.effective_parameters_schema()
            args_json = json.dumps(effective, ensure_ascii=False, indent=2)
            code_preview: str | None = None
            if ref.code and isinstance(ref.code, str) and ref.code.strip():
                raw = ref.code.strip()
                if len(raw) > _MAX_CODE_PREVIEW_CHARS:
                    code_preview = raw[:_MAX_CODE_PREVIEW_CHARS] + "\n# ... обрезано"
                else:
                    code_preview = raw
            merged[ref.tool_id] = PlatformToolDoc(
                tool_id=ref.tool_id,
                display_name=(ref.name or ref.tool_id).strip(),
                source="database",
                description=(ref.description or "").strip(),
                tags=list(ref.tags or []),
                args_schema_json=args_json,
                code_mode=_code_mode_str(ref.code_mode),
                mcp_server_id=ref.mcp_server_id,
                mcp_tool_name=ref.mcp_tool_name,
                code_preview=code_preview,
            )

    for name, tool in registry.list_all().items():
        if name in merged:
            continue
        if not getattr(type(tool), "listed_in_platform_tool_docs", True):
            continue
        schema = tool.parameters
        args_json = json.dumps(schema, ensure_ascii=False, indent=2)
        merged[name] = PlatformToolDoc(
            tool_id=name,
            display_name=name,
            source="registry_only",
            description=(tool.description or "").strip(),
            tags=list(tool.get_tags()),
            args_schema_json=args_json,
        )

    return sorted(merged.values(), key=lambda x: x.tool_id)
