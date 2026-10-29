"""Tests for file retention promotion."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.files.create_spec import FileSourceKind
from core.files.models import FileRecord, FileStatus
from core.files.object_storage import PLATFORM_STORAGE_ID
from core.files.retention import FileRetentionKind
from core.files.retention_promote import promote_file_retention_record


def _sample_record(**updates: object) -> FileRecord:
    base = FileRecord(
        file_id="file_test123",
                original_name="doc.txt",
        s3_key="files/file_test123_ab.txt",
        storage_id=PLATFORM_STORAGE_ID,
        content_type="text/plain",
        file_size=10,
        company_id="company_test",
        status=FileStatus.READY,
        retention_kind=FileRetentionKind.PLATFORM_DEFAULT.value,
        expires_at=datetime.now(UTC) + timedelta(days=10),
        metadata={},
    )
    return base.model_copy(update=updates)


def test_promote_office_document_clears_expires_at():
    record = _sample_record()
    promoted, changed = promote_file_retention_record(
        record,
        retention_kind=FileRetentionKind.OFFICE_DOCUMENT,
        source_kind=FileSourceKind.OFFICE_DOCUMENT,
    )
    assert changed is True
    assert promoted.retention_kind == FileRetentionKind.OFFICE_DOCUMENT.value
    assert promoted.expires_at is None
    assert promoted.metadata["source_kind"] == FileSourceKind.OFFICE_DOCUMENT.value


def test_promote_office_document_idempotent():
    record = _sample_record(
        retention_kind=FileRetentionKind.OFFICE_DOCUMENT.value,
        expires_at=None,
        metadata={"source_kind": FileSourceKind.OFFICE_DOCUMENT.value},
    )
    promoted, changed = promote_file_retention_record(
        record,
        retention_kind=FileRetentionKind.OFFICE_DOCUMENT,
        source_kind=FileSourceKind.OFFICE_DOCUMENT,
    )
    assert changed is False
    assert promoted is record


@pytest.mark.asyncio
async def test_files_service_promote_retention_persists(app, unique_id: str, frontend_di):
    _ = app
    from core.files.create_spec import FileCreateSpec
    from tests.fixtures.s3 import require_s3_configured

    require_s3_configured()
    spec = FileCreateSpec.model_validate(
        {
            "source_kind": "platform_auxiliary",
            "source_ref": {},
            "retention": {"kind": "platform_default"},
        }
    )
    record = await frontend_di.files_service.create(
        spec,
        f"promote-{unique_id}".encode("utf-8"),
        original_name=f"promote-{unique_id}.txt",
        content_type="text/plain",
    )
    assert record.expires_at is not None

    promoted = await frontend_di.files_service.promote_retention(
        record.file_id,
        retention_kind=FileRetentionKind.OFFICE_DOCUMENT,
        source_kind=FileSourceKind.OFFICE_DOCUMENT,
    )
    assert promoted.expires_at is None
    assert promoted.retention_kind == FileRetentionKind.OFFICE_DOCUMENT.value

    loaded = await frontend_di.files_service.get(record.file_id)
    assert loaded.expires_at is None
    assert loaded.retention_kind == FileRetentionKind.OFFICE_DOCUMENT.value
