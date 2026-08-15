"""Unit smoke: office_catalog / office_document OpenFGA model."""

from __future__ import annotations

import pytest

from apps.office.authz.tuples import (
    office_catalog_company_link,
    office_catalog_company_viewer_tuple,
    office_catalog_member_tuple,
    office_catalog_owner_tuple,
    office_catalog_parent_tuple,
    office_document_catalog_link,
    office_document_member_tuple,
    office_document_owner_tuple,
)
from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation
from core.identity.company_membership import set_company_member_roles
from core.models.identity_models import Company, User

pytestmark = [pytest.mark.timeout(60)]


@pytest.mark.asyncio
async def test_office_catalog_parent_ttu_and_company_visible(
    authz_service: AuthzService,
    unique_id: str,
    frontend_container,
) -> None:
    company_id = f"co-office-{unique_id}"
    owner_id = f"owner-{unique_id}"
    member_id = f"member-{unique_id}"
    peer_id = f"peer-{unique_id}"
    parent_id = f"cat-parent-{unique_id}"
    child_id = f"cat-child-{unique_id}"

    company_repository = frontend_container.company_repository
    user_repository = frontend_container.user_repository
    company = Company(company_id=company_id, name="Office", subdomain=f"o-{unique_id}")
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
            office_catalog_owner_tuple(parent_id, owner_id),
            office_catalog_company_link(parent_id, company_id),
            office_catalog_company_viewer_tuple(parent_id, company_id),
            office_catalog_owner_tuple(child_id, owner_id),
            office_catalog_parent_tuple(child_id, parent_id),
        ]
    )

    parent = AuthzObject.office_catalog(parent_id)
    child = AuthzObject.office_catalog(child_id)
    assert await authz_service.can_view(parent, user_id=member_id) is True
    assert await authz_service.can_view(child, user_id=member_id) is True
    assert await authz_service.can_view(child, user_id=peer_id) is False
    assert await authz_service.can_admin(parent, user_id=owner_id) is True
    assert await authz_service.can_admin(parent, user_id=member_id) is False


@pytest.mark.asyncio
async def test_office_document_inherits_catalog_and_direct_member(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    catalog_id = f"cat-{unique_id}"
    file_id = f"file-{unique_id}"
    owner_id = f"owner-{unique_id}"
    editor_id = f"editor-{unique_id}"
    stranger_id = f"stranger-{unique_id}"

    await authz_service.write(
        [
            office_catalog_owner_tuple(catalog_id, owner_id),
            office_catalog_member_tuple(catalog_id, editor_id, AuthzRelation.EDITOR),
            office_document_owner_tuple(file_id, owner_id),
            office_document_catalog_link(file_id, catalog_id),
        ]
    )
    doc = AuthzObject.office_document(file_id)
    assert await authz_service.can_view(doc, user_id=owner_id) is True
    assert await authz_service.can_view(doc, user_id=editor_id) is True
    assert await authz_service.can_edit(doc, user_id=editor_id) is True
    assert await authz_service.can_admin(doc, user_id=editor_id) is False
    assert await authz_service.can_edit(doc, user_id=owner_id) is True
    assert await authz_service.can_view(doc, user_id=stranger_id) is False


@pytest.mark.asyncio
async def test_office_document_direct_viewer_without_catalog_edit(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    catalog_id = f"cat-direct-{unique_id}"
    file_id = f"file-direct-{unique_id}"
    owner_id = f"owner-{unique_id}"
    viewer_id = f"viewer-{unique_id}"

    await authz_service.write(
        [
            office_catalog_owner_tuple(catalog_id, owner_id),
            office_document_owner_tuple(file_id, owner_id),
            office_document_catalog_link(file_id, catalog_id),
            office_document_member_tuple(file_id, viewer_id, AuthzRelation.VIEWER),
        ]
    )
    doc = AuthzObject.office_document(file_id)
    assert await authz_service.can_view(doc, user_id=viewer_id) is True
    assert await authz_service.can_edit(doc, user_id=viewer_id) is False
    assert (
        await authz_service.can_view(
            AuthzObject.office_catalog(catalog_id), user_id=viewer_id
        )
        is False
    )
