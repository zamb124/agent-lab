"""Office OpenFGA backfill from live catalogs/bindings (ACL members live only in OpenFGA)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

from apps.office.authz.tuples import (
    office_catalog_company_link,
    office_catalog_owner_tuple,
    office_catalog_parent_tuple,
    office_document_catalog_link,
    office_document_owner_tuple,
)
from apps.office.db.models import OfficeDocumentBinding, OfficeDocumentCatalog
from apps.office.di import OfficeDi
from core.authz.service import AuthzService
from core.config import get_settings
from core.di import open_di
from core.di.kit import ProcessIdentity
from core.files.urls import resolve_files_route_segment
from core.logging import get_logger

logger = get_logger(__name__)


async def backfill_office_authz(*, limit: int | None = None) -> tuple[int, int]:
    """Пересобирает catalog owner/parent и document edges из SQL.

    Member/share grants — FGA-only (OpenFGA store backup); SQL не PDP.
    """
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for Office authz backfill")

    async with open_di(
        OfficeDi,
        settings=settings,
        identity=ProcessIdentity(
            service_name="office",
            files_route_segment=resolve_files_route_segment("office"),
        ),
        database="office_url",
    ) as di:
        authz = di.authz_service
        catalogs_written, documents_written = await _write_office_authz_edges(
            authz, limit=limit
        )

    logger.info(
        "office.authz.backfill.complete.catalog_tuples",
        catalog_tuples=catalogs_written,
        documents=documents_written,
    )
    return catalogs_written, documents_written


async def _write_office_authz_edges(authz: AuthzService, *, limit: int | None) -> tuple[int, int]:
    catalogs_written = 0
    documents_written = 0

    catalog_rows = await OfficeDocumentCatalog.list_by_created_at(limit=limit)
    binding_rows = await OfficeDocumentBinding.list_by_created_at(limit=limit)

    for row in catalog_rows:
        catalog_id = row.catalog_id
        owner_user_id = row.owner_user_id
        company_id = row.company_id
        parent_catalog_id = row.parent_catalog_id
        writes = [
            office_catalog_owner_tuple(catalog_id, owner_user_id),
            office_catalog_company_link(catalog_id, company_id),
        ]
        if parent_catalog_id is not None:
            writes.append(office_catalog_parent_tuple(catalog_id, parent_catalog_id))
        await authz.write(writes)
        catalogs_written += len(writes)

    for binding in binding_rows:
        await authz.write(
            [
                office_document_owner_tuple(binding.file_id, binding.created_by_user_id),
                office_document_catalog_link(binding.file_id, binding.catalog_id),
            ]
        )
        documents_written += 1

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
