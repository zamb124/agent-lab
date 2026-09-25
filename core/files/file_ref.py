"""
Каноническая ссылка на файл в runtime state.

`FileRef` — единственная форма элемента `ExecutionState.files`: файл либо уже лежит
в платформенном хранилище (`file_id`), либо доступен по внешнему/локальному `url`.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import Field, model_validator

from core.files.models import FileRecord
from core.files.urls import files_download_url
from core.models import StrictBaseModel
from core.types import JsonObject, require_json_object

DOWNLOAD_FILE_ID_RE = re.compile(r"/files/download/([^/?#]+)")


def file_id_from_download_url(url: str) -> str | None:
    match = DOWNLOAD_FILE_ID_RE.search(url.strip())
    return match.group(1) if match else None


class FileDocumentCapability(StrictBaseModel):
    """Documents library capability attached to a FileRef (keyed by file_id)."""

    kind: Literal["onlyoffice"] = "onlyoffice"
    file_id: str = Field(min_length=1)
    catalog_id: str = Field(min_length=1)
    document_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    editor_url: str = Field(min_length=1)
    editable: bool = True


class FileCapabilities(StrictBaseModel):
    """Typed capabilities attached to a FileRef."""

    document: FileDocumentCapability | None = None


class FileRef(StrictBaseModel):
    """Канонический элемент `ExecutionState.files`."""

    file_id: str | None = Field(default=None, min_length=1)
    original_name: str = Field(min_length=1)
    url: str | None = Field(default=None, min_length=1)
    content_type: str = Field(min_length=1)
    file_size: int = Field(ge=0)
    checksum: str | None = Field(default=None, min_length=1)
    is_public: bool | None = None
    created_at: datetime | None = None
    capabilities: FileCapabilities = Field(default_factory=FileCapabilities)

    @model_validator(mode="before")
    @classmethod
    def accept_stored_record(cls, value: object) -> object:
        if isinstance(value, FileRecord):
            return stored_file_ref(value).model_dump()
        return value

    @model_validator(mode="after")
    def require_resolvable_source(self) -> "FileRef":
        if self.file_id is None and self.url is None:
            raise ValueError("FileRef must contain file_id or url")
        return self

    def to_json_object(self) -> JsonObject:
        return require_json_object(
            self.model_dump(mode="json", exclude_none=True),
            "FileRef",
        )


def format_a2a_files_content(files_data: list[FileRef]) -> str:
    """Append-only [FILE]...[/FILE] blocks for state.content / A2A text."""
    if not files_data:
        return ""

    parts: list[str] = []
    for file_ref in files_data:
        parts.append(
            "\n[FILE]\n"
            + f"original_name: {file_ref.original_name}\n"
            + f"url: {file_ref.url}\n"
            + f"content_type: {file_ref.content_type}\n"
            + "[/FILE]"
        )
    return "".join(parts)


def stored_file_ref(record: FileRecord, *, route_segment: str | None = None) -> FileRef:
    """Публичный FileRef из записи хранилища. s3_* в ответ не входят."""
    if record.download_url:
        url = record.download_url
    else:
        url = files_download_url(record.file_id, route_segment=route_segment)
    return FileRef(
        file_id=record.file_id,
        original_name=record.original_name,
        url=url,
        content_type=record.content_type,
        file_size=record.file_size,
        checksum=record.checksum,
        is_public=record.is_public,
        created_at=record.created_at,
    )


FileRefSource: TypeAlias = FileRef | FileRecord | JsonObject

__all__ = [
    "DOWNLOAD_FILE_ID_RE",
    "FileCapabilities",
    "FileDocumentCapability",
    "FileRef",
    "FileRefSource",
    "file_id_from_download_url",
    "format_a2a_files_content",
    "stored_file_ref",
]
