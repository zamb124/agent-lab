"""
Сервис очистки истекших данных.
Вынесен из Storage для избежания циклических зависимостей.
"""

import logging
from datetime import datetime, timezone
from sqlalchemy import select, delete

from core.db.storage import Storage
from core.files.s3_client import S3ClientFactory
from core.db.models import Storage as StorageModel
from apps.agents.container import get_agents_container
from apps.agents.container import get_agents_container

logger = logging.getLogger(__name__)


class CleanupService:
    """Сервис для очистки истекших данных"""

    def __init__(self, storage: Storage = None):
        if storage is None:
            storage = get_agents_container().storage
        self.storage = storage

    async def cleanup_expired(self) -> int:
        """
        Удаляет истекшие записи из БД и связанные S3 файлы.

        Returns:
            Количество удаленных записей
        """
        async with self.storage._get_session() as session:
            now = datetime.now(timezone.utc)

            # Сначала находим истекшие записи для проверки S3 файлов
            select_stmt = select(StorageModel.key, StorageModel.value).where(
                StorageModel.expired_at.is_not(None), StorageModel.expired_at < now
            )

            result = await session.execute(select_stmt)
            expired_records = result.fetchall()

            s3_files_deleted = 0

            # Проверяем каждую запись на наличие S3 файлов
            for key, value in expired_records:
                if key.startswith("s3:") and isinstance(value, dict):
                    # Это файловая запись в формате s3:provider:file_id - удаляем из S3
                    s3_key = value.get("s3_key")
                    s3_bucket = value.get("s3_bucket")
                    provider = value.get("provider")

                    if s3_key and s3_bucket:
                        try:
                            s3_client = S3ClientFactory.create_client_for_bucket(
                                s3_bucket
                            )
                            await s3_client.delete_object(s3_key)
                            s3_files_deleted += 1
                            logger.debug(
                                f"🗑️ Удален S3 файл: {s3_bucket}/{s3_key} (provider: {provider})"
                            )

                        except Exception as e:
                            logger.warning(
                                f"❌ Не удалось удалить S3 файл {s3_bucket}/{s3_key}: {e}"
                            )

            # Теперь удаляем записи из БД
            delete_stmt = delete(StorageModel).where(
                StorageModel.expired_at.is_not(None), StorageModel.expired_at < now
            )

            result = await session.execute(delete_stmt)
            deleted_count = result.rowcount
            await session.commit()

            if deleted_count > 0:
                logger.info(f"🧹 Очищено {deleted_count} истекших записей из Storage")
                if s3_files_deleted > 0:
                    logger.info(f"🗑️ Удалено {s3_files_deleted} S3 файлов")

            return deleted_count
