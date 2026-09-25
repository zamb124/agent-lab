"""Контекст CRM TaskIQ-воркера: company + user без привязки к очереди задач."""

from __future__ import annotations

from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation, AuthzSubjectKind
from core.context import set_context
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.utils.tokens import TokenType, get_token_service

# user_id из set_crm_context без реального пользователя — не искать в user_repository
_WORKER_PLACEHOLDER_USER_IDS = frozenset({"crm-worker"})


async def set_crm_context(
    company_id: str,
    namespace: str | None = None,
    auth_token: str | None = None,
    user_id: str | None = None,
    interface_language: str | None = None,
) -> None:
    if namespace is None:
        normalized_namespace = ""
    else:
        s = str(namespace).strip()
        if not s:
            raise ValueError(
                "namespace: empty string is not allowed, pass None when the context has no workspace"
            )
        normalized_namespace = s
    resolved_user_id = user_id or "crm-worker"
    lang = Language(interface_language) if interface_language is not None else Language.RU
    company_row = await Company.get(company_id)
    if company_row is None:
        raise ValueError(f"Company not found for CRM worker context: {company_id}")
    context = Context(
        user=User(user_id=resolved_user_id, name="CRM Worker"),
        active_company=company_row,
        session_id=f"crm-worker:{company_id}",
        channel="taskiq",
        active_namespace=normalized_namespace,
        auth_token=auth_token,
        language=lang,
    )
    _ = set_context(context)


async def build_auth_token_for_company(
    company_id: str,
    user_id: str | None,
    *,
    authz: AuthzService,
) -> str:
    resolved_user_id = user_id
    if resolved_user_id in _WORKER_PLACEHOLDER_USER_IDS:
        resolved_user_id = None
    if not resolved_user_id:
        company = await Company.get(company_id)
        if company is None:
            raise ValueError(f"Company not found for daily summary rebuild: {company_id}")
        if company.owner_user_id and company.owner_user_id.strip():
            resolved_user_id = company.owner_user_id.strip()
        else:
            subjects = await authz.list_users(
                AuthzObject.company(company_id),
                AuthzRelation.CAN_ADMIN,
            )
            admin_ids = sorted(
                {
                    subject.value.strip()
                    for subject in subjects
                    if subject.kind is AuthzSubjectKind.USER and subject.value.strip() != ""
                }
            )
            if not admin_ids:
                raise ValueError(f"No company CAN_ADMIN for daily summary: {company_id}")
            resolved_user_id = admin_ids[0]

    user = await User.get(resolved_user_id)
    if user is None:
        raise ValueError(f"User not found for daily summary auth token: {resolved_user_id}")

    token_service = get_token_service()
    return token_service.create_token(
        user_id=resolved_user_id,
        company_id=company_id,
        roles=user.companies.get(company_id, []),
        token_type=TokenType.SESSION,
    )


__all__ = ["build_auth_token_for_company", "set_crm_context"]
