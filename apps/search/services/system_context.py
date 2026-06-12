"""System context for platform search and crawl workers."""

from __future__ import annotations

from core.context import Context
from core.db.repositories.company_repository import CompanyRepository
from core.db.repositories.subdomain_repository import SubdomainRepository
from core.db.repositories.user_repository import UserRepository
from core.identity.system_bootstrap import ensure_system_admin_membership
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service


async def build_search_system_context(
    *,
    trace_id: str,
    company_repository: CompanyRepository,
    subdomain_repository: SubdomainRepository,
    user_repository: UserRepository,
    channel: str = "search",
) -> Context:
    company, user = await ensure_system_admin_membership(
        company_repository=company_repository,
        subdomain_repository=subdomain_repository,
        user_repository=user_repository,
    )
    if user is None:
        raise ValueError("system admin user is required for search system context")
    roles = user.companies.get(company.company_id, [])
    auth_token = get_token_service().create_token(
        user_id=user.user_id,
        company_id=company.company_id,
        roles=roles,
    )
    return Context(
        user=User(user_id=user.user_id, name=user.name or user.user_id, groups=user.groups),
        host="system",
        session_id=f"search:{trace_id}",
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
