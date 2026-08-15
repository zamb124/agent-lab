"""Company membership domain mutations + OpenFGA sync (PDP только FGA)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from core.authz.company_sync import remove_company_member, sync_company_member_roles
from core.authz.errors import AuthzUnavailable
from core.authz.service import AuthzService
from core.db.repositories.company_repository import CompanyRepository
from core.db.repositories.user_repository import UserRepository
from core.models.identity_models import Company, User


def _normalize_roles(roles: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    for role in roles:
        clean = role.strip()
        if clean and clean not in normalized:
            normalized.append(clean)
    if not normalized:
        raise ValueError("company membership roles must be non-empty")
    return normalized


async def set_company_member_roles(
    *,
    company_repository: CompanyRepository,
    user_repository: UserRepository,
    authz: AuthzService,
    company: Company,
    user: User,
    roles: Sequence[str],
) -> list[str]:
    """Пишет двустороннее членство (roster) и sync tuples в OpenFGA (fail-closed).

    При ошибке OpenFGA откатывает roster к предыдущему состоянию.
    """
    normalized = _normalize_roles(roles)
    previous_company_roles = list(company.members.get(user.user_id, []))
    previous_user_roles = list(user.companies.get(company.company_id, []))
    had_company_membership = user.user_id in company.members
    had_user_membership = company.company_id in user.companies
    previous_active_company_id = user.active_company_id

    now = datetime.now(timezone.utc)
    company.members[user.user_id] = list(normalized)
    company.updated_at = now
    user.companies[company.company_id] = list(normalized)
    user.updated_at = now
    _ = await company_repository.set(company)
    _ = await user_repository.set(user)
    try:
        await sync_company_member_roles(
            authz,
            company_id=company.company_id,
            user_id=user.user_id,
            roles=normalized,
        )
    except AuthzUnavailable:
        if had_company_membership:
            company.members[user.user_id] = previous_company_roles
        else:
            del company.members[user.user_id]
        company.updated_at = datetime.now(timezone.utc)
        if had_user_membership:
            user.companies[company.company_id] = previous_user_roles
        else:
            del user.companies[company.company_id]
        user.active_company_id = previous_active_company_id
        user.updated_at = datetime.now(timezone.utc)
        _ = await company_repository.set(company)
        _ = await user_repository.set(user)
        raise
    return normalized


async def remove_company_membership(
    *,
    company_repository: CompanyRepository,
    user_repository: UserRepository,
    authz: AuthzService,
    company: Company,
    user: User,
    allow_empty_companies: bool = False,
) -> None:
    """Снимает членство с обеих сторон и удаляет OpenFGA tuples.

    При ошибке OpenFGA восстанавливает roster.
    """
    previous_company_roles = list(company.members.get(user.user_id, []))
    previous_user_roles = list(user.companies.get(company.company_id, []))
    previous_active_company_id = user.active_company_id
    had_company_membership = user.user_id in company.members
    had_user_membership = company.company_id in user.companies

    now = datetime.now(timezone.utc)
    if user.user_id in company.members:
        del company.members[user.user_id]
        company.updated_at = now
        _ = await company_repository.set(company)
    if company.company_id in user.companies:
        del user.companies[company.company_id]
        if user.active_company_id == company.company_id:
            remaining = list(user.companies.keys())
            if not remaining:
                if not allow_empty_companies:
                    raise ValueError(
                        f"user {user.user_id} has no companies after leaving {company.company_id}"
                    )
                user.active_company_id = ""
            else:
                user.active_company_id = remaining[0]
        user.updated_at = now
        _ = await user_repository.set(user)
    try:
        await remove_company_member(
            authz,
            company_id=company.company_id,
            user_id=user.user_id,
        )
    except AuthzUnavailable:
        if had_company_membership:
            company.members[user.user_id] = previous_company_roles
            company.updated_at = datetime.now(timezone.utc)
            _ = await company_repository.set(company)
        if had_user_membership:
            user.companies[company.company_id] = previous_user_roles
            user.active_company_id = previous_active_company_id
            user.updated_at = datetime.now(timezone.utc)
            _ = await user_repository.set(user)
        raise


async def sync_existing_company_member(
    *,
    authz: AuthzService,
    company_id: str,
    user_id: str,
    roles: Sequence[str],
) -> None:
    """Только OpenFGA sync после внешней мутации membership (merge/bootstrap)."""
    await sync_company_member_roles(
        authz,
        company_id=company_id,
        user_id=user_id,
        roles=roles,
    )
