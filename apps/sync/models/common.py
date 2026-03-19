"""Общие Pydantic-модели для Sync API (идентификаторы, пагинация)."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field


class IDModel(BaseModel):
    """Базовая модель с идентификатором."""

    id: str = Field(description="Уникальный идентификатор ресурса.")


class TimestampedModel(BaseModel):
    """Базовая модель с временными метками."""

    created_at: datetime = Field(description="Время создания.")
    updated_at: datetime | None = Field(
        default=None,
        description="Время последнего обновления.",
    )


class UserBrief(BaseModel):
    """Краткая информация о пользователе (общая для всей платформы)."""

    id: str = Field(description="Идентификатор пользователя.")
    display_name: str = Field(description="Отображаемое имя.")
    avatar_url: str | None = Field(
        default=None,
        description="URL аватара пользователя.",
    )


class PaginationRequest(BaseModel):
    """Параметры пагинации для запросов списка."""

    limit: int = Field(default=50, ge=1, le=200, description="Сколько элементов вернуть.")
    before: str | None = Field(
        default=None,
        description="Курсор/идентификатор для постраничной загрузки назад.",
    )
    after: str | None = Field(
        default=None,
        description="Курсор/идентификатор для постраничной загрузки вперёд.",
    )


ItemT = TypeVar("ItemT")


class PaginationResponse(BaseModel, Generic[ItemT]):
    """Обёртка ответа с пагинацией."""

    items: list[ItemT] = Field(description="Элементы текущей страницы.")
    next_cursor: str | None = Field(
        default=None,
        description="Курсор для следующей страницы, если есть.",
    )
    prev_cursor: str | None = Field(
        default=None,
        description="Курсор для предыдущей страницы, если есть.",
    )
