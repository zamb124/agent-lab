#!/usr/bin/env python3
"""
Единая точка входа для миграций Alembic по всем сервисным БД.

Манифест: migrations/services.json (имена, модули моделей, ключи database.*).
Реестр заполняется в core.db.migration_manifest.bootstrap_migration_registry.

Использование:
  uv run python -m scripts.db_migrate upgrade
  uv run python -m scripts.db_migrate upgrade --service shared
  uv run python -m scripts.db_migrate revision -m "msg" --service agents --autogenerate
"""

from __future__ import annotations

import logging
import sys
from typing import Sequence

from core.db.migration_manifest import bootstrap_migration_registry


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    bootstrap_migration_registry()
    from core.db.cli import main as cli_main

    cli_main(list(argv) if argv is not None else sys.argv[1:])


if __name__ == "__main__":
    main()
