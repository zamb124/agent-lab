"""Role mailbox job-actor vs notify recipients."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from apps.idle_worker.tasks.mail_job_context import (
    enter_mail_binding_context,
    leave_mail_binding_context,
)
from apps.idle_worker.tasks.mail_recipients import (
    mailbox_recipient_user_ids,
    mailbox_role_job_actor_user,
)
from core.mail.authz.tuples import mailbox_binding_owner_tuple
from core.mail.models import MailboxBindingCreatePayload, MailboxBindingKind
from core.mail.service import MailService
from core.models.identity_models import Company, User
from tests.core.mail.complete_client_helpers import seed_connected_user_binding
from tests.core.mail.fakes import RecordingMailServerPort
from tests.fixtures.auth import set_test_company_member_roles

MailMemberSeed = Callable[..., Awaitable[tuple[Company, User]]]


@pytest.mark.asyncio
async def test_role_job_actor_uses_company_admin_when_recipients_empty(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    di,
    unique_id: str,
) -> None:
    company_id, admin_user_id, _user_binding = await seed_connected_user_binding(
        mail_service,
        mail_member_context,
        recording_mail_port,
        unique_id=unique_id,
        prefix="roleact",
    )
    role_binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.ROLE,
            user_id=None,
            local_part=f"ra{unique_id[:8]}",
            password="mailbox-pass",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    await di.authz_service.delete(
        [mailbox_binding_owner_tuple(role_binding.mailbox_binding_id, admin_user_id)]
    )

    recipients = await mailbox_recipient_user_ids(di.authz_service, role_binding)
    assert recipients == []
    actor = await mailbox_role_job_actor_user(di.authz_service, role_binding)
    assert actor.user_id == admin_user_id

    previous = await enter_mail_binding_context(di.authz_service, role_binding)
    try:
        assert actor.user_id == admin_user_id
    finally:
        leave_mail_binding_context(previous)


@pytest.mark.asyncio
async def test_role_job_actor_raises_without_admin(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    di,
    unique_id: str,
) -> None:
    company_id, admin_user_id, _user_binding = await seed_connected_user_binding(
        mail_service,
        mail_member_context,
        recording_mail_port,
        unique_id=unique_id,
        prefix="rolenoadm",
    )
    role_binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.ROLE,
            user_id=None,
            local_part=f"rn{unique_id[:8]}",
            password="mailbox-pass",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    await di.authz_service.delete(
        [mailbox_binding_owner_tuple(role_binding.mailbox_binding_id, admin_user_id)]
    )
    admin = await User.get(admin_user_id)
    if admin is None:
        raise RuntimeError(f"admin user missing: {admin_user_id}")
    admin.companies[company_id] = ["member"]
    await User.set(admin)
    await set_test_company_member_roles(
        di.authz_service,
        company_id=company_id,
        user_id=admin_user_id,
        roles=["member"],
    )

    recipients = await mailbox_recipient_user_ids(di.authz_service, role_binding)
    assert recipients == []
    with pytest.raises(ValueError, match="no FGA mailbox member for role mail job"):
        _ = await enter_mail_binding_context(di.authz_service, role_binding)
