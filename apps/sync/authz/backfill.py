"""Sync OpenFGA backfill: company tenancy + channel members (roles live only in OpenFGA)."""

from __future__ import annotations

import asyncio
import sys

from apps.sync.authz.tuples import sync_channel_company_link, sync_channel_member_tuple
from apps.sync.di import SyncDi
from apps.sync.models.channel import SyncChannel
from apps.sync.models.channel_member import SyncChannelMember
from core.authz.models import AuthzObject
from core.authz.types import AuthzRelation, AuthzSubjectKind
from core.config import get_settings
from core.di import open_di
from core.di.kit import ProcessIdentity
from core.files.urls import resolve_files_route_segment
from core.logging import get_logger

logger = get_logger(__name__)


async def backfill_sync_authz(*, limit: int | None = None) -> int:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for Sync authz backfill")
    async with open_di(
        SyncDi,
        settings=settings,
        identity=ProcessIdentity(
            service_name="sync",
            files_route_segment=resolve_files_route_segment("sync"),
        ),
        database="sync_url",
    ) as di:
        authz = di.authz_service
        written = 0
        company_rows = await SyncChannel.list_for_authz(limit=limit)
        member_rows = await SyncChannelMember.list_for_authz(limit=limit)

        owners_by_channel: dict[str, str] = {}
        for row in company_rows:
            channel_id = row.channel_id
            company_id = row.company_id
            created_by = row.created_by_user_id
            await authz.write([sync_channel_company_link(channel_id, company_id)])
            written += 1
            if created_by.strip() != "":
                owners_by_channel[channel_id] = created_by.strip()
                await authz.write(
                    [sync_channel_member_tuple(channel_id, created_by.strip(), AuthzRelation.OWNER)]
                )
                written += 1

        logger.info("sync.authz.backfill.settings.rows")
        for row in member_rows:
            channel_id = row.channel_id
            user_id = row.user_id
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


def _parse_limit(argv: list[str] | None) -> int | None:
    tokens = list(sys.argv[1:]) if argv is None else argv
    if len(tokens) == 0:
        return None
    if len(tokens) != 2 or tokens[0] != "--limit":
        raise RuntimeError("usage: python -m apps.sync.authz.backfill [--limit N]")
    token = tokens[1]
    digits = token.lstrip("-")
    if digits == "" or not digits.isdigit():
        raise RuntimeError("--limit must be an integer")
    return int(token)


def main(argv: list[str] | None = None) -> int:
    written = asyncio.run(backfill_sync_authz(limit=_parse_limit(argv)))
    _ = sys.stdout.write(f"tuples_written={written}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
