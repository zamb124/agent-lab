"""
Репозиторий для работы с FileRecord.
Использует service БД, is_global=False (изолирован по компаниям).
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, override

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.files.models import FileRecord, FileStatus
from core.logging import get_logger

logger = get_logger(__name__)


class FileRepository(BaseRepository[FileRecord]):
    """
    Репозиторий для работы с файлами.

    is_global=True — записи хранятся без префикса компании.
    Доступ для приватных файлов контролируется на уровне хендлера (сверка company_id),
    а не на уровне ключей хранилища.
    """

    is_global: ClassVar[bool] = True

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=FileRecord)

    @override
    def _get_key(self, file_id: str) -> str:
        return f"file:{file_id}"

    @override
    def _get_prefix(self) -> str:
        return "file:"

    @override
    def _get_table_name(self) -> str:
        return "storage"

    @override
    def _extract_entity_id(self, entity: FileRecord) -> str:
        return entity.file_id

    async def get_by_s3_key(self, provider: str, file_id: str) -> FileRecord | None:
        key = f"s3:{provider}:{file_id}"
        final_key = self._build_final_key(key)
        table_name = self._get_table_name()

        data = await self._storage.get_with_session_and_table(final_key, table_name)
        if data is None:
            return None

        return self.model_class.model_validate_json(data)

    async def set_by_s3_key(self, provider: str, file_record: FileRecord) -> bool:
        key = f"s3:{provider}:{file_record.file_id}"
        final_key = self._build_final_key(key)
        table_name = self._get_table_name()

        data = file_record.model_dump_json()
        return await self._storage.set_with_table(final_key, data, table_name)

    async def list_expired(self, *, before: datetime, limit: int) -> list[FileRecord]:
        table_name = self._get_table_name()
        prefix = self._get_prefix()
        expired: list[FileRecord] = []
        offset = 0
        page_size = max(limit * 20, 500)
        while len(expired) < limit:
            page_data = await self._storage.get_all_by_prefix_and_table(
                prefix,
                table_name,
                page_size,
                offset,
            )
            if not page_data:
                break
            for data in page_data.values():
                if len(expired) >= limit:
                    break
                record = FileRecord.model_validate_json(data)
                if record.deleted_at is not None:
                    continue
                if record.status == FileStatus.DELETED:
                    continue
                if record.expires_at is None:
                    continue
                if record.expires_at <= before:
                    expired.append(record)
            offset += len(page_data)
            if len(page_data) < page_size:
                break
        return expired

    async def list_missing_retention(self, *, limit: int) -> list[FileRecord]:
        final_prefix = self._build_final_key(self._get_prefix())
        table_name = self._get_table_name()
        missing: list[FileRecord] = []
        offset = 0
        page_size = max(limit * 20, 200)
        while len(missing) < limit:
            page_data = await self._storage.get_all_by_prefix_and_table(
                final_prefix,
                table_name,
                page_size,
                offset,
            )
            if not page_data:
                break
            for data in page_data.values():
                if len(missing) >= limit:
                    break
                record = FileRecord.model_validate_json(data)
                if record.deleted_at is not None:
                    continue
                if record.status == FileStatus.DELETED:
                    continue
                if record.retention_kind is not None and record.expires_at is not None:
                    continue
                missing.append(record)
            offset += len(page_data)
            if len(page_data) < page_size:
                break
        return missing
