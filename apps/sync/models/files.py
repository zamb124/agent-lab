"""Файл Sync: метаданные ``sync_files`` и ссылка вложения в сообщении."""

from datetime import UTC, datetime
from typing import ClassVar

from oxyde import Field as DbField
from oxyde import Index
from pydantic import BaseModel, Field

from core.models.platform_model import PlatformModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SyncFile(PlatformModel):
    """Строка ``sync_files``, алиас ``sync``, ``__global_model__``.

    Байты живут в платформенном ``FileRecord``. Эта строка нужна внешним ключам
    записи звонка и вложения сообщения.
    """

    __database_alias__: ClassVar[str | None] = "sync"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "sync_files"
        indexes: list[Index] = [
            Index(["company_id"]),
        ]

    file_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    original_name: str = DbField(max_length=255)
    content_type: str = DbField(max_length=255)
    file_size: int
    created_at: datetime = DbField(default_factory=_utcnow)
    storage_url: str | None = DbField(default=None, db_type="TEXT")
    checksum: str | None = DbField(default=None, max_length=128)


class FileLink(BaseModel):
    """Ссылка на файл, вложенный в сообщение."""

    file_id: str = Field(description="Идентификатор файла.")
    role: str = Field(
        default="attachment",
        description="Роль файла в контексте сообщения (attachment/preview/etc).",
    )
