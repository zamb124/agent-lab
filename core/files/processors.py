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
from core.files.models import FileMetadata, AudioMetadata, FileStatus
from core.clients.cloud_voice import CloudVoiceClientFactory

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

        s3_url = s3_client.get_public_url(s3_key) if public else None

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
        await s3_client.delete_file(file_record.s3_key)
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

        url = getattr(file_record, 'url', None) or getattr(file_record, 'direct_s3_url', None) or f"/api/v1/files/download/{file_record.file_id}"

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
        storage=None,
        bucket_name: Optional[str] = None,
    ):
        """
        Args:
            file_repository: FileRepository для работы с записями о файлах
            storage: Storage для CloudVoice (кэширование токенов)
            bucket_name: Имя S3 бакета
        """
        self.file_repository = file_repository
        self._storage = storage
        self.bucket_name = bucket_name
        self._s3_client: Optional[S3Client] = None
        self._voice_client = None

    async def _get_s3_client(self) -> S3Client:
        """Получает S3 клиент"""
        if self._s3_client is None:
            if self.bucket_name:
                self._s3_client = S3ClientFactory.create_client_for_bucket(self.bucket_name)
            else:
                self._s3_client = S3ClientFactory.create_default_client()

        return self._s3_client

    async def _get_voice_client(self):
        """Получает Cloud Voice клиент"""
        if self._voice_client is None:
            if self._storage is None:
                raise RuntimeError("Storage не установлен для CloudVoice")
            self._voice_client = CloudVoiceClientFactory.create_client(self._storage)
        return self._voice_client

    @staticmethod
    def extract_audio_info_from_message(message: str) -> List[Dict[str, Any]]:
        """
        Извлекает информацию об аудиофайлах из сообщения агента.

        Args:
            message: Сообщение которое может содержать аудио

        Returns:
            Список словарей с информацией об аудиофайлах
        """
        audios = []
        
        # Паттерн для полного формата: [AUDIO]...ID: audio_id...[/AUDIO]
        full_pattern = r"\[AUDIO\].*?ID:\s*([a-zA-Z0-9_]+).*?\[/AUDIO\]"
        
        # Паттерн для упрощенного формата: [AUDIO]audio_id[/AUDIO]
        simple_pattern = r"\[AUDIO\]([a-zA-Z0-9_]+)\[/AUDIO\]"
        
        # Сначала ищем полный формат
        for match in re.finditer(full_pattern, message, re.DOTALL):
            audio_id = match.group(1).strip()
            audio_info = {
                "name": f"audio_{audio_id[:8]}.ogg",
                "audio_id": audio_id,
                "url": f"/api/v1/files/download/audio/{audio_id}",
                "content_type": "audio/ogg; codecs=opus",
                "size": "unknown",
            }
            audios.append(audio_info)
        
        # Если не нашли полный формат, ищем упрощенный
        if not audios:
            for match in re.finditer(simple_pattern, message):
                audio_id = match.group(1).strip()
                audio_info = {
                    "name": f"audio_{audio_id[:8]}.ogg",
                    "audio_id": audio_id,
                    "url": f"/api/v1/files/download/audio/{audio_id}",
                    "content_type": "audio/ogg; codecs=opus",
                    "size": "unknown",
                }
                audios.append(audio_info)

        return audios

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

        s3_url = s3_client.get_public_url(s3_key) if public else None

        transcription = None
        transcription_status = "pending"

        if auto_recognize:
            logger.info("Запускаем распознавание речи...")
            voice_client = await self._get_voice_client()
            transcription = await voice_client.recognize_audio(data, language="ru-RU")
            transcription_status = "completed"
            logger.info(f"Распознан текст: {transcription[:100]}...")

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
            transcription=transcription,
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
_default_storage = None


def initialize_default_processors(file_repository, storage=None) -> None:
    """
    Инициализирует дефолтные процессоры с заданным file_repository.
    Вызывается при старте приложения в lifespan.
    
    Args:
        file_repository: FileRepository из контейнера приложения
        storage: Storage для CloudVoice (опционально)
    """
    global _default_file_repository, _default_storage
    _default_file_repository = file_repository
    _default_storage = storage


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
            storage=_default_storage
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

