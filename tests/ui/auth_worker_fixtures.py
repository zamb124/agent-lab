"""Session auth для UI E2E: компании per xdist-worker (не shared ``system``)."""

from __future__ import annotations

from core.authz.company_sync import sync_company_member_roles
from core.models.identity_models import User
from core.utils.tokens import get_token_service
from tests.fixtures.ai_provider_defaults import (
    company_with_test_ai_provider_defaults,
    make_test_company,
)
from tests.ui.e2e_worker import (
    ui_e2e_company2_id,
    ui_e2e_company_id,
    ui_e2e_subdomain,
    ui_e2e_subdomain_company2,
    ui_e2e_worker_id,
)


async def _ensure_company_member(
    frontend_container,
    *,
    company_id: str,
    company_name: str,
    subdomain: str,
    user_id: str,
    user_name: str,
    roles: list[str],
) -> str:
    existing = await frontend_container.company_repository.get(company_id)
    if existing is None:
        company = make_test_company(
            company_id=company_id,
            name=company_name,
            owner_user_id=user_id,
            members={user_id: roles},
            subdomain=subdomain,
        )
        await frontend_container.company_repository.set(company)
    else:
        existing = company_with_test_ai_provider_defaults(existing)
        if user_id not in existing.members:
            existing.members[user_id] = roles
        if existing.subdomain != subdomain:
            existing.subdomain = subdomain
        await frontend_container.company_repository.set(existing)
    await frontend_container.subdomain_repository.set_mapping(subdomain, company_id)

    user = User(
        user_id=user_id,
        name=user_name,
        emails=[f"{user_id}@{company_id}.test"],
        companies={company_id: roles},
        active_company_id=company_id,
    )
    await frontend_container.user_repository.set(user)
    await sync_company_member_roles(
        frontend_container.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=roles,
    )

    token_service = get_token_service()
    return token_service.create_token(user_id, company_id=company_id, roles=roles)


async def create_ui_e2e_owner_token(frontend_container) -> str:
    worker = ui_e2e_worker_id()
    company_id = ui_e2e_company_id()
    return await _ensure_company_member(
        frontend_container,
        company_id=company_id,
        company_name=f"UI E2E {company_id}",
        subdomain=ui_e2e_subdomain(),
        user_id=f"ui_owner_{worker}",
        user_name="System User 1",
        roles=["owner", "admin"],
    )


async def create_ui_e2e_member_token(frontend_container) -> str:
    worker = ui_e2e_worker_id()
    company_id = ui_e2e_company_id()
    return await _ensure_company_member(
        frontend_container,
        company_id=company_id,
        company_name=f"UI E2E {company_id}",
        subdomain=ui_e2e_subdomain(),
        user_id=f"ui_member_{worker}",
        user_name="System User 2",
        roles=["member"],
    )


async def create_ui_e2e_company2_owner_token(frontend_container) -> str:
    worker = ui_e2e_worker_id()
    company_id = ui_e2e_company2_id()
    return await _ensure_company_member(
        frontend_container,
        company_id=company_id,
        company_name=f"UI E2E {company_id}",
        subdomain=ui_e2e_subdomain_company2(),
        user_id=f"ui_c2_owner_{worker}",
        user_name="Company2 User 1",
        roles=["owner", "admin"],
    )


async def create_ui_e2e_company2_member_token(frontend_container) -> str:
    worker = ui_e2e_worker_id()
    company_id = ui_e2e_company2_id()
    return await _ensure_company_member(
        frontend_container,
        company_id=company_id,
        company_name=f"UI E2E {company_id}",
        subdomain=ui_e2e_subdomain_company2(),
        user_id=f"ui_c2_member_{worker}",
        user_name="Company2 User 2",
        roles=["member"],
    )
