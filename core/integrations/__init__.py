"""
Универсальный механизм авторизации внешних интеграций.

OAuthService — единый OAuth2 flow (start, complete, refresh, get_valid_token).
IntegrationCredentialRepository — хранение per-user OAuth токенов.
"""

from core.integrations.guided_integration_error import (
    GuidedIntegrationError,
    GuidedIntegrationLink,
)
from core.integrations.models import (
    IntegrationCredential,
    IntegrationProvider,
    OAuthProviderConfig,
)
from core.integrations.oauth_service import OAuthService, set_oauth_credential_saved_hook
from core.integrations.providers.amocrm import parse_amocrm_subdomain_from_referer
from core.integrations.repository import IntegrationCredentialRepository

__all__ = [
    "GuidedIntegrationError",
    "GuidedIntegrationLink",
    "IntegrationCredential",
    "IntegrationCredentialRepository",
    "IntegrationProvider",
    "OAuthProviderConfig",
    "OAuthService",
    "parse_amocrm_subdomain_from_referer",
    "set_oauth_credential_saved_hook",
]
