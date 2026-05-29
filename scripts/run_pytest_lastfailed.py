from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_CACHE_FILE = Path(".pytest_cache/v/cache/lastfailed")
XDIST_GROUP_SUFFIX_RE = re.compile(r"^(?P<nodeid>.+)@[A-Za-z0-9_]+$")


def _normalize_nodeid(nodeid: str) -> str:
    match = XDIST_GROUP_SUFFIX_RE.match(nodeid)
    if match is None:
        return nodeid
    return match.group("nodeid")


def _load_failed_nodeids(cache_file: Path) -> list[str]:
    if not cache_file.exists():
        return []

    raw: Any = json.loads(cache_file.read_text())
    if not isinstance(raw, dict):
        raise RuntimeError(f"pytest lastfailed cache must be an object: {cache_file}")

    nodeids: list[str] = []
    for nodeid, failed in raw.items():
        if not isinstance(nodeid, str):
            raise RuntimeError(f"pytest lastfailed cache contains non-string nodeid: {cache_file}")
        if failed is True:
            nodeids.append(_normalize_nodeid(nodeid))

    return nodeids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run exactly the nodeids stored in pytest's lastfailed cache.",
    )
    parser.add_argument("--cache-file", type=Path, default=DEFAULT_CACHE_FILE)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    pytest_args = list(args.pytest_args)
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]

    nodeids = _load_failed_nodeids(args.cache_file)
    if not nodeids:
        print(f"No failed pytest nodeids in {args.cache_file}; strict rerun skipped.")
        return 0

    print(f"Strict pytest lastfailed rerun: {len(nodeids)} nodeids")
    for nodeid in nodeids:
        print(f"  {nodeid}")

    command = ["uv", "run", "pytest", *nodeids, *pytest_args]
    try:
        completed = subprocess.run(command, timeout=args.timeout, check=False)
    except subprocess.TimeoutExpired:
        print(f"Strict pytest lastfailed rerun timed out after {args.timeout:g} seconds.", file=sys.stderr)
        return 124

    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
