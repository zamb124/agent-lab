"""Mail OpenFGA backfill from live mailbox_bindings (members live only in OpenFGA)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

from sqlalchemy import text

from core.authz.factory import build_authz_service
from core.config import get_settings
from core.db.database import get_session_factory
from core.logging import get_logger
from core.mail.authz.tuples import (
    mailbox_binding_company_link,
    mailbox_binding_owner_tuple,
)

logger = get_logger(__name__)


async def backfill_mail_authz(*, limit: int | None = None) -> tuple[int, int]:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for Mail authz backfill")
    if not settings.database.shared_url:
        raise RuntimeError("database.shared_url is required for Mail authz backfill")

    authz = build_authz_service()
    session_factory = await get_session_factory(settings.database.shared_url)
    company_written = 0
    owners_written = 0

    async with session_factory() as session:
        company_sql = (
            "SELECT mailbox_binding_id, company_id FROM mailbox_bindings "
            "ORDER BY mailbox_binding_id"
        )
        if limit is not None:
            company_sql = f"{company_sql} LIMIT {int(limit)}"
        company_rows = list((await session.execute(text(company_sql))).mappings().all())

        owner_sql = (
            "SELECT mailbox_binding_id, user_id FROM mailbox_bindings "
            "WHERE user_id IS NOT NULL ORDER BY mailbox_binding_id"
        )
        if limit is not None:
            owner_sql = f"{owner_sql} LIMIT {int(limit)}"
        owner_rows = list((await session.execute(text(owner_sql))).mappings().all())

    for row in company_rows:
        mailbox_binding_id = cast(str, row["mailbox_binding_id"])
        company_id = cast(str, row["company_id"])
        await authz.write(
            [mailbox_binding_company_link(mailbox_binding_id, company_id)]
        )
        company_written += 1

    for row in owner_rows:
        mailbox_binding_id = cast(str, row["mailbox_binding_id"])
        user_id = cast(str, row["user_id"])
        await authz.write(
            [mailbox_binding_owner_tuple(mailbox_binding_id, user_id)]
        )
        owners_written += 1

    logger.info(
        "mail authz backfill company=%s owners=%s",
        company_written,
        owners_written,
    )
    return company_written, owners_written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill Mail OpenFGA tuples")
    _ = parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    company, owners = asyncio.run(
        backfill_mail_authz(limit=cast(int | None, args.limit))
    )
    _ = sys.stdout.write(f"company={company} owners={owners}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
