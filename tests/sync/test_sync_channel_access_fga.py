"""Sync channel access service — live OpenFGA sole PDP."""

from __future__ import annotations

import pytest

from apps.sync.services.sync_channel_access_service import SyncChannelAccessService
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject, AuthzSubject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation

pytestmark = [pytest.mark.timeout(60)]


@pytest.mark.asyncio
async def test_sync_channel_access_service_roles(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    access = SyncChannelAccessService(authz_service)
    channel_id = f"ch-acc-{unique_id}"
    owner_id = f"owner-{unique_id}"
    admin_id = f"admin-{unique_id}"
    member_id = f"member-{unique_id}"

    await access.sync_channel_created(
        channel_id,
        company_id=f"co-{unique_id}",
        owner_user_id=owner_id,
        member_user_ids=[member_id],
    )
    await access.set_member(channel_id, user_id=admin_id, relation="admin")

    obj = AuthzObject.sync_channel(channel_id)
    assert await authz_service.can_view(obj, user_id=member_id) is True
    assert await authz_service.can_admin(obj, user_id=member_id) is False
    assert await authz_service.can_admin(obj, user_id=admin_id) is True
    assert await authz_service.check(
        AuthzSubject.user(owner_id),
        AuthzRelation.OWNER,
        obj,
    ) is True

    rows = await access.list_member_rows_by_user_id_asc(channel_id)
    by_user = {uid: role for uid, role in rows}
    assert by_user[owner_id] == "owner"
    assert by_user[admin_id] == "admin"
    assert by_user[member_id] == "member"

    await authz_service.require_can_admin(obj, user_id=admin_id)
    with pytest.raises(AuthzDenied):
        await authz_service.require_can_admin(obj, user_id=member_id)

    await access.remove_member(channel_id, user_id=member_id)
    assert await authz_service.can_view(obj, user_id=member_id) is False
