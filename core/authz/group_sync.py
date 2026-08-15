"""Синхронизация User.groups ↔ OpenFGA group#member."""

from __future__ import annotations

from collections.abc import Sequence

from core.authz.ids import PLATFORM_ADMIN_GROUP, is_openfga_user_subject_id
from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.platform_sync import platform_admin_group_tuple
from core.authz.service import AuthzService
from core.authz.types import AuthzObjectType, AuthzRelation


def _normalize_ids(values: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        clean = value.strip()
        if clean and clean not in normalized:
            normalized.append(clean)
    return normalized


def _membership_keys(
    groups: Sequence[str], company_ids: Sequence[str]
) -> set[tuple[str, str | None]]:
    names = _normalize_ids(groups)
    companies = _normalize_ids(company_ids)
    keys: set[tuple[str, str | None]] = set()
    if PLATFORM_ADMIN_GROUP in names:
        keys.add((PLATFORM_ADMIN_GROUP, None))
    tenant_names = [name for name in names if name != PLATFORM_ADMIN_GROUP]
    for company_id in companies:
        for group_name in tenant_names:
            keys.add((group_name, company_id))
    return keys


def group_member_tuple(
    group_name: str, user_id: str, *, company_id: str | None = None
) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.user(user_id),
        relation=AuthzRelation.MEMBER,
        obj=AuthzObject.group(group_name, company_id=company_id),
    )


def group_company_link(group_name: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
        relation=AuthzRelation.COMPANY,
        obj=AuthzObject.group(group_name, company_id=company_id),
    )


def unscoped_group_object(group_name: str) -> AuthzObject:
    """Голый `group:{name}` без company-scope (для backfill delete)."""
    if not group_name or group_name == PLATFORM_ADMIN_GROUP:
        raise ValueError(f"unscoped group name invalid: {group_name!r}")
    return AuthzObject(AuthzObjectType.GROUP, group_name)


async def sync_user_groups(
    authz: AuthzService,
    *,
    user_id: str,
    groups: Sequence[str],
    company_ids: Sequence[str],
    previous_groups: Sequence[str] | None = None,
    previous_company_ids: Sequence[str] | None = None,
) -> None:
    """Fail-closed write: user → member на group:{company}/{name} (admin глобальный).

    Synthetic AuthN ids с ':' не являются OpenFGA ``user:<id>`` — skip dual-write.
    JWT ``User.groups`` — список имён; FGA-объект квалифицируется company_id.
    """
    if not is_openfga_user_subject_id(user_id):
        return
    desired = _membership_keys(groups, company_ids)
    if previous_groups is None:
        previous: set[tuple[str, str | None]] = set()
    else:
        previous_companies = (
            company_ids if previous_company_ids is None else previous_company_ids
        )
        previous = _membership_keys(previous_groups, previous_companies)
    writes: list[AuthzTuple] = []
    for group_name, company_id in sorted(desired - previous, key=lambda item: (item[0], item[1] or "")):
        writes.append(group_member_tuple(group_name, user_id, company_id=company_id))
        if company_id is not None:
            writes.append(group_company_link(group_name, company_id))
    if PLATFORM_ADMIN_GROUP in _normalize_ids(groups):
        writes.append(platform_admin_group_tuple())
    deletes = [
        group_member_tuple(group_name, user_id, company_id=company_id)
        for group_name, company_id in sorted(
            previous - desired, key=lambda item: (item[0], item[1] or "")
        )
    ]
    if writes or deletes:
        await authz.write_and_delete(writes, deletes)


async def remove_user_groups(
    authz: AuthzService,
    *,
    user_id: str,
    groups: Sequence[str],
    company_ids: Sequence[str],
) -> None:
    if not is_openfga_user_subject_id(user_id):
        return
    deletes = [
        group_member_tuple(group_name, user_id, company_id=company_id)
        for group_name, company_id in sorted(
            _membership_keys(groups, company_ids),
            key=lambda item: (item[0], item[1] or ""),
        )
    ]
    if deletes:
        await authz.delete(deletes)


async def delete_unscoped_group_tuples(
    authz: AuthzService, group_names: Sequence[str]
) -> int:
    """Удаляет голые `group:{name}` (не admin) после переноса на company-scope."""
    deleted = 0
    for group_name in _normalize_ids(group_names):
        if group_name == PLATFORM_ADMIN_GROUP:
            continue
        member_tuples = await authz.list_tuples(unscoped_group_object(group_name))
        if member_tuples:
            await authz.delete(member_tuples)
            deleted += len(member_tuples)
    return deleted
