"""
Модели для работы с файлами (shared между всеми сервисами).

ВАЖНО: Это shared модели - используются всеми сервисами через shared БД.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from oxyde import Q
from pydantic import BaseModel, Field, SerializerFunctionWrapHandler, model_serializer

from core.files.retention import FileRetentionKind, FileRetentionSpec, resolve_retention_ttl_seconds
from core.files.urls import files_download_url
from core.models.platform_model import PlatformModel
from core.types import JsonObject, require_serializer_json_object


class FileStatus(str, Enum):
    """Статус файла"""

    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class AudioTranscriptionStatus(str, Enum):
    """Канонический статус транскрипции аудио."""

    IDLE = "idle"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


STT_FAILED_ERROR_CODE = "stt_failed"


class FileRecord(PlatformModel):
    """Файл. Глобальная таблица ``files`` в ``platform_shared``.

    Доступ к байтам проверяет ``FileGate`` по принципалу, не менеджер.
    ``s3_key`` и ``storage_id`` пишутся в таблицу и не попадают в JSON ответа.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    file_id: str = DbField(db_pk=True, description="Уникальный ID файла в системе")

    class Meta:
        is_table: bool = True
        table_name: str = "files"

    original_name: str = DbField(db_type="TEXT", description="Оригинальное имя файла")
    s3_key: str = DbField(db_type="TEXT", description="Ключ файла в S3")
    storage_id: str = DbField(
        db_index=True,
        description="Хранилище байтов: platform или storage_id компании",
    )
    storage_url: str | None = DbField(
        default=None,
        db_type="TEXT",
        description="Прямой URL источника файла для proxy-download",
    )
    content_type: str = DbField(db_type="TEXT", description="MIME тип файла")
    file_size: int = DbField(description="Размер файла в байтах")
    checksum: str | None = DbField(
        default=None,
        description="SHA-256 hex содержимого файла (как при upload в core.files.api)",
    )
    status: FileStatus = DbField(default=FileStatus.UPLOADING, db_index=True, description="Статус файла")
    uploaded_by: str | None = DbField(default=None, description="ID пользователя который загрузил")
    company_id: str | None = DbField(default=None, db_index=True, description="ID компании владельца файла")
    metadata: JsonObject = DbField(default_factory=dict, description="Дополнительные метаданные файла")
    tags: list[str] = DbField(default_factory=list, description="Теги для категоризации")
    is_public: bool = DbField(default=False, description="Доступен ли файл без авторизации")
    download_url: str | None = DbField(
        default=None,
        db_type="TEXT",
        description=(
            "Same-origin download URL сервиса, который создал FileRecord "
            "(`/{segment}/api/v1/files/download/{file_id}`)."
        ),
    )
    created_at: datetime = DbField(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Время создания файла",
    )
    updated_at: datetime = DbField(
        default_factory=lambda: datetime.now(timezone.utc),
        db_index=True,
        description="Время обновления файла",
    )
    deleted_at: datetime | None = DbField(default=None, description="Время удаления файла")
    retention_kind: str | None = DbField(
        default=None,
        description="Канонический FileRetentionKind для audit и purge",
    )
    expires_at: datetime | None = DbField(
        default=None,
        db_index=True,
        description="None только для permanent (ttl_seconds=0)",
    )
    duration_ms: int | None = DbField(default=None, description="Длительность аудио в миллисекундах")
    language: str | None = DbField(default=None, description="Язык аудио (ru, en, ...)")
    sample_rate: int | None = DbField(default=None, description="Частота дискретизации в Гц")
    channels: int | None = DbField(default=None, description="Количество аудио каналов (1, 2)")
    audio_format: str | None = DbField(default=None, description="Формат аудио (mp3, wav, ogg)")
    transcription_status: AudioTranscriptionStatus = DbField(
        default=AudioTranscriptionStatus.IDLE,
        description="Текущий статус расшифровки аудио.",
    )
    transcription_text: str | None = DbField(default=None, db_type="TEXT", description="Результат распознавания речи.")
    transcription_error: str | None = DbField(default=None, db_type="TEXT", description="Текст ошибки расшифровки.")
    transcription_provider: str | None = DbField(
        default=None,
        description="Идентификатор STT-провайдера, обработавшего аудио.",
    )

    @classmethod
    async def list_expired(cls, *, before: datetime, limit: int) -> list[Self]:
        return await (
            cls.objects.filter(
                deleted_at__isnull=True,
                expires_at__isnull=False,
                expires_at__lte=before,
            )
            .exclude(status=FileStatus.DELETED)
            .limit(limit)
            .all()
        )

    @classmethod
    async def list_missing_retention(cls, *, limit: int) -> list[Self]:
        finite_kinds = [
            kind.value
            for kind in FileRetentionKind
            if resolve_retention_ttl_seconds(FileRetentionSpec(kind=kind)) > 0
        ]
        return await (
            cls.objects.filter(deleted_at__isnull=True)
            .exclude(status=FileStatus.DELETED)
            .filter(
                Q(retention_kind__isnull=True)
                | Q(expires_at__isnull=True, retention_kind__in=finite_kinds)
            )
            .limit(limit)
            .all()
        )

    @classmethod
    async def count_for_storage(cls, storage_id: str) -> int:
        return await (
            cls.objects.filter(storage_id=storage_id, deleted_at__isnull=True)
            .exclude(status=FileStatus.DELETED)
            .count()
        )

    @classmethod
    async def list_for_storage_after(
        cls,
        storage_id: str,
        *,
        after_file_id: str | None,
        limit: int,
    ) -> list[Self]:
        query = cls.objects.filter(storage_id=storage_id, deleted_at__isnull=True).exclude(
            status=FileStatus.DELETED
        )
        if after_file_id is not None and after_file_id != "":
            query = query.filter(file_id__gt=after_file_id)
        return await query.order_by("file_id").limit(limit).all()

    @classmethod
    async def claim_storage_move(
        cls,
        file_id: str,
        *,
        source_storage_id: str,
        target_storage_id: str,
        s3_key: str,
    ) -> bool:
        affected = await cls.objects.filter(
            file_id=file_id,
            storage_id=source_storage_id,
        ).update(storage_id=target_storage_id, s3_key=s3_key)
        return affected == 1

    @model_serializer(mode="wrap", when_used="json")
    def _json_without_storage_location(self, handler: SerializerFunctionWrapHandler) -> JsonObject:
        payload = require_serializer_json_object(handler, self, "FileRecord")
        for name in ("s3_key", "storage_id"):
            if name in payload:
                del payload[name]
        return payload

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = update_fields
        now = datetime.now(timezone.utc)
        if is_create and "created_at" not in self.model_fields_set:
            self.created_at = now
        self.updated_at = now

    @property
    def url(self) -> str:
        """
        Same-origin URL для доступа к файлу через Files API текущего или создавшего сервиса.

        Если `download_url` задан при создании — возвращает его.
        Иначе строит URL по `files_route_segment` процесса.
        """
        if self.download_url:
            return self.download_url
        return files_download_url(self.file_id)


class AudioAttachmentContent(BaseModel):
    """Канонический payload аудио-вложения для сообщений сервисов."""

    file_id: str = Field(description="Идентификатор файла в системе.")
    original_name: str = Field(description="Оригинальное имя файла.")
    content_type: str = Field(description="MIME-тип аудиофайла.")
    file_size: int = Field(description="Размер аудио в байтах.")
    duration_ms: int = Field(description="Длительность аудио в миллисекундах.")
    waveform: list[int] | None = Field(
        default=None,
        description="Опциональные значения амплитуды для визуализации волны.",
    )
    transcription_status: AudioTranscriptionStatus = Field(
        default=AudioTranscriptionStatus.IDLE,
        description="Текущий статус расшифровки аудио.",
    )
    transcription_text: str | None = Field(
        default=None,
        description="Результат распознавания речи.",
    )
    transcription_error: str | None = Field(
        default=None,
        description="Текст ошибки расшифровки.",
    )
    source_speech_to_chat: bool = Field(
        default=False,
        description="Сегмент с серверного speech-to-chat; авто-STT канала на сообщение не ставится.",
    )


class FileReadPreviewResponse(BaseModel):
    """Текстовое превью содержимого файла (извлечение без vision для изображений)."""

    text: str = Field(description="Извлечённый текст (может быть усечён для UI)")
    truncated: bool = Field(description="Усечён ли текст по лимиту превью")
    page_count: int = Field(default=0, description="Число страниц после чтения")
    detected_kind: str = Field(description="Тип файла по FileReader")
    content_type: str | None = Field(default=None, description="Content-Type после распознавания")
    warnings: list[str] = Field(default_factory=list, description="Предупреждения парсера")
    preview_note: str | None = Field(
        default=None,
        description="Пояснение для пользователя (например для изображений)",
    )


class VideoAttachmentContent(BaseModel):
    """Видеовложение в сообщении (запись звонка и т.п.)."""

    file_id: str = Field(description="Идентификатор файла в системе.")
    original_name: str = Field(description="Оригинальное имя файла.")
    content_type: str = Field(description="MIME-тип, например video/mp4.")
    file_size: int = Field(description="Размер файла в байтах.")
    duration_ms: int | None = Field(
        default=None,
        description="Длительность в миллисекундах, если известна.",
    )
    transcription_status: AudioTranscriptionStatus = Field(
        default=AudioTranscriptionStatus.IDLE,
        description="Статус расшифровки аудиодорожки.",
    )
    transcription_text: str | None = Field(
        default=None,
        description="Результат распознавания речи.",
    )
    transcription_error: str | None = Field(
        default=None,
        description="Текст ошибки расшифровки.",
    )


