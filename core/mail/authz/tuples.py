"""Mail mailbox_binding OpenFGA tuple helpers."""

from __future__ import annotations

from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.types import AuthzRelation

_MAIL_MEMBER_RELATIONS: frozenset[AuthzRelation] = frozenset(
    {
        AuthzRelation.MEMBER,
        AuthzRelation.MANAGER,
    }
)


def mailbox_binding_company_link(mailbox_binding_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
        relation=AuthzRelation.COMPANY,
        obj=AuthzObject.mailbox_binding(mailbox_binding_id),
    )


def mailbox_binding_owner_tuple(mailbox_binding_id: str, owner_user_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.user(owner_user_id),
        relation=AuthzRelation.OWNER,
        obj=AuthzObject.mailbox_binding(mailbox_binding_id),
    )


def mailbox_binding_member_tuple(
    mailbox_binding_id: str, user_id: str, relation: AuthzRelation
) -> AuthzTuple:
    if relation not in _MAIL_MEMBER_RELATIONS:
        raise ValueError(
            f"mailbox_binding member relation must be member|manager, got {relation}"
        )
    return AuthzTuple(
        subject=AuthzSubject.user(user_id),
        relation=relation,
        obj=AuthzObject.mailbox_binding(mailbox_binding_id),
    )
