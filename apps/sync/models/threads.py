"""Модели тредов (Thread) для Sync API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from apps.sync.models.common import UserBrief


class ThreadRow(BaseModel):
    """Строка треда в базе данных."""

    thread_id: str = Field(description="Идентификатор треда.")
    channel_id: str = Field(description="Канал, в котором находится тред.")
    root_message_id: str = Field(description="Корневое сообщение треда.")
    title: str | None = Field(default=None, description="Опциональный заголовок треда.")
    created_at: datetime = Field(description="Время создания треда.")
    created_by_user_id: str = Field(description="Создатель треда.")


class ThreadRead(BaseModel):
    """Полная информация о треде."""

    thread_id: str = Field(description="Идентификатор треда.")
    channel_id: str = Field(description="Канал, в котором находится тред.")
    root_message_id: str = Field(description="Корневое сообщение треда.")
    title: str | None = Field(
        default=None,
        description="Опциональный заголовок треда.",
    )
    created_at: datetime = Field(description="Время создания треда.")
    created_by: UserBrief = Field(description="Пользователь, создавший тред.")


class ThreadCreate(BaseModel):
    """Создание треда от корневого сообщения."""

    root_message_id: str = Field(description="Корневое сообщение для треда.")
    title: str | None = Field(
        default=None,
        description="Опциональный заголовок треда.",
    )


class ThreadSummary(BaseModel):
    """Краткое представление треда для списков."""

    thread_id: str = Field(description="Идентификатор треда.")
    channel_id: str = Field(description="Канал треда.")
    root_message_preview: str = Field(
        description="Краткий текстовый превью корневого сообщения.",
    )
    replies_count: int = Field(description="Количество ответов в треде.")
    last_reply_at: datetime | None = Field(
        default=None,
        description="Время последнего ответа.",
    )
