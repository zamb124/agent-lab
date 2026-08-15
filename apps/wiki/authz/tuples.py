"""Wiki-specific OpenFGA tuple helpers."""

from __future__ import annotations

from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.types import AuthzRelation


def wiki_page_owner_tuple(wiki_page_id: str, owner_user_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.user(owner_user_id),
        relation=AuthzRelation.OWNER,
        obj=AuthzObject.wiki_page(wiki_page_id),
    )


def wiki_page_parent_tuple(wiki_page_id: str, parent_page_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.wiki_page(parent_page_id)),
        relation=AuthzRelation.PARENT,
        obj=AuthzObject.wiki_page(wiki_page_id),
    )


def wiki_page_company_link(wiki_page_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
        relation=AuthzRelation.COMPANY,
        obj=AuthzObject.wiki_page(wiki_page_id),
    )


def wiki_page_company_viewer_tuple(wiki_page_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.company_member(company_id),
        relation=AuthzRelation.COMPANY_VIEWER,
        obj=AuthzObject.wiki_page(wiki_page_id),
    )


def wiki_page_member_tuple(
    wiki_page_id: str, user_id: str, relation: AuthzRelation
) -> AuthzTuple:
    if relation not in (AuthzRelation.VIEWER, AuthzRelation.EDITOR):
        raise ValueError(f"wiki page member relation must be viewer|editor, got {relation}")
    return AuthzTuple(
        subject=AuthzSubject.user(user_id),
        relation=relation,
        obj=AuthzObject.wiki_page(wiki_page_id),
    )
