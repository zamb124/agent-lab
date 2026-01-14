"""
Модели для работы с файлами (shared между всеми сервисами).

ВАЖНО: Это shared модели - используются всеми сервисами через shared БД.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from enum import Enum


class CloudVoiceTokenConfig(BaseModel):
    """Конфигурация токенов Cloud Voice API"""
    
    client_id: str = Field(description="Идентификатор клиента Cloud Voice API")
    access_token: str = Field(description="Токен доступа к API")
    refresh_token: str = Field(description="Токен для обновления access_token")
    expires_at: datetime = Field(description="Время когда истекает access_token")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Время создания токена"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Время последнего обновления токена"
    )
    
    def is_expired(self) -> bool:
        """Проверяет истек ли access_token"""
        return datetime.now(timezone.utc) >= self.expires_at
    
    def is_refresh_expired(self, refresh_ttl_days: int = 30) -> bool:
        """Проверяет истек ли refresh_token"""
        refresh_expires_at = self.created_at + timedelta(days=refresh_ttl_days)
        return datetime.now(timezone.utc) >= refresh_expires_at


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
    def direct_s3_url(self) -> Optional[str]:
        """Прямой S3 URL для доступа к файлу"""
        if not self.s3_endpoint or not self.s3_bucket or not self.s3_key:
            return None

        endpoint = self.s3_endpoint.rstrip('/')
        return f"{endpoint}/{self.s3_bucket}/{self.s3_key}"

    @property
    def url(self) -> str:
        """Прокси URL для доступа к файлу через API (для контроля доступа)"""
        return f"/api/v1/files/download/{self.file_id}"

    @property
    def audio_id(self) -> str:
        """Алиас для file_id для обратной совместимости с AudioRecord"""
        return self.file_id


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
        description="ID запроса к сервису распознавания речи"
    )


FileMetadata = FileRecord
AudioMetadata = AudioRecord
