"""Эталон code_agent CLI: ненулевой exit."""

from __future__ import annotations

import sys


def main() -> None:
    sys.stderr.write("guest fail_cli\n")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
