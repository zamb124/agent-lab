"""Rewrite checked-in Flow JSON fixtures to the one-way Flow UI contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.models.flow_interface_migration import migrate_flow_config_payload
from core.types import parse_json_object


class _Args(argparse.Namespace):
    paths: list[Path]

    def __init__(self) -> None:
        super().__init__()
        self.paths = []


def main() -> None:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("paths", nargs="+", type=Path)
    args = _Args()
    _ = parser.parse_args(namespace=args)
    for path in args.paths:
        payload = parse_json_object(
            path.read_text(encoding="utf-8"),
            str(path),
        )
        migrated = migrate_flow_config_payload(payload)
        _ = path.write_text(
            json.dumps(migrated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
