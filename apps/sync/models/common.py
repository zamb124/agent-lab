"""Общие Pydantic-модели для Sync API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TimestampedModel(BaseModel):
    """Базовая модель с временными метками."""

    created_at: datetime = Field(description="Время создания.")
    updated_at: datetime | None = Field(
        default=None,
        description="Время последнего обновления.",
    )


class UserBrief(BaseModel):
    """Краткая информация о пользователе (общая для всей платформы)."""

    user_id: str = Field(description="Идентификатор пользователя.")
    display_name: str = Field(description="Отображаемое имя.")
    avatar_url: str | None = Field(
        default=None,
        description="URL аватара пользователя.",
    )
