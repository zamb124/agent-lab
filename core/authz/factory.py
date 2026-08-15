"""Фабрика AuthzService из settings."""

from core.authz.client import OpenFgaAuthzClient
from core.authz.errors import AuthzConfigError
from core.authz.service import AuthzService
from core.authz.types import AuthzConsistency
from core.config import get_settings
from core.config.models import OpenFGAConfig


def build_authz_service(config: OpenFGAConfig | None = None) -> AuthzService:
    settings = get_settings()
    openfga = config if config is not None else settings.openfga
    if openfga.enabled:
        if not openfga.store_id.strip():
            raise AuthzConfigError(
                "openfga.enabled=true requires openfga.store_id "
                + "(make dev-up / make test-up / pin Helm OPENFGA_STORE_ID)"
            )
        if not openfga.authorization_model_id.strip():
            raise AuthzConfigError(
                "openfga.enabled=true requires openfga.authorization_model_id "
                + "(make dev-up / make test-up / pin Helm OPENFGA_AUTHORIZATION_MODEL_ID)"
            )
    client = OpenFgaAuthzClient(
        api_url=openfga.api_url,
        store_id=openfga.store_id,
        authorization_model_id=openfga.authorization_model_id,
        api_token=openfga.api_token,
        timeout_ms=openfga.timeout_ms,
    )
    return AuthzService(
        client,
        enabled=openfga.enabled,
        default_consistency=AuthzConsistency(openfga.default_consistency),
    )
