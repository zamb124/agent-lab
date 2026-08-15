"""Phase 2: company membership dual-write + admin gates."""

from __future__ import annotations

import pytest

from core.authz import AuthzRelation, AuthzService, AuthzSubject
from core.authz.company_sync import (
    check_company_admin,
    require_company_admin,
    sync_company_member_roles,
)
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.identity.company_membership import (
    remove_company_membership,
    set_company_member_roles,
)
from core.models.identity_models import Company, User


@pytest.mark.asyncio
async def test_require_company_admin_via_fga(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    company_id = f"co-adm-{unique_id}"
    admin_id = f"admin-{unique_id}"
    member_id = f"member-{unique_id}"
    company = Company(
        company_id=company_id,
        name="Adm",
        subdomain=f"adm-{unique_id}",
        members={admin_id: ["admin"], member_id: ["member"]},
    )

    await sync_company_member_roles(
        authz_service, company_id=company_id, user_id=admin_id, roles=["admin"]
    )
    await sync_company_member_roles(
        authz_service, company_id=company_id, user_id=member_id, roles=["member"]
    )

    assert (
        await check_company_admin(authz_service, user_id=admin_id, company=company)
        is True
    )
    assert (
        await check_company_admin(authz_service, user_id=member_id, company=company)
        is False
    )
    await require_company_admin(authz_service, user_id=admin_id, company=company)
    with pytest.raises(AuthzDenied):
        await require_company_admin(authz_service, user_id=member_id, company=company)

    assert await authz_service.check(
        AuthzSubject.user(admin_id),
        AuthzRelation.CAN_ADMIN,
        AuthzObject.company(company_id),
    )


@pytest.mark.asyncio
async def test_set_and_remove_company_membership_dual_write(
    authz_service: AuthzService,
    frontend_container,
    unique_id: str,
) -> None:
    company_repository = frontend_container.company_repository
    user_repository = frontend_container.user_repository
    company_id = f"co-mem-{unique_id}"
    user_id = f"u-mem-{unique_id}"
    company = Company(
        company_id=company_id,
        name="Mem",
        subdomain=f"mem-{unique_id}",
        members={},
    )
    user = User(user_id=user_id, name="Mem User", companies={})
    _ = await company_repository.set(company)
    _ = await user_repository.set(user)

    roles = await set_company_member_roles(
        company_repository=company_repository,
        user_repository=user_repository,
        authz=authz_service,
        company=company,
        user=user,
        roles=["owner", "admin"],
    )
    assert roles == ["owner", "admin"]

    loaded_company = await company_repository.get(company_id)
    assert loaded_company is not None
    assert loaded_company.members[user_id] == ["owner", "admin"]
    loaded_user = await user_repository.get(user_id)
    assert loaded_user is not None
    assert loaded_user.companies[company_id] == ["owner", "admin"]
    assert await authz_service.check(
        AuthzSubject.user(user_id),
        AuthzRelation.CAN_ADMIN,
        AuthzObject.company(company_id),
    )

    await remove_company_membership(
        company_repository=company_repository,
        user_repository=user_repository,
        authz=authz_service,
        company=loaded_company,
        user=loaded_user,
        allow_empty_companies=True,
    )
    after_company = await company_repository.get(company_id)
    assert after_company is not None
    assert user_id not in after_company.members
    after_user = await user_repository.get(user_id)
    assert after_user is not None
    assert company_id not in after_user.companies
    assert (
        await authz_service.check(
            AuthzSubject.user(user_id),
            AuthzRelation.MEMBER,
            AuthzObject.company(company_id),
        )
        is False
    )


@pytest.mark.asyncio
async def test_sync_company_member_roles_skips_colon_user_id(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    company_id = f"co-skip-{unique_id}"
    await sync_company_member_roles(
        authz_service,
        company_id=company_id,
        user_id=f"guest:{unique_id}",
        roles=["member"],
    )
    assert (
        await authz_service.list_tuples(AuthzObject.company(company_id))
        == []
    )
