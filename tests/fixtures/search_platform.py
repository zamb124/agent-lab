"""Предусловия search-worker для любого теста, который ходит в search: system admin и runet-индекс."""

from __future__ import annotations

import pytest_asyncio

from core.authz.company_sync import sync_company_member_roles
from core.identity.system_bootstrap import (
    ADMIN_ROLE,
    SYSTEM_ADMIN_EMAIL,
    ensure_system_admin_membership,
    ensure_system_company_exists,
)
from core.models.identity_models import SYSTEM_COMPANY_ID, Company, User
from tests.fixtures.search_runet import ensure_runet_platform_index_seeded


@pytest_asyncio.fixture(scope="session")
async def search_worker_prerequisites(setup_database_before_tests, frontend_di) -> None:
    """Worker context (build_system_admin_job_context) и seed runet требуют system admin email."""
    _ = setup_database_before_tests
    company = await ensure_system_company_exists()
    _, admin_user = await ensure_system_admin_membership(authz=frontend_di.authz_service)
    if admin_user is None:
        admin_user_id = "user_zambas124_yandex_ru_test"
        admin_user = User(
            user_id=admin_user_id,
            name="Platform System Admin",
            emails=[SYSTEM_ADMIN_EMAIL],
            companies={SYSTEM_COMPANY_ID: [ADMIN_ROLE]},
        )
        await User.set(admin_user)
        member_roles = list(company.members.get(admin_user_id, []))
        if ADMIN_ROLE not in member_roles:
            member_roles.append(ADMIN_ROLE)
        company.members[admin_user_id] = member_roles
        await Company.set(company)
        await sync_company_member_roles(
            frontend_di.authz_service,
            company_id=SYSTEM_COMPANY_ID,
            user_id=admin_user_id,
            roles=member_roles,
        )
    await ensure_runet_platform_index_seeded()
