#!/usr/bin/env python3
"""CI gate: builtin tool parameter schema strictness and tools import canon."""

from __future__ import annotations

import ast
import sys
from importlib import import_module
from pathlib import Path

from apps.flows.src.tools.base import BaseTool
from apps.flows.tools.builtin_specs import BUILTIN_TOOL_SPECS
from core.types import require_json_object

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "apps" / "flows" / "tools"

SERVICE_CLIENT_ALLOWLIST: frozenset[str] = frozenset()

FORBIDDEN_CALLS: frozenset[str] = frozenset(
    {
        "ServiceClient",
        "get_worktracker_tool_port",
        "get_schedule_service",
        "get_team_directory_facade",
        "get_device_tunnel_facade",
        "get_text_transform_service",
        "get_file_bytes",
        "get_agent_skill_service",
        "get_hitl_work_item_service",
        "get_code_runner",
        "get_lara_facade",
        "resolve_google_workspace_auth",
        "WorktrackerToolPort",
        "FlowsEditorPort",
        "TeamDirectoryFacade",
        "DeviceTunnelFacade",
    }
)

FORBIDDEN_IMPORT_MODULES: frozenset[str] = frozenset(
    {
        "apps.flows.src.services.platform_facades",
        "apps.flows.src.services.worktracker_ports",
        "apps.flows.src.services.flows_editor_port",
        "apps.flows.src.clients.crm_client",
        "apps.flows.src.clients.files_client",
        "apps.flows.src.clients.runtime_deps",
    }
)

FORBIDDEN_IMPORT_NAMES: frozenset[str] = frozenset(
    {
        "WorktrackerToolPort",
        "FlowsEditorPort",
        "TeamDirectoryFacade",
        "DeviceTunnelFacade",
        "get_worktracker_tool_port",
        "get_schedule_service",
        "get_team_directory_facade",
        "get_device_tunnel_facade",
        "get_text_transform_service",
        "get_file_bytes",
        "get_agent_skill_service",
        "get_hitl_work_item_service",
        "get_code_runner",
        "get_lara_facade",
        "resolve_google_workspace_auth",
    }
)


def _collect_schema_errors() -> tuple[list[str], list[str]]:
    hard_errors: list[str] = []
    description_warnings: list[str] = []

    for module_name, attr_name in BUILTIN_TOOL_SPECS:
        module = import_module(module_name)
        tool_candidate = getattr(module, attr_name)
        if not isinstance(tool_candidate, BaseTool):
            hard_errors.append(f"{module_name}.{attr_name}: expected BaseTool instance")
            continue
        tool = tool_candidate
        tool_id = tool.name
        # stock в разработке: контракт builtin не гейтится, пока сервис не влит.
        if tool_id.startswith("stock_"):
            continue
        schema = tool.parameters

        if schema.get("type") != "object":
            hard_errors.append(f"{tool_id}: parameters root type must be object, got {schema.get('type')!r}")
            continue

        if schema.get("additionalProperties") is not False:
            hard_errors.append(
                (
                    f"{tool_id}: parameters root must set additionalProperties=false "
                    "(use Pydantic parameters_model with extra='forbid')"
                )
            )

        raw_properties = schema.get("properties")
        if not isinstance(raw_properties, dict):
            hard_errors.append(f"{tool_id}: parameters.properties must be an object")
            continue

        properties = require_json_object(raw_properties, f"{tool_id}.parameters.properties")
        for property_name, property_schema in properties.items():
            if not isinstance(property_schema, dict):
                hard_errors.append(f"{tool_id}: property {property_name!r} must be object schema")
                continue
            if not property_schema.get("description"):
                description_warnings.append(f"{tool_id}: property {property_name!r} missing description")

    return hard_errors, description_warnings


def _forbidden_calls_in_source(source: str) -> set[str]:
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
            found.add(func.id)
        if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_CALLS:
            found.add(func.attr)
    return found


def _forbidden_imports_in_source(source: str) -> list[str]:
    tree = ast.parse(source)
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_IMPORT_MODULES:
                    hits.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in FORBIDDEN_IMPORT_MODULES:
                hits.append(module)
            for alias in node.names:
                if alias.name in FORBIDDEN_IMPORT_NAMES:
                    hits.append(f"{module}.{alias.name}" if module else alias.name)
    return hits


def _collect_tools_dir_violations() -> list[str]:
    errors: list[str] = []

    for path in sorted(TOOLS_DIR.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        source = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO_ROOT)
        forbidden = _forbidden_calls_in_source(source)
        if path.name not in SERVICE_CLIENT_ALLOWLIST and "ServiceClient" in forbidden:
            errors.append(
                (
                    f"{rel}: direct ServiceClient() forbidden "
                    "(use typed XxxClient; legacy allowlist only)"
                )
            )
        legacy_calls = forbidden.intersection(FORBIDDEN_CALLS - {"ServiceClient"})
        if legacy_calls:
            joined = ", ".join(sorted(legacy_calls))
            errors.append(f"{rel}: forbidden call(s): {joined}")
        for import_hit in _forbidden_imports_in_source(source):
            errors.append(f"{rel}: forbidden import: {import_hit}")
    return errors


def main() -> int:
    schema_errors, description_warnings = _collect_schema_errors()
    import_errors = _collect_tools_dir_violations()
    hard_errors = schema_errors + import_errors

    if description_warnings:
        print(
            f"check_tool_contracts: WARN ({len(description_warnings)} missing Field descriptions)",
            file=sys.stderr,
        )
        for message in description_warnings:
            print(f"  {message}", file=sys.stderr)

    if hard_errors:
        print(f"check_tool_contracts: FAIL ({len(hard_errors)} issue(s))", file=sys.stderr)
        for message in hard_errors:
            print(f"  {message}", file=sys.stderr)
        return 1

    print(f"check_tool_contracts: OK ({len(BUILTIN_TOOL_SPECS)} builtins)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
