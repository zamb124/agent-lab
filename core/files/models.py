"""
Модели для работы с файлами (shared между всеми сервисами).

ВАЖНО: Это shared модели - используются всеми сервисами через shared БД.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum


class FileStatus(str, Enum):
    """Статус файла"""
    
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class FileRecord(BaseModel):
    """
    Запись о файле в системе (shared модель).
    Хранится в shared БД, доступна всем сервисам.
    """

    file_id: str = Field(description="Уникальный ID файла в системе")
    provider: str = Field(description="Провайдер S3 (aws, yandex, minio, etc.)")
    original_name: str = Field(description="Оригинальное имя файла")
    s3_key: str = Field(description="Ключ файла в S3")
    s3_bucket: str = Field(description="Bucket в S3")
    s3_endpoint: Optional[str] = Field(default=None, description="Endpoint URL провайдера")
    content_type: str = Field(description="MIME тип файла")
    file_size: int = Field(description="Размер файла в байтах")
    checksum: Optional[str] = Field(default=None, description="MD5 или другая контрольная сумма")
    status: FileStatus = Field(default=FileStatus.UPLOADING, description="Статус файла")
    uploaded_by: Optional[str] = Field(default=None, description="ID пользователя который загрузил")
    company_id: Optional[str] = Field(default=None, description="ID компании владельца файла")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Дополнительные метаданные файла")
    tags: List[str] = Field(default_factory=list, description="Теги для категоризации")
    is_public: bool = Field(default=False, description="Доступен ли файл без авторизации")
    download_url: Optional[str] = Field(
        default=None,
        description=(
            "Same-origin URL для скачивания через API (устанавливается сервисом при загрузке). "
            "Если не задан, используется /api/v1/files/download/{file_id}."
        ),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Время создания файла"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Время обновления файла"
    )
    deleted_at: Optional[datetime] = Field(default=None, description="Время удаления файла")

    @property
    def key(self) -> str:
        """Ключ для хранения в БД"""
        return f"s3:{self.provider}:{self.file_id}"

    @property
    def url(self) -> str:
        """
        Same-origin URL для доступа к файлу через API.

        Если сервис задал download_url при загрузке — возвращает его.
        Иначе возвращает путь agents-сервиса (для обратной совместимости).
        """
        if self.download_url:
            return self.download_url
        return f"/api/v1/files/download/{self.file_id}"

    @property
    def audio_id(self) -> str:
        """Алиас для file_id для обратной совместимости с AudioRecord"""
        return self.file_id


class FileResponse(BaseModel):
    """
    Публичное представление файла для API-ответов.

    Не содержит внутренних полей (s3_key, s3_bucket, s3_endpoint).
    Используется как return-тип всех file-эндпоинтов во всех сервисах.
    """

    file_id: str
    original_name: str
    content_type: str
    file_size: int
    url: str
    checksum: Optional[str] = None
    is_public: bool
    created_at: datetime

    @classmethod
    def from_record(cls, record: "FileRecord") -> "FileResponse":
        return cls(
            file_id=record.file_id,
            original_name=record.original_name,
            content_type=record.content_type,
            file_size=record.file_size,
            url=record.url,
            checksum=record.checksum,
            is_public=record.is_public,
            created_at=record.created_at,
        )


class AudioRecord(FileRecord):
    """
    Запись об аудиофайле (shared модель).
    Наследуется от FileRecord, добавляя специфичные для аудио поля.
    """

    duration: Optional[float] = Field(default=None, description="Длительность аудио в секундах")
    transcription: Optional[str] = Field(default=None, description="Текстовая расшифровка аудио")
    language: Optional[str] = Field(default=None, description="Язык аудио (ru, en, ...)")
    sample_rate: Optional[int] = Field(default=None, description="Частота дискретизации в Гц")
    channels: Optional[int] = Field(default=None, description="Количество аудио каналов (1, 2)")
    audio_format: Optional[str] = Field(default=None, description="Формат аудио (mp3, wav, ogg)")
    recognition_text: Optional[str] = Field(default=None, description="Текст, распознанный из аудио")
    recognition_confidence: Optional[float] = Field(
        default=None,
        description="Уверенность в правильности распознавания (0.0-1.0)"
    )
    recognition_qid: Optional[str] = Field(
        default=None,
        description="ID запроса к STT сервису"
    )


FileMetadata = FileRecord
AudioMetadata = AudioRecord
