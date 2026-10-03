#!/usr/bin/env python3
"""CI-gate: пакета ``apps/flows/src/clients`` нет.

HTTP-клиент живёт в ``core/clients/``. Фасад сценария flows — в ``apps/flows/src/services/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENTS = REPO_ROOT / "apps" / "flows" / "src" / "clients"


def main() -> int:
    if CLIENTS.exists():
        print("check_flows_src_clients: FAIL", file=sys.stderr)
        print("  apps/flows/src/clients: package is forbidden", file=sys.stderr)
        return 1
    print("check_flows_src_clients: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
