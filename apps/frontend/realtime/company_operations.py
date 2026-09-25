"""Команды консоли компании: настройки, команда, инвайты, API-ключи, статус сервисов."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from pydantic import Field

from apps.frontend.di import Di
from apps.frontend.models import (
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
from core.errors.boundary import PlatformNotFoundError
from core.identity.company_membership import (
    remove_company_membership,
    set_company_member_roles,
)
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.api_key import ApiKeyRecord
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
    payload: EmptyPayload, *, user: User, di: Di
) -> CompanySettingsResponse:
    _ = payload, user, di
    _ = require_company()
    return _company_settings(require_active_company())


async def op_company_settings_update(
    payload: CompanySettingsUpdate, *, user: User, di: Di
) -> CompanySettingsUpdateResponse:
    _ = user
    _ = await require_company_admin(di.authz_service)
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
        _ = await Company.set(company)
        logger.info("company.settings.updated", company_id=company.company_id)
    return CompanySettingsUpdateResponse(
        message="Настройки обновлены",
        company=CompanySettingsUpdatedCompany(
            name=company.name,
            monthly_budget=company.monthly_budget,
            metadata=company.metadata,
        ),
    )


async def _require_member(company: Company, user_id: str) -> User:
    if user_id not in company.members:
        raise PlatformNotFoundError("Member not found", error_code='not_found')
    target_user = await User.get(user_id)
    if target_user is None:
        raise PlatformNotFoundError("User not found", error_code='not_found')
    return target_user


async def op_team_member_roles_update(
    payload: TeamMemberRolesUpdatePayload, *, user: User, di: Di
) -> TeamMemberRoleUpdateResponse:
    _ = user
    _ = await require_company_admin(di.authz_service)
    company = require_active_company()
    target_user = await _require_member(company, payload.user_id)
    if payload.user_id == company.owner_user_id and "owner" not in payload.roles:
        raise_invalid(ValueError("cannot remove owner role from the company owner"))
    for role in payload.roles:
        if role not in COMPANY_ROLES:
            raise_invalid(ValueError(f"invalid role: {role}"))
    roles = await set_company_member_roles(
        authz=di.authz_service,
        company=company,
        user=target_user,
        roles=payload.roles,
    )
    logger.info("team.member.roles_updated", user_id=payload.user_id, company_id=company.company_id)
    return TeamMemberRoleUpdateResponse(user_id=payload.user_id, roles=roles)


async def op_team_member_remove(
    payload: TeamMemberIdPayload, *, user: User, di: Di
) -> TeamMemberRemoveResponse:
    _ = user
    _ = await require_company_admin(di.authz_service)
    company = require_active_company()
    target_user = await _require_member(company, payload.user_id)
    if payload.user_id == company.owner_user_id:
        raise_invalid(ValueError("cannot remove the company owner"))
    await remove_company_membership(
        authz=di.authz_service,
        company=company,
        user=target_user,
        allow_empty_companies=True,
    )
    logger.info("team.member.removed", user_id=payload.user_id, company_id=company.company_id)
    return TeamMemberRemoveResponse(message="Участник удален из команды")


async def op_invites_generate(
    payload: InviteGeneratePayload, *, user: User, di: Di
) -> InviteGenerated:
    """Одноразовая ссылка-приглашение в компанию; принимает её HTTP `/api/invites/accept` (ставит cookie)."""
    scope = await require_company_admin(di.authz_service)
    if payload.role not in COMPANY_ROLES:
        raise_invalid(ValueError(f"invalid role. allowed: {', '.join(sorted(COMPANY_ROLES))}"))
    token, _ = get_invite_token_service().create(
        company_id=scope.company_id, role=payload.role, invited_by=user.user_id
    )
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=INVITE_EXPIRES_SECONDS)
    invite_url = await di.short_link_service.mint_company_invite(token, expires_at)
    logger.info("invites.generated", company_id=scope.company_id, role=payload.role)
    return InviteGenerated(invite_url=invite_url, role=payload.role, expires_in_seconds=INVITE_EXPIRES_SECONDS)


async def op_api_keys_list(
    payload: OffsetPayload, *, user: User, di: Di
) -> OffsetPage[ApiKeyRecord]:
    _ = user
    _ = di
    scope = require_company()
    records = await ApiKeyRecord.list_by_company(
        scope.company_id, limit=payload.limit, offset=payload.offset
    )
    return OffsetPage[ApiKeyRecord](
        items=records, total=len(records), limit=payload.limit, offset=payload.offset
    )


async def op_api_keys_create(
    payload: ApiKeyCreate, *, user: User, di: Di
) -> ApiKeyCreated:
    """Секрет показывается один раз: в БД хранится только sha256 и префикс."""
    scope = await require_company_admin(di.authz_service)
    for key_scope in payload.scopes:
        if key_scope not in API_KEY_SCOPES:
            raise_invalid(
                ValueError(f"invalid scope: {key_scope}. allowed: {', '.join(sorted(API_KEY_SCOPES))}")
            )
    secret = f"hum_{secrets.token_urlsafe(32)}"
    key_id = f"key_{secrets.token_urlsafe(16)}"
    _ = await ApiKeyRecord.set(
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
    payload: ApiKeyRenamePayload, *, user: User, di: Di
) -> ApiKeyRenamed:
    _ = user
    scope = await require_company_admin(di.authz_service)
    updated = await ApiKeyRecord.update_name(payload.key_id, scope.company_id, payload.name)
    if not updated:
        raise PlatformNotFoundError("Key not found", error_code='not_found')
    return ApiKeyRenamed(key_id=payload.key_id, name=payload.name)


async def op_api_keys_revoke(
    payload: ApiKeyIdPayload, *, user: User, di: Di
) -> ApiKeyRevoked:
    _ = user
    scope = await require_company_admin(di.authz_service)
    revoked = await ApiKeyRecord.revoke(payload.key_id, scope.company_id)
    if not revoked:
        raise PlatformNotFoundError("Key not found or already revoked", error_code='not_found')
    return ApiKeyRevoked()
