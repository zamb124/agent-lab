"""Datasource OpenFGA backfill from datasource_connections."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

from sqlalchemy import text

from core.authz.factory import build_authz_service
from core.config import get_settings
from core.datasources.authz.tuples import (
    datasource_company_link,
    datasource_company_viewer_tuple,
    datasource_owner_tuple,
    datasource_platform_link,
)
from core.db.database import get_session_factory
from core.logging import get_logger

logger = get_logger(__name__)


async def backfill_datasource_authz(*, limit: int | None = None) -> tuple[int, int]:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for datasource authz backfill")
    if not settings.database.shared_url:
        raise RuntimeError("database.shared_url is required for datasource authz backfill")

    authz = build_authz_service()
    session_factory = await get_session_factory(settings.database.shared_url)
    written = 0

    async with session_factory() as session:
        sql = (
            "SELECT datasource_id, company_id, owner_user_id "
            "FROM datasource_connections ORDER BY datasource_id"
        )
        if limit is not None:
            sql = f"{sql} LIMIT {int(limit)}"
        rows = list((await session.execute(text(sql))).mappings().all())

    for row in rows:
        datasource_id = cast(str, row["datasource_id"])
        company_id = cast(str, row["company_id"])
        owner_user_id = cast(str, row["owner_user_id"])
        await authz.write(
            [
                datasource_company_link(datasource_id, company_id),
                datasource_platform_link(datasource_id, company_id=company_id),
                datasource_owner_tuple(
                    datasource_id, owner_user_id, company_id=company_id
                ),
                datasource_company_viewer_tuple(datasource_id, company_id),
            ]
        )
        written += 1

    logger.info("datasource authz backfill connections=%s", written)
    return written, written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill datasource OpenFGA tuples")
    _ = parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    written, _owners = asyncio.run(
        backfill_datasource_authz(limit=cast(int | None, args.limit))
    )
    _ = sys.stdout.write(f"backfill_datasource_authz written={written}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
