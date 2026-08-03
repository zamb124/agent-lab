#!/usr/bin/env python3
"""CI gate: builtin tool tags — whitelist, 1 tag (dual only crm+worktracker)."""

from __future__ import annotations

import sys
from importlib import import_module

from apps.flows.tools.builtin_specs import BUILTIN_TOOL_SPECS

TOOL_TAG_WHITELIST: frozenset[str] = frozenset(
    {
        "crm",
        "documents",
        "files",
        "sync",
        "worktracker",
        "wiki",
        "web",
        "knowledge",
        "scheduling",
        "google_docs",
        "google_sheets",
        "viz",
        "flows",
        "device",
        "text",
        "misc",
    }
)

ALLOWED_DUAL: frozenset[str] = frozenset({"crm", "worktracker"})


def _collect_errors() -> list[str]:
    errors: list[str] = []
    for module_name, attr_name in BUILTIN_TOOL_SPECS:
        module = import_module(module_name)
        tool = getattr(module, attr_name)
        tags = list(tool.get_tags())
        tool_id = tool.name
        if not isinstance(tool_id, str) or tool_id.strip() == "":
            raise ValueError(f"{module_name}.{attr_name}: tool.name must be non-empty str")
        if not (1 <= len(tags) <= 2):
            errors.append(
                f"{tool_id}: expected 1–2 tags, got {len(tags)} {tags!r}"
            )
            continue
        unknown = [tag for tag in tags if tag not in TOOL_TAG_WHITELIST]
        if unknown:
            errors.append(
                f"{tool_id}: unknown tags {unknown!r} (allowed={sorted(TOOL_TAG_WHITELIST)})"
            )
            continue
        if len(tags) == 2 and frozenset(tags) != ALLOWED_DUAL:
            errors.append(
                f"{tool_id}: dual tags must be {{crm, worktracker}}, got {tags!r}"
            )
    return errors


def main() -> int:
    errors = _collect_errors()
    if errors:
        print(f"check_tool_tags: FAIL ({len(errors)} issue(s))", file=sys.stderr)
        for message in errors:
            print(f"  {message}", file=sys.stderr)
        return 1
    print(f"check_tool_tags: OK ({len(BUILTIN_TOOL_SPECS)} builtins)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
