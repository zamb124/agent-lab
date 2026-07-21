"""
Company-owned integration credentials (sentinel user_id=__company__).

Хранятся в той же таблице integration_credentials, без per-vendor схемы.
Google Workspace SA: token_type=service_account, access_token=Fernet(SA JSON).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from core.ai.company_settings import decrypt_secret, encrypt_secret
from core.clients.google_workspace_auth import GoogleAuthMaterial
from core.clients.google_workspace_scopes import (
    GOOGLE_OAUTH_SERVICE_CANONICAL,
    GOOGLE_WORKSPACE_SCOPES,
)
from core.config.models import GoogleWorkspaceConfig
from core.context import get_context
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.integrations.constants import (
    COMPANY_INTEGRATION_USER_ID,
    METADATA_IMPERSONATE_EMAIL,
    TOKEN_TYPE_SERVICE_ACCOUNT,
)
from core.integrations.models import IntegrationCredential, IntegrationProvider
from core.integrations.repository import IntegrationCredentialRepository
from core.logging import get_logger
from core.models.base import StrictBaseModel
from core.types import JsonObject, parse_json_object

logger = get_logger(__name__)


class CompanyIntegrationPermissionError(Exception):
    """Caller lacks admin role for company-owned credentials."""


class CompanyIntegrationConfigError(Exception):
    """Invalid company credential payload or system config."""


class CompanyIntegrationReadOnlyError(Exception):
    """System company credentials are reconcile-only."""


class GoogleWorkspaceCompanyCredentialPublic(StrictBaseModel):
    """Публичная проекция company Google Workspace SA (без секретов)."""

    provider: str
    service: str
    token_type: str
    configured: bool
    impersonate_email: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GoogleWorkspaceCompanyCredentialPut(StrictBaseModel):
    """Admin PUT: Service Account JSON + optional DWD subject."""

    service_account_json: str
    impersonate_email: str | None = None


class GoogleWorkspaceSystemReconcileResult(StrictBaseModel):
    """Результат seed system company Google Workspace SA из conf."""

    ensured: bool


def require_company_admin(company_id: str) -> None:
    ctx = get_context()
    if ctx is None:
        raise CompanyIntegrationPermissionError("authenticated user is required")
    roles = ctx.user.companies.get(company_id, [])
    if "admin" not in roles:
        raise CompanyIntegrationPermissionError(
            f"admin role required for company_id={company_id}"
        )


def google_auth_material_from_service_account_credential(
    credential: IntegrationCredential,
) -> GoogleAuthMaterial:
    """Расшифровывает company SA credential → GoogleAuthMaterial."""
    if credential.token_type != TOKEN_TYPE_SERVICE_ACCOUNT:
        raise CompanyIntegrationConfigError(
            f"expected token_type={TOKEN_TYPE_SERVICE_ACCOUNT!r}, "
            + f"got {credential.token_type!r}"
        )
    credentials_json = decrypt_secret(credential.access_token)
    _ = parse_json_object(credentials_json, "google.service_account")
    subject = _optional_impersonate_email(credential.metadata)
    return GoogleAuthMaterial(
        credentials_json=credentials_json,
        subject=subject,
    )


def _optional_impersonate_email(metadata: JsonObject) -> str | None:
    raw = metadata.get(METADATA_IMPERSONATE_EMAIL)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise CompanyIntegrationConfigError(
            f"metadata.{METADATA_IMPERSONATE_EMAIL} must be a string"
        )
    stripped = raw.strip()
    if stripped == "":
        return None
    return stripped


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_service_account_json(service_account_json: str) -> str:
    stripped = service_account_json.strip()
    if stripped == "":
        raise CompanyIntegrationConfigError("service_account_json must not be empty")
    try:
        _ = parse_json_object(stripped, "google.service_account")
    except ValueError as exc:
        raise CompanyIntegrationConfigError(str(exc)) from exc
    return stripped


def _normalize_impersonate_email(impersonate_email: str | None) -> str | None:
    if impersonate_email is None:
        return None
    stripped = impersonate_email.strip()
    if stripped == "":
        return None
    return stripped


class CompanyIntegrationCredentialService:
    """CRUD company-owned credentials на integration_credentials."""

    _repository: IntegrationCredentialRepository
    _google_workspace_config: GoogleWorkspaceConfig

    def __init__(
        self,
        repository: IntegrationCredentialRepository,
        google_workspace_config: GoogleWorkspaceConfig,
    ) -> None:
        self._repository = repository
        self._google_workspace_config = google_workspace_config

    async def get_google_workspace_company_public(
        self,
        company_id: str,
    ) -> GoogleWorkspaceCompanyCredentialPublic:
        credential = await self._repository.get_by_user_provider_service(
            company_id=company_id,
            user_id=COMPANY_INTEGRATION_USER_ID,
            provider=IntegrationProvider.GOOGLE,
            service=GOOGLE_OAUTH_SERVICE_CANONICAL,
        )
        if credential is None:
            return GoogleWorkspaceCompanyCredentialPublic(
                provider=IntegrationProvider.GOOGLE.value,
                service=GOOGLE_OAUTH_SERVICE_CANONICAL,
                token_type=TOKEN_TYPE_SERVICE_ACCOUNT,
                configured=False,
            )
        return GoogleWorkspaceCompanyCredentialPublic(
            provider=str(credential.provider),
            service=credential.service,
            token_type=credential.token_type
            if credential.token_type is not None
            else TOKEN_TYPE_SERVICE_ACCOUNT,
            configured=True,
            impersonate_email=_optional_impersonate_email(credential.metadata),
            created_at=credential.created_at,
            updated_at=credential.updated_at,
        )

    async def get_google_workspace_auth_material(
        self,
        company_id: str,
    ) -> GoogleAuthMaterial | None:
        credential = await self._repository.get_by_user_provider_service(
            company_id=company_id,
            user_id=COMPANY_INTEGRATION_USER_ID,
            provider=IntegrationProvider.GOOGLE,
            service=GOOGLE_OAUTH_SERVICE_CANONICAL,
        )
        if credential is None:
            return None
        return google_auth_material_from_service_account_credential(credential)

    async def upsert_google_workspace_service_account(
        self,
        company_id: str,
        payload: GoogleWorkspaceCompanyCredentialPut,
        *,
        allow_system: bool = False,
    ) -> GoogleWorkspaceCompanyCredentialPublic:
        if company_id == SYSTEM_COMPANY_ID and not allow_system:
            raise CompanyIntegrationReadOnlyError(
                "system company Google Workspace is managed via reconcile"
            )
        if not allow_system:
            require_company_admin(company_id)

        sa_json = _validate_service_account_json(payload.service_account_json)
        impersonate = _normalize_impersonate_email(payload.impersonate_email)
        now = _utcnow()
        existing = await self._repository.get_by_user_provider_service(
            company_id=company_id,
            user_id=COMPANY_INTEGRATION_USER_ID,
            provider=IntegrationProvider.GOOGLE,
            service=GOOGLE_OAUTH_SERVICE_CANONICAL,
        )
        metadata: JsonObject = {}
        if impersonate is not None:
            metadata[METADATA_IMPERSONATE_EMAIL] = impersonate

        credential = IntegrationCredential(
            credential_id=existing.credential_id if existing is not None else uuid4().hex,
            company_id=company_id,
            user_id=COMPANY_INTEGRATION_USER_ID,
            provider=IntegrationProvider.GOOGLE,
            service=GOOGLE_OAUTH_SERVICE_CANONICAL,
            access_token=encrypt_secret(sa_json),
            refresh_token=None,
            expires_at=None,
            scope=" ".join(GOOGLE_WORKSPACE_SCOPES),
            token_type=TOKEN_TYPE_SERVICE_ACCOUNT,
            metadata=metadata,
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        await self._repository.upsert(credential)
        logger.info(
            "integrations.company_google_workspace.upserted",
            company_id=company_id,
            has_impersonate=impersonate is not None,
        )
        return await self.get_google_workspace_company_public(company_id)

    async def delete_google_workspace_service_account(
        self,
        company_id: str,
        *,
        allow_system: bool = False,
    ) -> bool:
        if company_id == SYSTEM_COMPANY_ID and not allow_system:
            raise CompanyIntegrationReadOnlyError(
                "system company Google Workspace is managed via reconcile"
            )
        if not allow_system:
            require_company_admin(company_id)
        deleted = await self._repository.delete_by_user_provider_service(
            company_id=company_id,
            user_id=COMPANY_INTEGRATION_USER_ID,
            provider=IntegrationProvider.GOOGLE,
            service=GOOGLE_OAUTH_SERVICE_CANONICAL,
        )
        if deleted:
            logger.info(
                "integrations.company_google_workspace.deleted",
                company_id=company_id,
            )
        return deleted

    async def reconcile_system_google_workspace(self) -> GoogleWorkspaceSystemReconcileResult:
        system_cfg = self._google_workspace_config.system
        if not system_cfg.enabled:
            return GoogleWorkspaceSystemReconcileResult(ensured=False)
        if system_cfg.service_account_json is None:
            raise CompanyIntegrationConfigError(
                "google_workspace.system.service_account_json is required when enabled"
            )
        _ = await self.upsert_google_workspace_service_account(
            SYSTEM_COMPANY_ID,
            GoogleWorkspaceCompanyCredentialPut(
                service_account_json=system_cfg.service_account_json,
                impersonate_email=system_cfg.impersonate_email,
            ),
            allow_system=True,
        )
        return GoogleWorkspaceSystemReconcileResult(ensured=True)
