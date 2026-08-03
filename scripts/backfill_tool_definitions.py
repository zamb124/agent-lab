#!/usr/bin/env python3
"""Print builtin ToolDefinition backfill count; optionally write JSON snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from apps.flows.src.services.tool_definition_backfill import (
    BUILTIN_TOOL_DEFINITION_SEMVER,
    iter_builtin_tool_definitions,
)
from apps.flows.tools.builtin_specs import BUILTIN_TOOL_SPECS

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = (
    REPO_ROOT / "apps" / "flows" / "bundles" / "_seed" / "tool_definitions_snapshot.json"
)


class _BackfillCliArgs(argparse.Namespace):
    write: bool = False
    output: Path = DEFAULT_SNAPSHOT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument(
        "--write",
        action="store_true",
        help=f"Write JSON snapshot to {DEFAULT_SNAPSHOT}",
    )
    _ = parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_SNAPSHOT,
        help="Snapshot path when --write is set",
    )
    args = parser.parse_args(argv, namespace=_BackfillCliArgs())

    definitions = iter_builtin_tool_definitions()
    count = len(definitions)
    specs_count = len(BUILTIN_TOOL_SPECS)
    if count != specs_count:
        print(
            "backfill_tool_definitions: FAIL count mismatch "
            + f"definitions={count} specs={specs_count}",
            file=sys.stderr,
        )
        return 1

    print(
        "backfill_tool_definitions: OK "
        + f"({count} builtins, semver={BUILTIN_TOOL_DEFINITION_SEMVER})"
    )

    if args.write:
        payload = {
            "semver": BUILTIN_TOOL_DEFINITION_SEMVER,
            "count": count,
            "definitions": [item.model_dump(mode="json") for item in definitions],
        }
        output_path = args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _ = output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote snapshot: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
