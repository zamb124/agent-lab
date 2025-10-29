"""
Модели для файлов и аудио.
"""

from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime, timezone, timedelta

from ..fields import Field


class CloudVoiceTokenConfig(BaseModel):
    """Конфигурация токенов Cloud Voice API"""
    
    client_id: str = Field(
        title="Client ID",
        description="Идентификатор клиента Cloud Voice API"
    )
    access_token: str = Field(
        title="Access Token",
        description="Токен доступа к API"
    )
    refresh_token: str = Field(
        title="Refresh Token", 
        description="Токен для обновления access_token"
    )
    expires_at: datetime = Field(
        title="Время истечения",
        description="Время когда истекает access_token"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Время создания",
        description="Время создания токена"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Время обновления",
        description="Время последнего обновления токена"
    )
    
    def is_expired(self) -> bool:
        """Проверяет истек ли access_token"""
        return datetime.now(timezone.utc) >= self.expires_at
    
    def is_refresh_expired(self, refresh_ttl_days: int = 30) -> bool:
        """Проверяет истек ли refresh_token (по умолчанию 30 дней)"""
        refresh_expires_at = self.created_at + timedelta(days=refresh_ttl_days)
        return datetime.now(timezone.utc) >= refresh_expires_at


class FileStatus(str, Enum):
    """Статус файла"""

    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    FAILED = "failed"
    DELETED = "deleted"


class FileRecord(BaseModel):
    """Запись о файле в системе"""

    file_id: str = Field(
        title="ID файла", description="Уникальный ID файла в системе", readonly=True
    )
    provider: str = Field(
        title="Провайдер",
        description="Провайдер S3 (aws, yandex, minio, etc.)",
    )
    original_name: str = Field(
        title="Оригинальное имя", description="Оригинальное имя файла"
    )
    s3_key: str = Field(title="Ключ S3", description="Ключ файла в S3", readonly=True)
    s3_bucket: str = Field(title="Bucket S3", description="Bucket в S3", readonly=True)
    s3_endpoint: Optional[str] = Field(
        default=None,
        title="Endpoint S3",
        description="Endpoint URL провайдера",
        readonly=True,
    )
    content_type: str = Field(
        title="Тип содержимого", description="MIME тип файла", readonly=True
    )
    file_size: int = Field(
        title="Размер файла", description="Размер файла в байтах", readonly=True
    )
    checksum: Optional[str] = Field(
        default=None,
        title="Контрольная сумма",
        description="MD5 или другая контрольная сумма",
        readonly=True,
    )
    status: FileStatus = Field(
        default=FileStatus.UPLOADING,
        title="Статус",
        description="Статус файла",
        readonly=True,
    )
    uploaded_by: Optional[str] = Field(
        default=None,
        title="Загрузил",
        description="ID пользователя который загрузил",
        readonly=True,
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        title="Метаданные",
        description="Дополнительные метаданные файла",
    )
    tags: List[str] = Field(
        default_factory=list,
        title="Теги",
        description="Теги для категоризации",
    )
    is_public: bool = Field(
        default=False,
        title="Публичный",
        description="Доступен ли файл без авторизации",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создан",
        description="Время создания файла",
        readonly=True,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Обновлен",
        description="Время обновления файла",
        readonly=True,
    )

    @property
    def key(self) -> str:
        """Ключ для хранения в БД"""
        return f"s3:{self.provider}:{self.file_id}"

    @property
    def url(self) -> Optional[str]:
        """URL для скачивания файла через нашу платформу"""
        if not self.file_id:
            return None

        from app.core.context import get_context
        from app.core.config import settings
        
        context = get_context()
        subdomain = context.active_company.subdomain if context and context.active_company else None
        
        # Для локального окружения используем localhost с поддоменом
        if settings.server.env in ("local", "development"):
            protocol = "http"
            if subdomain:
                host = f"{subdomain}.localhost:{settings.server.port}"
            else:
                host = f"localhost:{settings.server.port}"
            return f"{protocol}://{host}/api/v1/files/download/{self.file_id}"
        
        # Для продакшн используем домен с поддоменом
        if subdomain:
            return f"https://{subdomain}.{settings.server.domain}/api/v1/files/download/{self.file_id}"
        else:
            return f"https://{settings.server.domain}/api/v1/files/download/{self.file_id}"

    @property
    def direct_s3_url(self) -> Optional[str]:
        """Прямой S3 URL для доступа к файлу"""
        if not self.s3_endpoint or not self.s3_bucket or not self.s3_key:
            return None

        endpoint = self.s3_endpoint.rstrip('/')
        return f"{endpoint}/{self.s3_bucket}/{self.s3_key}"

    @property
    def audio_id(self) -> str:
        """Алиас для file_id для обратной совместимости с AudioRecord"""
        return self.file_id


class AudioRecord(FileRecord):
    """Запись об аудиофайле"""

    duration: Optional[float] = Field(
        default=None,
        title="Длительность",
        description="Длительность аудио в секундах",
    )
    transcription: Optional[str] = Field(
        default=None,
        title="Транскрипция",
        description="Текстовая расшифровка аудио",
    )
    language: Optional[str] = Field(
        default=None, title="Язык", description="Язык аудио (ru, en, ...)"
    )
    sample_rate: Optional[int] = Field(
        default=None,
        title="Частота дискретизации",
        description="Частота дискретизации в Гц",
    )
    channels: Optional[int] = Field(
        default=None, title="Каналы", description="Количество аудио каналов (1, 2)"
    )
    audio_format: Optional[str] = Field(
        default=None, title="Формат", description="Формат аудио (mp3, wav, ogg)"
    )
    recognition_text: Optional[str] = Field(
        default=None,
        title="Распознанный текст",
        description="Текст, распознанный из аудио"
    )
    recognition_confidence: Optional[float] = Field(
        default=None,
        title="Уверенность распознавания",
        description="Уверенность в правильности распознавания (0.0-1.0)"
    )
    recognition_qid: Optional[str] = Field(
        default=None,
        title="ID запроса распознавания",
        description="ID запроса к сервису распознавания речи для отладки"
    )

