"""Unit smoke: platform_namespace OpenFGA model and dual-write helpers."""

from __future__ import annotations

import pytest

from core.authz.company_sync import sync_company_member_roles
from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation, AuthzSubjectKind
from core.namespace.authz.tuples import (
    platform_namespace_company_editor_tuple,
    platform_namespace_company_link,
    platform_namespace_company_viewer_tuple,
    platform_namespace_owner_tuple,
)

pytestmark = [pytest.mark.timeout(60)]


@pytest.mark.asyncio
async def test_platform_namespace_company_member_can_view_workspace(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    company_id = f"co-{unique_id}"
    namespace = f"ws-{unique_id}"
    member_id = f"member-{unique_id}"
    stranger_id = f"stranger-{unique_id}"

    await sync_company_member_roles(
        authz_service,
        company_id=company_id,
        user_id=member_id,
        roles=["member"],
    )
    await authz_service.write(
        [
            platform_namespace_company_link(company_id, namespace),
            platform_namespace_company_viewer_tuple(company_id, namespace),
            platform_namespace_company_editor_tuple(company_id, namespace),
        ]
    )

    obj = AuthzObject.platform_namespace(company_id, namespace)
    company_tuples = await authz_service.list_tuples(obj, relation=AuthzRelation.COMPANY)
    assert len(company_tuples) == 1
    assert company_tuples[0].subject.kind is AuthzSubjectKind.OBJECT
    assert company_tuples[0].subject.value == f"company:{company_id}"
    assert await authz_service.can_view(obj, user_id=member_id) is True
    assert await authz_service.can_edit(obj, user_id=member_id) is True
    assert await authz_service.can_view(obj, user_id=stranger_id) is False


@pytest.mark.asyncio
async def test_platform_namespace_personal_owner_and_company_link(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    company_id = f"co-{unique_id}"
    namespace = f"user-{unique_id}"
    owner_id = f"owner-{unique_id}"
    stranger_id = f"stranger-{unique_id}"

    await authz_service.write(
        [
            platform_namespace_company_link(company_id, namespace),
            platform_namespace_company_viewer_tuple(company_id, namespace),
            platform_namespace_company_editor_tuple(company_id, namespace),
            platform_namespace_owner_tuple(company_id, namespace, owner_id),
        ]
    )

    obj = AuthzObject.platform_namespace(company_id, namespace)
    assert await authz_service.can_view(obj, user_id=owner_id) is True
    assert await authz_service.can_admin(obj, user_id=owner_id) is True
    assert await authz_service.can_view(obj, user_id=stranger_id) is False
