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

import argparse
import asyncio
import logging
import sys
from typing import Sequence

from core.db.migration_manifest import bootstrap_migration_registry, get_migration_service_names
from core.db.migrations import (
    run_current_async,
    run_downgrade_async,
    run_heads,
    run_history,
    run_migrations_async,
    run_revision,
)

_SERVICE_CHOICES = tuple(sorted(get_migration_service_names()))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="db-migrate",
        description="Миграции Alembic по сервисным БД (деревья migrations/<service>/).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    u = sub.add_parser("upgrade", help="upgrade head (все БД или одна)")
    u.add_argument(
        "--service",
        choices=_SERVICE_CHOICES,
        help="Только указанный сервис; без флага — все пять",
    )

    r = sub.add_parser("revision", help="создать ревизию в дереве сервиса")
    r.add_argument("-m", "--message", required=True, help="сообщение ревизии")
    r.add_argument(
        "--service",
        required=True,
        choices=_SERVICE_CHOICES,
        help="дерево Alembic (migrations/<service>)",
    )
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--autogenerate",
        action="store_true",
        help="сравнить модели с БД и сгенерировать операции",
    )
    g.add_argument(
        "--empty",
        action="store_true",
        help="пустая ревизия без autogenerate",
    )

    d = sub.add_parser("downgrade", help="downgrade в дереве сервиса")
    d.add_argument(
        "--service",
        required=True,
        choices=_SERVICE_CHOICES,
    )
    d.add_argument(
        "revision",
        nargs="?",
        default="-1",
        help="ревизия или -1 (по умолчанию)",
    )

    c = sub.add_parser("current", help="текущая ревизия в БД сервиса")
    c.add_argument("--service", required=True, choices=_SERVICE_CHOICES)

    h = sub.add_parser("history", help="история ревизий в дереве")
    h.add_argument("--service", required=True, choices=_SERVICE_CHOICES)

    hd = sub.add_parser("heads", help="heads в дереве скриптов")
    hd.add_argument("--service", required=True, choices=_SERVICE_CHOICES)

    return p


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    bootstrap_migration_registry()

    raw = list(argv) if argv is not None else sys.argv[1:]
    args = _build_parser().parse_args(raw)

    if args.command == "upgrade":
        asyncio.run(run_migrations_async(service=args.service))
        return

    if args.command == "revision":
        auto = bool(args.autogenerate)
        run_revision(args.service, args.message, autogenerate=auto)
        return

    if args.command == "downgrade":
        asyncio.run(run_downgrade_async(args.service, args.revision))
        return

    if args.command == "current":
        asyncio.run(run_current_async(args.service))
        return

    if args.command == "history":
        run_history(args.service)
        return

    if args.command == "heads":
        run_heads(args.service)
        return

    raise RuntimeError(f"Неизвестная команда: {args.command}")


if __name__ == "__main__":
    main()
