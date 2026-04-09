"""Тесты FileRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.db.models import SyncFile
from apps.sync.db.repositories.file_repository import SyncFileRepository


@pytest.mark.asyncio
async def test_file_create_and_get(
    file_repo: SyncFileRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    f_test_1 = f"{unique_id}_f_test_1"
    entity = SyncFile(
        file_id=f_test_1,
        company_id=company_id,
        original_name="doc.txt",
        mime_type="text/plain",
        size_bytes=5,
        storage_url="s3://bucket/key",
        checksum="abc",
        created_at=datetime.now(tz=UTC),
    )
    await file_repo.create(entity)
    loaded = await file_repo.get(f_test_1)
    assert loaded is not None
    assert loaded.file_id == f_test_1
    assert loaded.company_id == company_id
    assert loaded.original_name == "doc.txt"


@pytest.mark.asyncio
async def test_file_list_all_company_isolation(
    file_repo: SyncFileRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    f_a = f"{unique_id}_f_a"
    f_b = f"{unique_id}_f_b"
    other_company = f"{unique_id}_other_company"
    await file_repo.create(
        SyncFile(
            file_id=f_a,
            company_id=company_id,
            original_name="a",
            mime_type="text/plain",
            size_bytes=1,
            storage_url="s3://a",
            checksum=None,
            created_at=datetime.now(tz=UTC),
        )
    )
    await file_repo.create(
        SyncFile(
            file_id=f_b,
            company_id=other_company,
            original_name="b",
            mime_type="text/plain",
            size_bytes=1,
            storage_url="s3://b",
            checksum=None,
            created_at=datetime.now(tz=UTC),
        )
    )
    only_a = await file_repo.list_all(company_id=company_id)
    ids = {r.file_id for r in only_a}
    assert ids == {f_a}
