"""
Процессор для обработки файлов из разных источников.
Сохраняет файлы в S3 и создает записи в БД.
"""

import json
import re
import logging
import hashlib
import mimetypes
import uuid
from typing import Optional, Dict, Any
from pathlib import Path
import httpx

from .core_clients.s3_client import S3ClientFactory, get_default_s3_client
from app.models import FileRecord, FileStatus
from .storage import Storage
from .config import settings

logger = logging.getLogger(__name__)


class FileProcessor:
    """
    Процессор для обработки файлов.
    Загружает файлы в S3 и сохраняет метаданные в БД.
    """

    def __init__(self, bucket_name: Optional[str] = None):
        """
        Инициализация процессора.

        Args:
            bucket_name: Имя S3 бакета (если не указан, используется дефолтный)
        """
        self.bucket_name = bucket_name
        self.storage = Storage()
        self._s3_client = None

    async def _get_s3_client(self):
        """Получает S3 клиент"""
        if self._s3_client is None:
            if self.bucket_name:
                self._s3_client = S3ClientFactory.create_client_for_bucket(
                    self.bucket_name
                )
            else:
                self._s3_client = await get_default_s3_client()

            if not self._s3_client:
                raise ValueError("S3 клиент не настроен")

        return self._s3_client

    async def close(self):
        """Закрывает S3 клиент"""
        if self._s3_client:
            await self._s3_client.close()
            self._s3_client = None

    async def process_file_from_bytes(
        self,
        data: bytes,
        original_name: str,
        content_type: Optional[str] = None,
        uploaded_by: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
        public: bool = False,
    ) -> FileRecord:
        """
        Обрабатывает файл из данных в памяти.

        Args:
            data: Данные файла
            original_name: Оригинальное имя файла
            content_type: MIME тип (автоопределяется если не указан)
            uploaded_by: ID пользователя
            metadata: Дополнительные метаданные
            tags: Теги файла
            public: Сделать файл публично доступным (ACL: public-read)

        Returns:
            Запись о файле
        """
        # Генерируем уникальный ID файла
        file_id = f"file_{uuid.uuid4().hex[:12]}"

        # Определяем MIME тип
        if not content_type:
            content_type, _ = mimetypes.guess_type(original_name)
            if not content_type:
                content_type = "application/octet-stream"

        # Вычисляем MD5 хеш
        checksum = hashlib.md5(data).hexdigest()

        # Генерируем S3 ключ в формате как в бакете
        folder_uuid = str(uuid.uuid4())
        s3_key = f"files/{folder_uuid}/{original_name}"

        # Получаем S3 клиент
        s3_client = await self._get_s3_client()

        # Создаем запись в БД (статус UPLOADING)
        file_record = FileRecord(
            file_id=file_id,
            provider=s3_client.provider_name,
            original_name=original_name,
            s3_key=s3_key,
            s3_bucket=s3_client.bucket_name,
            s3_endpoint=s3_client.endpoint_url,
            content_type=content_type,
            file_size=len(data),
            checksum=checksum,
            status=FileStatus.UPLOADING,
            uploaded_by=uploaded_by,
            metadata=metadata or {},
            tags=tags or [],
            is_public=public,
        )

        # Сохраняем запись в БД
        await self.storage.set(file_record.key, file_record.model_dump_json())
        logger.info(f"📝 Создана запись о файле в БД: {file_record.key}")

        # Подготавливаем метаданные для S3 (только строки)
        s3_metadata = {
            "file_id": file_id,
            "original_name": original_name,
            "uploaded_by": uploaded_by or "unknown",
        }

        # Добавляем пользовательские метаданные, конвертируя в строки
        if metadata:
            for k, v in metadata.items():
                s3_metadata[k] = str(v)

        # Загружаем файл в S3
        await s3_client.upload_bytes(
            data=data,
            key=s3_key,
            content_type=content_type,
            metadata=s3_metadata,
            acl="public-read" if public else None,
        )

        # Обновляем статус на UPLOADED
        file_record.status = FileStatus.UPLOADED
        logger.info(f"✅ Файл загружен в S3: {s3_key}")

        # Сохраняем обновленный статус
        await self.storage.set(file_record.key, file_record.model_dump_json())

        return file_record

    async def process_file_from_url(
        self,
        file_url: str,
        original_name: Optional[str] = None,
        uploaded_by: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
    ) -> FileRecord:
        """
        Обрабатывает файл по URL (например, из Telegram).

        Args:
            file_url: URL файла для скачивания
            original_name: Оригинальное имя файла
            uploaded_by: ID пользователя
            metadata: Дополнительные метаданные
            tags: Теги файла

        Returns:
            Запись о файле
        """
        # Скачиваем файл по URL
        async with httpx.AsyncClient() as client:
            response = await client.get(file_url)

            if response.status_code != 200:
                raise ValueError(
                    f"Не удалось скачать файл по URL: {response.status_code}"
                )

            data = response.content

            # Определяем имя файла если не указано
            if not original_name:
                # Пытаемся извлечь из URL
                original_name = Path(file_url).name
                if not original_name or "." not in original_name:
                    original_name = f"file_{uuid.uuid4().hex[:8]}"

            # Определяем content_type из ответа или по расширению
            content_type = response.headers.get("content-type")

            return await self.process_file_from_bytes(
                data=data,
                original_name=original_name,
                content_type=content_type,
                uploaded_by=uploaded_by,
                metadata=metadata,
                tags=tags,
            )

    async def get_file_record(
        self, file_id: str, provider: Optional[str] = None
    ) -> Optional[FileRecord]:
        """
        Получает запись о файле из БД.

        Args:
            file_id: ID файла
            provider: Провайдер (если не указан, ищем по всем)

        Returns:
            Запись о файле или None
        """
        if provider:
            # Поиск по конкретному провайдеру
            key = f"s3:{provider}:{file_id}"
            data = await self.storage.get(key)

            if data:
                return FileRecord(**json.loads(data))
        else:
            # Поиск по всем провайдерам
            for bucket_name, bucket_config in settings.s3.buckets.items():
                if bucket_config.enabled:
                    key = f"s3:{bucket_config.provider}:{file_id}"
                    data = await self.storage.get(key)

                    if data:
                        return FileRecord(**json.loads(data))

        return None

    async def delete_file(self, file_id: str, provider: Optional[str] = None) -> bool:
        """
        Удаляет файл из S3 и обновляет запись в БД.

        Args:
            file_id: ID файла
            provider: Провайдер (если не указан, ищем по всем)

        Returns:
            True если удаление успешно
        """
        # Получаем запись о файле
        file_record = await self.get_file_record(file_id, provider)
        if not file_record:
            logger.warning(f"Файл {file_id} не найден в БД")
            return False

        try:
            # Создаем S3 клиент для этого файла
            s3_client = S3ClientFactory.create_client_for_bucket(file_record.s3_bucket)

            # Удаляем из S3
            delete_success = await s3_client.delete_object(file_record.s3_key)

            if delete_success:
                # Обновляем статус в БД
                file_record.status = FileStatus.DELETED
                await self.storage.set(file_record.key, file_record.model_dump_json())
                logger.info(f"✅ Файл удален: {file_id}")
                return True
            else:
                logger.error(f"❌ Не удалось удалить файл из S3: {file_id}")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка удаления файла {file_id}: {e}")
            return False
        finally:
            if "s3_client" in locals():
                await s3_client.close()

    def format_file_message(self, file_record: FileRecord) -> str:
        """
        Форматирует сообщение о файле для агента.

        Args:
            file_record: Запись о файле

        Returns:
            Отформатированное сообщение
        """
        size_mb = file_record.file_size / (1024 * 1024)
        size_str = (
            f"{size_mb:.2f} MB" if size_mb >= 1 else f"{file_record.file_size} байт"
        )

        return f"📎 Файл: {file_record.original_name} (ID: {file_record.file_id}, Скачать: {file_record.url}, Тип: {file_record.content_type}, Размер: {size_str})"

    @staticmethod
    def extract_file_info_from_message(message: str) -> list[Dict[str, str]]:
        """
        Извлекает информацию о файлах из сообщения агента.

        Args:
            message: Сообщение которое может содержать файлы

        Returns:
            Список словарей с информацией о файлах
        """
        # Паттерн для поиска файлов в сообщении
        pattern = r"\[FILE\]\s*📎 Файл: ([^(]+) \(ID: ([^,]+), URL: ([^,]+), тип: ([^,]+), размер: ([^)]+)\)\s*\[/FILE\]"

        files = []
        for match in re.finditer(pattern, message):
            files.append(
                {
                    "name": match.group(1).strip(),
                    "file_id": match.group(2).strip(),
                    "url": match.group(3).strip(),
                    "content_type": match.group(4).strip(),
                    "size": match.group(5).strip(),
                }
            )

        return files


# Глобальный экземпляр процессора
_default_file_processor: Optional[FileProcessor] = None


async def get_default_file_processor() -> FileProcessor:
    """Получает дефолтный файловый процессор"""
    global _default_file_processor

    if _default_file_processor is None:
        _default_file_processor = FileProcessor()

    return _default_file_processor


async def close_default_file_processor():
    """Закрывает дефолтный файловый процессор"""
    global _default_file_processor

    if _default_file_processor:
        await _default_file_processor.close()
        _default_file_processor = None
