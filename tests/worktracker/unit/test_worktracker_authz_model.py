"""Unit smoke: work_queue OpenFGA model."""

from __future__ import annotations

import pytest

from apps.worktracker.authz.tuples import work_queue_member_tuple, work_queue_owner_tuple
from apps.worktracker.services.work_queue_access_service import WorkQueueAccessService
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation, AuthzSubjectKind

pytestmark = [pytest.mark.timeout(60)]


@pytest.mark.asyncio
async def test_work_queue_owner_and_member_gates(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    queue_id = f"wq-{unique_id}"
    owner_id = f"owner-{unique_id}"
    member_id = f"member-{unique_id}"
    stranger_id = f"stranger-{unique_id}"

    await authz_service.write(
        [
            work_queue_owner_tuple(queue_id, owner_id),
            work_queue_member_tuple(queue_id, member_id, AuthzRelation.MEMBER),
        ]
    )

    obj = AuthzObject.work_queue(queue_id)
    assert await authz_service.can_view(obj, user_id=owner_id) is True
    assert await authz_service.can_view(obj, user_id=member_id) is True
    assert await authz_service.can_view(obj, user_id=stranger_id) is False
    assert await authz_service.can_admin(obj, user_id=owner_id) is True
    assert await authz_service.can_admin(obj, user_id=member_id) is False


@pytest.mark.asyncio
async def test_work_queue_access_service_company_link_and_deny(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    access = WorkQueueAccessService(authz_service)
    queue_id = f"wq-acc-{unique_id}"
    company_id = f"co-{unique_id}"
    owner_id = f"owner-{unique_id}"
    member_id = f"member-{unique_id}"
    stranger_id = f"stranger-{unique_id}"

    await access.sync_queue_created(queue_id, company_id=company_id, owner_user_id=owner_id)
    await access.set_member(queue_id, user_id=member_id, relation="member")

    company_tuples = await authz_service.list_tuples(
        AuthzObject.work_queue(queue_id),
        relation=AuthzRelation.COMPANY,
    )
    assert len(company_tuples) == 1
    assert company_tuples[0].subject.kind is AuthzSubjectKind.OBJECT
    assert company_tuples[0].subject.value == f"company:{company_id}"

    assert await authz_service.can_view(AuthzObject.work_queue(queue_id), user_id=member_id) is True
    assert await authz_service.can_view(AuthzObject.work_queue(queue_id), user_id=stranger_id) is False
    with pytest.raises(AuthzDenied):
        await authz_service.require_can_admin(
            AuthzObject.work_queue(queue_id), user_id=member_id
        )
    with pytest.raises(AuthzDenied):
        await authz_service.require_can_view(
            AuthzObject.work_queue(queue_id), user_id=stranger_id
        )

    viewable = await access.list_viewable_queue_ids(user_id=member_id)
    assert queue_id in viewable
    assert queue_id not in await access.list_viewable_queue_ids(user_id=stranger_id)

    await access.remove_member(queue_id, user_id=member_id)
    assert await authz_service.can_view(AuthzObject.work_queue(queue_id), user_id=member_id) is False
