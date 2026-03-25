"""Превью корневой ленты канала и сводка для списка каналов."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apps.sync.models.messages import MessageContentType


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


def lane_preview_from_content_row(content_type: str, data: dict) -> str:
    """Текст превью из первого блока контента последнего сообщения."""
    if content_type == MessageContentType.TEXT_PLAIN.value:
        body = data.get("body")
        if not isinstance(body, str):
            raise ValueError("text/plain: поле body должно быть строкой.")
        stripped = body.strip()
        if stripped == "":
            return ""
        return _truncate(stripped, 120)
    if content_type == MessageContentType.CODE_BLOCK.value:
        return "[Код]"
    if content_type == MessageContentType.MOCK_IMAGE.value:
        return "[Изображение]"
    if content_type == MessageContentType.GIT_REFERENCE.value:
        return "[Git]"
    if content_type == MessageContentType.CUSTOM_TOOL_RESPONSE.value:
        return "[Инструмент]"
    raise ValueError(f"Неизвестный тип контента для превью: {content_type!r}.")
