"""Команды консоли компании: настройки, команда, инвайты, API-ключи, статус сервисов."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from pydantic import Field

from apps.frontend.container import FrontendContainer
from apps.frontend.models import (
    ApiKey,
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyUpdate,
    CompanySettingsResponse,
    CompanySettingsUpdate,
    CompanySettingsUpdatedCompany,
    CompanySettingsUpdateResponse,
    TeamMemberRemoveResponse,
    TeamMemberRoleUpdateResponse,
    TeamMemberUpdate,
)
from core.context import require_active_company
from core.db.models.platform import ApiKeyRecord
from core.errors.boundary import PlatformNotFoundError
from core.identity.company_membership import (
    remove_company_membership,
    set_company_member_roles,
)
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.identity_models import Company, User
from core.pagination import OffsetPage
from core.request_scope import require_company, require_company_admin
from core.utils.invite_tokens import INVITE_EXPIRES_SECONDS, get_invite_token_service
from core.websocket import EmptyPayload, raise_invalid

logger = get_logger(__name__)

COMPANY_ROLES: frozenset[str] = frozenset({"owner", "admin", "developer", "viewer"})
API_KEY_SCOPES: frozenset[str] = frozenset(
    {"agents:read", "agents:write", "crm:read", "crm:write", "rag:read", "rag:write", "billing:read"}
)
class OffsetPayload(StrictBaseModel):
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class TeamMemberRolesUpdatePayload(TeamMemberUpdate):
    user_id: str = Field(min_length=1)


class TeamMemberIdPayload(StrictBaseModel):
    user_id: str = Field(min_length=1)


class InviteGeneratePayload(StrictBaseModel):
    role: str = "developer"


class InviteGenerated(StrictBaseModel):
    invite_url: str
    role: str
    expires_in_seconds: int


class ApiKeyIdPayload(StrictBaseModel):
    key_id: str = Field(min_length=1)


class ApiKeyRenamePayload(ApiKeyUpdate):
    key_id: str = Field(min_length=1)


class ApiKeyRenamed(StrictBaseModel):
    success: bool = True
    key_id: str
    name: str


class ApiKeyRevoked(StrictBaseModel):
    success: bool = True
    message: str = "API ключ отозван"


def _company_settings(company: Company) -> CompanySettingsResponse:
    return CompanySettingsResponse(
        company_id=company.company_id,
        name=company.name,
        subdomain=company.subdomain,
        owner_user_id=company.owner_user_id,
        status=company.status,
        monthly_budget=company.monthly_budget,
        tariff_plan=company.tariff_plan.value,
        created_at=company.created_at.isoformat(),
        metadata=company.metadata,
    )


async def op_company_settings_get(
    payload: EmptyPayload, *, user: User, container: FrontendContainer
) -> CompanySettingsResponse:
    _ = payload, user, container
    _ = require_company()
    return _company_settings(require_active_company())


async def op_company_settings_update(
    payload: CompanySettingsUpdate, *, user: User, container: FrontendContainer
) -> CompanySettingsUpdateResponse:
    _ = user
    _ = await require_company_admin(container.authz_service)
    company = require_active_company()
    updated = False
    if payload.name is not None:
        company.name = payload.name
        updated = True
    if payload.monthly_budget is not None:
        if payload.monthly_budget < 0:
            raise_invalid(ValueError("monthly_budget cannot be negative"))
        company.monthly_budget = payload.monthly_budget
        updated = True
    if payload.metadata is not None:
        company.metadata.update(payload.metadata)
        updated = True
    if updated:
        _ = await container.company_repository.set(company)
        logger.info("company.settings.updated", company_id=company.company_id)
    return CompanySettingsUpdateResponse(
        message="Настройки обновлены",
        company=CompanySettingsUpdatedCompany(
            name=company.name,
            monthly_budget=company.monthly_budget,
            metadata=company.metadata,
        ),
    )


async def _require_member(container: FrontendContainer, company: Company, user_id: str) -> User:
    if user_id not in company.members:
        raise PlatformNotFoundError("Member not found", error_code='not_found')
    target_user = await container.user_repository.get(user_id)
    if target_user is None:
        raise PlatformNotFoundError("User not found", error_code='not_found')
    return target_user


async def op_team_member_roles_update(
    payload: TeamMemberRolesUpdatePayload, *, user: User, container: FrontendContainer
) -> TeamMemberRoleUpdateResponse:
    _ = user
    _ = await require_company_admin(container.authz_service)
    company = require_active_company()
    target_user = await _require_member(container, company, payload.user_id)
    if payload.user_id == company.owner_user_id and "owner" not in payload.roles:
        raise_invalid(ValueError("cannot remove owner role from the company owner"))
    for role in payload.roles:
        if role not in COMPANY_ROLES:
            raise_invalid(ValueError(f"invalid role: {role}"))
    roles = await set_company_member_roles(
        company_repository=container.company_repository,
        user_repository=container.user_repository,
        authz=container.authz_service,
        company=company,
        user=target_user,
        roles=payload.roles,
    )
    logger.info("team.member.roles_updated", user_id=payload.user_id, company_id=company.company_id)
    return TeamMemberRoleUpdateResponse(user_id=payload.user_id, roles=roles)


async def op_team_member_remove(
    payload: TeamMemberIdPayload, *, user: User, container: FrontendContainer
) -> TeamMemberRemoveResponse:
    _ = user
    _ = await require_company_admin(container.authz_service)
    company = require_active_company()
    target_user = await _require_member(container, company, payload.user_id)
    if payload.user_id == company.owner_user_id:
        raise_invalid(ValueError("cannot remove the company owner"))
    await remove_company_membership(
        company_repository=container.company_repository,
        user_repository=container.user_repository,
        authz=container.authz_service,
        company=company,
        user=target_user,
        allow_empty_companies=True,
    )
    logger.info("team.member.removed", user_id=payload.user_id, company_id=company.company_id)
    return TeamMemberRemoveResponse(message="Участник удален из команды")


async def op_invites_generate(
    payload: InviteGeneratePayload, *, user: User, container: FrontendContainer
) -> InviteGenerated:
    """Одноразовая ссылка-приглашение в компанию; принимает её HTTP `/api/invites/accept` (ставит cookie)."""
    scope = await require_company_admin(container.authz_service)
    if payload.role not in COMPANY_ROLES:
        raise_invalid(ValueError(f"invalid role. allowed: {', '.join(sorted(COMPANY_ROLES))}"))
    token, _ = get_invite_token_service().create(
        company_id=scope.company_id, role=payload.role, invited_by=user.user_id
    )
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=INVITE_EXPIRES_SECONDS)
    invite_url = await container.short_link_service.mint_company_invite(token, expires_at)
    logger.info("invites.generated", company_id=scope.company_id, role=payload.role)
    return InviteGenerated(invite_url=invite_url, role=payload.role, expires_in_seconds=INVITE_EXPIRES_SECONDS)


def _api_key_model(record: ApiKeyRecord) -> ApiKey:
    return ApiKey(
        key_id=record.key_id,
        name=record.name,
        key_prefix=record.key_prefix,
        scopes=record.scopes,
        created_at=record.created_at,
        last_used=record.last_used,
        company_id=record.company_id,
        created_by=record.created_by,
    )


async def op_api_keys_list(
    payload: OffsetPayload, *, user: User, container: FrontendContainer
) -> OffsetPage[ApiKey]:
    _ = user
    scope = require_company()
    records = await container.api_key_repository.list_by_company(
        scope.company_id, limit=payload.limit, offset=payload.offset
    )
    items = [_api_key_model(record) for record in records]
    return OffsetPage[ApiKey](items=items, total=len(items), limit=payload.limit, offset=payload.offset)


async def op_api_keys_create(
    payload: ApiKeyCreate, *, user: User, container: FrontendContainer
) -> ApiKeyCreated:
    """Секрет показывается один раз: в БД хранится только sha256 и префикс."""
    scope = await require_company_admin(container.authz_service)
    for key_scope in payload.scopes:
        if key_scope not in API_KEY_SCOPES:
            raise_invalid(
                ValueError(f"invalid scope: {key_scope}. allowed: {', '.join(sorted(API_KEY_SCOPES))}")
            )
    secret = f"hum_{secrets.token_urlsafe(32)}"
    key_id = f"key_{secrets.token_urlsafe(16)}"
    await container.api_key_repository.create(
        ApiKeyRecord(
            key_id=key_id,
            company_id=scope.company_id,
            name=payload.name,
            key_hash=hashlib.sha256(secret.encode()).hexdigest(),
            key_prefix=secret[:12],
            scopes=payload.scopes,
            created_by=user.user_id,
            revoked=False,
            created_at=datetime.now(timezone.utc),
        )
    )
    logger.info("api_keys.created", key_id=key_id, company_id=scope.company_id)
    return ApiKeyCreated(key_id=key_id, name=payload.name, secret=secret, scopes=payload.scopes)


async def op_api_keys_rename(
    payload: ApiKeyRenamePayload, *, user: User, container: FrontendContainer
) -> ApiKeyRenamed:
    _ = user
    scope = await require_company_admin(container.authz_service)
    updated = await container.api_key_repository.update_name(payload.key_id, scope.company_id, payload.name)
    if not updated:
        raise PlatformNotFoundError("Key not found", error_code='not_found')
    return ApiKeyRenamed(key_id=payload.key_id, name=payload.name)


async def op_api_keys_revoke(
    payload: ApiKeyIdPayload, *, user: User, container: FrontendContainer
) -> ApiKeyRevoked:
    _ = user
    scope = await require_company_admin(container.authz_service)
    revoked = await container.api_key_repository.revoke(payload.key_id, scope.company_id)
    if not revoked:
        raise PlatformNotFoundError("Key not found or already revoked", error_code='not_found')
    return ApiKeyRevoked()
