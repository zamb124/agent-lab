"""Модели файлов для Sync API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FileRead(BaseModel):
    """Файл, сохранённый в системе."""

    id: str = Field(description="Идентификатор файла.")
    original_name: str = Field(description="Оригинальное имя файла.")
    mime_type: str = Field(description="MIME-тип файла.")
    size_bytes: int = Field(description="Размер файла в байтах.")
    storage_url: str = Field(description="URL в хранилище (S3/MinIO и т.п.).")
    checksum: str | None = Field(
        default=None,
        description="Контрольная сумма содержимого файла.",
    )
    created_at: datetime = Field(description="Время загрузки файла.")


class FileUploadResponse(BaseModel):
    """Ответ API на успешную загрузку файла."""

    file: FileRead = Field(description="Информация о загруженном файле.")


class FileLink(BaseModel):
    """Ссылка на файл, вложенный в сообщение."""

    file_id: str = Field(description="Идентификатор файла.")
    role: str = Field(
        default="attachment",
        description="Роль файла в контексте сообщения (attachment/preview/etc).",
    )
