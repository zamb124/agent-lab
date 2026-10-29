"""
Модели для работы с файлами (shared между всеми сервисами).

ВАЖНО: Это shared модели - используются всеми сервисами через shared БД.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from oxyde import Index as OxydeIndex
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
        indexes: list[OxydeIndex] = [
            OxydeIndex(
                ["catalog_id", "name_key"],
                unique=True,
                where="deleted_at IS NULL AND catalog_id IS NOT NULL",
            ),
        ]

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
    source_kind: str = DbField(default="", max_length=64, db_index=True, description="FileSourceKind записи")
    catalog_id: str | None = DbField(
        default=None,
        max_length=64,
        db_index=True,
        description="Каталог Документов; NULL только у exempt-источников",
    )
    name_key: str | None = DbField(
        default=None,
        max_length=255,
        description="NFC casefold original_name для уникальности в каталоге",
    )
    deleted_at: datetime | None = DbField(default=None, description="Корзина Документов")
    deleted_by_user_id: str | None = DbField(default=None, max_length=100)
    authz_synced_at: datetime | None = DbField(default=None)
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
    async def list_unordered_expired(cls, *, before: datetime, limit: int) -> list[Self]:
        """Живые файлы с expires_at не позже before и статусом не DELETED. Порядка нет. Не больше limit."""
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
    async def list_unordered_missing_retention(cls, *, limit: int) -> list[Self]:
        """Живые файлы не DELETED без retention_kind либо с пустым expires_at при конечном виде хранения. Порядка нет. Не больше limit."""
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
    async def list_alive_for_storage_by_file_id_after_asc(
        cls,
        storage_id: str,
        *,
        after_file_id: str | None,
        limit: int,
    ) -> list[Self]:
        """Живые файлы хранилища, не DELETED, ORDER BY file_id ASC, не больше limit. after_file_id is None или пустая строка не фильтрует. limit в теле не проверяется."""
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

    @classmethod
    async def claim_content_replace(
        cls,
        file_id: str,
        *,
        expected_checksum: str | None,
        s3_key: str,
        file_size: int,
        checksum: str,
    ) -> bool:
        query = cls.objects.filter(file_id=file_id, checksum=expected_checksum)
        affected = await query.update(s3_key=s3_key, file_size=file_size, checksum=checksum)
        return affected == 1

    @classmethod
    async def list_pending_authz_with_catalog_by_created_at_asc(cls, *, limit: int) -> list[Self]:
        """Файлы с пустым authz_synced_at и непустым catalog_id, ORDER BY created_at ASC, не больше limit."""
        return await (
            cls.objects.filter(authz_synced_at__isnull=True, catalog_id__isnull=False)
            .order_by("created_at")
            .limit(limit)
            .all()
        )

    @classmethod
    async def list_alive_in_catalog_by_updated_at_desc(cls, *, company_id: str, catalog_id: str) -> list[Self]:
        """Живые файлы каталога, ORDER BY updated_at DESC. Предела нет. Пустые поля не проверяются."""
        return await (
            cls.objects.filter(company_id=company_id, catalog_id=catalog_id, deleted_at__isnull=True)
            .order_by("-updated_at")
            .all()
        )

    @classmethod
    async def count_in_catalog(cls, catalog_id: str) -> int:
        return await cls.objects.filter(catalog_id=catalog_id, deleted_at__isnull=True).count()

    @classmethod
    async def count_held_in_catalog(cls, catalog_id: str) -> int:
        return await cls.objects.filter(catalog_id=catalog_id).count()

    @classmethod
    async def by_file_id(cls, file_id: str, company_id: str) -> Self | None:
        """Строка по file_id в компании. Нет строки — None. Пустые идентификаторы не проверяются."""
        return await cls.objects.filter(file_id=file_id, company_id=company_id).get_or_none()

    @classmethod
    async def count_alive(cls, company_id: str) -> int:
        return await cls.objects.filter(company_id=company_id, deleted_at__isnull=True, catalog_id__isnull=False).count()

    @classmethod
    async def list_alive_matching_original_name_by_updated_at_desc(
        cls,
        company_id: str,
        catalog_ids: list[str],
        title_query: str,
        limit: int,
    ) -> list[Self]:
        """Живые файлы компании в каталогах, у которых original_name содержит title_query. Порядок — updated_at по убыванию, не больше limit. Пустой список каталогов — []."""
        if not catalog_ids:
            return []
        return await (
            cls.objects.filter(
                company_id=company_id,
                catalog_id__in=catalog_ids,
                deleted_at__isnull=True,
                original_name__icontains=title_query,
            )
            .order_by("-updated_at")
            .limit(limit)
            .all()
        )

    @classmethod
    async def list_with_catalog_by_original_name_asc(cls, company_id: str, query: str, limit: int) -> list[Self]:
        """Живые файлы компании с каталогом по возрастанию original_name, не больше limit. Пустой query не фильтрует имя."""
        rows = cls.objects.filter(company_id=company_id, deleted_at__isnull=True, catalog_id__isnull=False)
        if query != "":
            rows = rows.filter(original_name__icontains=query)
        return await rows.order_by("original_name").limit(limit).all()

    @classmethod
    async def mark_trashed(cls, record: Self, *, user_id: str, deleted_at: datetime) -> Self:
        record.deleted_at = deleted_at
        record.deleted_by_user_id = user_id
        _ = await record.save()
        return record

    @classmethod
    async def clear_trash(cls, record: Self) -> Self:
        record.deleted_at = None
        record.deleted_by_user_id = None
        _ = await record.save()
        return record

    @classmethod
    async def trashed_in_catalog(cls, catalog_id: str) -> list[Self]:
        return await cls.objects.filter(
            catalog_id=catalog_id,
            deleted_at__isnull=False,
        ).all()

    @classmethod
    async def trashed_in_namespace_by_deleted_at_desc(cls, company_id: str, namespace_catalog_ids: list[str]) -> list[Self]:
        """Файлы namespace в корзине, ORDER BY deleted_at DESC. Предела нет. Пустой namespace_catalog_ids — []."""
        if not namespace_catalog_ids:
            return []
        return await (
            cls.objects.filter(
                company_id=company_id,
                catalog_id__in=namespace_catalog_ids,
                deleted_at__isnull=False,
            )
            .order_by("-deleted_at")
            .all()
        )

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


