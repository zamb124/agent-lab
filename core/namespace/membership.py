"""Хелпер: после записи membership гарантировать personal namespace."""

from __future__ import annotations

from core.context import get_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.namespace.service import NamespaceService


async def ensure_personal_namespace_for_user(
    namespace_service: NamespaceService,
    user: User,
    *,
    company: Company | None = None,
) -> None:
    """
    Идемпотентно создаёт personal Namespace для user.

    Если передан ``company`` и он не совпадает с active_company в Context —
    временно переключает контекст на эту компанию (и восстанавливает после).
    """
    display_name = user.name.strip()
    if display_name == "":
        raise ValueError(
            f"user {user.user_id} has empty name; cannot create personal namespace"
        )

    previous: Context | None = get_context()
    switched = False
    if company is not None:
        active = previous.active_company if previous is not None else None
        if active is None or active.company_id != company.company_id:
            if previous is None:
                raise ValueError(
                    "ensure_personal_namespace_for_user requires Context when switching company"
                )
            set_context(
                previous.model_copy(
                    update={
                        "active_company": company,
                        "user": user.model_copy(
                            update={"active_company_id": company.company_id}
                        ),
                    }
                )
            )
            switched = True

    try:
        _ = await namespace_service.ensure_personal_namespace(
            user.user_id,
            display_name=display_name,
        )
    finally:
        if switched and previous is not None:
            set_context(previous)
