"""Модели и опции для FileWriter."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ContentKind(str, Enum):
    """Распознанный вид входного содержимого (для режима auto)."""

    MARKDOWN = "markdown"
    BASE64 = "base64"
    RAW = "raw"


ContentMode = Literal["auto", "markdown", "base64", "raw"]


class WriteOptions(BaseModel):
    """Параметры записи и загрузки вложений по URL из markdown."""

    text_encoding: str = Field(default="utf-8", description="Кодировка для str в режиме raw")
    max_image_bytes: int = Field(
        default=15 * 1024 * 1024,
        ge=1,
        description="Максимальный размер одного изображения по HTTP",
    )
    http_timeout_seconds: float = Field(default=30.0, gt=0, description="Таймаут HTTP для картинок")
    pdf_max_image_width_pt: float = Field(default=400.0, gt=0, description="Макс. ширина картинки в PDF (pt)")
    docx_image_width_inches: float = Field(default=5.0, gt=0, description="Ширина вставки в DOCX (дюймы)")


class FileWriteResult(BaseModel):
    """Результат build_bytes до загрузки в S3."""

    data: bytes
    content_type: str
    conversion_applied: bool = Field(
        description="True если применялся markdown-пайплайн (не raw/base64 passthrough)"
    )
    checksum_sha256_hex: str = Field(description="SHA-256 hex содержимого data")
