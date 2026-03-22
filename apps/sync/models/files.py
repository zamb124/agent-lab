"""Модели файлов для Sync (только контекст вложений в сообщениях)."""

from pydantic import BaseModel, Field


class FileLink(BaseModel):
    """Ссылка на файл, вложенный в сообщение."""

    file_id: str = Field(description="Идентификатор файла.")
    role: str = Field(
        default="attachment",
        description="Роль файла в контексте сообщения (attachment/preview/etc).",
    )
