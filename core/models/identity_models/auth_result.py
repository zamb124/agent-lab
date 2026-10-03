"""Результат входа."""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.models.identity_models.auth_session import AuthSession
from core.models.identity_models.user import User


class AuthResult(BaseModel):
    """Результат авторизации"""

    success: bool = Field(description="Успешность авторизации")
    user: User | None = Field(default=None, description="Авторизованный пользователь")
    session: AuthSession | None = Field(default=None, description="Сессия авторизации")
    token: str | None = Field(default=None, description="JWT токен")
    error_message: str | None = Field(default=None, description="Сообщение об ошибке")
    redirect_url: str | None = Field(default=None, description="URL для редиректа")
