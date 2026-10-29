"""Прогон гейтов без остановки на первом падении.

    python -m scripts.gates --suite lint
    python -m scripts.gates --gate backend.taskiq
    python -m scripts.gates --list
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys

from scripts.gates.kit import REPO_ROOT
from scripts.gates.registry import GATES, Gate, by_name, select_suite


def _split_extra(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" not in argv:
        return argv, []
    index = argv.index("--")
    return argv[:index], argv[index + 1 :]


def _run(gate: Gate, extra: list[str]) -> int:
    argv = [*gate.argv, *extra]
    if argv[0] == "python":
        argv[0] = sys.executable
    print(f"=== {gate.name} ===", flush=True)
    completed = subprocess.run(argv, cwd=REPO_ROOT, check=False)
    return completed.returncode


def _print_list(gates: tuple[Gate, ...]) -> None:
    for gate in gates:
        suites = ",".join(sorted(gate.suites))
        print(f"{gate.name}\t{suites}\t{shlex.join(gate.argv)}")


def main(argv: list[str] | None = None) -> int:
    raw, extra = _split_extra(list(sys.argv[1:] if argv is None else argv))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=sorted({"lint", "lint_ts", "static", "network", "events"}))
    parser.add_argument("--gate", action="append", default=[])
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(raw)
    if args.suite and args.gate:
        print("gates: --suite and --gate are mutually exclusive", file=sys.stderr)
        return 2
    if args.list and not args.suite and not args.gate:
        _print_list(GATES)
        return 0
    if args.suite:
        selected = select_suite(args.suite)
    elif args.gate:
        selected = tuple(by_name(name) for name in args.gate)
    else:
        parser.print_help(sys.stderr)
        return 2
    if args.list:
        _print_list(selected)
        return 0
    if extra and len(selected) != 1:
        print("gates: extra args require exactly one --gate", file=sys.stderr)
        return 2
    failed: list[str] = []
    for gate in selected:
        if _run(gate, extra) != 0:
            failed.append(gate.name)
    print(f"gates: {len(selected)} ran, {len(failed)} failed", flush=True)
    if failed:
        print("failed: " + ", ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
