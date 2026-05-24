"""
Доменные модели универсального механизма интеграций.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import Field

from core.models.base import StrictBaseModel
from core.types import JsonObject


class IntegrationProvider(StrEnum):
    GOOGLE = "google"
    YANDEX = "yandex"
    AMOCRM = "amocrm"


class IntegrationCredential(StrictBaseModel):
    """Per-user OAuth credential, хранится в integration_credentials (shared DB)."""

    credential_id: str
    company_id: str
    user_id: str
    provider: IntegrationProvider
    service: str
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    scope: str | None = None
    token_type: str | None = None
    metadata: JsonObject = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self.expires_at


class CredentialInfo(StrictBaseModel):
    """Публичная проекция credential для UI (без токенов)."""

    provider: str
    service: str
    created_at: datetime


class OAuthProviderConfig(StrictBaseModel):
    """Конфигурация OAuth2-провайдера, читается из settings.auth.providers."""

    provider: IntegrationProvider
    client_id: str
    client_secret: str
    auth_url: str
    token_url: str
    token_request_format: str = "form"
