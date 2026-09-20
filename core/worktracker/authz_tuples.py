"""Worktracker work_queue OpenFGA tuple helpers."""

from __future__ import annotations

from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.types import AuthzRelation

_QUEUE_MEMBER_RELATIONS: frozenset[AuthzRelation] = frozenset(
    {
        AuthzRelation.OWNER,
        AuthzRelation.MEMBER,
    }
)


def work_queue_company_link(work_queue_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
        relation=AuthzRelation.COMPANY,
        obj=AuthzObject.work_queue(work_queue_id),
    )


def work_queue_owner_tuple(work_queue_id: str, owner_user_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.user(owner_user_id),
        relation=AuthzRelation.OWNER,
        obj=AuthzObject.work_queue(work_queue_id),
    )


def work_queue_member_tuple(
    work_queue_id: str, user_id: str, relation: AuthzRelation
) -> AuthzTuple:
    if relation not in _QUEUE_MEMBER_RELATIONS:
        raise ValueError(f"work_queue member relation must be owner|member, got {relation}")
    return AuthzTuple(
        subject=AuthzSubject.user(user_id),
        relation=relation,
        obj=AuthzObject.work_queue(work_queue_id),
    )
