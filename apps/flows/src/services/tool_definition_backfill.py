"""Backfill ToolDefinition records from registered builtin BaseTool instances."""

from __future__ import annotations

import importlib

from apps.flows.src.models.tool_contracts import ToolDefinition
from apps.flows.src.services.tool_definition_builder import (
    BUILTIN_TOOL_DEFINITION_SEMVER,
    BUILTIN_TOOL_DEFINITION_VERSION,
    build_tool_definition_from_base_tool,
)
from apps.flows.src.tools.base import BaseTool
from apps.flows.tools.builtin_specs import BUILTIN_TOOL_SPECS

__all__ = [
    "BUILTIN_TOOL_DEFINITION_SEMVER",
    "BUILTIN_TOOL_DEFINITION_VERSION",
    "build_tool_definition_from_base_tool",
    "iter_builtin_tool_definitions",
]


def iter_builtin_tool_definitions() -> list[ToolDefinition]:
    """Load every BUILTIN_TOOL_SPECS entry and convert it to ToolDefinition."""
    definitions: list[ToolDefinition] = []
    for module_name, attr_name in BUILTIN_TOOL_SPECS:
        module = importlib.import_module(module_name)
        raw_tool = module.__dict__.get(attr_name)
        if not isinstance(raw_tool, BaseTool):
            raise TypeError(
                f"Builtin tool {module_name}.{attr_name} must be a BaseTool instance"
            )
        definitions.append(build_tool_definition_from_base_tool(raw_tool))
    return definitions
