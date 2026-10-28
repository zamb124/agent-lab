"""Mail OpenFGA backfill from live mailbox_bindings (members live only in OpenFGA)."""

from __future__ import annotations

import asyncio
import sys

from core.authz.factory import build_authz_service
from core.config import get_settings
from core.db.oxyde_runtime import close_oxyde_databases, init_oxyde_databases
from core.logging import get_logger
from core.mail.authz.tuples import (
    mailbox_binding_company_link,
    mailbox_binding_owner_tuple,
)
from core.mail.models import MailboxBinding

logger = get_logger(__name__)


def _parse_limit(argv: list[str] | None) -> int | None:
    tokens = list(sys.argv[1:]) if argv is None else argv
    if len(tokens) == 0:
        return None
    if len(tokens) != 2 or tokens[0] != "--limit":
        raise RuntimeError("usage: python -m core.mail.authz.backfill [--limit N]")
    token = tokens[1]
    digits = token.lstrip("-")
    if digits == "" or not digits.isdigit():
        raise RuntimeError("--limit must be an integer")
    return int(token)


async def backfill_mail_authz(*, limit: int | None = None) -> tuple[int, int]:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for Mail authz backfill")
    shared_url = settings.database.shared_url
    if shared_url is None or shared_url == "":
        raise RuntimeError("database.shared_url is required for Mail authz backfill")

    authz = build_authz_service()
    company_written = 0
    owners_written = 0

    for row in await MailboxBinding.list_all_by_mailbox_binding_id(limit=limit):
        await authz.write(
            [mailbox_binding_company_link(row.mailbox_binding_id, row.company_id)]
        )
        company_written += 1

    for row in await MailboxBinding.list_with_user_by_mailbox_binding_id(limit=limit):
        user_id = row.user_id
        if user_id is None:
            raise ValueError(
                f"mailbox binding {row.mailbox_binding_id} user_id is required"
            )
        await authz.write(
            [mailbox_binding_owner_tuple(row.mailbox_binding_id, user_id)]
        )
        owners_written += 1

    logger.info(
        "mail.authz.backfill.company.owners",
        company=company_written,
        owners=owners_written,
    )
    return company_written, owners_written


def main(argv: list[str] | None = None) -> int:
    limit = _parse_limit(argv)

    async def _run() -> tuple[int, int]:
        settings = get_settings()
        shared_url = settings.database.shared_url
        if shared_url is None or shared_url == "":
            raise RuntimeError("database.shared_url is required for Mail authz backfill")
        await init_oxyde_databases(default_url=shared_url, shared_url=shared_url)
        try:
            return await backfill_mail_authz(limit=limit)
        finally:
            await close_oxyde_databases()

    company, owners = asyncio.run(_run())
    _ = sys.stdout.write(f"company={company} owners={owners}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
