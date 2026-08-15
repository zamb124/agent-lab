"""Office-specific OpenFGA tuple helpers."""

from __future__ import annotations

from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.types import AuthzRelation


def office_catalog_owner_tuple(catalog_id: str, owner_user_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.user(owner_user_id),
        relation=AuthzRelation.OWNER,
        obj=AuthzObject.office_catalog(catalog_id),
    )


def office_catalog_parent_tuple(catalog_id: str, parent_catalog_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.office_catalog(parent_catalog_id)),
        relation=AuthzRelation.PARENT,
        obj=AuthzObject.office_catalog(catalog_id),
    )


def office_catalog_company_link(catalog_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
        relation=AuthzRelation.COMPANY,
        obj=AuthzObject.office_catalog(catalog_id),
    )


def office_catalog_company_viewer_tuple(catalog_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.company_member(company_id),
        relation=AuthzRelation.VIEWER,
        obj=AuthzObject.office_catalog(catalog_id),
    )


def office_catalog_member_tuple(
    catalog_id: str, user_id: str, relation: AuthzRelation
) -> AuthzTuple:
    if relation not in (AuthzRelation.VIEWER, AuthzRelation.EDITOR):
        raise ValueError(f"office catalog member relation must be viewer|editor, got {relation}")
    return AuthzTuple(
        subject=AuthzSubject.user(user_id),
        relation=relation,
        obj=AuthzObject.office_catalog(catalog_id),
    )


def office_document_owner_tuple(file_id: str, owner_user_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.user(owner_user_id),
        relation=AuthzRelation.OWNER,
        obj=AuthzObject.office_document(file_id),
    )


def office_document_catalog_link(file_id: str, catalog_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.office_catalog(catalog_id)),
        relation=AuthzRelation.CATALOG,
        obj=AuthzObject.office_document(file_id),
    )


def office_document_member_tuple(
    file_id: str, user_id: str, relation: AuthzRelation
) -> AuthzTuple:
    if relation not in (AuthzRelation.VIEWER, AuthzRelation.EDITOR):
        raise ValueError(f"office document member relation must be viewer|editor, got {relation}")
    return AuthzTuple(
        subject=AuthzSubject.user(user_id),
        relation=relation,
        obj=AuthzObject.office_document(file_id),
    )
