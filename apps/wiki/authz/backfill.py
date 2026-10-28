"""Wiki OpenFGA backfill from live wiki_pages (ACL members live only in OpenFGA)."""

from __future__ import annotations

import asyncio
import sys

from apps.wiki.authz.tuples import (
    wiki_page_company_link,
    wiki_page_company_viewer_tuple,
    wiki_page_owner_tuple,
    wiki_page_parent_tuple,
)
from apps.wiki.di import WikiDi
from apps.wiki.models.page import WikiPage
from core.authz.backfill_limit import parse_backfill_limit
from core.authz.service import AuthzService
from core.config import get_settings
from core.di import ProcessIdentity, open_di
from core.logging import get_logger

logger = get_logger(__name__)


async def backfill_wiki_authz(*, limit: int | None = None) -> int:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for Wiki authz backfill")

    identity = ProcessIdentity(service_name="wiki", files_route_segment="wiki")
    async with open_di(
        WikiDi,
        settings=settings,
        identity=identity,
        database="wiki_url",
    ) as di:
        return await _write_page_tuples(di.authz_service, limit=limit)


async def _write_page_tuples(authz: AuthzService, *, limit: int | None) -> int:
    pages_written = 0
    page_rows = await WikiPage.alive_by_created_at(limit=limit)

    for row in page_rows:
        wiki_page_id = row.wiki_page_id
        company_id = row.company_id
        owner_user_id = row.created_by_user_id
        writes = [
            wiki_page_owner_tuple(wiki_page_id, owner_user_id),
            wiki_page_company_link(wiki_page_id, company_id),
        ]
        parent_page_id = row.parent_page_id
        if parent_page_id is not None:
            writes.append(wiki_page_parent_tuple(wiki_page_id, parent_page_id))
        if row.company_visible:
            writes.append(wiki_page_company_viewer_tuple(wiki_page_id, company_id))
        await authz.write(writes)
        pages_written += 1

    logger.info("wiki.authz.backfill.complete.pages", pages=pages_written)
    return pages_written


def main(argv: list[str] | None = None) -> int:
    limit = parse_backfill_limit("Backfill Wiki pages into OpenFGA", argv)
    pages = asyncio.run(backfill_wiki_authz(limit=limit))
    _ = sys.stdout.write(f"pages={pages}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
