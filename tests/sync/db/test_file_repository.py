"""Метаданные файла Sync: запись и чтение по компании."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.models.files import SyncFile


@pytest.mark.asyncio
async def test_file_create_and_get(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    _ = sync_db_clean
    f_test_1 = f"{unique_id}_f_test_1"
    entity = SyncFile(
        file_id=f_test_1,
        company_id=company_id,
        original_name="doc.txt",
        content_type="text/plain",
        file_size=5,
        storage_url="s3://bucket/key",
        checksum="abc",
        created_at=datetime.now(tz=UTC),
    )
    _ = await SyncFile.set(entity)
    loaded = await SyncFile.get(f_test_1)
    assert loaded is not None
    assert loaded.file_id == f_test_1
    assert loaded.company_id == company_id
    assert loaded.original_name == "doc.txt"


@pytest.mark.asyncio
async def test_file_list_all_company_isolation(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    _ = sync_db_clean
    f_a = f"{unique_id}_f_a"
    f_b = f"{unique_id}_f_b"
    other_company = f"{unique_id}_other_company"
    _ = await SyncFile.set(
        SyncFile(
            file_id=f_a,
            company_id=company_id,
            original_name="a",
            content_type="text/plain",
            file_size=1,
            storage_url="s3://a",
            checksum=None,
            created_at=datetime.now(tz=UTC),
        )
    )
    _ = await SyncFile.set(
        SyncFile(
            file_id=f_b,
            company_id=other_company,
            original_name="b",
            content_type="text/plain",
            file_size=1,
            storage_url="s3://b",
            checksum=None,
            created_at=datetime.now(tz=UTC),
        )
    )
    rows = await SyncFile.objects.filter(company_id=company_id).limit(1000).all()
    ids = {row.file_id for row in rows}
    assert ids == {f_a}
