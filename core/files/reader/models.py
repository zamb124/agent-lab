"""Единая схема результата чтения файла (FileReadResult)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from core.files.file_ref import FileRef, file_id_from_download_url


class FileReadKind(StrEnum):
    TEXT = "text"
    HTML = "html"
    PDF = "pdf"
    OFFICE = "office"
    SPREADSHEET = "spreadsheet"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    UNKNOWN = "unknown"


class ReadAssetKind(StrEnum):
    EMBEDDED_IMAGE = "embedded_image"
    PAGE_RASTER = "page_raster"
    ATTACHMENT = "attachment"


class ReadAsset(BaseModel):
    kind: ReadAssetKind
    content_type: str | None = None
    checksum: str = Field(description="SHA-256 hex сырых байт фрагмента")
    file_id: str | None = None
    width: int | None = None
    height: int | None = None
    bytes_b64: str | None = Field(
        default=None,
        description="Base64 только при ReadOptions.include_asset_bytes=True",
    )


class ReadPage(BaseModel):
    index: int = Field(ge=0)
    label: str | None = None
    text: str = ""
    assets: list[ReadAsset] = Field(default_factory=list)


class FileReadResult(BaseModel):
    file_name: str
    content_type: str | None = None
    detected_kind: FileReadKind
    page_count: int = Field(ge=0)
    pages: list[ReadPage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_file_id: str | None = None
    source_checksum: str | None = Field(
        default=None,
        description="SHA-256 hex всего исходного файла",
    )


class ReadOptions(BaseModel):
    include_asset_bytes: bool = False
    source_file_id: str | None = None
    source_checksum: str | None = None
    vision_model: str | None = None
    vision_prompt: str | None = Field(
        default=None,
        description="Текст инструкции для vision-модели при разборе изображений; иначе встроенный промпт извлечения текста.",
    )
    transcription_company_id: str | None = Field(
        default=None,
        description=(
            "company_id для tier-резолва STT при чтении audio/video; "
            "если None — из активного платформенного контекста."
        ),
    )


def merge_file_ref_read_options(
    file_ref: FileRef,
    opts: ReadOptions,
) -> ReadOptions:
    if isinstance(opts.source_file_id, str) and opts.source_file_id.strip():
        return opts
    if file_ref.file_id is not None:
        return opts.model_copy(update={"source_file_id": file_ref.file_id})
    if file_ref.url is not None:
        parsed = file_id_from_download_url(file_ref.url)
        if parsed:
            return opts.model_copy(update={"source_file_id": parsed})
    return opts


class FileTypeInfo(BaseModel):
    detected_kind: FileReadKind
    content_type: str | None = None
    extension: str = ""
