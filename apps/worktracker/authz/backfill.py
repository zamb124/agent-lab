"""Worktracker OpenFGA backfill from live work_queues (members live only in OpenFGA)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

from sqlalchemy import text

from apps.worktracker.container import get_worktracker_container
from core.config import get_settings
from core.logging import get_logger
from core.worktracker.authz_tuples import (
    work_queue_company_link,
    work_queue_owner_tuple,
)

logger = get_logger(__name__)


async def backfill_worktracker_authz(*, limit: int | None = None) -> int:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for Worktracker authz backfill")

    container = get_worktracker_container()
    authz = container.authz_service
    db = container.worktracker_db
    written = 0

    async with db.session() as session:
        company_sql = (
            "SELECT work_queue_id, company_id, owner_user_id "
            "FROM work_queues ORDER BY work_queue_id"
        )
        if limit is not None:
            company_sql = f"{company_sql} LIMIT {int(limit)}"
        company_rows = list((await session.execute(text(company_sql))).mappings().all())

    for row in company_rows:
        work_queue_id = cast(str, row["work_queue_id"])
        company_id = cast(str, row["company_id"])
        owner_user_id = cast(str, row["owner_user_id"])
        writes = [
            work_queue_company_link(work_queue_id, company_id),
            work_queue_owner_tuple(work_queue_id, owner_user_id),
        ]
        await authz.write(writes)
        written += len(writes)

    logger.info("worktracker authz backfill wrote tuples=%s", written)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill Worktracker OpenFGA tuples")
    _ = parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    written = asyncio.run(backfill_worktracker_authz(limit=cast(int | None, args.limit)))
    _ = sys.stdout.write(f"tuples_written={written}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
