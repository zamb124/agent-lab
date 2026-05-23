"""Модели каналов (Channel) для Sync API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from apps.sync.models.common import UserBrief


def _validate_avatar_url(v: str | None) -> str | None:
    if v is not None and not v.startswith("/"):
        raise ValueError("avatar_url должен быть относительным URL платформы (начинается с /)")
    return v


class ChannelType(str, Enum):
    """Тип канала."""

    DIRECT = "direct"
    GROUP = "group"
    TOPIC = "topic"
    CALENDAR_MEETING = "calendar_meeting"


class ChannelRead(BaseModel):
    """Канал или чат (единая сущность)."""

    channel_id: str = Field(description="Идентификатор канала.")
    namespace: str = Field(
        description="Платформенный namespace, в котором живёт канал (1:1 c shared NamespaceRepository).",
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
    pinned_message_ids: list[str] = Field(
        default_factory=list,
        description="Упорядоченный список закреплённых сообщений (message_id).",
    )
    peer: UserBrief | None = Field(
        default=None,
        description="Собеседник в direct (участник, отличный от текущего пользователя).",
    )
    avatar_url: str | None = Field(
        default=None,
        description="URL аватара канала (topic/group).",
    )
    unread_count: int = Field(
        default=0,
        description="Число непрочитанных сообщений в основной ленте (не треды).",
    )
    mention_unread_count: int = Field(
        default=0,
        description="Непрочитанные сообщения основной ленты, где текущего пользователя упомянули.",
    )
    last_message_preview: str | None = Field(
        default=None,
        description="Краткий текст последнего сообщения основной ленты.",
    )
    last_message_at: datetime | None = Field(
        default=None,
        description="Время последнего сообщения основной ленты.",
    )
    peer_last_read_at: datetime | None = Field(
        default=None,
        description="Время, до которого собеседник прочитал основную ленту (только для direct).",
    )
    notifications_muted: bool = Field(
        default=False,
        description="Уведомления о новых сообщениях отключены для текущего пользователя в этом канале.",
    )
    transcribe_voice_messages: bool = Field(
        default=False,
        description="Автоматически ставить в очередь STT для входящих голосовых сообщений.",
    )
    speech_to_chat_enabled: bool = Field(
        default=False,
        description="Речь участников звонка в ленту (серверный LiveKit egress по микрофону).",
    )


class ChannelCreate(BaseModel):
    """Параметры для создания канала/чата."""

    namespace: str | None = Field(
        default=None,
        description=(
            "Платформенный namespace (1:1 с shared NamespaceRepository). "
            "Для topic обязателен; для direct/calendar_meeting если опущен — "
            "используется 'default'."
        ),
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
    transcribe_voice_messages: bool | None = Field(
        default=None,
        description=(
            "Если задано — оверрайд над дефолтом из Namespace.sync_settings. "
            "Иначе берётся `Namespace.sync_settings.transcribe_voice_messages` или false."
        ),
    )
    speech_to_chat_enabled: bool | None = Field(
        default=None,
        description=(
            "Если задано — оверрайд над дефолтом из Namespace.sync_settings. "
            "Иначе берётся `Namespace.sync_settings.speech_to_chat_enabled` или false."
        ),
    )


class ChannelUpdate(BaseModel):
    """Обновление настроек канала."""

    name: str | None = Field(default=None, description="Новое имя канала.")
    is_private: bool | None = Field(default=None, description="Новый флаг приватности.")
    avatar_url: str | None = Field(default=None, description="URL аватара или null для сброса.")

    @field_validator("avatar_url")
    @classmethod
    def avatar_url_must_be_relative(cls, v: str | None) -> str | None:
        return _validate_avatar_url(v)

    transcribe_voice_messages: bool | None = Field(
        default=None,
        description="Авто-транскрипция голосовых сообщений в канале.",
    )
    speech_to_chat_enabled: bool | None = Field(
        default=None,
        description="Речь звонка в ленту через LiveKit egress.",
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


class ChannelNotificationSettingsUpdate(BaseModel):
    """Настройки уведомлений текущего пользователя в канале."""

    notifications_muted: bool = Field(
        description="Не отправлять платформенные уведомления о новых сообщениях в этом канале.",
    )
