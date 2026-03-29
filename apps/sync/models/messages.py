"""Модели сообщений и полиморфного контента для Sync API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Union

from pydantic import BaseModel, Field

from apps.sync.models.common import UserBrief
from core.files.models import AudioAttachmentContent, AudioTranscriptionStatus

# Один текстовый блок text/plain — как лимит одного сообщения в Telegram (4096).
SYNC_MESSAGE_TEXT_MAX_CHARS = 4096


class MessageStatus(str, Enum):
    """Статус доставки сообщения."""

    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class MessageContentType(str, Enum):
    """Тип блока контента сообщения."""

    TEXT_PLAIN = "text/plain"
    CODE_BLOCK = "code/block"
    MOCK_IMAGE = "mock/image"
    FILE_IMAGE = "file/image"
    FILE_DOCUMENT = "file/document"
    FILE_AUDIO = "file/audio"
    GIT_REFERENCE = "git/reference"
    CUSTOM_TOOL_RESPONSE = "custom_tool_response"


class TextPlainContent(BaseModel):
    """Текстовый блок с поддержкой Markdown."""

    body: str = Field(
        ...,
        max_length=SYNC_MESSAGE_TEXT_MAX_CHARS,
        description="Текст сообщения в формате совместимом с Markdown.",
    )
    mentions: list[str] | None = Field(
        default=None,
        description="Идентификаторы упомянутых участников канала (user_id).",
    )


class CodeBlockContent(BaseModel):
    """Блок исходного кода."""

    language: str = Field(description="Язык программирования.")
    source: str = Field(description="Исходный код.")
    git_ref_id: str | None = Field(
        default=None,
        description="Опциональная ссылка на Git-ресурс, с которым связан код.",
    )


class MockImageContent(BaseModel):
    """Блок изображения/макета."""

    file_id: str = Field(description="Идентификатор файла в системе.")
    alt_text: str | None = Field(
        default=None,
        description="Альтернативный текст для изображения.",
    )


class FileAttachmentContent(BaseModel):
    """Вложение файла — фото/видео (file/image) или документ (file/document)."""

    file_id: str = Field(description="Идентификатор файла в системе.")
    filename: str = Field(description="Оригинальное имя файла.")
    mime_type: str = Field(description="MIME-тип файла.")
    size: int = Field(description="Размер файла в байтах.")


class GitReferenceContent(BaseModel):
    """Блок, ссылающийся на абстрактный Git-ресурс."""

    git_ref_id: str = Field(description="Идентификатор GitResourceRef.")


class CustomToolResponseContent(BaseModel):
    """Ответ внешнего инструмента или AI-агента."""

    tool_name: str = Field(description="Имя инструмента, сформировавшего ответ.")
    response_data: dict = Field(
        description="Произвольные данные ответа инструмента.",
    )


ContentData = Union[
    TextPlainContent,
    CodeBlockContent,
    FileAttachmentContent,
    AudioAttachmentContent,
    MockImageContent,
    GitReferenceContent,
    CustomToolResponseContent,
]


class MessageContentModel(BaseModel):
    """Полиморфный блок контента сообщения."""

    type: MessageContentType = Field(description="Тип блока контента.")
    data: ContentData = Field(description="Данные блока контента.")
    order: int = Field(description="Позиция блока в сообщении.")


class ReactionEntry(BaseModel):
    """Одна реакция на сообщение (хранится в JSON на строке сообщения)."""

    user_id: str = Field(description="Кто поставил.")
    emoji: str = Field(description="Символ эмодзи.")
    created_at: datetime = Field(description="Время установки.")


class ForwardedFromChannel(BaseModel):
    """Источник пересланного сообщения (другой канал)."""

    channel_id: str = Field(description="Идентификатор канала-источника.")
    channel_name: str | None = Field(
        default=None,
        description="Имя канала на момент пересылки (если было в БД).",
    )


class MessageRead(BaseModel):
    """Сообщение, возвращаемое из API."""

    id: str = Field(description="Идентификатор сообщения.")
    channel_id: str = Field(description="Канал, в котором находится сообщение.")
    thread_id: str | None = Field(
        default=None,
        description="Тред, к которому относится сообщение (если есть).",
    )
    parent_message_id: str | None = Field(
        default=None,
        description="Сообщение, на которое дан ответ (если есть).",
    )
    sender: UserBrief = Field(description="Отправитель сообщения.")
    status: MessageStatus = Field(description="Статус доставки сообщения.")
    sent_at: datetime = Field(description="Время отправки сообщения.")
    edited_at: datetime | None = Field(
        default=None,
        description="Время последнего редактирования сообщения.",
    )
    contents: list[MessageContentModel] = Field(
        description="Список блоков контента сообщения.",
    )
    reactions: list[ReactionEntry] = Field(
        default_factory=list,
        description="Реакции пользователей.",
    )
    forwarded_from: ForwardedFromChannel | None = Field(
        default=None,
        description="Если сообщение переслано из другого канала.",
    )
    mentioned_user_ids: list[str] | None = Field(
        default=None,
        description="Дублирует mentions из первого блока text/plain для клиента.",
    )


class MessageCreate(BaseModel):
    """Тело запроса для создания сообщения."""

    thread_id: str | None = Field(
        default=None,
        description="Тред, в который отправляется сообщение (если новое корневое -- null).",
    )
    parent_message_id: str | None = Field(
        default=None,
        description="Сообщение, на которое отправляется ответ.",
    )
    contents: list[MessageContentModel] = Field(
        description="Блоки контента нового сообщения.",
    )
    mentioned_user_ids: list[str] | None = Field(
        default=None,
        description="Упоминания участников канала; сервер записывает в data первого text/plain.",
    )


class MessageEdit(BaseModel):
    """Тело редактирования сообщения."""

    contents: list[MessageContentModel] = Field(
        description="Новый набор блоков контента.",
    )


class MessageRow(BaseModel):
    """Строка сообщения в базе данных."""

    id: str = Field(description="Идентификатор сообщения.")
    channel_id: str = Field(description="Канал, в котором находится сообщение.")
    thread_id: str | None = Field(default=None, description="Тред сообщения.")
    parent_message_id: str | None = Field(default=None, description="Родительское сообщение.")
    sender_user_id: str = Field(description="Идентификатор отправителя.")
    status: str = Field(description="Статус доставки сообщения.")
    sent_at: datetime = Field(description="Время отправки сообщения.")
    edited_at: datetime | None = Field(default=None, description="Время редактирования.")


class MessageContentRow(BaseModel):
    """Строка контента сообщения в базе данных."""

    id: int = Field(description="Идентификатор строки контента.")
    message_id: str = Field(description="Идентификатор сообщения.")
    type: str = Field(description="Тип блока контента.")
    order: int = Field(description="Порядок блока.")
    data: dict = Field(description="JSON-данные блока.")
