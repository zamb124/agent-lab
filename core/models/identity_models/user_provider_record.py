"""Таблица идентичности."""

from __future__ import annotations

from typing import ClassVar, Self

from oxyde import Field as DbField
from pydantic import Field

from core.models.identity_models.contracts import (
    AuthProvider,
)
from core.models.platform_model import PlatformModel
from core.types import JsonObject


class UserProviderRecord(PlatformModel):
    """Одна связь пользователя с OAuth-провайдером. Таблица ``user_providers``."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    user_provider_id: str = DbField(db_pk=True, description="provider_name:provider_user_id")
    user_id: str = DbField(db_index=True, description="Пользователь платформы")
    provider_user_id: str = DbField(db_index=True, description="ID пользователя у провайдера")
    provider_name: AuthProvider = DbField(description="Провайдер авторизации")

    class Meta:
        is_table: bool = True
        table_name: str = "user_providers"
        unique_together: list[tuple[str, str]] = [("provider_name", "provider_user_id")]

    email: str = DbField(description="Email пользователя у провайдера")
    avatar_url: str | None = Field(default=None, description="URL аватара у провайдера")
    metadata: JsonObject = Field(default_factory=dict, description="Данные профиля провайдера")

    @classmethod
    async def find_by_provider_user_id(cls, provider_user_id: str) -> Self | None:
        if provider_user_id == "":
            raise ValueError("provider_user_id is required")
        return await cls.objects.filter(provider_user_id=provider_user_id).first()

    @classmethod
    async def list_by_user_id(cls, user_id: str) -> list[Self]:
        if user_id == "":
            raise ValueError("user_id is required")
        return await cls.objects.filter(user_id=user_id).all()
