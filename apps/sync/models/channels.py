"""Модели каналов (Channel) для Sync API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ChannelType(str, Enum):
    """Тип канала."""

    DIRECT = "direct"
    GROUP = "group"
    TOPIC = "topic"


class ChannelRead(BaseModel):
    """Канал или чат (единая сущность)."""

    id: str = Field(description="Идентификатор канала.")
    space_id: str | None = Field(
        default=None,
        description="Пространство, в котором живёт канал (для topic/group).",
    )
    type: ChannelType = Field(description="Тип канала.")
    name: str | None = Field(
        default=None,
        description="Имя канала (для topic обязательно).",
    )
    is_private: bool = Field(
        description="Флаг приватности канала (доступ только по приглашению).",
    )
    created_at: datetime = Field(description="Время создания канала.")
    created_by_user_id: str = Field(description="Создатель канала.")


class ChannelCreate(BaseModel):
    """Параметры для создания канала/чата."""

    space_id: str | None = Field(
        default=None,
        description="Пространство, если канал привязан к Space.",
    )
    type: ChannelType = Field(description="Тип создаваемого канала.")
    name: str | None = Field(
        default=None,
        description="Имя канала (для topic обязательно).",
    )
    is_private: bool = Field(
        default=False,
        description="Создавать приватный канал.",
    )
    member_ids: list[str] | None = Field(
        default=None,
        description="Начальный список участников (актуально для direct/group).",
    )


class ChannelUpdate(BaseModel):
    """Обновление настроек канала."""

    name: str | None = Field(
        default=None,
        description="Новое имя канала.",
    )
    is_private: bool | None = Field(
        default=None,
        description="Новый флаг приватности.",
    )


class ChannelMemberRead(BaseModel):
    """Участник канала."""

    user_id: str = Field(description="Идентификатор пользователя.")
    role: str = Field(description="Роль пользователя в канале (owner/admin/member/viewer).")


class ChannelMemberAdd(BaseModel):
    """Добавление участника в канал."""

    user_id: str = Field(description="Идентификатор пользователя.")
    role: str = Field(
        default="member",
        description="Роль участника (по умолчанию member).",
    )
