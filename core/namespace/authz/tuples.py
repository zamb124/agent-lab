"""Platform namespace OpenFGA tuple helpers."""

from __future__ import annotations

from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.types import AuthzRelation


def platform_namespace_company_link(company_id: str, namespace: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
        relation=AuthzRelation.COMPANY,
        obj=AuthzObject.platform_namespace(company_id, namespace),
    )


def platform_namespace_company_viewer_tuple(
    company_id: str, namespace: str
) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.company_member(company_id),
        relation=AuthzRelation.VIEWER,
        obj=AuthzObject.platform_namespace(company_id, namespace),
    )


def platform_namespace_company_editor_tuple(
    company_id: str, namespace: str
) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.company_member(company_id),
        relation=AuthzRelation.EDITOR,
        obj=AuthzObject.platform_namespace(company_id, namespace),
    )


def platform_namespace_owner_tuple(
    company_id: str, namespace: str, owner_user_id: str
) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.user(owner_user_id),
        relation=AuthzRelation.OWNER,
        obj=AuthzObject.platform_namespace(company_id, namespace),
    )
