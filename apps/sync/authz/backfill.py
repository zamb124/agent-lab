"""Sync OpenFGA backfill: company tenancy + channel members (roles live only in OpenFGA)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

from sqlalchemy import text

from apps.sync.authz.tuples import sync_channel_company_link, sync_channel_member_tuple
from apps.sync.container import get_sync_container
from core.authz.models import AuthzObject
from core.authz.types import AuthzRelation, AuthzSubjectKind
from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)


async def backfill_sync_authz(*, limit: int | None = None) -> int:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for Sync authz backfill")

    container = get_sync_container()
    authz = container.authz_service
    db = container.sync_db
    written = 0

    async with db.session() as session:
        company_sql = (
            "SELECT channel_id, company_id, created_by_user_id "
            "FROM sync_channels ORDER BY channel_id"
        )
        if limit is not None:
            company_sql = f"{company_sql} LIMIT {int(limit)}"
        company_rows = list((await session.execute(text(company_sql))).mappings().all())

        member_sql = (
            "SELECT channel_id, user_id FROM sync_channel_members ORDER BY channel_id, user_id"
        )
        if limit is not None:
            member_sql = f"{member_sql} LIMIT {int(limit)}"
        member_rows = list((await session.execute(text(member_sql))).mappings().all())

    owners_by_channel: dict[str, str] = {}
    for row in company_rows:
        channel_id = cast(str, row["channel_id"])
        company_id = cast(str, row["company_id"])
        created_by = cast(str | None, row["created_by_user_id"])
        await authz.write([sync_channel_company_link(channel_id, company_id)])
        written += 1
        if created_by is not None and created_by.strip():
            owners_by_channel[channel_id] = created_by.strip()
            await authz.write(
                [sync_channel_member_tuple(channel_id, created_by.strip(), AuthzRelation.OWNER)]
            )
            written += 1

    logger.info("sync.authz.backfill.settings.rows")
    for row in member_rows:
        channel_id = cast(str, row["channel_id"])
        user_id = cast(str, row["user_id"])
        if owners_by_channel.get(channel_id) == user_id:
            continue
        existing = await authz.list_tuples(AuthzObject.sync_channel(channel_id))
        existing_relations = {
            item.relation
            for item in existing
            if item.subject.kind is AuthzSubjectKind.USER and item.subject.value == user_id
        }
        if AuthzRelation.OWNER in existing_relations or AuthzRelation.ADMIN in existing_relations:
            logger.info("sync.authz.backfill.skip.member", channel_id=channel_id, user_id=user_id)
            continue
        if AuthzRelation.MEMBER in existing_relations:
            continue
        await authz.write([sync_channel_member_tuple(channel_id, user_id, AuthzRelation.MEMBER)])
        written += 1

    logger.info("sync.authz.backfill.wrote.tuples", tuples=written)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill Sync channel OpenFGA tuples")
    _ = parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    written = asyncio.run(backfill_sync_authz(limit=cast(int | None, args.limit)))
    _ = sys.stdout.write(f"tuples_written={written}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
