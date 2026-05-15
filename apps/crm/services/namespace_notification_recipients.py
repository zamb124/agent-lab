"""
Получатели broadcast-уведомлений CRM по namespace (участники компании + гранты на namespace).
Используется для daily summary и WS-событий заметок.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.crm.db.repositories.access_grant_repository import AccessGrantRepository
    from core.db.repositories import CompanyRepository


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
    company_repository: CompanyRepository,
    access_grant_repository: AccessGrantRepository,
) -> list[str]:
    company = await company_repository.get(company_id)
    if company is None:
        raise ValueError(f"Company not found for namespace broadcast: {company_id}")

    company_user_ids = set(company.members.keys())
    if company.owner_user_id:
        company_user_ids.add(company.owner_user_id)
    if not company_user_ids:
        raise ValueError(f"Company has no members for namespace broadcast: {company_id}")

    normalized_namespace = normalize_namespace_for_broadcast(namespace)
    recipients: set[str] = set(company_user_ids)
    if normalized_namespace in {"all", "default"}:
        return sorted(recipients)

    grants = await access_grant_repository.find_by_resource(
        resource_type="namespace",
        resource_id=normalized_namespace,
        resource_company_id=company_id,
    )
    for grant in grants:
        if grant.grant_type == "public":
            continue
        if grant.grant_type == "user":
            if not grant.target_user_id:
                raise ValueError("Namespace user grant must contain target_user_id")
            recipients.add(grant.target_user_id)
            continue
        if grant.grant_type == "company":
            if not grant.target_company_id:
                raise ValueError("Namespace company grant must contain target_company_id")
            target_company = await company_repository.get(grant.target_company_id)
            if target_company is None:
                raise ValueError(
                    f"Target company not found for namespace grant: {grant.target_company_id}"
                )
            recipients.update(target_company.members.keys())
            if target_company.owner_user_id:
                recipients.add(target_company.owner_user_id)
    return sorted(recipients)
