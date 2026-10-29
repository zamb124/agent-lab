"""Expired file purge."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from core.config import get_settings
from core.files.models import FileRecord
from core.files.storage import FileStorage
from core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PurgeBatchResult:
    purged_count: int
    failed_file_ids: list[str]


class FilePurgeService:
    def __init__(self) -> None:
        self._storage: FileStorage = FileStorage()

    async def purge_expired_batch(self) -> PurgeBatchResult:
        settings = get_settings()
        if not settings.files.retention.purge_enabled:
            return PurgeBatchResult(purged_count=0, failed_file_ids=[])

        batch_limit = settings.files.retention.purge_batch_size
        now = datetime.now(UTC)
        expired = await FileRecord.list_unordered_expired(before=now, limit=batch_limit)
        failed: list[str] = []
        purged = 0
        for record in expired:
            deleted = await self._storage.delete(record.file_id)
            if deleted:
                purged += 1
            else:
                failed.append(record.file_id)
        if purged:
            logger.info("files.file.purge.batch.completed", purged_count=purged)
        return PurgeBatchResult(purged_count=purged, failed_file_ids=failed)
