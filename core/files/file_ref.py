"""
Каноническая ссылка на файл в runtime state.

`FileRef` — единственная форма элемента `ExecutionState.files`: файл либо уже лежит
в платформенном хранилище (`file_id`), либо доступен по внешнему/локальному `url`.
"""

from __future__ import annotations

import re
from typing import Literal, TypeAlias

from pydantic import Field, model_validator

from core.files.models import FileRecord, FileResponse
from core.models import StrictBaseModel
from core.types import JsonObject, require_json_object

DOWNLOAD_FILE_ID_RE = re.compile(r"/files/download/([^/?#]+)")


def file_id_from_download_url(url: str) -> str | None:
    match = DOWNLOAD_FILE_ID_RE.search(url.strip())
    return match.group(1) if match else None


class FileDocumentCapability(StrictBaseModel):
    """OnlyOffice document binding attached to a FileRef."""

    kind: Literal["onlyoffice"] = "onlyoffice"
    binding_id: str = Field(min_length=1)
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
    capabilities: FileCapabilities = Field(default_factory=FileCapabilities)

    @model_validator(mode="before")
    @classmethod
    def accept_file_storage_models(cls, value: object) -> object:
        if isinstance(value, FileRecord):
            return {
                "file_id": value.file_id,
                "original_name": value.original_name,
                "url": value.url,
                "content_type": value.content_type,
                "file_size": value.file_size,
                "checksum": value.checksum,
                "is_public": value.is_public,
            }
        if isinstance(value, FileResponse):
            return {
                "file_id": value.file_id,
                "original_name": value.original_name,
                "url": value.url,
                "content_type": value.content_type,
                "file_size": value.file_size,
                "checksum": value.checksum,
                "is_public": value.is_public,
            }
        return value

    @model_validator(mode="after")
    def require_resolvable_source(self) -> "FileRef":
        if self.file_id is None and self.url is None:
            raise ValueError("FileRef должен содержать file_id или url")
        return self

    @classmethod
    def from_record(cls, record: FileRecord) -> "FileRef":
        return cls.model_validate(record)

    @classmethod
    def from_response(cls, response: FileResponse) -> "FileRef":
        return cls.model_validate(response)

    def to_json_object(self) -> JsonObject:
        return require_json_object(
            self.model_dump(mode="json", exclude_none=True),
            "FileRef",
        )


FileRefSource: TypeAlias = FileRef | FileRecord | FileResponse | JsonObject

__all__ = [
    "DOWNLOAD_FILE_ID_RE",
    "FileCapabilities",
    "FileDocumentCapability",
    "FileRef",
    "FileRefSource",
    "file_id_from_download_url",
]
