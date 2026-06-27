"""
Retention, backfill и purge для unified Files API.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.files.backfill import FileRetentionBackfillService
from core.files.create_spec import FileCreateSpec
from core.files.models import FileStatus
from core.files.purge import FilePurgeService
from core.files.retention import FileRetentionKind, FileRetentionSpec, resolve_retention_ttl_seconds
from tests.fixtures.s3 import require_s3_configured


def _platform_auxiliary_spec(*, is_public: bool = False) -> FileCreateSpec:
    return FileCreateSpec.model_validate(
        {
            "source_kind": "platform_auxiliary",
            "source_ref": {},
            "retention": {"kind": "platform_default"},
            "post_create": {"is_public": is_public},
        }
    )


def test_resolve_retention_ttl_permanent_is_zero():
    ttl = resolve_retention_ttl_seconds(FileRetentionSpec(kind=FileRetentionKind.PERMANENT))
    assert ttl == 0


def test_resolve_retention_ttl_flow_session_positive():
    ttl = resolve_retention_ttl_seconds(FileRetentionSpec(kind=FileRetentionKind.FLOW_SESSION))
    assert ttl > 0


def test_resolve_retention_ttl_custom_seconds():
    ttl = resolve_retention_ttl_seconds(
        FileRetentionSpec(kind=FileRetentionKind.GENERATED_EPHEMERAL, ttl_seconds=3600)
    )
    assert ttl == 3600


@pytest.mark.asyncio
async def test_backfill_sets_retention_fields(app, file_db_clean, unique_id: str):
    _ = app
    from apps.frontend.container import get_frontend_container
    require_s3_configured()
    container = get_frontend_container()
    record = await container.files_service.create(
        _platform_auxiliary_spec(),
        f"backfill-{unique_id}".encode("utf-8"),
        original_name=f"backfill-{unique_id}.txt",
        content_type="text/plain",
    )
    repo = container.file_repository
    stale = record.model_copy(update={"retention_kind": None, "expires_at": None})
    _ = await repo.set(stale)

    backfill = FileRetentionBackfillService(repo)
    batch = await backfill.backfill_batch(limit=50)
    assert batch.updated >= 1

    loaded = await container.files_service.get(record.file_id)
    assert loaded.retention_kind is not None
    assert loaded.retention_kind != ""


@pytest.mark.asyncio
async def test_purge_deletes_expired_file(app, file_db_clean, unique_id: str):
    _ = app
    from apps.frontend.container import get_frontend_container
    require_s3_configured()
    container = get_frontend_container()
    record = await container.files_service.create(
        _platform_auxiliary_spec(),
        f"purge-{unique_id}".encode("utf-8"),
        original_name=f"purge-{unique_id}.txt",
        content_type="text/plain",
    )
    expired_at = datetime.now(UTC) - timedelta(minutes=5)
    repo = container.file_repository
    expired = record.model_copy(
        update={
            "retention_kind": FileRetentionKind.GENERATED_EPHEMERAL,
            "expires_at": expired_at,
        }
    )
    _ = await repo.set(expired)

    purge = FilePurgeService(repo)
    batch = await purge.purge_expired_batch()
    assert batch.purged_count >= 1

    with pytest.raises(ValueError, match="file not found"):
        await container.files_service.get(record.file_id)


@pytest.mark.asyncio
async def test_purge_skips_permanent_files(app, unique_id: str):
    _ = app
    from apps.frontend.container import get_frontend_container
    require_s3_configured()
    container = get_frontend_container()
    record = await container.files_service.create(
        _platform_auxiliary_spec(),
        f"permanent-{unique_id}".encode("utf-8"),
        original_name=f"permanent-{unique_id}.txt",
        content_type="text/plain",
    )
    repo = container.file_repository
    permanent = record.model_copy(
        update={
            "retention_kind": FileRetentionKind.PERMANENT,
            "expires_at": None,
            "status": FileStatus.READY,
        }
    )
    _ = await repo.set(permanent)

    purge = FilePurgeService(repo)
    _ = await purge.purge_expired_batch()

    loaded = await container.files_service.get(record.file_id)
    assert loaded.file_id == record.file_id
