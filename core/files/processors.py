"""
Процессоры для обработки файлов и аудио.
Сохраняют файлы в S3 и создают записи в БД через FileRepository.
"""

import re
import logging
import hashlib
import mimetypes
import uuid
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from pathlib import Path

from core.files.s3_client import S3ClientFactory, S3Client
from core.files.models import (
    AudioMetadata,
    AudioTranscriptionStatus,
    FileMetadata,
    FileStatus,
)
from core.clients.stt_client import BaseSTTClient, STTClientFactory

if TYPE_CHECKING:
    from core.files.file_repository import FileRepository

logger = logging.getLogger(__name__)


class FileProcessor:
    """
    Процессор для обработки файлов.
    Загружает файлы в S3 и сохраняет метаданные через FileRepository.
    """

    def __init__(self, file_repository: "FileRepository", bucket_name: Optional[str] = None):
        """
        Args:
            file_repository: FileRepository для работы с записями о файлах
            bucket_name: Имя S3 бакета (если не указан, используется дефолтный)
        """
        self.file_repository = file_repository
        self.bucket_name = bucket_name
        self._s3_client: Optional[S3Client] = None

    async def _get_s3_client(self) -> S3Client:
        """Получает S3 клиент"""
        if self._s3_client is None:
            if self.bucket_name:
                self._s3_client = S3ClientFactory.create_client_for_bucket(self.bucket_name)
            else:
                self._s3_client = S3ClientFactory.create_default_client()

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
        tags: Optional[List[str]] = None,
        public: bool = False,
    ) -> FileMetadata:
        """
        Обрабатывает файл из данных в памяти.

        Args:
            data: Данные файла
            original_name: Оригинальное имя файла
            content_type: MIME тип
            uploaded_by: ID пользователя
            metadata: Дополнительные метаданные
            tags: Теги файла
            public: Сделать файл публичным

        Returns:
            Метаданные файла
        """
        file_id = f"file_{uuid.uuid4().hex[:12]}"

        if not content_type:
            content_type, _ = mimetypes.guess_type(original_name)
            if not content_type:
                content_type = "application/octet-stream"

        file_hash = hashlib.sha256(data).hexdigest()[:16]
        extension = Path(original_name).suffix or ".bin"
        s3_key = f"files/{file_id}_{file_hash}{extension}"

        s3_client = await self._get_s3_client()

        await s3_client.upload_bytes(
            data=data,
            key=s3_key,
            metadata=metadata or {},
            content_type=content_type,
            public=public,
        )

        file_record = FileMetadata(
            file_id=file_id,
            provider=s3_client.provider_name,
            original_name=original_name,
            content_type=content_type,
            file_size=len(data),
            s3_bucket=s3_client.bucket_name,
            s3_key=s3_key,
            s3_endpoint=s3_client.endpoint_url,
            uploaded_by=uploaded_by,
            is_public=public,
            status=FileStatus.READY,
            metadata=metadata or {},
            tags=tags or [],
        )

        await self.file_repository.set(file_record)

        logger.info(f"Файл обработан: {file_id} ({original_name}, {len(data)} байт)")
        return file_record

    async def get_file_record(self, file_id: str) -> Optional[FileMetadata]:
        """
        Получает запись о файле.

        Args:
            file_id: ID файла

        Returns:
            Запись о файле или None
        """
        return await self.file_repository.get(file_id)

    async def delete_file(self, file_id: str) -> bool:
        """
        Удаляет файл из S3 и БД.

        Args:
            file_id: ID файла

        Returns:
            True если удаление успешно
        """
        file_record = await self.get_file_record(file_id)
        if not file_record:
            logger.warning(f"Файл {file_id} не найден в БД")
            return False

        s3_client = S3ClientFactory.create_client_for_bucket(file_record.s3_bucket)
        try:
            await s3_client.delete_file(file_record.s3_key)
        finally:
            await s3_client.close()

        await self.file_repository.delete(file_id)

        logger.info(f"Файл удален: {file_id}")
        return True

    def format_file_message(self, file_record) -> str:
        """
        Форматирует сообщение о файле для агента.

        Args:
            file_record: Запись о файле (FileRecord или FileMetadata)

        Returns:
            Отформатированное сообщение в формате [FILE] ... [/FILE]
        """
        size_mb = file_record.file_size / (1024 * 1024)
        size_str = (
            f"{size_mb:.2f} MB" if size_mb >= 1 else f"{file_record.file_size} байт"
        )

        url = file_record.url

        return (
            f"[FILE] "
            f"Файл: {file_record.original_name} "
            f"(ID: {file_record.file_id}, "
            f"URL: {url}, "
            f"тип: {file_record.content_type}, "
            f"размер: {size_str}) "
            f"[/FILE]"
        )

    @staticmethod
    def extract_file_info_from_message(message_content: str) -> List[Dict[str, str]]:
        """
        Извлекает информацию о файлах из текста сообщения.
        Поддерживает несколько форматов для обратной совместимости.

        Args:
            message_content: Текст сообщения

        Returns:
            Список словарей с информацией о файлах (ключи: name, file_id, url, content_type, size)
        """
        file_info_list = []
        
        # Формат: [FILE] Файл: name (ID: id, URL: url, тип: type, размер: size) [/FILE]
        # Может быть с переносами строк и эмодзи внутри
        pattern = r'\[FILE\][\s\n]*📎?\s*Файл:\s*([^\(]+)\s*\(ID:\s*([^,]+),\s*URL:\s*([^,]+),\s*тип:\s*([^,]+),\s*размер:\s*([^)]+)\)[\s\n]*\[/FILE\]'
        matches = re.findall(pattern, message_content, re.MULTILINE)
        
        for filename, file_id, url, content_type, size in matches:
            file_info_list.append({
                "name": filename.strip(),
                "file_id": file_id.strip(),
                "url": url.strip(),
                "content_type": content_type.strip(),
                "size": size.strip(),
            })
        
        # Также поддерживаем формат без [FILE]...[/FILE] для обратной совместимости
        if not file_info_list:
            old_pattern = r'📎\s*Файл:\s*([^\(]+)\s*\(ID:\s*(file_[a-f0-9]{12})'
            old_matches = re.findall(old_pattern, message_content)
            for filename, file_id in old_matches:
                file_info_list.append({
                    "name": filename.strip(),
                    "file_id": file_id.strip(),
                })

        return file_info_list


class AudioProcessor:
    """
    Процессор для обработки аудиофайлов.
    Загружает аудио в S3, сохраняет метаданные через FileRepository и распознает речь.
    """

    def __init__(
        self,
        file_repository: "FileRepository",
        bucket_name: Optional[str] = None,
    ):
        """
        Args:
            file_repository: FileRepository для работы с записями о файлах
            bucket_name: Имя S3 бакета
        """
        self.file_repository = file_repository
        self.bucket_name = bucket_name
        self._s3_client: Optional[S3Client] = None
        self._stt_client: Optional[BaseSTTClient] = None

    async def _get_s3_client(self) -> S3Client:
        """Получает S3 клиент"""
        if self._s3_client is None:
            if self.bucket_name:
                self._s3_client = S3ClientFactory.create_client_for_bucket(self.bucket_name)
            else:
                self._s3_client = S3ClientFactory.create_default_client()

        return self._s3_client

    async def _get_stt_client(self) -> BaseSTTClient:
        """Получает STT клиент."""
        if self._stt_client is None:
            self._stt_client = STTClientFactory.create_client()
        return self._stt_client

    @staticmethod
    def extract_audio_info_from_message(message: str) -> List[Dict[str, Any]]:
        """
        Legacy AUDIO-теги удалены из платформы.

        Args:
            message: Текст сообщения

        Returns:
            Всегда пустой список, т.к. [AUDIO] формат больше не поддерживается.
        """
        _ = message
        return []

    async def close(self):
        """Закрывает клиенты"""
        if self._s3_client:
            await self._s3_client.close()
            self._s3_client = None

    async def process_audio_from_bytes(
        self,
        data: bytes,
        original_name: str,
        content_type: str = "audio/wave",
        uploaded_by: Optional[str] = None,
        auto_recognize: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        public: bool = True,
    ) -> AudioMetadata:
        """
        Обрабатывает аудиофайл из данных в памяти.

        Args:
            data: Данные аудиофайла
            original_name: Оригинальное имя файла
            content_type: MIME тип аудио
            uploaded_by: ID пользователя
            auto_recognize: Автоматически распознавать речь
            metadata: Дополнительные метаданные
            tags: Теги аудиофайла
            public: Сделать файл публичным

        Returns:
            Метаданные аудиофайла
        """
        logger.info(f"Начинаем обработку аудио: {original_name}, размер={len(data)} байт")

        file_id = f"file_{uuid.uuid4().hex[:12]}"
        file_hash = hashlib.sha256(data).hexdigest()[:16]
        extension = Path(original_name).suffix or ".wav"
        s3_key = f"audio/{file_id}_{file_hash}{extension}"

        s3_client = await self._get_s3_client()

        await s3_client.upload_bytes(
            data=data,
            key=s3_key,
            metadata=metadata or {},
            content_type=content_type,
            public=public,
        )

        transcription_text = None
        stt_result = None
        transcription_status = AudioTranscriptionStatus.IDLE

        if auto_recognize:
            logger.info("Запускаем распознавание речи...")
            stt_client = await self._get_stt_client()
            stt_result = await stt_client.transcribe_audio(
                audio_bytes=data,
                file_name=original_name,
                mime_type=content_type,
                language="ru",
            )
            transcription_text = stt_result.text
            transcription_status = stt_result.status
            logger.info(f"Распознан текст: {transcription_text[:100]}...")

        audio_record = AudioMetadata(
            file_id=file_id,
            provider=s3_client.provider_name,
            original_name=original_name,
            content_type=content_type,
            file_size=len(data),
            s3_bucket=s3_client.bucket_name,
            s3_key=s3_key,
            s3_endpoint=s3_client.endpoint_url,
            uploaded_by=uploaded_by,
            status=FileStatus.READY,
            metadata=metadata or {},
            tags=tags or [],
            transcription_status=transcription_status,
            transcription_text=transcription_text,
            transcription_error=stt_result.error if stt_result is not None else None,
            transcription_provider=stt_result.provider if stt_result is not None else None,
        )

        await self.file_repository.set(audio_record)

        logger.info(f"Аудио обработано: {file_id}")
        return audio_record

    async def get_audio_record(self, audio_id: str) -> Optional[AudioMetadata]:
        """
        Получает запись об аудиофайле.

        Args:
            audio_id: ID аудиофайла

        Returns:
            Запись об аудиофайле или None
        """
        return await self.file_repository.get(audio_id)


_default_file_processor: Optional[FileProcessor] = None
_default_audio_processor: Optional[AudioProcessor] = None
_default_file_repository = None


def initialize_default_processors(file_repository) -> None:
    """
    Инициализирует дефолтные процессоры с заданным file_repository.
    Вызывается при старте приложения в lifespan.
    
    Args:
        file_repository: FileRepository из контейнера приложения
    """
    global _default_file_repository
    _default_file_repository = file_repository


async def get_default_file_processor() -> FileProcessor:
    """
    Получает дефолтный файловый процессор.
    Требует предварительного вызова initialize_default_processors().
    """
    global _default_file_processor
    
    if _default_file_processor is None:
        if _default_file_repository is None:
            raise RuntimeError(
                "Процессоры не инициализированы. "
                "Вызовите initialize_default_processors(file_repository) при старте приложения."
            )
        _default_file_processor = FileProcessor(file_repository=_default_file_repository)
    
    return _default_file_processor


async def get_default_audio_processor() -> AudioProcessor:
    """
    Получает дефолтный аудио процессор.
    Требует предварительного вызова initialize_default_processors().
    """
    global _default_audio_processor
    
    if _default_audio_processor is None:
        if _default_file_repository is None:
            raise RuntimeError(
                "Процессоры не инициализированы. "
                "Вызовите initialize_default_processors(file_repository) при старте приложения."
            )
        _default_audio_processor = AudioProcessor(
            file_repository=_default_file_repository,
        )
    
    return _default_audio_processor


async def close_default_file_processor():
    """Закрывает дефолтный файловый процессор"""
    global _default_file_processor
    if _default_file_processor:
        await _default_file_processor.close()
        _default_file_processor = None


async def close_default_audio_processor():
    """Закрывает дефолтный аудио процессор"""
    global _default_audio_processor
    if _default_audio_processor:
        await _default_audio_processor.close()
        _default_audio_processor = None

