"""Bootstrap инварианты для системной компании."""

from __future__ import annotations

from core.authz.company_sync import sync_company_member_roles
from core.authz.service import AuthzService
from core.context.job_context import build_job_context
from core.logging import get_logger
from core.models.context_models import Context
from core.models.identity_models import SYSTEM_COMPANY_ID, Company, User

logger = get_logger(__name__)

SYSTEM_COMPANY_SUBDOMAIN = "system"
SYSTEM_COMPANY_NAME = "System"
SYSTEM_ADMIN_EMAIL = "zambas124@yandex.ru"
ADMIN_ROLE = "admin"


async def ensure_system_company_exists() -> Company:
    """Гарантирует наличие system-компании в shared storage."""
    company = await Company.get(SYSTEM_COMPANY_ID)
    if company is None:
        company = Company(
            company_id=SYSTEM_COMPANY_ID,
            name=SYSTEM_COMPANY_NAME,
            subdomain=SYSTEM_COMPANY_SUBDOMAIN,
            members={},
        )
        _ = await Company.set(company)
        logger.info("identity.bootstrap.created.system.company")

    company_needs_update = False
    if company.subdomain != SYSTEM_COMPANY_SUBDOMAIN:
        company.subdomain = SYSTEM_COMPANY_SUBDOMAIN
        company_needs_update = True

    if company_needs_update:
        _ = await Company.set(company)
        logger.info("identity.bootstrap.updated.system.company.subdomain", SYSTEM_COMPANY_SUBDOMAIN=SYSTEM_COMPANY_SUBDOMAIN)

    return company


async def _users_for_admin_email(user_email: str) -> list[User]:
    matched_users = await User.list_containing_email_ci_by_user_id_asc(user_email)
    if len(matched_users) > 1:
        matched_user_ids = ", ".join(user.user_id for user in matched_users)
        raise ValueError(f"Multiple users found for {user_email}: {matched_user_ids}")
    return matched_users


async def load_system_admin_membership(
    *,
    user_email: str = SYSTEM_ADMIN_EMAIL,
) -> tuple[Company, User]:
    """Читает system-компанию и admin-пользователя. Без FGA и без roster-мутаций."""
    company = await Company.get(SYSTEM_COMPANY_ID)
    if company is None:
        raise ValueError("system company is required")
    matched_users = await _users_for_admin_email(user_email)
    if not matched_users:
        raise ValueError(f"system admin user {user_email} not found")
    target_user = matched_users[0]
    company_roles = company.members.get(target_user.user_id, [])
    user_roles = target_user.companies.get(company.company_id, [])
    if ADMIN_ROLE not in company_roles or ADMIN_ROLE not in user_roles:
        raise ValueError(
            f"system admin roster missing admin role for {user_email} in {company.company_id}"
        )
    return company, target_user


async def build_system_admin_job_context(
    *,
    trace_id: str,
    session_id: str,
    channel: str = "system",
) -> Context:
    """``Context`` + JWT системного админа для scheduler-тиков и фоновых задач платформы."""
    company, user = await load_system_admin_membership()
    return build_job_context(
        company=company,
        user=user,
        host="system",
        trace_id=trace_id,
        session_id=session_id,
        channel=channel,
    )


async def ensure_system_admin_membership(
    *,
    authz: AuthzService,
    user_email: str = SYSTEM_ADMIN_EMAIL,
) -> tuple[Company, User | None]:
    """Гарантирует system-компанию и при наличии пользователя user_email — роль admin в ней."""
    system_company = await ensure_system_company_exists()

    matched_users = await _users_for_admin_email(user_email)
    if not matched_users:
        logger.warning("identity.bootstrap.skipped.admin.grant.user", user_email=user_email)
        return system_company, None

    target_user = matched_users[0]
    company_roles = system_company.members.get(target_user.user_id, [])
    user_roles = target_user.companies.get(system_company.company_id, [])
    company_needs_update = ADMIN_ROLE not in company_roles
    user_needs_update = ADMIN_ROLE not in user_roles

    if company_needs_update:
        stored = await Company.put_member_roles(
            system_company.company_id,
            target_user.user_id,
            [*company_roles, ADMIN_ROLE],
        )
        system_company.members = stored.members
        system_company.updated_at = stored.updated_at
    if user_needs_update:
        target_user.companies[system_company.company_id] = [*user_roles, ADMIN_ROLE]

    if user_needs_update:
        _ = await User.set(target_user)
    if company_needs_update or user_needs_update:
        await sync_company_member_roles(
            authz,
            company_id=system_company.company_id,
            user_id=target_user.user_id,
            roles=system_company.members[target_user.user_id],
        )
        logger.info("identity.bootstrap.updated.granted.admin.role", user_email=user_email, company_id=system_company.company_id)

    return system_company, target_user
