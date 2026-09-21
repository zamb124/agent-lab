"""Office OpenFGA backfill from live catalogs/bindings (ACL members live only in OpenFGA)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

from sqlalchemy import text

from apps.office.authz.tuples import (
    office_catalog_company_link,
    office_catalog_owner_tuple,
    office_catalog_parent_tuple,
    office_document_catalog_link,
    office_document_owner_tuple,
)
from apps.office.container import get_office_container
from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)


async def backfill_office_authz(*, limit: int | None = None) -> tuple[int, int]:
    """Пересобирает catalog owner/parent и document edges из SQL.

    Member/share grants — FGA-only (OpenFGA store backup); SQL не PDP.
    """
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for Office authz backfill")

    container = get_office_container()
    authz = container.authz_service
    db = container.office_db

    catalogs_written = 0
    documents_written = 0

    async with db.session() as session:
        catalog_sql = (
            "SELECT catalog_id, parent_catalog_id, owner_user_id, company_id "
            "FROM office_document_catalogs ORDER BY created_at ASC"
        )
        if limit is not None:
            catalog_sql += f" LIMIT {int(limit)}"
        catalog_rows = list((await session.execute(text(catalog_sql))).mappings().all())

        binding_sql = (
            "SELECT file_id, catalog_id, created_by_user_id "
            "FROM office_document_bindings ORDER BY created_at ASC"
        )
        if limit is not None:
            binding_sql += f" LIMIT {int(limit)}"
        bindings = list((await session.execute(text(binding_sql))).mappings().all())

    for row in catalog_rows:
        catalog_id = cast(str, row["catalog_id"])
        owner_user_id = cast(str, row["owner_user_id"])
        company_id = cast(str, row["company_id"])
        parent_catalog_id = cast(str | None, row["parent_catalog_id"])
        writes = [
            office_catalog_owner_tuple(catalog_id, owner_user_id),
            office_catalog_company_link(catalog_id, company_id),
        ]
        if parent_catalog_id is not None:
            writes.append(office_catalog_parent_tuple(catalog_id, parent_catalog_id))
        await authz.write(writes)
        catalogs_written += len(writes)

    for binding in bindings:
        await authz.write(
            [
                office_document_owner_tuple(
                    cast(str, binding["file_id"]),
                    cast(str, binding["created_by_user_id"]),
                ),
                office_document_catalog_link(
                    cast(str, binding["file_id"]),
                    cast(str, binding["catalog_id"]),
                ),
            ]
        )
        documents_written += 1

    logger.info("office.authz.backfill.complete.catalog_tuples", catalog_tuples=catalogs_written, documents=documents_written)
    return catalogs_written, documents_written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill Office edges into OpenFGA")
    _ = parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    limit: int | None = cast(int | None, args.limit)
    catalogs, documents = asyncio.run(backfill_office_authz(limit=limit))
    _ = sys.stdout.write(f"catalog_tuples={catalogs}\n")
    _ = sys.stdout.write(f"documents={documents}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
