"""Backfill OpenFGA tuples from domain Company.members."""

from __future__ import annotations

import asyncio
import sys

from core.authz.backfill_limit import parse_backfill_limit
from core.authz.company_sync import sync_company_member_roles
from core.authz.factory import build_authz_service
from core.config import get_settings
from core.db.oxyde_runtime import close_oxyde_databases, init_oxyde_databases
from core.logging import get_logger
from core.models.identity_models import Company

logger = get_logger(__name__)


async def backfill_company_members(*, limit: int | None = None) -> int:
    """Пишет tuples для всех company.members. Возвращает число sync-вызовов."""
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for company backfill")
    authz = build_authz_service()
    if not authz.enabled:
        raise RuntimeError("openfga.enabled must be true for company backfill")
    written = 0
    companies = await Company.list(limit=10_000)
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
    logger.info("authz.company.backfill.complete.tuples_synced", tuples_synced=written)
    return written


def main(argv: list[str] | None = None) -> int:
    limit = parse_backfill_limit("Backfill company membership into OpenFGA", argv)

    async def _run() -> int:
        settings = get_settings()
        shared_url = settings.database.shared_url
        if shared_url is None or shared_url == "":
            raise RuntimeError(
                "database.shared_url is required for company authz backfill"
            )
        await init_oxyde_databases(default_url=shared_url, shared_url=shared_url)
        try:
            return await backfill_company_members(limit=limit)
        finally:
            await close_oxyde_databases()

    written = asyncio.run(_run())
    _ = sys.stdout.write(f"synced={written}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
