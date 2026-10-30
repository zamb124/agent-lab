"""Company membership domain mutations + OpenFGA sync (PDP только FGA)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from core.authz.company_sync import remove_company_member, sync_company_member_roles
from core.authz.errors import AuthzUnavailable
from core.authz.group_sync import sync_user_groups
from core.authz.service import AuthzService
from core.models.identity_models import Company, User, UserStatus


def _normalize_roles(roles: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    for role in roles:
        clean = role.strip()
        if clean and clean not in normalized:
            normalized.append(clean)
    if not normalized:
        raise ValueError("company membership roles must be non-empty")
    return normalized


def _apply_stored_roster(company: Company, stored: Company) -> None:
    company.members = stored.members
    company.updated_at = stored.updated_at


async def set_company_member_roles(
    *,
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

    user.companies[company.company_id] = list(normalized)
    user.updated_at = datetime.now(timezone.utc)
    stored = await Company.put_member_roles(
        company.company_id,
        user.user_id,
        normalized,
    )
    _apply_stored_roster(company, stored)
    _ = await User.set(user)
    try:
        await sync_company_member_roles(
            authz,
            company_id=company.company_id,
            user_id=user.user_id,
            roles=normalized,
        )
    except AuthzUnavailable:
        if had_company_membership:
            rolled = await Company.put_member_roles(
                company.company_id,
                user.user_id,
                previous_company_roles,
            )
        else:
            rolled = await Company.discard_member(
                company.company_id,
                user.user_id,
            )
        _apply_stored_roster(company, rolled)
        if had_user_membership:
            user.companies[company.company_id] = previous_user_roles
        else:
            del user.companies[company.company_id]
        user.active_company_id = previous_active_company_id
        user.updated_at = datetime.now(timezone.utc)
        _ = await User.set(user)
        raise
    return normalized


async def remove_company_membership(
    *,
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
        stored = await Company.discard_member(company.company_id, user.user_id)
        _apply_stored_roster(company, stored)
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
        _ = await User.set(user)
    try:
        await remove_company_member(
            authz,
            company_id=company.company_id,
            user_id=user.user_id,
        )
    except AuthzUnavailable:
        if had_company_membership:
            rolled = await Company.put_member_roles(
                company.company_id,
                user.user_id,
                previous_company_roles,
            )
            _apply_stored_roster(company, rolled)
        if had_user_membership:
            user.companies[company.company_id] = previous_user_roles
            user.active_company_id = previous_active_company_id
            user.updated_at = datetime.now(timezone.utc)
            _ = await User.set(user)
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


SYSTEM_ACTOR_USER_ID = "system"
_SYSTEM_ACTOR_ROLES: tuple[str, ...] = ("owner", "admin")
_SYSTEM_ACTOR_GROUPS: tuple[str, ...] = ("admin", "developers")


async def ensure_system_actor_membership(*, authz: AuthzService, company_id: str) -> None:
    """Двустороннее членство ``user:system`` — roster и OpenFGA грант вместе.

    Middleware создаёт ``User('system')`` как internal runtime user с roster
    ``['guest']``: FGA-только грант при таком roster стирается первым же
    roster-derived sync — поэтому roster здесь приводится к owner/admin.
    Компании без строки (init до создания) получают user-side roster + FGA.
    """
    company = await Company.get(company_id)
    user = await User.get(SYSTEM_ACTOR_USER_ID)
    if user is None:
        user = User(
            user_id=SYSTEM_ACTOR_USER_ID,
            name="System",
            status=UserStatus.ACTIVE,
            groups=list(_SYSTEM_ACTOR_GROUPS),
            companies={},
            active_company_id=company_id,
            emails=[],
            attributes={"kind": "internal_platform_context", "runtime_identity": True},
        )
    merged_groups = list(dict.fromkeys([*user.groups, *_SYSTEM_ACTOR_GROUPS]))
    if merged_groups != user.groups:
        user.groups = merged_groups
    if company is None:
        user.companies[company_id] = list(_SYSTEM_ACTOR_ROLES)
        user.updated_at = datetime.now(timezone.utc)
        _ = await User.set(user)
        await sync_company_member_roles(
            authz,
            company_id=company_id,
            user_id=SYSTEM_ACTOR_USER_ID,
            roles=_SYSTEM_ACTOR_ROLES,
        )
    else:
        _ = await set_company_member_roles(
            authz=authz,
            company=company,
            user=user,
            roles=_SYSTEM_ACTOR_ROLES,
        )
    await sync_user_groups(
        authz,
        user_id=SYSTEM_ACTOR_USER_ID,
        groups=list(_SYSTEM_ACTOR_GROUPS),
        company_ids=[company_id],
        previous_groups=[],
    )
