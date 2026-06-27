#!/usr/bin/env python3
"""Сверяет suffixes Goose tools в desktop E2E с каноническим контрактом."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GOOSE_E2E_DIR = REPO_ROOT / "tests/agent/desktop_e2e"

REQUIRED_TOOL_SUFFIXES: dict[str, tuple[str, ...]] = {
    "developer": ("tree", "write", "shell", "edit", "read_image"),
    "memory": (
        "remember_memory",
        "retrieve_memories",
        "remove_specific_memory",
        "remove_memory_category",
    ),
    "computercontroller": (
        "web_scrape",
        "cache",
        "pdf_tool",
        "docx_tool",
        "xlsx_tool",
        "automation_script",
        "computer_control",
    ),
    "autovisualiser": (
        "render_sankey",
        "render_radar",
        "render_donut",
        "render_treemap",
        "render_chord",
        "render_map",
        "render_mermaid",
        "show_chart",
    ),
    "tutorial": ("load_tutorial",),
    "platform": (
        "analyze",
        "todo_write",
        "list_apps",
        "search_available_extensions",
        "load",
        "load_skill",
    ),
}

RESOLVE_SUFFIX_RE = re.compile(
    r'resolve_tool_name\([^,]+,\s*"([a-z0-9_]+)"\)',
)
NAME_SUFFIX_RE = re.compile(
    r'name_suffix\s*=\s*"([a-z0-9_]+)"',
)


def _collect_suffixes_from_file(path: Path) -> set[str]:
    source = path.read_text(encoding="utf-8")
    suffixes: set[str] = set()
    suffixes.update(RESOLVE_SUFFIX_RE.findall(source))
    suffixes.update(NAME_SUFFIX_RE.findall(source))
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Name) or func.id != "resolve_tool_name":
            continue
        if len(node.args) < 2:
            continue
        suffix_arg = node.args[1]
        if isinstance(suffix_arg, ast.Constant) and isinstance(suffix_arg.value, str):
            suffixes.add(suffix_arg.value)
    return suffixes


def main() -> int:
    goose_test_files = sorted(GOOSE_E2E_DIR.glob("test_agent_desktop_goose*.py"))
    if not goose_test_files:
        print("check_agent_goose_tool_contract: no goose E2E files", file=sys.stderr)
        return 1
    covered: set[str] = set()
    for path in goose_test_files:
        covered.update(_collect_suffixes_from_file(path))
    missing: list[str] = []
    for group, suffixes in REQUIRED_TOOL_SUFFIXES.items():
        for suffix in suffixes:
            if suffix not in covered:
                missing.append(f"{group}:{suffix}")
    if missing:
        print("check_agent_goose_tool_contract: missing tool suffix coverage:", file=sys.stderr)
        for item in missing:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("check_agent_goose_tool_contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
