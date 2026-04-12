"""
Универсальный механизм авторизации внешних интеграций.

OAuthService — единый OAuth2 flow (start, complete, refresh, get_valid_token).
IntegrationCredentialRepository — хранение per-user OAuth токенов.
"""

from core.integrations.models import (
    IntegrationCredential,
    IntegrationProvider,
    OAuthProviderConfig,
)
from core.integrations.oauth_service import OAuthService
from core.integrations.repository import IntegrationCredentialRepository

__all__ = [
    "IntegrationCredential",
    "IntegrationCredentialRepository",
    "IntegrationProvider",
    "OAuthProviderConfig",
    "OAuthService",
]
