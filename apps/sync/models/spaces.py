"""Модели пространств (Spaces) для Sync API.

Sync-space жёстко 1:1 связан с платформенным namespace (shared KV `namespaces`):
поле `namespace` обязательное при создании, immutable после, уникально в рамках
компании. Это позволяет глобальному селекту namespace в платформе (CRM/RAG/Sync/...)
переключать «активное пространство» одинаково во всех сервисах.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


NAMESPACE_SLUG_PATTERN = r"^[a-z][a-z0-9_-]{0,99}$"


def _validate_avatar_url(v: str | None) -> str | None:
    if v is not None and not v.startswith("/"):
        raise ValueError("avatar_url должен быть относительным URL платформы (начинается с /)")
    return v


def _validate_namespace_slug(v: str) -> str:
    import re as _re
    if not isinstance(v, str) or not _re.fullmatch(NAMESPACE_SLUG_PATTERN, v):
        raise ValueError(
            "namespace должен начинаться с латинской буквы и содержать только "
            "латиницу, цифры, '-', '_' (1..100 символов).",
        )
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
    namespace: str = Field(
        description="Платформенный namespace (shared KV); 1:1 со SyncSpace.",
    )
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

    name: str = Field(min_length=1, description="Человекочитаемое имя пространства.")
    namespace: str = Field(
        min_length=1,
        max_length=100,
        description=(
            "Slug платформенного namespace (shared KV). Уникален в пределах "
            "компании; immutable после создания."
        ),
    )
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

    @field_validator("namespace")
    @classmethod
    def namespace_must_be_slug(cls, v: str) -> str:
        return _validate_namespace_slug(v)


class SpaceUpdate(BaseModel):
    """Обновление параметров пространства.

    `namespace` отсутствует — поле immutable: имя shared-namespace задаётся
    только при создании. Переименование пространства (отображаемое name)
    разрешено и не затрагивает связь с платформенным namespace.
    """

    name: str | None = Field(default=None, description="Новое имя пространства.")
    description: str | None = Field(default=None, description="Новое описание пространства.")
    avatar_url: str | None = Field(default=None, description="URL аватара или null для сброса.")
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
