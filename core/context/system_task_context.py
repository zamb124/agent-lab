"""Построение системного контекста для фоновых scheduler/worker задач."""

from __future__ import annotations

from core.identity.system_bootstrap import SYSTEM_ADMIN_EMAIL, ensure_system_admin_membership
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service


async def build_system_auth_context(
    container: object,
    *,
    trace_id: str,
    session_id: str,
    channel: str = "system",
) -> Context:
    """Создаёт системный контекст с active_company и auth_token для фоновой задачи."""
    company, user = await ensure_system_admin_membership(container)
    if user is None:
        raise ValueError(
            f"Нет пользователя с email {SYSTEM_ADMIN_EMAIL}: контекст для фоновых задач не собрать"
        )
    roles = user.companies.get(company.company_id, [])
    auth_token = get_token_service().create_token(
        user_id=user.user_id,
        company_id=company.company_id,
        roles=roles,
    )
    return Context(
        user=User(user_id=user.user_id, name=user.name or user.user_id, groups=user.groups),
        host="system",
        session_id=session_id,
        channel=channel,
        language=Language.RU,
        active_company=Company(
            company_id=company.company_id,
            name=company.name,
            subdomain=company.subdomain,
        ),
        user_companies=[],
        trace_id=trace_id,
        auth_token=auth_token,
    )
