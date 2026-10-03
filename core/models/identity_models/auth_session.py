"""Таблица идентичности."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar

from oxyde import Field as DbField
from pydantic import Field

from core.models.identity_models.contracts import (
    AuthProvider,
)
from core.models.platform_model import PlatformModel
from core.types import JsonObject


class AuthSession(PlatformModel):
    """Сессия входа. Глобальная таблица ``auth_sessions`` в ``platform_shared``."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    session_id: str = DbField(
        db_pk=True,
        title="ID сессии",
        description="Уникальный ID сессии авторизации",
        json_schema_extra={"readonly": True},
    )

    class Meta:
        is_table: bool = True
        table_name: str = "auth_sessions"

    user_id: str = DbField(
        db_index=True,
        title="ID пользователя",
        description="Ссылка на пользователя",
        json_schema_extra={"readonly": True},
    )
    provider: AuthProvider = DbField(
        title="Провайдер", description="Провайдер авторизации", json_schema_extra={"readonly": True}
    )
    access_token: str | None = Field(
        default=None,
        title="Токен доступа",
        description="Токен доступа от провайдера",
        json_schema_extra={"groups": {"admin": {"hidden": False}, "user": {"hidden": True}}},
    )
    refresh_token: str | None = Field(
        default=None,
        title="Refresh токен",
        description="Refresh токен от провайдера",
        json_schema_extra={"groups": {"admin": {"hidden": False}, "user": {"hidden": True}}},
    )
    expires_at: str | None = Field(
        default=None,
        title="Истекает",
        description="Время истечения сессии (ISO строка)",
        json_schema_extra={"readonly": True},
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создана",
        description="Время создания сессии",
        json_schema_extra={"readonly": True},
    )
    last_activity: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Последняя активность",
        description="Время последней активности",
        json_schema_extra={"readonly": True},
    )
    metadata: JsonObject = Field(
        default_factory=dict,
        title="Метаданные",
        description="Дополнительные данные сессии",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
