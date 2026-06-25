"""Backfill retention fields for FileRecord rows missing retention metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from core.files.create_spec import FileSourceKind
from core.files.file_repository import FileRepository
from core.files.registry import default_retention_for_source
from core.files.retention import FileRetentionKind, FileRetentionSpec, resolve_retention_ttl_seconds
from core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RetentionBackfillBatchResult:
    scanned: int
    updated: int
    skipped: int


def _retention_from_record_metadata(metadata_source_kind: str | None) -> FileRetentionSpec:
    if metadata_source_kind is None or metadata_source_kind == "":
        return FileRetentionSpec(kind=FileRetentionKind.PLATFORM_DEFAULT)
    try:
        source_kind = FileSourceKind(metadata_source_kind)
    except ValueError:
        return FileRetentionSpec(kind=FileRetentionKind.PLATFORM_DEFAULT)
    return default_retention_for_source(source_kind)


def _expires_at_from_ttl(created_at: datetime, ttl_seconds: int) -> datetime | None:
    if ttl_seconds == 0:
        return None
    base = created_at if created_at.tzinfo is not None else created_at.replace(tzinfo=UTC)
    return base + timedelta(seconds=ttl_seconds)


class FileRetentionBackfillService:
    def __init__(self, file_repository: FileRepository) -> None:
        self._repository: FileRepository = file_repository

    async def backfill_batch(self, *, limit: int) -> RetentionBackfillBatchResult:
        records = await self._repository.list_missing_retention(limit=limit)
        updated = 0
        skipped = 0
        for record in records:
            metadata_source = record.metadata.get("source_kind")
            source_kind_value = metadata_source if isinstance(metadata_source, str) else None
            retention = _retention_from_record_metadata(source_kind_value)
            ttl_seconds = resolve_retention_ttl_seconds(retention)
            expires_at = _expires_at_from_ttl(record.created_at, ttl_seconds)
            if record.retention_kind == retention.kind and record.expires_at == expires_at:
                skipped += 1
                continue
            patched = record.model_copy(
                update={
                    "retention_kind": retention.kind,
                    "expires_at": expires_at,
                    "updated_at": datetime.now(UTC),
                }
            )
            _ = await self._repository.set(patched)
            updated += 1
        if updated:
            logger.info("file retention backfill batch", updated_count=updated)
        return RetentionBackfillBatchResult(
            scanned=len(records),
            updated=updated,
            skipped=skipped,
        )
