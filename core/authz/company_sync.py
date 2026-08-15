"""Синхронизация company membership ↔ OpenFGA + admin gates (только FGA)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.authz.ids import is_openfga_user_subject_id
from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation
from core.models.identity_models import Company

# Roster roles → FGA company relations. `member` is the flow-employee roster role.
# Company can_view = member (TTU: owner → admin → member). Direct member tuple
# keeps tenancy Check 1-hop; without it secrets/flows Check denies under OpenFGA load.
_COMPANY_ROLE_RELATION: Mapping[str, AuthzRelation] = {
    "owner": AuthzRelation.OWNER,
    "admin": AuthzRelation.ADMIN,
    "developer": AuthzRelation.MEMBER,
    "viewer": AuthzRelation.MEMBER,
    "member": AuthzRelation.MEMBER,
}


def company_roles_imply_admin(roles: Sequence[str]) -> bool:
    """Roster helper: roles содержат owner/admin. Не PDP — check_company_admin для ACL."""
    return any(role in ("owner", "admin") for role in roles)


def company_role_tuples(company_id: str, user_id: str, roles: Sequence[str]) -> list[AuthzTuple]:
    obj = AuthzObject.company(company_id)
    subject = AuthzSubject.user(user_id)
    tuples: list[AuthzTuple] = []
    seen: set[AuthzRelation] = set()
    for role in roles:
        relation = _COMPANY_ROLE_RELATION.get(role)
        if relation is None or relation in seen:
            continue
        seen.add(relation)
        tuples.append(AuthzTuple(subject=subject, relation=relation, obj=obj))
    if roles and AuthzRelation.MEMBER not in seen:
        tuples.append(
            AuthzTuple(subject=subject, relation=AuthzRelation.MEMBER, obj=obj)
        )
    return tuples


async def sync_company_member_roles(
    authz: AuthzService,
    *,
    company_id: str,
    user_id: str,
    roles: Sequence[str],
) -> None:
    """Fail-closed write в OpenFGA (AuthzService.assert type company).

    Synthetic AuthN ids с ``:`` (``guest:…``, share visitor tokens) не являются
    OpenFGA ``user:<id>`` — dual-write пропускает их, как ``sync_user_groups``.
    """
    if not is_openfga_user_subject_id(user_id):
        return
    obj = AuthzObject.company(company_id)
    subject = AuthzSubject.user(user_id)
    desired = {
        item.relation for item in company_role_tuples(company_id, user_id, roles)
    }
    deletes = [
        AuthzTuple(subject=subject, relation=relation, obj=obj)
        for relation in (
            AuthzRelation.OWNER,
            AuthzRelation.ADMIN,
            AuthzRelation.MEMBER,
        )
        if relation not in desired
    ]
    writes = company_role_tuples(company_id, user_id, roles)
    await authz.write_and_delete(writes, deletes)


async def remove_company_member(
    authz: AuthzService,
    *,
    company_id: str,
    user_id: str,
) -> None:
    if not is_openfga_user_subject_id(user_id):
        return
    obj = AuthzObject.company(company_id)
    subject = AuthzSubject.user(user_id)
    await authz.delete(
        [
            AuthzTuple(subject=subject, relation=relation, obj=obj)
            for relation in (
                AuthzRelation.OWNER,
                AuthzRelation.ADMIN,
                AuthzRelation.MEMBER,
            )
        ]
    )


async def check_company_admin(
    authz: AuthzService,
    *,
    user_id: str,
    company: Company,
) -> bool:
    """Thin re-export: AuthzService.can_admin на company."""
    return await authz.can_admin(
        AuthzObject.company(company.company_id), user_id=user_id
    )


async def require_company_admin(
    authz: AuthzService,
    *,
    user_id: str,
    company: Company,
) -> None:
    """Thin re-export: AuthzService.require_can_admin на company."""
    await authz.require_can_admin(
        AuthzObject.company(company.company_id), user_id=user_id
    )
