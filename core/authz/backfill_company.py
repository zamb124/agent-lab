"""Backfill OpenFGA tuples from domain Company.members."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

from core.authz.company_sync import sync_company_member_roles
from core.authz.factory import build_authz_service
from core.config import get_settings
from core.db.repositories.company_repository import CompanyRepository
from core.db.storage import Storage
from core.logging import get_logger

logger = get_logger(__name__)


async def backfill_company_members(*, limit: int | None = None) -> int:
    """Пишет tuples для всех company.members. Возвращает число sync-вызовов."""
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for company backfill")
    authz = build_authz_service()
    if not authz.enabled:
        raise RuntimeError("openfga.enabled must be true for company backfill")
    storage = Storage(db_url=str(settings.database.shared_url))
    company_repository = CompanyRepository(storage=storage)
    written = 0
    companies = await company_repository.list(limit=10_000)
    try:
        for company in companies:
            if limit is not None and written >= limit:
                break
            for user_id, roles in company.members.items():
                if limit is not None and written >= limit:
                    break
                await sync_company_member_roles(
                    authz,
                    company_id=company.company_id,
                    user_id=user_id,
                    roles=roles,
                )
                written += 1
    finally:
        await authz.close()
    logger.info("company backfill complete tuples_synced=%s", written)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill company membership into OpenFGA")
    _ = parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    limit = cast(int | None, args.limit)
    written = asyncio.run(backfill_company_members(limit=limit))
    _ = sys.stdout.write(f"synced={written}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
