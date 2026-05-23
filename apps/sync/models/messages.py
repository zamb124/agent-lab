"""Модели сообщений и полиморфного контента для Sync API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from apps.sync.models.common import UserBrief
from core.files.models import (
    AudioAttachmentContent,
    VideoAttachmentContent,
)

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
    FILE_VIDEO = "file/video"
    CALL_BOUNDARY = "call/boundary"
    CALL_TRANSCRIPT = "call/transcript"
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
    original_name: str = Field(description="Оригинальное имя файла.")
    content_type: str = Field(description="MIME-тип файла.")
    file_size: int = Field(description="Размер файла в байтах.")


class GitReferenceContent(BaseModel):
    """Блок, ссылающийся на абстрактный Git-ресурс."""

    git_ref_id: str = Field(description="Идентификатор GitResourceRef.")


class CustomToolResponseContent(BaseModel):
    """Ответ внешнего инструмента или AI-агента."""

    tool_name: str = Field(description="Имя инструмента, сформировавшего ответ.")
    response_data: dict[str, Any] = Field(
        description="Произвольные данные ответа инструмента.",
    )


class CallBoundaryContent(BaseModel):
    """Маркер начала или окончания звонка в ленте канала."""

    call_id: str = Field(description="Идентификатор звонка.")
    phase: Literal["started", "ended"] = Field(description="Фаза сессии.")
    has_recording: bool = Field(
        default=True,
        description="Для phase=ended: есть успешно завершённая серверная запись (status uploaded).",
    )


class CallTranscriptEntry(BaseModel):
    """Одна реплика в транскрипте звонка."""

    user_id: str = Field(description="Идентификатор участника (user_id или guest:...).")
    display_name: str = Field(description="Отображаемое имя участника.")
    avatar_url: str | None = Field(default=None, description="URL аватара участника.")
    is_guest: bool = Field(default=False, description="Гостевой участник (без профиля).")
    timestamp: datetime = Field(description="Время реплики.")
    text: str = Field(description="Текст реплики.")


class CallTranscriptContent(BaseModel):
    """Структурированный транскрипт звонка с данными об участниках и таймингами."""

    call_id: str = Field(description="Идентификатор звонка.")
    entries: list[CallTranscriptEntry] = Field(description="Реплики в хронологическом порядке.")


ContentData = (
    TextPlainContent
    | CodeBlockContent
    | FileAttachmentContent
    | AudioAttachmentContent
    | VideoAttachmentContent
    | CallBoundaryContent
    | CallTranscriptContent
    | MockImageContent
    | GitReferenceContent
    | CustomToolResponseContent
)


class MessageContentModel(BaseModel):
    """Полиморфный блок контента сообщения."""

    type: MessageContentType = Field(description="Тип блока контента.")
    data: ContentData = Field(description="Данные блока контента.")
    order: int = Field(description="Позиция блока в сообщении.")

    @model_validator(mode="after")
    def _coerce_file_video_payload(self) -> MessageContentModel:
        """Union ContentData отдаёт приоритет FileAttachmentContent; для file/video нужен VideoAttachmentContent."""
        if self.type == MessageContentType.FILE_VIDEO and isinstance(self.data, FileAttachmentContent):
            fa = self.data
            object.__setattr__(
                self,
                "data",
                VideoAttachmentContent(
                    file_id=fa.file_id,
                    original_name=fa.original_name,
                    content_type=fa.content_type,
                    file_size=fa.file_size,
                    duration_ms=None,
                ),
            )
        return self


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

    message_id: str = Field(description="Идентификатор сообщения.")
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
    call_id: str | None = Field(
        default=None,
        description="Привязка к сессии звонка (агрегация транскрипции по митингу).",
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
    call_id: str | None = Field(
        default=None,
        description="Связать сообщение с активным/завершённым звонком (голос, чат оверлея, запись).",
    )
    local_id: str | None = Field(
        default=None,
        description=(
            "Клиентский идентификатор optimistic-сообщения. Не сохраняется в БД, "
            "но эхо-возвращается в payload push-события sync/message/created, "
            "чтобы UI отправителя удалил pending optimistic-запись и не показывал дубль."
        ),
    )


class MessageEdit(BaseModel):
    """Тело редактирования сообщения."""

    contents: list[MessageContentModel] = Field(
        description="Новый набор блоков контента.",
    )


class MessageRow(BaseModel):
    """Строка сообщения в базе данных."""

    message_id: str = Field(description="Идентификатор сообщения.")
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
    data: dict[str, Any] = Field(description="JSON-данные блока.")
