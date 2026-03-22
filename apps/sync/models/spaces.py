"""Модели пространств (Spaces) для Sync API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


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

    name: str | None = Field(
        default=None,
        description="Новое имя пространства.",
    )
    description: str | None = Field(
        default=None,
        description="Новое описание пространства.",
    )
    avatar_url: str | None = Field(
        default=None,
        description="URL аватара или null для сброса.",
    )
