"""Unit smoke: sync_channel OpenFGA model."""

from __future__ import annotations

import pytest

from apps.sync.authz.tuples import sync_channel_company_link, sync_channel_member_tuple
from core.authz.models import AuthzObject, AuthzSubject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation, AuthzSubjectKind

pytestmark = [pytest.mark.timeout(60)]


@pytest.mark.asyncio
async def test_sync_channel_owner_admin_member_gates(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    channel_id = f"ch-{unique_id}"
    owner_id = f"owner-{unique_id}"
    admin_id = f"admin-{unique_id}"
    member_id = f"member-{unique_id}"
    stranger_id = f"stranger-{unique_id}"

    await authz_service.write(
        [
            sync_channel_member_tuple(channel_id, owner_id, AuthzRelation.OWNER),
            sync_channel_member_tuple(channel_id, admin_id, AuthzRelation.ADMIN),
            sync_channel_member_tuple(channel_id, member_id, AuthzRelation.MEMBER),
        ]
    )

    obj = AuthzObject.sync_channel(channel_id)
    assert await authz_service.can_view(obj, user_id=owner_id) is True
    assert await authz_service.can_view(obj, user_id=admin_id) is True
    assert await authz_service.can_view(obj, user_id=member_id) is True
    assert await authz_service.can_view(obj, user_id=stranger_id) is False

    assert await authz_service.can_admin(obj, user_id=owner_id) is True
    assert await authz_service.can_admin(obj, user_id=admin_id) is True
    assert await authz_service.can_admin(obj, user_id=member_id) is False

    assert (
        await authz_service.check(
            AuthzSubject.user(owner_id),
            AuthzRelation.OWNER,
            obj,
        )
        is True
    )
    assert (
        await authz_service.check(
            AuthzSubject.user(member_id),
            AuthzRelation.OWNER,
            obj,
        )
        is False
    )


@pytest.mark.asyncio
async def test_sync_channel_company_link_written(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    channel_id = f"ch-co-{unique_id}"
    company_id = f"co-{unique_id}"
    owner_id = f"owner-{unique_id}"

    await authz_service.write(
        [
            sync_channel_company_link(channel_id, company_id),
            sync_channel_member_tuple(channel_id, owner_id, AuthzRelation.OWNER),
        ]
    )

    obj = AuthzObject.sync_channel(channel_id)
    company_tuples = await authz_service.list_tuples(obj, relation=AuthzRelation.COMPANY)
    assert len(company_tuples) == 1
    assert company_tuples[0].subject.kind is AuthzSubjectKind.OBJECT
    assert company_tuples[0].subject.value == f"company:{company_id}"
    assert await authz_service.can_view(obj, user_id=owner_id) is True
