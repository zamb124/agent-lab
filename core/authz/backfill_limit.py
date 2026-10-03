"""Типизированный --limit для CLI backfill OpenFGA."""

from __future__ import annotations

import argparse


class BackfillLimitArgs(argparse.Namespace):
    limit: int | None = None


def parse_backfill_limit(description: str, argv: list[str] | None) -> int | None:
    parser = argparse.ArgumentParser(description=description)
    _ = parser.add_argument("--limit", type=int, default=None)
    parsed = BackfillLimitArgs()
    _ = parser.parse_args(argv, namespace=parsed)
    return parsed.limit
