"""
Процессоры для обработки файлов и аудио.
Сохраняют файлы в S3 и создают записи в БД через FileRepository.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

from core.context import require_active_company
from core.files.audio_transcode import (
    resolve_ios_transcode_source,
    transcode_audio_bytes_to_m4a_aac,
)
from core.files.file_ref import FileRef
from core.files.media.transcriber import MediaTranscriber
from core.files.models import (
    AudioRecord,
    AudioTranscriptionStatus,
    FileRecord,
    FileStatus,
)
from core.files.s3_client import S3Client, S3ClientFactory
from core.logging import get_logger
from core.types import JsonObject

if TYPE_CHECKING:
    from core.files.file_repository import FileRepository

logger = get_logger(__name__)
FILE_MESSAGE_RE = re.compile(
    r"\[FILE\][\s\n]*📎?\s*Файл:\s*([^\(]+)\s*"
    + r"\(ID:\s*([^,]+),\s*URL:\s*([^,]+),\s*тип:\s*([^,]+),\s*"
    + r"размер:\s*([^)]+)\)[\s\n]*\[/FILE\]",
    re.MULTILINE,
)


def _to_ascii_s3_metadata(metadata: JsonObject) -> dict[str, str]:
    """
    S3 user-defined metadata должна быть ASCII-only строками.
    При этом в FileRecord.metadata мы сохраняем исходные значения (включая Unicode).
    """
    out: dict[str, str] = {}
    for raw_key, raw_value in metadata.items():
        key = raw_key.strip()
        if isinstance(raw_value, Mapping) or (
            isinstance(raw_value, Sequence) and not isinstance(raw_value, str)
        ):
            value = json.dumps(raw_value, ensure_ascii=False, separators=(",", ":"))
        else:
            value = str(raw_value)

        out[key] = value if value.isascii() else quote(value, safe="")
    return out


class FileProcessor:
    """
    Процессор для обработки файлов.
    Загружает файлы в S3 и сохраняет метаданные через FileRepository.
    """

    def __init__(self, file_repository: FileRepository, bucket_name: str | None = None):
        """
        Аргументы:
            file_repository: FileRepository для работы с записями о файлах
            bucket_name: Имя S3 бакета (если не указан, используется дефолтный)
        """
        self.file_repository: FileRepository = file_repository
        self.bucket_name: str | None = bucket_name
        self._s3_client: S3Client | None = None

    async def get_s3_client(self) -> S3Client:
        """Получает S3 клиент"""
        if self._s3_client is None:
            if self.bucket_name:
                self._s3_client = S3ClientFactory.create_client_for_bucket(self.bucket_name)
            else:
                self._s3_client = S3ClientFactory.create_default_client()
        return self._s3_client

    async def close(self) -> None:
        """Закрывает S3 клиент"""
        if self._s3_client:
            await self._s3_client.close()
            self._s3_client = None

    @staticmethod
    def _original_name_with_extension_from_content_type(
        original_name: str, content_type: str
    ) -> str:
        """Если в имени нет суффикса, добавляет его по MIME (S3-ключ и метаданные согласованы)."""
        if Path(original_name).suffix:
            return original_name
        ext = mimetypes.guess_extension(content_type.strip(), strict=False)
        if ext and not original_name.endswith(ext):
            return f"{original_name}{ext}"
        return original_name

    async def process_file_from_bytes(
        self,
        data: bytes,
        original_name: str,
        content_type: str | None = None,
        uploaded_by: str | None = None,
        metadata: JsonObject | None = None,
        tags: list[str] | None = None,
        public: bool = False,
    ) -> FileRecord:
        """
        Обрабатывает файл из данных в памяти.

        Аргументы:
            data: Данные файла
            original_name: Оригинальное имя файла
            content_type: MIME тип
            uploaded_by: ID пользователя
            metadata: Дополнительные метаданные
            tags: Теги файла
            public: Сделать файл публичным

        Возвращает:
            Метаданные файла
        """
        file_id = f"file_{uuid.uuid4().hex[:12]}"

        if not content_type:
            content_type, _ = mimetypes.guess_type(original_name)
            if not content_type:
                content_type = "application/octet-stream"

        original_name = FileProcessor._original_name_with_extension_from_content_type(
            original_name, content_type
        )

        needs_ios, src_suffix = resolve_ios_transcode_source(
            content_type,
            original_name,
            data,
        )
        if needs_ios:
            data = await transcode_audio_bytes_to_m4a_aac(data, src_suffix)
            content_type = "audio/mp4"
            stem = Path(original_name).stem
            if stem == "" or stem == ".":
                stem = "voice"
            original_name = f"{stem}.m4a"

        file_hash = hashlib.sha256(data).hexdigest()[:16]
        extension = Path(original_name).suffix or ".bin"
        s3_key = f"files/{file_id}_{file_hash}{extension}"

        s3_client = await self.get_s3_client()

        s3_metadata = _to_ascii_s3_metadata(metadata or {})
        _ = await s3_client.upload_bytes(
            data=data,
            key=s3_key,
            metadata=s3_metadata,
            content_type=content_type,
            public=public,
        )

        file_record = FileRecord(
            file_id=file_id,
            provider=s3_client.provider_name,
            original_name=original_name,
            content_type=content_type,
            file_size=len(data),
            s3_bucket=s3_client.require_bucket_config_key(),
            s3_key=s3_key,
            s3_endpoint=s3_client.endpoint_url,
            uploaded_by=uploaded_by,
            is_public=public,
            status=FileStatus.READY,
            metadata=metadata or {},
            tags=tags or [],
        )

        _ = await self.file_repository.set(file_record)

        logger.info(f"Файл обработан: {file_id} ({original_name}, {len(data)} байт)")
        return file_record

    async def persist_uploaded_file(
        self,
        *,
        data: bytes,
        original_name: str,
        content_type: str,
        uploaded_by: str | None,
        company_id: str,
        public: bool,
        download_url_prefix: str,
        content_sha256_hex: str | None = None,
        metadata: JsonObject | None = None,
        tags: list[str] | None = None,
    ) -> FileRecord:
        """
        Один путь для «байты с клиента или воркера → S3 + FileRecord»: process_file_from_bytes,
        затем company_id, same-origin download_url и при необходимости checksum (как POST .../files/).
        """
        file_record = await self.process_file_from_bytes(
            data=data,
            original_name=original_name,
            content_type=content_type,
            uploaded_by=uploaded_by,
            metadata=metadata,
            tags=tags,
            public=public,
        )
        prefix = download_url_prefix.rstrip("/")
        file_record.company_id = company_id
        file_record.download_url = f"{prefix}/{file_record.file_id}"
        if content_sha256_hex is not None:
            file_record.checksum = content_sha256_hex
        _ = await self.file_repository.set(file_record)
        return file_record

    async def persist_uploaded_file_as_file_ref(
        self,
        *,
        data: bytes,
        original_name: str,
        content_type: str,
        uploaded_by: str | None,
        company_id: str,
        public: bool,
        download_url_prefix: str,
        content_sha256_hex: str | None = None,
        metadata: JsonObject | None = None,
        tags: list[str] | None = None,
    ) -> FileRef:
        """
        Байты с клиента → S3 + FileRecord + канонический FileRef для runtime state.
        """
        effective_type = content_type.strip()
        if not effective_type:
            raise ValueError("content_type обязателен для FileRef")
        record = await self.persist_uploaded_file(
            data=data,
            original_name=original_name,
            content_type=effective_type,
            uploaded_by=uploaded_by,
            company_id=company_id,
            public=public,
            download_url_prefix=download_url_prefix,
            content_sha256_hex=content_sha256_hex,
            metadata=metadata,
            tags=tags,
        )
        prefix = download_url_prefix.rstrip("/")
        url = record.download_url if record.download_url else f"{prefix}/{record.file_id}"
        return FileRef(
            file_id=record.file_id,
            original_name=record.original_name,
            url=url,
            content_type=record.content_type,
            file_size=record.file_size,
            checksum=record.checksum,
            is_public=record.is_public,
        )

    async def get_file_record(self, file_id: str) -> FileRecord | None:
        """
        Получает запись о файле.

        Аргументы:
            file_id: ID файла

        Возвращает:
            Запись о файле или None
        """
        return await self.file_repository.get(file_id)

    async def delete_file(self, file_id: str) -> bool:
        """
        Удаляет файл из S3 и БД.

        Аргументы:
            file_id: ID файла

        Возвращает:
            True если удаление успешно
        """
        file_record = await self.get_file_record(file_id)
        if not file_record:
            logger.warning(f"Файл {file_id} не найден в БД")
            return False

        s3_client = S3ClientFactory.create_client_for_bucket(file_record.s3_bucket)
        try:
            _ = await s3_client.delete_file(file_record.s3_key)
        finally:
            await s3_client.close()

        _ = await self.file_repository.delete(file_id)

        logger.info(f"Файл удален: {file_id}")
        return True

    def format_file_message(self, file_record: FileRecord) -> str:
        """
        Форматирует сообщение о файле для агента.

        Аргументы:
            file_record: Запись о файле

        Возвращает:
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
    def extract_file_info_from_message(message_content: str) -> list[JsonObject]:
        """
        Извлекает информацию о файлах из текста сообщения.

        Аргументы:
            message_content: Текст сообщения

        Возвращает:
            Список словарей с информацией о файлах (ключи: original_name, file_id, url, content_type, file_size)
        """
        file_info_list: list[JsonObject] = []

        for match in FILE_MESSAGE_RE.finditer(message_content):
            file_info_list.append({
                "original_name": match.group(1).strip(),
                "file_id": match.group(2).strip(),
                "url": match.group(3).strip(),
                "content_type": match.group(4).strip(),
                "file_size": match.group(5).strip(),
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
        bucket_name: str | None = None,
    ) -> None:
        self.file_repository: FileRepository = file_repository
        self.bucket_name: str | None = bucket_name
        self._s3_client: S3Client | None = None

    async def get_s3_client(self) -> S3Client:
        if self._s3_client is None:
            if self.bucket_name:
                self._s3_client = S3ClientFactory.create_client_for_bucket(self.bucket_name)
            else:
                self._s3_client = S3ClientFactory.create_default_client()
        return self._s3_client

    async def close(self) -> None:
        if self._s3_client:
            await self._s3_client.close()
            self._s3_client = None

    async def process_audio_from_bytes(
        self,
        data: bytes,
        original_name: str,
        content_type: str = "audio/wave",
        uploaded_by: str | None = None,
        auto_recognize: bool = True,
        language: str | None = None,
        metadata: JsonObject | None = None,
        tags: list[str] | None = None,
        public: bool = True,
    ) -> AudioRecord:
        """Загружает аудио в S3 и при auto_recognize транскрибирует через MediaTranscriber."""
        logger.info("Обработка аудио: %s, размер=%s байт", original_name, len(data))

        file_id = f"file_{uuid.uuid4().hex[:12]}"
        file_hash = hashlib.sha256(data).hexdigest()[:16]
        extension = Path(original_name).suffix or ".wav"
        s3_key = f"audio/{file_id}_{file_hash}{extension}"

        s3_client = await self.get_s3_client()

        _ = await s3_client.upload_bytes(
            data=data,
            key=s3_key,
            metadata=_to_ascii_s3_metadata(metadata or {}),
            content_type=content_type,
            public=public,
        )

        transcription_text = None
        transcription_status = AudioTranscriptionStatus.IDLE
        transcription_error: str | None = None
        transcription_provider: str | None = None

        if auto_recognize:
            company_id = require_active_company().company_id
            if company_id == "":
                raise ValueError(
                    "process_audio_from_bytes: активная компания в контексте обязательна для auto_recognize."
                )
            transcriber = MediaTranscriber(company_id=company_id)
            transcription_result = await transcriber.transcribe_audio(
                audio_bytes=data,
                file_name=original_name,
                content_type=content_type,
                language=language,
            )
            transcription_text = transcription_result.text
            transcription_status = AudioTranscriptionStatus.DONE
            transcription_provider = transcription_result.provider

        audio_record = AudioRecord(
            file_id=file_id,
            provider=s3_client.provider_name,
            original_name=original_name,
            content_type=content_type,
            file_size=len(data),
            s3_bucket=s3_client.require_bucket_config_key(),
            s3_key=s3_key,
            s3_endpoint=s3_client.endpoint_url,
            uploaded_by=uploaded_by,
            status=FileStatus.READY,
            metadata=metadata or {},
            tags=tags or [],
            transcription_status=transcription_status,
            transcription_text=transcription_text,
            transcription_error=transcription_error,
            transcription_provider=transcription_provider,
        )

        _ = await self.file_repository.set(audio_record)
        logger.info("Аудио обработано: %s", file_id)
        return audio_record

    async def get_audio_record(self, audio_id: str) -> AudioRecord | None:
        record = await self.file_repository.get(audio_id)
        if record is None:
            return None
        if isinstance(record, AudioRecord):
            return record
        return AudioRecord.model_validate(record.model_dump(mode="json"))

_default_file_processor: FileProcessor | None = None
_default_audio_processor: AudioProcessor | None = None
_default_file_repository: FileRepository | None = None

def initialize_default_processors(file_repository: FileRepository) -> None:
    """
    Инициализирует дефолтные процессоры с заданным file_repository.
    Вызывается при старте приложения в lifespan.

    Аргументы:
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
                + "Вызовите initialize_default_processors(file_repository) при старте приложения."
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
                + "Вызовите initialize_default_processors(file_repository) при старте приложения."
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
