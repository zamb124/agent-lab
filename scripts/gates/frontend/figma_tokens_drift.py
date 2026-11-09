#!/usr/bin/env python3
"""CI-gate: tokens.css не расходится с синкнутым в Figma слепком.

Дрейф = изменили токены и не прогнали `figma_tokens sync`. Проверка —
`scripts.tools.figma_tokens check` (extract против
`scripts/tools/figma_tokens.snapshot.json`).
"""

from __future__ import annotations

import sys

from scripts.tools.figma_tokens import cmd_check


def main() -> int:
    return cmd_check()


if __name__ == "__main__":
    sys.exit(main())
