"""Unit smoke: wiki_page OpenFGA model."""

from __future__ import annotations

import pytest

from apps.wiki.authz.tuples import (
    wiki_page_company_link,
    wiki_page_company_viewer_tuple,
    wiki_page_member_tuple,
    wiki_page_owner_tuple,
    wiki_page_parent_tuple,
)
from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation
from core.identity.company_membership import set_company_member_roles
from core.models.identity_models import Company, User

pytestmark = [pytest.mark.timeout(60)]


@pytest.mark.asyncio
async def test_wiki_page_parent_ttu_viewer_editor_inheritance(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    owner_id = f"owner-{unique_id}"
    viewer_id = f"viewer-{unique_id}"
    editor_id = f"editor-{unique_id}"
    stranger_id = f"stranger-{unique_id}"
    parent_id = f"page-parent-{unique_id}"
    child_id = f"page-child-{unique_id}"

    await authz_service.write(
        [
            wiki_page_owner_tuple(parent_id, owner_id),
            wiki_page_member_tuple(parent_id, viewer_id, AuthzRelation.VIEWER),
            wiki_page_member_tuple(parent_id, editor_id, AuthzRelation.EDITOR),
            wiki_page_owner_tuple(child_id, owner_id),
            wiki_page_parent_tuple(child_id, parent_id),
        ]
    )

    child = AuthzObject.wiki_page(child_id)
    assert await authz_service.can_view(child, user_id=owner_id) is True
    assert await authz_service.can_view(child, user_id=viewer_id) is True
    assert await authz_service.can_edit(child, user_id=editor_id) is True
    assert await authz_service.can_edit(child, user_id=viewer_id) is False
    assert await authz_service.can_view(child, user_id=stranger_id) is False


@pytest.mark.asyncio
async def test_wiki_page_company_direct_can_view_not_edit(
    authz_service: AuthzService,
    unique_id: str,
    frontend_container,
) -> None:
    company_id = f"co-wiki-{unique_id}"
    owner_id = f"owner-{unique_id}"
    member_id = f"member-{unique_id}"
    stranger_id = f"stranger-{unique_id}"
    page_id = f"page-company-{unique_id}"

    company_repository = frontend_container.company_repository
    user_repository = frontend_container.user_repository
    company = Company(company_id=company_id, name="Wiki", subdomain=f"w-{unique_id}")
    owner = User(user_id=owner_id, name="Owner", companies={})
    member = User(user_id=member_id, name="Member", companies={})
    _ = await company_repository.set(company)
    _ = await user_repository.set(owner)
    _ = await user_repository.set(member)
    _ = await set_company_member_roles(
        company_repository=company_repository,
        user_repository=user_repository,
        authz=authz_service,
        company=company,
        user=owner,
        roles=["owner"],
    )
    company = await company_repository.get(company_id)
    assert company is not None
    _ = await set_company_member_roles(
        company_repository=company_repository,
        user_repository=user_repository,
        authz=authz_service,
        company=company,
        user=member,
        roles=["member"],
    )

    await authz_service.write(
        [
            wiki_page_owner_tuple(page_id, owner_id),
            wiki_page_company_link(page_id, company_id),
            wiki_page_company_viewer_tuple(page_id, company_id),
        ]
    )

    page = AuthzObject.wiki_page(page_id)
    assert await authz_service.can_view(page, user_id=member_id) is True
    assert await authz_service.can_edit(page, user_id=member_id) is False
    assert await authz_service.can_view(page, user_id=stranger_id) is False


@pytest.mark.asyncio
async def test_wiki_private_child_under_public_parent_does_not_inherit_company(
    authz_service: AuthzService,
    unique_id: str,
    frontend_container,
) -> None:
    company_id = f"co-wiki-priv-{unique_id}"
    owner_id = f"owner-{unique_id}"
    member_id = f"member-{unique_id}"
    parent_id = f"page-pub-parent-{unique_id}"
    child_id = f"page-priv-child-{unique_id}"

    company_repository = frontend_container.company_repository
    user_repository = frontend_container.user_repository
    company = Company(company_id=company_id, name="Wiki Private", subdomain=f"wp-{unique_id}")
    owner = User(user_id=owner_id, name="Owner", companies={})
    member = User(user_id=member_id, name="Member", companies={})
    _ = await company_repository.set(company)
    _ = await user_repository.set(owner)
    _ = await user_repository.set(member)
    _ = await set_company_member_roles(
        company_repository=company_repository,
        user_repository=user_repository,
        authz=authz_service,
        company=company,
        user=owner,
        roles=["owner"],
    )
    company = await company_repository.get(company_id)
    assert company is not None
    _ = await set_company_member_roles(
        company_repository=company_repository,
        user_repository=user_repository,
        authz=authz_service,
        company=company,
        user=member,
        roles=["member"],
    )

    await authz_service.write(
        [
            wiki_page_owner_tuple(parent_id, owner_id),
            wiki_page_company_link(parent_id, company_id),
            wiki_page_company_viewer_tuple(parent_id, company_id),
            wiki_page_owner_tuple(child_id, owner_id),
            wiki_page_parent_tuple(child_id, parent_id),
        ]
    )

    parent = AuthzObject.wiki_page(parent_id)
    child = AuthzObject.wiki_page(child_id)
    assert await authz_service.can_view(parent, user_id=member_id) is True
    assert await authz_service.can_view(child, user_id=member_id) is False


@pytest.mark.asyncio
async def test_wiki_page_can_admin_owner_only(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    owner_id = f"owner-{unique_id}"
    editor_id = f"editor-{unique_id}"
    page_id = f"page-admin-{unique_id}"

    await authz_service.write(
        [
            wiki_page_owner_tuple(page_id, owner_id),
            wiki_page_member_tuple(page_id, editor_id, AuthzRelation.EDITOR),
        ]
    )

    page = AuthzObject.wiki_page(page_id)
    assert await authz_service.can_admin(page, user_id=owner_id) is True
    assert await authz_service.can_admin(page, user_id=editor_id) is False
    assert await authz_service.can_edit(page, user_id=editor_id) is True
