"""Команды компаний: проверка slug, создание, system-access участников компании system.

Перевыпуск SESSION JWT и `Set-Cookie` — граница HTTP (REST-зеркало через
`attach_session_auth_cookie`); по WS клиент после создания компании делает полную
навигацию на `redirect_url`, и `AuthMiddleware` (host-wins) перепривязывает сессию сам.
"""

from __future__ import annotations

import uuid

from pydantic import Field

from apps.frontend.di import Di
from apps.idle_worker.tasks.task_names import TASK_INIT_NEW_COMPANY
from core.errors.boundary import PlatformAccessDeniedError, PlatformNotFoundError
from core.identity.company_membership import (
    remove_company_membership,
    set_company_member_roles,
)
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.identity_models import SYSTEM_COMPANY_ID, Company, User
from core.namespace import ensure_personal_namespace_for_user
from core.tasks import enqueue
from core.utils.domain import build_url
from core.utils.subdomain import validate_slug
from core.websocket import raise_invalid

logger = get_logger(__name__)

SYSTEM_ASSIGNABLE_ROLES: tuple[str, ...] = ("admin", "developer", "viewer")


class CompanySlugCheckPayload(StrictBaseModel):
    slug: str = Field(min_length=1)


class CompanySlugCheckResult(StrictBaseModel):
    available: bool
    slug: str


class CompanyCreatePayload(StrictBaseModel):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    public_host: str = Field(min_length=1, description="Host браузера — apex для redirect_url на субдомен")


class CompanyCreated(StrictBaseModel):
    company_id: str
    name: str
    subdomain: str
    redirect_url: str


class SystemAccessGrantPayload(StrictBaseModel):
    company_id: str = Field(min_length=1)
    role: str = Field(min_length=1)


class SystemAccessGranted(StrictBaseModel):
    success: bool = True
    company_id: str
    roles: list[str]


class SystemAccessRevokePayload(StrictBaseModel):
    company_id: str = Field(min_length=1)


class SystemAccessRevoked(StrictBaseModel):
    success: bool = True
    company_id: str
    switched_to_system: bool


def _require_system_member(user: User) -> None:
    if SYSTEM_COMPANY_ID not in user.companies:
        raise PlatformAccessDeniedError("Available only to members of the system company", error_code='forbidden')


async def op_companies_slug_check(
    payload: CompanySlugCheckPayload, *, user: User, di: Di
) -> CompanySlugCheckResult:
    _ = user
    _ = di
    slug = payload.slug.lower().strip()
    is_valid, _ = validate_slug(slug)
    if not is_valid:
        return CompanySlugCheckResult(available=False, slug=slug)
    existing = await Company.by_subdomain(slug)
    return CompanySlugCheckResult(available=existing is None, slug=slug)


async def op_companies_create(
    payload: CompanyCreatePayload, *, user: User, di: Di
) -> CompanyCreated:
    name = payload.name.strip()
    slug = payload.slug.lower().strip()
    if not name:
        raise_invalid(ValueError("company name is required"))
    is_valid, error = validate_slug(slug)
    if not is_valid:
        raise_invalid(ValueError(error))
    if await Company.by_subdomain(slug) is not None:
        raise_invalid(ValueError("this address is already taken"))

    company = Company(
        company_id=str(uuid.uuid4()),
        name=name,
        subdomain=slug,
        owner_user_id=user.user_id,
        status="active",
        members={user.user_id: ["owner"]},
        metadata={"initialization_status": "pending"},
    )
    _ = await Company.set(company)
    user.companies[company.company_id] = ["owner"]
    user.active_company_id = company.company_id
    _ = await set_company_member_roles(
        authz=di.authz_service,
        company=company,
        user=user,
        roles=["owner"],
    )
    await ensure_personal_namespace_for_user(di.namespace_service, user, company=company)
    init_task = await enqueue(
        TASK_INIT_NEW_COMPANY,
        company_id=company.company_id,
        company_name=name,
        subdomain=slug,
        owner_user_id=user.user_id,
    )
    logger.info(
        "frontend.company_created",
        company_id=company.company_id,
        company_subdomain=slug,
        owner_user_id=user.user_id,
        taskiq_task_id=init_task.task_id,
    )
    return CompanyCreated(
        company_id=company.company_id,
        name=company.name,
        subdomain=slug,
        redirect_url=build_url(payload.public_host, "/dashboard", slug),
    )


async def _require_target_company(company_id: str) -> Company:
    target_company_id = company_id.strip()
    if not target_company_id:
        raise_invalid(ValueError("company_id must not be empty"))
    if target_company_id == SYSTEM_COMPANY_ID:
        raise_invalid(ValueError("cannot change access to the system company through this endpoint"))
    target_company = await Company.get(target_company_id)
    if target_company is None:
        raise PlatformNotFoundError("Company not found", error_code='not_found')
    return target_company


async def op_companies_system_access_grant(
    payload: SystemAccessGrantPayload, *, user: User, di: Di
) -> SystemAccessGranted:
    """Участник компании system входит в чужую компанию с ролью admin/developer/viewer."""
    _require_system_member(user)
    role = payload.role.strip()
    if role not in SYSTEM_ASSIGNABLE_ROLES:
        raise_invalid(ValueError(f"invalid role: {role}. allowed: {', '.join(SYSTEM_ASSIGNABLE_ROLES)}"))
    target_company = await _require_target_company(payload.company_id)
    existing_roles = target_company.members.get(user.user_id, [])
    merged_roles = list(dict.fromkeys([*existing_roles, role]))
    _ = await set_company_member_roles(
        authz=di.authz_service,
        company=target_company,
        user=user,
        roles=merged_roles,
    )
    await ensure_personal_namespace_for_user(di.namespace_service, user, company=target_company)
    return SystemAccessGranted(company_id=target_company.company_id, roles=merged_roles)


async def op_companies_system_access_revoke(
    payload: SystemAccessRevokePayload, *, user: User, di: Di
) -> SystemAccessRevoked:
    """Выход из чужой компании; если она была активной — активная снова `system`."""
    _require_system_member(user)
    target_company = await _require_target_company(payload.company_id)
    if user.user_id not in target_company.members or target_company.company_id not in user.companies:
        raise PlatformNotFoundError("User is not a member of the selected company", error_code='not_found')
    switched_to_system = user.active_company_id == target_company.company_id
    await remove_company_membership(
        authz=di.authz_service,
        company=target_company,
        user=user,
    )
    if switched_to_system:
        user.active_company_id = SYSTEM_COMPANY_ID
        _ = await User.set(user)
    return SystemAccessRevoked(company_id=target_company.company_id, switched_to_system=switched_to_system)
