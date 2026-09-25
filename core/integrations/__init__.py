"""
Универсальный механизм авторизации внешних интеграций.

OAuthService — единый OAuth2 flow (start, complete, refresh, get_valid_token).
IntegrationCredential — хранение per-user OAuth токенов.
Company-owned credentials — user_id=COMPANY_INTEGRATION_USER_ID (__company__).
"""

from core.integrations.company_credentials import (
    CompanyIntegrationCredentialService,
    GoogleWorkspaceCompanyCredentialPublic,
    GoogleWorkspaceCompanyCredentialPut,
    GoogleWorkspaceSystemReconcileResult,
)
from core.integrations.constants import (
    COMPANY_INTEGRATION_USER_ID,
    TOKEN_TYPE_SERVICE_ACCOUNT,
)
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

__all__ = [
    "COMPANY_INTEGRATION_USER_ID",
    "CompanyIntegrationCredentialService",
    "GuidedIntegrationError",
    "GuidedIntegrationLink",
    "GoogleWorkspaceCompanyCredentialPublic",
    "GoogleWorkspaceCompanyCredentialPut",
    "GoogleWorkspaceSystemReconcileResult",
    "IntegrationCredential",
    "IntegrationProvider",
    "OAuthProviderConfig",
    "OAuthService",
    "TOKEN_TYPE_SERVICE_ACCOUNT",
    "parse_amocrm_subdomain_from_referer",
    "set_oauth_credential_saved_hook",
]
