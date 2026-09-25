"""Backfill OpenFGA group#member from User.groups."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

from core.authz.factory import build_authz_service
from core.authz.group_sync import delete_unscoped_group_tuples, sync_user_groups
from core.authz.ids import PLATFORM_ADMIN_GROUP
from core.config import get_settings
from core.logging import get_logger
from core.models.identity_models import User

logger = get_logger(__name__)


async def backfill_user_groups(*, limit: int | None = None) -> int:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for group backfill")
    authz = build_authz_service()
    if not authz.enabled:
        raise RuntimeError("openfga.enabled must be true for group backfill")
    written = 0
    unscoped_names: set[str] = set()
    users = await User.list(limit=10_000)
    try:
        for user in users:
            if limit is not None and written >= limit:
                break
            await sync_user_groups(
                authz,
                user_id=user.user_id,
                groups=user.groups,
                company_ids=list(user.companies.keys()),
                previous_groups=[],
            )
            for group_name in user.groups:
                clean = group_name.strip()
                if clean and clean != PLATFORM_ADMIN_GROUP:
                    unscoped_names.add(clean)
            written += 1
        deleted = await delete_unscoped_group_tuples(authz, sorted(unscoped_names))
    finally:
        await authz.close()
    logger.info("authz.group.backfill.complete.users_synced.unscoped_tuples_deleted", users_synced=written, unscoped_tuples_deleted=deleted)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill User.groups into OpenFGA")
    _ = parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    limit = cast(int | None, args.limit)
    written = asyncio.run(backfill_user_groups(limit=limit))
    _ = sys.stdout.write(f"synced={written}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
