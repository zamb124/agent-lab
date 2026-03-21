"""Участники компании для Sync UI (личные чаты)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompanyMemberRead(BaseModel):
    """Краткие данные участника активной компании."""

    user_id: str = Field(description="Идентификатор пользователя.")
    name: str = Field(description="Отображаемое имя.")
    roles: list[str] = Field(description="Роли в компании.")
    avatar_url: str | None = Field(default=None, description="URL аватара.")
