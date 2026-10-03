#!/usr/bin/env python3
"""
Миграции Oxyde по сервисным базам из migrations/services.json.

Использование:
  uv run python -m scripts.db_migrate upgrade
  uv run python -m scripts.db_migrate upgrade --service shared
  uv run python -m scripts.db_migrate makemigrations
  uv run python -m scripts.db_migrate makemigrations --service flows
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Sequence

from core.db.migration_manifest import bootstrap_migration_registry, get_migration_service_names
from core.db.migrations import generate_migration_files, run_migrations_async
from core.db.postgres_service_databases import ensure_postgres_service_databases_async

_SERVICE_CHOICES = tuple(sorted(get_migration_service_names()))


def _exit_zero_after_k8s_init_migrate() -> None:
    """
    K8s init-container db-migrate должен завершиться сразу после upgrade.

    На Python 3.14t (PYTHON_GIL=0) интерпретатор иногда не выходит после asyncio.run()
    при параллельном старте многих pod'ов: миграции в логах уже завершены, но PID 1
    остаётся живым → Init:1/2 бесконечно, helm --wait падает по timeout.
    """
    os._exit(0)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="db-migrate",
        description="Миграции Oxyde по сервисным БД (migrations/<service>/NNNN_<name>.py).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    u = sub.add_parser("upgrade", help="применить неприменённые файлы (все БД или одна)")
    u.add_argument(
        "--service",
        choices=_SERVICE_CHOICES,
        help="Только указанный сервис; без флага — все из migrations/services.json",
    )

    created = sub.add_parser("makemigrations", help="снять диф моделей в файл миграции")
    created.add_argument(
        "--service",
        choices=_SERVICE_CHOICES,
        help="Только указанный сервис; без флага — все из migrations/services.json",
    )

    return p


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    bootstrap_migration_registry()

    raw = list(argv) if argv is not None else sys.argv[1:]
    args = _build_parser().parse_args(raw)

    if args.command == "upgrade":
        async def _upgrade() -> None:
            await ensure_postgres_service_databases_async()
            await run_migrations_async(service=args.service)

        asyncio.run(_upgrade())
        _exit_zero_after_k8s_init_migrate()

    if args.command == "makemigrations":
        generate_migration_files(service=args.service)
        return

    raise RuntimeError(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
