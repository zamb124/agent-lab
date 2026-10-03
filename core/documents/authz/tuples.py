"""Tuples дерева Документов."""

from __future__ import annotations

from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.types import AuthzRelation


def document_catalog_owner_tuple(catalog_id: str, owner_user_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.user(owner_user_id),
        relation=AuthzRelation.OWNER,
        obj=AuthzObject.document_catalog(catalog_id),
    )


def document_catalog_company_link(catalog_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
        relation=AuthzRelation.COMPANY,
        obj=AuthzObject.document_catalog(catalog_id),
    )


def document_catalog_parent_tuple(catalog_id: str, parent_catalog_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.document_catalog(parent_catalog_id)),
        relation=AuthzRelation.PARENT,
        obj=AuthzObject.document_catalog(catalog_id),
    )


def document_catalog_lister_tuple(catalog_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.company_member(company_id),
        relation=AuthzRelation.LISTER,
        obj=AuthzObject.document_catalog(catalog_id),
    )


def document_catalog_company_viewer_tuple(catalog_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.company_member(company_id),
        relation=AuthzRelation.VIEWER,
        obj=AuthzObject.document_catalog(catalog_id),
    )


def document_catalog_source_tuple(catalog_id: str, source: AuthzObject) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(source),
        relation=AuthzRelation.SOURCE,
        obj=AuthzObject.document_catalog(catalog_id),
    )


def document_catalog_member_tuple(
    catalog_id: str, user_id: str, relation: AuthzRelation
) -> AuthzTuple:
    if relation not in (AuthzRelation.VIEWER, AuthzRelation.EDITOR):
        raise ValueError(f"document catalog member relation must be viewer|editor, got {relation}")
    return AuthzTuple(
        subject=AuthzSubject.user(user_id),
        relation=relation,
        obj=AuthzObject.document_catalog(catalog_id),
    )


def document_file_owner_tuple(file_id: str, owner_user_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.user(owner_user_id),
        relation=AuthzRelation.OWNER,
        obj=AuthzObject.document_file(file_id),
    )


def document_file_catalog_link(file_id: str, catalog_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.document_catalog(catalog_id)),
        relation=AuthzRelation.CATALOG,
        obj=AuthzObject.document_file(file_id),
    )


def document_file_source_tuple(file_id: str, source: AuthzObject) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(source),
        relation=AuthzRelation.SOURCE,
        obj=AuthzObject.document_file(file_id),
    )


def document_file_member_tuple(file_id: str, user_id: str, relation: AuthzRelation) -> AuthzTuple:
    if relation not in (AuthzRelation.VIEWER, AuthzRelation.EDITOR):
        raise ValueError(f"document file member relation must be viewer|editor, got {relation}")
    return AuthzTuple(
        subject=AuthzSubject.user(user_id),
        relation=relation,
        obj=AuthzObject.document_file(file_id),
    )
