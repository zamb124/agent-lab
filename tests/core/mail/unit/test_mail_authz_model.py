"""Unit smoke: mailbox_binding OpenFGA model."""

from __future__ import annotations

import pytest

from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation, AuthzSubjectKind
from core.mail.authz.tuples import (
    mailbox_binding_company_link,
    mailbox_binding_member_tuple,
    mailbox_binding_owner_tuple,
)

pytestmark = [pytest.mark.timeout(60)]


@pytest.mark.asyncio
async def test_mailbox_binding_member_vs_manager(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    binding_id = f"mb-{unique_id}"
    owner_id = f"owner-{unique_id}"
    member_id = f"member-{unique_id}"
    manager_id = f"manager-{unique_id}"
    stranger_id = f"stranger-{unique_id}"

    await authz_service.write(
        [
            mailbox_binding_owner_tuple(binding_id, owner_id),
            mailbox_binding_member_tuple(binding_id, member_id, AuthzRelation.MEMBER),
            mailbox_binding_member_tuple(binding_id, manager_id, AuthzRelation.MANAGER),
        ]
    )

    obj = AuthzObject.mailbox_binding(binding_id)
    assert await authz_service.can_view(obj, user_id=member_id) is True
    assert await authz_service.can_edit(obj, user_id=member_id) is False
    assert await authz_service.can_edit(obj, user_id=manager_id) is True
    assert await authz_service.can_admin(obj, user_id=manager_id) is True
    assert await authz_service.can_admin(obj, user_id=owner_id) is True
    assert await authz_service.can_view(obj, user_id=stranger_id) is False


@pytest.mark.asyncio
async def test_mailbox_binding_company_link_written(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    binding_id = f"mb-co-{unique_id}"
    company_id = f"co-{unique_id}"
    owner_id = f"owner-{unique_id}"

    await authz_service.write(
        [
            mailbox_binding_company_link(binding_id, company_id),
            mailbox_binding_owner_tuple(binding_id, owner_id),
        ]
    )

    obj = AuthzObject.mailbox_binding(binding_id)
    company_tuples = await authz_service.list_tuples(obj, relation=AuthzRelation.COMPANY)
    assert len(company_tuples) == 1
    assert company_tuples[0].subject.kind is AuthzSubjectKind.OBJECT
    assert company_tuples[0].subject.value == f"company:{company_id}"
    assert await authz_service.can_view(obj, user_id=owner_id) is True
