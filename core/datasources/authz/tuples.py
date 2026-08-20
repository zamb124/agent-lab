"""OpenFGA tuples для company-owned datasource."""

from __future__ import annotations

from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.types import AuthzRelation


def datasource_company_link(datasource_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
        relation=AuthzRelation.COMPANY,
        obj=AuthzObject.datasource(datasource_id, company_id=company_id),
    )


def datasource_platform_link(datasource_id: str, *, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.platform()),
        relation=AuthzRelation.PLATFORM,
        obj=AuthzObject.datasource(datasource_id, company_id=company_id),
    )


def datasource_owner_tuple(
    datasource_id: str, owner_user_id: str, *, company_id: str
) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.user(owner_user_id),
        relation=AuthzRelation.OWNER,
        obj=AuthzObject.datasource(datasource_id, company_id=company_id),
    )


def datasource_company_viewer_tuple(datasource_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.company_member(company_id),
        relation=AuthzRelation.VIEWER,
        obj=AuthzObject.datasource(datasource_id, company_id=company_id),
    )
