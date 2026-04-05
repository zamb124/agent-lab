"""Единая схема результата чтения файла (FileReadResult)."""

from __future__ import annotations

from enum import StrEnum
from typing import List, Optional

from pydantic import BaseModel, Field


class FileReadKind(StrEnum):
    TEXT = "text"
    PDF = "pdf"
    OFFICE = "office"
    SPREADSHEET = "spreadsheet"
    IMAGE = "image"
    UNKNOWN = "unknown"


class ReadAssetKind(StrEnum):
    EMBEDDED_IMAGE = "embedded_image"
    PAGE_RASTER = "page_raster"
    ATTACHMENT = "attachment"


class ReadAsset(BaseModel):
    kind: ReadAssetKind
    mime_type: Optional[str] = None
    checksum: str = Field(description="SHA-256 hex сырых байт фрагмента")
    file_id: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    bytes_b64: Optional[str] = Field(
        default=None,
        description="Base64 только при ReadOptions.include_asset_bytes=True",
    )


class ReadPage(BaseModel):
    index: int = Field(ge=0)
    label: Optional[str] = None
    text: str = ""
    assets: List[ReadAsset] = Field(default_factory=list)


class FileReadResult(BaseModel):
    file_name: str
    mime_type: Optional[str] = None
    detected_kind: FileReadKind
    page_count: int = Field(ge=0)
    pages: List[ReadPage] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    source_file_id: Optional[str] = None
    source_checksum: Optional[str] = Field(
        default=None,
        description="SHA-256 hex всего исходного файла",
    )


class ReadOptions(BaseModel):
    include_asset_bytes: bool = False
    source_file_id: Optional[str] = None
    source_checksum: Optional[str] = None
    vision_model: str = "google/gemini-2.5-flash-preview"
    vision_prompt: Optional[str] = Field(
        default=None,
        description="Текст инструкции для vision-модели при разборе изображений; иначе встроенный промпт извлечения текста.",
    )


class FileTypeInfo(BaseModel):
    detected_kind: FileReadKind
    mime_type: Optional[str] = None
    extension: str = ""
