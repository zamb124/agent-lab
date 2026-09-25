"""Stock-specific OpenFGA tuple helpers."""

from __future__ import annotations

from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.types import AuthzRelation


def stock_warehouse_company_link(warehouse_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
        relation=AuthzRelation.COMPANY,
        obj=AuthzObject.stock_warehouse(warehouse_id, company_id=company_id),
    )


def stock_warehouse_owner_tuple(warehouse_id: str, company_id: str, owner_user_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.user(owner_user_id),
        relation=AuthzRelation.OWNER,
        obj=AuthzObject.stock_warehouse(warehouse_id, company_id=company_id),
    )


def stock_warehouse_member_tuple(
    warehouse_id: str, company_id: str, user_id: str, relation: AuthzRelation
) -> AuthzTuple:
    if relation not in (AuthzRelation.VIEWER, AuthzRelation.EDITOR):
        raise ValueError(
            f"stock warehouse member relation must be viewer|editor, got {relation}"
        )
    return AuthzTuple(
        subject=AuthzSubject.user(user_id),
        relation=relation,
        obj=AuthzObject.stock_warehouse(warehouse_id, company_id=company_id),
    )


def stock_warehouse_company_member_tuple(
    warehouse_id: str, company_id: str, relation: AuthzRelation
) -> AuthzTuple:
    """Доступ всей компании (`company#member`) к складу: viewer|editor."""
    if relation not in (AuthzRelation.VIEWER, AuthzRelation.EDITOR):
        raise ValueError(
            f"stock warehouse company-member relation must be viewer|editor, got {relation}"
        )
    return AuthzTuple(
        subject=AuthzSubject.company_member(company_id),
        relation=relation,
        obj=AuthzObject.stock_warehouse(warehouse_id, company_id=company_id),
    )
