"""Модели пространств (Spaces) для Sync API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _validate_avatar_url(v: str | None) -> str | None:
    if v is not None and not v.startswith("/"):
        raise ValueError("avatar_url должен быть относительным URL платформы (начинается с /)")
    return v


class SpaceRead(BaseModel):
    """Пространство, объединяющее каналы и чаты."""

    id: str = Field(description="Идентификатор пространства.")
    name: str = Field(description="Человекочитаемое имя пространства.")
    description: str | None = Field(
        default=None,
        description="Описание пространства.",
    )
    avatar_url: str | None = Field(
        default=None,
        description="URL аватара (изображение).",
    )
    namespace: str | None = Field(default=None, description="Общий namespace для CRM/RAG.")
    created_at: datetime = Field(description="Время создания пространства.")
    created_by_user_id: str = Field(description="Создатель пространства.")
    transcribe_voice_messages: bool = Field(
        default=False,
        description="Значение по умолчанию для новых каналов: авто-STT голосовых.",
    )
    speech_to_chat_enabled: bool = Field(
        default=False,
        description="Значение по умолчанию для новых каналов: речь звонка в ленту (LiveKit egress).",
    )


class SpaceCreate(BaseModel):
    """Параметры для создания пространства."""

    name: str = Field(description="Человекочитаемое имя пространства.")
    description: str | None = Field(
        default=None,
        description="Описание пространства.",
    )
    transcribe_voice_messages: bool = Field(
        default=False,
        description="Дефолт авто-STT для новых каналов в этом пространстве.",
    )
    speech_to_chat_enabled: bool = Field(
        default=False,
        description="Дефолт «речь в ленту» для новых каналов в этом пространстве.",
    )


class SpaceUpdate(BaseModel):
    """Обновление параметров пространства."""

    name: str | None = Field(default=None, description="Новое имя пространства.")
    description: str | None = Field(default=None, description="Новое описание пространства.")
    avatar_url: str | None = Field(default=None, description="URL аватара или null для сброса.")
    namespace: str | None = Field(default=None, description="Общий namespace CRM/RAG или null для сброса.")
    transcribe_voice_messages: bool | None = Field(
        default=None,
        description="Дефолт для новых каналов в space; существующие каналы не меняются.",
    )
    speech_to_chat_enabled: bool | None = Field(
        default=None,
        description="Дефолт «речь в ленту» для новых каналов; существующие каналы не меняются.",
    )

    @field_validator("avatar_url")
    @classmethod
    def avatar_url_must_be_relative(cls, v: str | None) -> str | None:
        return _validate_avatar_url(v)
