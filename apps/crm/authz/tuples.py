"""CRM-specific OpenFGA tuple helpers. Shared company/user — в core.authz."""

from __future__ import annotations

from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.types import AuthzRelation


def crm_entity_owner_tuple(entity_id: str, owner_user_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.user(owner_user_id),
        relation=AuthzRelation.OWNER,
        obj=AuthzObject.crm_entity(entity_id),
    )


def crm_entity_namespace_link(
    entity_id: str, company_id: str, namespace: str
) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.crm_namespace(company_id, namespace)),
        relation=AuthzRelation.NAMESPACE,
        obj=AuthzObject.crm_entity(entity_id),
    )


def crm_namespace_company_link(company_id: str, namespace: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
        relation=AuthzRelation.COMPANY,
        obj=AuthzObject.crm_namespace(company_id, namespace),
    )


def crm_namespace_company_viewer_tuple(company_id: str, namespace: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.company_member(company_id),
        relation=AuthzRelation.VIEWER,
        obj=AuthzObject.crm_namespace(company_id, namespace),
    )


def crm_namespace_company_editor_tuple(company_id: str, namespace: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.company_member(company_id),
        relation=AuthzRelation.EDITOR,
        obj=AuthzObject.crm_namespace(company_id, namespace),
    )


def crm_grant_tuple(
    *,
    resource_type: str,
    resource_id: str,
    resource_company_id: str,
    grant_type: str,
    role: str,
    target_user_id: str | None,
    target_company_id: str | None,
) -> AuthzTuple:
    relation = AuthzRelation(role)
    if resource_type == "entity":
        obj = AuthzObject.crm_entity(resource_id)
    elif resource_type == "namespace":
        obj = AuthzObject.crm_namespace(resource_company_id, resource_id)
    else:
        raise ValueError(f"unsupported CRM grant resource_type: {resource_type}")

    if grant_type == "public":
        subject = AuthzSubject.public()
    elif grant_type == "user":
        if not target_user_id:
            raise ValueError("target_user_id is required for user grant")
        subject = AuthzSubject.user(target_user_id)
    elif grant_type == "company":
        if not target_company_id:
            raise ValueError("target_company_id is required for company grant")
        subject = AuthzSubject.company_member(target_company_id)
    else:
        raise ValueError(f"unsupported CRM grant_type: {grant_type}")

    return AuthzTuple(subject=subject, relation=relation, obj=obj)
