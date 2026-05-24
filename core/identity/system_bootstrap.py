"""Bootstrap инварианты для системной компании."""

from __future__ import annotations

from typing import Protocol, cast

from core.db.repositories.company_repository import CompanyRepository
from core.db.repositories.subdomain_repository import SubdomainRepository
from core.db.repositories.user_repository import UserRepository
from core.logging import get_logger
from core.models.identity_models import Company, User

logger = get_logger(__name__)

SYSTEM_COMPANY_ID = "system"
SYSTEM_COMPANY_SUBDOMAIN = "system"
SYSTEM_COMPANY_NAME = "System"
SYSTEM_ADMIN_EMAIL = "zambas124@yandex.ru"
ADMIN_ROLE = "admin"


class SystemBootstrapContainer(Protocol):
    @property
    def company_repository(self) -> CompanyRepository: ...

    @property
    def subdomain_repository(self) -> SubdomainRepository: ...

    @property
    def user_repository(self) -> UserRepository: ...


def as_system_bootstrap_container(container: object) -> SystemBootstrapContainer:
    return cast(SystemBootstrapContainer, container)


async def ensure_system_company_exists(container: SystemBootstrapContainer) -> Company:
    """Гарантирует наличие system-компании в shared storage."""
    company = await container.company_repository.get(SYSTEM_COMPANY_ID)
    if company is None:
        company = Company(
            company_id=SYSTEM_COMPANY_ID,
            name=SYSTEM_COMPANY_NAME,
            subdomain=SYSTEM_COMPANY_SUBDOMAIN,
            members={},
        )
        _ = await container.company_repository.set(company)
        logger.info("Bootstrap created system company")

    company_needs_update = False
    if company.subdomain != SYSTEM_COMPANY_SUBDOMAIN:
        company.subdomain = SYSTEM_COMPANY_SUBDOMAIN
        company_needs_update = True

    if company_needs_update:
        _ = await container.company_repository.set(company)
        logger.info("Bootstrap updated system company subdomain to %s", SYSTEM_COMPANY_SUBDOMAIN)

    _ = await container.subdomain_repository.set_mapping(SYSTEM_COMPANY_SUBDOMAIN, SYSTEM_COMPANY_ID)
    return company


async def ensure_system_admin_membership(
    container: SystemBootstrapContainer,
    *,
    user_email: str = SYSTEM_ADMIN_EMAIL,
) -> tuple[Company, User | None]:
    """Гарантирует system-компанию и при наличии пользователя user_email — роль admin в ней."""
    system_company = await ensure_system_company_exists(container)

    users = await container.user_repository.list(limit=10000)
    matched_users = [user for user in users if user_email in user.emails]
    if not matched_users:
        logger.warning(
            "Bootstrap skipped admin grant: user with email %s not found",
            user_email,
        )
        return system_company, None
    if len(matched_users) > 1:
        matched_user_ids = ", ".join(user.user_id for user in matched_users)
        raise ValueError(f"Multiple users found for {user_email}: {matched_user_ids}")

    target_user = matched_users[0]
    company_roles = system_company.members.get(target_user.user_id, [])
    user_roles = target_user.companies.get(system_company.company_id, [])
    company_needs_update = ADMIN_ROLE not in company_roles
    user_needs_update = ADMIN_ROLE not in user_roles

    if company_needs_update:
        system_company.members[target_user.user_id] = [*company_roles, ADMIN_ROLE]
    if user_needs_update:
        target_user.companies[system_company.company_id] = [*user_roles, ADMIN_ROLE]

    if company_needs_update or user_needs_update:
        _ = await container.company_repository.set(system_company)
        _ = await container.user_repository.set(target_user)
        logger.info(
            "Bootstrap updated: granted admin role for %s in company %s",
            user_email,
            system_company.company_id,
        )
    else:
        logger.info(
            "Bootstrap check passed: %s already has admin rights in %s",
            user_email,
            system_company.company_id,
        )

    return system_company, target_user
