"""Чтение живых FileRecord по original_name внутри каталогов."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.documents.catalog import DocumentCatalog
from core.files.create_spec import FileSourceKind
from core.files.models import FileRecord, FileStatus
from core.files.object_storage import PLATFORM_STORAGE_ID


async def _catalog(company_id: str, unique_id: str, title: str) -> DocumentCatalog:
    catalog, _created = await DocumentCatalog.ensure_child(
        company_id=company_id,
        namespace=f"ns_{unique_id}",
        parent_catalog_id=None,
        title=title,
        owner_user_id=f"user_{unique_id}",
    )
    return catalog


def _record(
    *,
    file_id: str,
    company_id: str,
    catalog_id: str | None,
    original_name: str,
    updated_at: datetime,
    deleted_at: datetime | None = None,
) -> FileRecord:
    return FileRecord(
        file_id=file_id,
        original_name=original_name,
        name_key=original_name.casefold(),
        s3_key=f"files/{file_id}",
        storage_id=PLATFORM_STORAGE_ID,
        content_type="text/plain",
        file_size=1,
        status=FileStatus.READY,
        company_id=company_id,
        catalog_id=catalog_id,
        source_kind=FileSourceKind.OFFICE_DOCUMENT if catalog_id else "",
        updated_at=updated_at,
        deleted_at=deleted_at,
    )


@pytest.mark.asyncio
async def test_list_alive_by_original_name_orders_alive_catalog_rows(
    frontend_di,
    unique_id: str,
) -> None:
    _ = frontend_di
    company_id = f"co_{unique_id}"
    catalog = await _catalog(company_id, unique_id, f"cat {unique_id}")
    catalog_id = catalog.catalog_id
    other_catalog = await _catalog(company_id, unique_id, f"other {unique_id}")
    token = f"tok{unique_id}"
    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 1, 2, tzinfo=UTC)
    older_id = f"file_old_{unique_id}"
    newer_id = f"file_new_{unique_id}"
    trashed_id = f"file_trash_{unique_id}"
    other_catalog_id = f"file_other_cat_{unique_id}"
    other_company_id = f"file_other_co_{unique_id}"
    _ = await FileRecord.set(
        _record(
            file_id=older_id,
            company_id=company_id,
            catalog_id=catalog_id,
            original_name=f"older-{token}.txt",
            updated_at=older,
        )
    )
    _ = await FileRecord.set(
        _record(
            file_id=newer_id,
            company_id=company_id,
            catalog_id=catalog_id,
            original_name=f"newer-{token}.txt",
            updated_at=newer,
        )
    )
    _ = await FileRecord.set(
        _record(
            file_id=trashed_id,
            company_id=company_id,
            catalog_id=catalog_id,
            original_name=f"trash-{token}.txt",
            updated_at=newer,
            deleted_at=newer,
        )
    )
    _ = await FileRecord.set(
        _record(
            file_id=other_catalog_id,
            company_id=company_id,
            catalog_id=other_catalog.catalog_id,
            original_name=f"other-{token}.txt",
            updated_at=newer,
        )
    )
    _ = await FileRecord.set(
        _record(
            file_id=other_company_id,
            company_id=f"foreign_{unique_id}",
            catalog_id=catalog_id,
            original_name=f"foreign-{token}.txt",
            updated_at=newer,
        )
    )

    found = await FileRecord.list_alive_matching_original_name_by_updated_at_desc(company_id, [catalog_id], token, 10)
    assert [row.file_id for row in found] == [newer_id, older_id]
    limited = await FileRecord.list_alive_matching_original_name_by_updated_at_desc(company_id, [catalog_id], token, 1)
    assert [row.file_id for row in limited] == [newer_id]
    assert await FileRecord.list_alive_matching_original_name_by_updated_at_desc(company_id, [], token, 10) == []


@pytest.mark.asyncio
async def test_list_with_catalog_by_original_name_skips_empty_catalog_and_trash(
    frontend_di,
    unique_id: str,
) -> None:
    _ = frontend_di
    company_id = f"co_named_{unique_id}"
    catalog = await _catalog(company_id, unique_id, f"cat named {unique_id}")
    catalog_id = catalog.catalog_id
    token = f"nm{unique_id}"
    moment = datetime(2026, 2, 1, tzinfo=UTC)
    alpha_id = f"file_alpha_{unique_id}"
    beta_id = f"file_beta_{unique_id}"
    loose_id = f"file_loose_{unique_id}"
    trashed_id = f"file_named_trash_{unique_id}"
    _ = await FileRecord.set(
        _record(
            file_id=beta_id,
            company_id=company_id,
            catalog_id=catalog_id,
            original_name=f"b-{token}.txt",
            updated_at=moment,
        )
    )
    _ = await FileRecord.set(
        _record(
            file_id=alpha_id,
            company_id=company_id,
            catalog_id=catalog_id,
            original_name=f"a-{token}.txt",
            updated_at=moment,
        )
    )
    _ = await FileRecord.set(
        _record(
            file_id=loose_id,
            company_id=company_id,
            catalog_id=None,
            original_name=f"a-{token}-loose.txt",
            updated_at=moment,
        )
    )
    _ = await FileRecord.set(
        _record(
            file_id=trashed_id,
            company_id=company_id,
            catalog_id=catalog_id,
            original_name=f"a-{token}-trash.txt",
            updated_at=moment,
            deleted_at=moment,
        )
    )

    found = await FileRecord.list_with_catalog_by_original_name_asc(company_id, token, 10)
    assert [row.file_id for row in found] == [alpha_id, beta_id]
    limited = await FileRecord.list_with_catalog_by_original_name_asc(company_id, "", 1)
    assert [row.file_id for row in limited] == [alpha_id]
