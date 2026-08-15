"""Sync-specific OpenFGA tuple helpers."""

from __future__ import annotations

from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.types import AuthzRelation

_CHANNEL_MEMBER_RELATIONS: frozenset[AuthzRelation] = frozenset(
    {
        AuthzRelation.OWNER,
        AuthzRelation.ADMIN,
        AuthzRelation.MEMBER,
    }
)


def sync_channel_company_link(channel_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
        relation=AuthzRelation.COMPANY,
        obj=AuthzObject.sync_channel(channel_id),
    )


def sync_channel_member_tuple(
    channel_id: str, user_id: str, relation: AuthzRelation
) -> AuthzTuple:
    if relation not in _CHANNEL_MEMBER_RELATIONS:
        raise ValueError(
            f"sync_channel member relation must be owner|admin|member, got {relation}"
        )
    return AuthzTuple(
        subject=AuthzSubject.user(user_id),
        relation=relation,
        obj=AuthzObject.sync_channel(channel_id),
    )
