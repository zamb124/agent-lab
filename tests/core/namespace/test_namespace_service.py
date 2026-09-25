"""Unit tests for NamespaceService personal/kind canon."""


from __future__ import annotations

import pytest

from core.authz.company_sync import sync_company_member_roles
from core.authz.models import AuthzObject
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, NamespaceKind, User, UserStatus
from core.namespace.service import (
    NamespaceService,
    infer_namespace_kind,
    personal_namespace_name,
)
from tests.fixtures.auth import set_test_company_member_roles  # noqa: F401


def test_personal_namespace_name() -> None:
    assert personal_namespace_name("u1") == "user-u1"
    with pytest.raises(ValueError):
        personal_namespace_name("  ")


def test_infer_namespace_kind() -> None:
    assert infer_namespace_kind("default") == NamespaceKind.COMPANY_WORKSPACE
    assert infer_namespace_kind("sales") == NamespaceKind.COMPANY_WORKSPACE
    assert infer_namespace_kind("user-abc") == NamespaceKind.PERSONAL
    assert infer_namespace_kind("office-catalog-x") == NamespaceKind.TECHNICAL
    assert infer_namespace_kind("llm-memory-x") == NamespaceKind.TECHNICAL
    assert infer_namespace_kind("wiki-restricted-sales") == NamespaceKind.TECHNICAL


@pytest.fixture()
def namespace_service(di) -> NamespaceService:
    return di.namespace_service


@pytest.fixture()
def company_context(unique_id: str):
    company_id = f"nsco_{unique_id}"
    user = User(
        user_id=f"nsu_{unique_id}",
        name=f"NS User {unique_id}",
        status=UserStatus.ACTIVE,
        companies={company_id: ["owner"]},
        active_company_id=company_id,
    )
    company = Company(
        company_id=company_id,
        name=f"NS Co {unique_id}",
        subdomain=f"ns{unique_id}"[:32],
        owner_user_id=user.user_id,
        members={user.user_id: ["owner"]},
    )
    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )
    try:
        yield company, user
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_ensure_personal_namespace(
    namespace_service: NamespaceService,
    company_context: tuple[Company, User],
    unique_id: str,
) -> None:
    _company, user = company_context
    display = f"Person {unique_id}"
    first = await namespace_service.ensure_personal_namespace(
        user.user_id, display_name=display
    )
    assert first.kind == NamespaceKind.PERSONAL
    assert first.name == personal_namespace_name(user.user_id)
    assert first.owner_user_id == user.user_id
    assert first.description == display
    second = await namespace_service.ensure_personal_namespace(
        user.user_id, display_name=display
    )
    assert second.name == first.name
    renamed = await namespace_service.ensure_personal_namespace(
        user.user_id, display_name=f"Renamed {unique_id}"
    )
    assert renamed.description == f"Renamed {unique_id}"


@pytest.mark.asyncio
async def test_create_rejects_personal_via_create(
    namespace_service: NamespaceService,
    company_context: tuple[Company, User],
    unique_id: str,
) -> None:
    _ = company_context
    with pytest.raises(ValueError, match="ensure_personal_namespace"):
        _ = await namespace_service.create(
            name=f"ws_{unique_id}",
            kind=NamespaceKind.PERSONAL,
            owner_user_id=f"u_{unique_id}",
        )


@pytest.mark.asyncio
async def test_list_excludes_technical(
    namespace_service: NamespaceService,
    company_context: tuple[Company, User],
    unique_id: str,
) -> None:
    _ = company_context
    tech_name = f"office-catalog-{unique_id}"
    _ = await namespace_service.get_or_create(
        tech_name,
        description="tech",
        kind=NamespaceKind.TECHNICAL,
    )
    product = await namespace_service.list(limit=500)
    assert all(ns.kind != NamespaceKind.TECHNICAL for ns in product)
    workspaces = await namespace_service.list_company_workspaces(limit=500)
    assert all(ns.kind == NamespaceKind.COMPANY_WORKSPACE for ns in workspaces)


@pytest.mark.asyncio
async def test_ensure_exists_repairs_missing_platform_namespace_tuples(
    namespace_service: NamespaceService,
    company_context: tuple[Company, User],
    di,
) -> None:
    company, user = company_context
    await sync_company_member_roles(
        di.authz_service,
        company_id=company.company_id,
        user_id=user.user_id,
        roles=["owner"],
    )
    created = await namespace_service.create(name=f"ws_{user.user_id}")
    obj = AuthzObject.platform_namespace(company.company_id, created.name)
    existing = await di.authz_service.list_tuples(obj)
    assert existing
    await di.authz_service.delete(existing)
    assert await di.authz_service.can_view(obj, user_id=user.user_id) is False

    repaired = await namespace_service.ensure_exists(created.name)
    assert repaired.name == created.name
    assert await di.authz_service.can_view(obj, user_id=user.user_id) is True
