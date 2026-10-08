from __future__ import annotations

import pytest

from apps.flows.di import FlowsDi
from core.authz.company_sync import sync_company_member_roles
from core.identity.system_bootstrap import (
    ensure_system_admin_membership,
    ensure_system_company_exists,
    load_system_admin_membership,
)
from core.models.identity_models import SYSTEM_COMPANY_ID, Company, User
from tests.fixtures.auth import set_test_company_member_roles  # noqa: F401


@pytest.mark.asyncio
async def test_bootstrap_adds_admin_role_to_system_company_and_user(
    app,
    di: FlowsDi,
    unique_id: str,
) -> None:
    _ = app
    user_id = f"bootstrap_admin_{unique_id}"
    email = f"{user_id}@example.com"
    _ = await User.set(
        User(
            user_id=user_id,
            name="Viktor",
            emails=[email],
            companies={SYSTEM_COMPANY_ID: ["viewer"]},
        )
    )
    try:
        await ensure_system_admin_membership(
            authz=di.authz_service,
            user_email=email,
        )
        stored_user = await User.get(user_id)
        stored_company = await Company.get(SYSTEM_COMPANY_ID)
        assert stored_user is not None
        assert stored_company is not None
        assert "admin" in stored_company.members[user_id]
        assert "admin" in stored_user.companies[SYSTEM_COMPANY_ID]
        assert await di.authz_service.check_company_admin(
            company_id=SYSTEM_COMPANY_ID,
            user_id=user_id,
        )
    finally:
        _ = await Company.discard_member(SYSTEM_COMPANY_ID, user_id)
        await sync_company_member_roles(
            di.authz_service,
            company_id=SYSTEM_COMPANY_ID,
            user_id=user_id,
            roles=[],
        )


@pytest.mark.asyncio
async def test_bootstrap_skips_admin_when_target_email_user_missing(
    app,
    di: FlowsDi,
    unique_id: str,
) -> None:
    _ = app
    returned_company, returned_user = await ensure_system_admin_membership(
        authz=di.authz_service,
        user_email=f"missing-{unique_id}@example.com",
    )

    assert returned_company.company_id == SYSTEM_COMPANY_ID
    assert returned_user is None


@pytest.mark.asyncio
async def test_bootstrap_creates_system_company_when_missing(app) -> None:
    _ = app
    company = await ensure_system_company_exists()

    assert company.company_id == SYSTEM_COMPANY_ID
    assert company.subdomain == "system"
    stored = await Company.get(SYSTEM_COMPANY_ID)
    assert stored is not None


@pytest.mark.asyncio
async def test_bootstrap_skips_fga_write_when_already_admin(
    app,
    di: FlowsDi,
    unique_id: str,
) -> None:
    _ = app
    user_id = f"bootstrap_already_{unique_id}"
    email = f"{user_id}@example.com"
    _ = await User.set(
        User(
            user_id=user_id,
            name="Viktor",
            emails=[email],
            companies={SYSTEM_COMPANY_ID: ["admin"]},
        )
    )
    _ = await Company.put_member_roles(SYSTEM_COMPANY_ID, user_id, ["admin"])
    try:
        returned_company, returned_user = await ensure_system_admin_membership(
            authz=di.authz_service,
            user_email=email,
        )
        assert returned_company.company_id == SYSTEM_COMPANY_ID
        assert returned_user is not None
        assert returned_user.user_id == user_id
        assert (
            await di.authz_service.check_company_admin(
                company_id=SYSTEM_COMPANY_ID,
                user_id=user_id,
            )
            is False
        )
    finally:
        _ = await Company.discard_member(SYSTEM_COMPANY_ID, user_id)


@pytest.mark.asyncio
async def test_load_system_admin_membership_returns_existing_admin(app, unique_id: str) -> None:
    _ = app
    user_id = f"load_admin_{unique_id}"
    email = f"{user_id}@example.com"
    _ = await User.set(
        User(
            user_id=user_id,
            name="Viktor",
            emails=[email],
            companies={SYSTEM_COMPANY_ID: ["admin"]},
        )
    )
    _ = await Company.put_member_roles(SYSTEM_COMPANY_ID, user_id, ["admin"])
    try:
        loaded_company, loaded_user = await load_system_admin_membership(
            user_email=email,
        )
        assert loaded_company.company_id == SYSTEM_COMPANY_ID
        assert loaded_user.user_id == user_id
    finally:
        _ = await Company.discard_member(SYSTEM_COMPANY_ID, user_id)


@pytest.mark.asyncio
async def test_load_system_admin_membership_requires_admin_user(app, unique_id: str) -> None:
    _ = app
    with pytest.raises(ValueError, match="system admin user"):
        await load_system_admin_membership(
            user_email=f"missing-admin-{unique_id}@example.com",
        )


@pytest.mark.asyncio
async def test_load_system_admin_membership_requires_admin_role(app, unique_id: str) -> None:
    _ = app
    user_id = f"load_viewer_{unique_id}"
    email = f"{user_id}@example.com"
    _ = await User.set(
        User(
            user_id=user_id,
            name="Viktor",
            emails=[email],
            companies={SYSTEM_COMPANY_ID: ["viewer"]},
        )
    )
    with pytest.raises(ValueError, match="system admin roster missing admin role"):
        await load_system_admin_membership(
            user_email=email,
        )


@pytest.mark.asyncio
async def test_load_system_admin_membership_rejects_duplicate_email(app, unique_id: str) -> None:
    _ = app
    email = f"dup-{unique_id}@example.com"
    user_one_id = f"dup_a_{unique_id}"
    user_two_id = f"dup_b_{unique_id}"
    _ = await User.set(
        User(
            user_id=user_one_id,
            name="Viktor",
            emails=[email],
            companies={SYSTEM_COMPANY_ID: ["admin"]},
        )
    )
    _ = await User.set(
        User(
            user_id=user_two_id,
            name="Viktor-2",
            emails=[email.upper()],
            companies={SYSTEM_COMPANY_ID: ["admin"]},
        )
    )
    with pytest.raises(ValueError, match="Multiple users found"):
        await load_system_admin_membership(
            user_email=email,
        )
