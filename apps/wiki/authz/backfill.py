"""Wiki OpenFGA backfill from live wiki_pages (ACL members live only in OpenFGA)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

from sqlalchemy import text

from apps.wiki.authz.tuples import (
    wiki_page_company_link,
    wiki_page_company_viewer_tuple,
    wiki_page_owner_tuple,
    wiki_page_parent_tuple,
)
from apps.wiki.container import get_wiki_container
from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)


async def backfill_wiki_authz(*, limit: int | None = None) -> int:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for Wiki authz backfill")

    container = get_wiki_container()
    authz = container.authz_service
    db = container.wiki_db

    pages_written = 0

    async with db.session() as session:
        page_sql = (
            "SELECT wiki_page_id, company_id, parent_page_id, created_by_user_id, "
            "company_visible "
            "FROM wiki_pages WHERE deleted_at IS NULL ORDER BY created_at ASC"
        )
        if limit is not None:
            page_sql += f" LIMIT {int(limit)}"
        page_rows = list((await session.execute(text(page_sql))).mappings().all())

    for row in page_rows:
        wiki_page_id = cast(str, row["wiki_page_id"])
        company_id = cast(str, row["company_id"])
        owner_user_id = cast(str, row["created_by_user_id"])
        writes = [
            wiki_page_owner_tuple(wiki_page_id, owner_user_id),
            wiki_page_company_link(wiki_page_id, company_id),
        ]
        parent_page_id = cast(str | None, row["parent_page_id"])
        if parent_page_id is not None:
            writes.append(wiki_page_parent_tuple(wiki_page_id, parent_page_id))
        if bool(cast(bool, row["company_visible"])):
            writes.append(wiki_page_company_viewer_tuple(wiki_page_id, company_id))
        await authz.write(writes)
        pages_written += 1

    logger.info("wiki.authz.backfill.complete.pages", pages=pages_written)
    return pages_written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill Wiki pages into OpenFGA")
    _ = parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    limit: int | None = cast(int | None, args.limit)
    pages = asyncio.run(backfill_wiki_authz(limit=limit))
    _ = sys.stdout.write(f"pages={pages}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
