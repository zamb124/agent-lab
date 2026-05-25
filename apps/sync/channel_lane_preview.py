"""Превью корневой ленты канала и сводка для списка каналов."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apps.sync.models.messages import (
    CallBoundaryContent,
    MessageContentModel,
    MessageContentType,
    TextPlainContent,
)


@dataclass(frozen=True)
class ChannelLaneSummary:
    """Непрочитанные и последнее сообщение в основной ленте (без тредов)."""

    unread_count: int
    last_message_preview: str | None
    last_message_at: datetime | None
    mention_unread_count: int = 0


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def lane_preview_from_content(content: MessageContentModel) -> str:
    """Текст превью из первого блока контента последнего сообщения."""
    if content.type == MessageContentType.TEXT_PLAIN:
        if not isinstance(content.data, TextPlainContent):
            raise ValueError("text/plain: ожидается TextPlainContent.")
        stripped = content.data.body.strip()
        if stripped == "":
            return ""
        return _truncate(stripped, 120)
    if content.type == MessageContentType.CODE_BLOCK:
        return "[Код]"
    if content.type == MessageContentType.MOCK_IMAGE:
        return "[Изображение]"
    if content.type == MessageContentType.FILE_IMAGE:
        return "[Фото]"
    if content.type == MessageContentType.FILE_DOCUMENT:
        return "[Файл]"
    if content.type == MessageContentType.FILE_AUDIO:
        return "[Аудио]"
    if content.type == MessageContentType.FILE_VIDEO:
        return "[Видео]"
    if content.type == MessageContentType.CALL_TRANSCRIPT:
        return "[Транскрипт звонка]"
    if content.type == MessageContentType.CALL_BOUNDARY:
        if not isinstance(content.data, CallBoundaryContent):
            raise ValueError("call/boundary: ожидается CallBoundaryContent.")
        if content.data.phase == "started":
            return "[Звонок начался]"
        if content.data.phase == "ended":
            return "[Звонок завершён]"
    if content.type == MessageContentType.GIT_REFERENCE:
        return "[Git]"
    if content.type == MessageContentType.CUSTOM_TOOL_RESPONSE:
        return "[Инструмент]"
    raise ValueError(f"Неизвестный тип контента для превью: {content.type.value!r}.")
