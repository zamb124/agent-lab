"""Office OpenFGA backfill from live catalogs/bindings (ACL members live only in OpenFGA)."""

from __future__ import annotations

import asyncio
import sys

from apps.office.di import OfficeDi
from core.authz.backfill_limit import parse_backfill_limit
from core.authz.service import AuthzService
from core.config import get_settings
from core.di import open_di
from core.di.kit import ProcessIdentity
from core.documents.authz.tuples import (
    document_catalog_company_link,
    document_catalog_lister_tuple,
    document_catalog_owner_tuple,
    document_catalog_parent_tuple,
    document_file_catalog_link,
    document_file_owner_tuple,
)
from core.documents.catalog import DocumentCatalog
from core.files.models import FileRecord
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

    catalog_rows = await DocumentCatalog.list_all_by_created_at(limit=limit)
    file_limit = limit if limit is not None else 1000
    binding_rows = await FileRecord.objects.filter(catalog_id__isnull=False).limit(file_limit).all()

    for row in catalog_rows:
        writes = [
            document_catalog_owner_tuple(row.catalog_id, row.owner_user_id),
            document_catalog_company_link(row.catalog_id, row.company_id),
        ]
        if row.parent_catalog_id is None:
            writes.append(document_catalog_lister_tuple(row.catalog_id, row.company_id))
        else:
            writes.append(document_catalog_parent_tuple(row.catalog_id, row.parent_catalog_id))
        await authz.write(writes)
        catalogs_written += len(writes)

    for binding in binding_rows:
        if binding.catalog_id is None or binding.uploaded_by is None:
            continue
        await authz.write(
            [
                document_file_owner_tuple(binding.file_id, binding.uploaded_by),
                document_file_catalog_link(binding.file_id, binding.catalog_id),
            ]
        )
        documents_written += 1

    return catalogs_written, documents_written


def main(argv: list[str] | None = None) -> int:
    limit = parse_backfill_limit("Backfill Office edges into OpenFGA", argv)
    catalogs, documents = asyncio.run(backfill_office_authz(limit=limit))
    _ = sys.stdout.write(f"catalog_tuples={catalogs}\n")
    _ = sys.stdout.write(f"documents={documents}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
