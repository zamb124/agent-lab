"""Datasource OpenFGA backfill from datasource_connections."""

from __future__ import annotations

import asyncio
import sys

from core.authz.factory import build_authz_service
from core.config import get_settings
from core.datasources.authz.tuples import (
    datasource_company_link,
    datasource_company_viewer_tuple,
    datasource_owner_tuple,
    datasource_platform_link,
)
from core.datasources.models import DatasourceConnection
from core.db.oxyde_runtime import close_oxyde_databases, init_oxyde_databases
from core.logging import get_logger

logger = get_logger(__name__)


def _parse_limit(argv: list[str] | None) -> int | None:
    tokens = list(sys.argv[1:]) if argv is None else argv
    if len(tokens) == 0:
        return None
    if len(tokens) != 2 or tokens[0] != "--limit":
        raise RuntimeError("usage: python -m core.datasources.authz.backfill [--limit N]")
    token = tokens[1]
    digits = token.lstrip("-")
    if digits == "" or not digits.isdigit():
        raise RuntimeError("--limit must be an integer")
    return int(token)


async def backfill_datasource_authz(*, limit: int | None = None) -> tuple[int, int]:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for datasource authz backfill")
    shared_url = settings.database.shared_url
    if shared_url is None or shared_url == "":
        raise RuntimeError("database.shared_url is required for datasource authz backfill")

    authz = build_authz_service()
    written = 0
    for row in await DatasourceConnection.list_all_by_datasource_id_asc(limit=limit):
        await authz.write(
            [
                datasource_company_link(row.datasource_id, row.company_id),
                datasource_platform_link(row.datasource_id, company_id=row.company_id),
                datasource_owner_tuple(
                    row.datasource_id, row.owner_user_id, company_id=row.company_id
                ),
                datasource_company_viewer_tuple(row.datasource_id, row.company_id),
            ]
        )
        written += 1

    logger.info("datasources.datasource.authz.backfill.connections", connections=written)
    return written, written


def main(argv: list[str] | None = None) -> int:
    limit = _parse_limit(argv)

    async def _run() -> tuple[int, int]:
        settings = get_settings()
        shared_url = settings.database.shared_url
        if shared_url is None or shared_url == "":
            raise RuntimeError("database.shared_url is required for datasource authz backfill")
        await init_oxyde_databases(default_url=shared_url, shared_url=shared_url)
        try:
            return await backfill_datasource_authz(limit=limit)
        finally:
            await close_oxyde_databases()

    written, _owners = asyncio.run(_run())
    _ = sys.stdout.write(f"backfill_datasource_authz written={written}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
