"""
Получатели broadcast-уведомлений CRM по namespace.

Для realtime note/summary delivery используется ``publish_event_to_company``:
``crm_namespace.can_view`` включает ``company#member``, и ``list_users``
разворачивает весь roster (под нагрузкой — ``deadline_exceeded``).

``resolve_user_ids_for_namespace_broadcast`` — только для точечных сценариев
(тесты/админские списки), не для hot-path fanout на каждый note create.
"""

from __future__ import annotations

from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.authz.types import AuthzObjectType, AuthzRelation, AuthzSubjectKind


def normalize_namespace_for_broadcast(namespace: str | None) -> str:
    if namespace is None:
        return "all"
    if namespace.strip() == "":
        return "all"
    return namespace


async def resolve_user_ids_for_namespace_broadcast(
    company_id: str,
    namespace: str | None,
    *,
    authz: AuthzService,
) -> list[str]:
    """Развернуть recipients через OpenFGA list_users (дорого на большом roster)."""
    normalized_namespace = normalize_namespace_for_broadcast(namespace)
    if normalized_namespace in {"all", "default"}:
        subjects = await authz.list_users(
            AuthzObject.company(company_id),
            AuthzRelation.MEMBER,
            user_filters=(AuthzObjectType.USER,),
        )
    else:
        subjects = await authz.list_users(
            AuthzObject.crm_namespace(company_id, normalized_namespace),
            AuthzRelation.CAN_VIEW,
            user_filters=(AuthzObjectType.USER,),
        )

    user_ids: set[str] = set()
    for subject in subjects:
        if subject.kind is AuthzSubjectKind.USER:
            user_ids.add(subject.value)
            continue
        if subject.kind is AuthzSubjectKind.PUBLIC:
            continue
        raise ValueError(
            f"namespace broadcast unexpected subject kind: {subject.kind.value}"
        )
    if not user_ids:
        message = (
            "No FGA recipients for namespace broadcast: "
            f"company={company_id} namespace={normalized_namespace}"
        )
        raise ValueError(message)
    return sorted(user_ids)
