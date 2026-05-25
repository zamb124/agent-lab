"""
Репозиторий для работы с FileRecord.
Использует service БД, is_global=False (изолирован по компаниям).
"""


from typing import ClassVar, override

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.files.models import FileRecord
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
        """
        Получает файл по S3 ключу.

        Args:
            provider: Провайдер S3
            file_id: ID файла

        Returns:
            FileRecord или None
        """
        key = f"s3:{provider}:{file_id}"
        final_key = self._build_final_key(key)
        table_name = self._get_table_name()

        data = await self._storage.get_with_session_and_table(final_key, table_name)
        if data is None:
            return None

        return self.model_class.model_validate_json(data)

    async def set_by_s3_key(self, provider: str, file_record: FileRecord) -> bool:
        """
        Сохраняет файл по S3 ключу.

        Args:
            provider: Провайдер S3
            file_record: Запись о файле

        Returns:
            True если сохранение успешно
        """
        key = f"s3:{provider}:{file_record.file_id}"
        final_key = self._build_final_key(key)
        table_name = self._get_table_name()

        data = file_record.model_dump_json()
        return await self._storage.set_with_table(final_key, data, table_name)
