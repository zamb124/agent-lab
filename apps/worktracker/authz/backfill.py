"""Worktracker OpenFGA backfill from live work_queues (members live only in OpenFGA)."""

from __future__ import annotations

import asyncio
import sys

from apps.worktracker.di import WorktrackerDi
from core.authz.backfill_limit import parse_backfill_limit
from core.config import get_settings
from core.di import ProcessIdentity, open_di
from core.logging import get_logger
from core.worktracker.authz_tuples import (
    work_queue_company_link,
    work_queue_owner_tuple,
)
from core.worktracker.models import WorkQueue

logger = get_logger(__name__)


async def backfill_worktracker_authz(*, limit: int | None = None) -> int:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for Worktracker authz backfill")

    identity = ProcessIdentity(service_name="worktracker", files_route_segment="worktracker")
    async with open_di(
        WorktrackerDi,
        settings=settings,
        identity=identity,
        database="worktracker_url",
    ) as di:
        authz = di.authz_service
    written = 0

    company_rows = await WorkQueue.list_by_work_queue_id(limit=limit)

    for row in company_rows:
        work_queue_id = row.work_queue_id
        company_id = row.company_id
        owner_user_id = row.owner_user_id
        writes = [
            work_queue_company_link(work_queue_id, company_id),
            work_queue_owner_tuple(work_queue_id, owner_user_id),
        ]
        await authz.write(writes)
        written += len(writes)

    logger.info("worktracker.authz.backfill.wrote.tuples", tuples=written)
    return written


def main(argv: list[str] | None = None) -> int:
    limit = parse_backfill_limit("Backfill Worktracker OpenFGA tuples", argv)
    written = asyncio.run(backfill_worktracker_authz(limit=limit))
    _ = sys.stdout.write(f"tuples_written={written}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
