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
    auto_export_transcript_to_crm: bool = Field(
        default=False,
        description="Автоэкспорт транскрипта встречи в CRM.",
    )
    auto_export_summary_to_crm: bool = Field(
        default=False,
        description="Автоэкспорт summary встречи в CRM.",
    )
    created_at: datetime = Field(description="Время создания пространства.")
    created_by_user_id: str = Field(description="Создатель пространства.")


class SpaceCreate(BaseModel):
    """Параметры для создания пространства."""

    name: str = Field(description="Человекочитаемое имя пространства.")
    description: str | None = Field(
        default=None,
        description="Описание пространства.",
    )


class SpaceUpdate(BaseModel):
    """Обновление параметров пространства."""

    name: str | None = Field(default=None, description="Новое имя пространства.")
    description: str | None = Field(default=None, description="Новое описание пространства.")
    avatar_url: str | None = Field(default=None, description="URL аватара или null для сброса.")
    namespace: str | None = Field(default=None, description="Общий namespace CRM/RAG или null для сброса.")
    auto_export_transcript_to_crm: bool | None = Field(default=None)
    auto_export_summary_to_crm: bool | None = Field(default=None)

    @field_validator("avatar_url")
    @classmethod
    def avatar_url_must_be_relative(cls, v: str | None) -> str | None:
        return _validate_avatar_url(v)
