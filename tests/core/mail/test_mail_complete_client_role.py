"""Offline: role mailbox ACL, members, sync + RAG namespace."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from core.context import set_context
from core.mail.exceptions import MailPermissionError
from core.mail.models import (
    INBOX_FOLDER,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailboxBindingMemberPayload,
    MailboxBindingMemberRole,
    MailMessageListPayload,
    StoredMailMessage,
)
from core.mail.service import MailService
from core.models.context_models import Context
from core.models.identity_models import Company, User, UserStatus
from tests.core.mail.complete_client_helpers import (
    inbox_message,
    seed_connected_user_binding,
)
from tests.core.mail.fakes import RecordingMailServerPort

MailMemberSeed = Callable[..., Awaitable[tuple[Company, User]]]


async def _switch_context(
    di,
    *,
    company: Company,
    user_id: str,
    roles: list[str],
) -> User:
    user = User(
        user_id=user_id,
        name=f"Role user {user_id}",
        status=UserStatus.ACTIVE,
        emails=[f"{user_id}@mail.test"],
        companies={company.company_id: roles},
        active_company_id=company.company_id,
    )
    await User.set(user)
    from tests.fixtures.auth import set_test_company_member_roles

    await set_test_company_member_roles(
        di.authz_service,
        company_id=company.company_id,
        user_id=user_id,
        roles=roles,
    )
    refreshed = await Company.get(company.company_id)
    if refreshed is None:
        raise RuntimeError(f"company missing after membership sync: {company.company_id}")
    set_context(
        Context(
            user=user,
            active_company=refreshed,
            user_companies=[refreshed],
            channel="test",
        )
    )
    return user


@pytest.mark.asyncio
async def test_role_binding_members_acl_and_rag_namespace(
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
        prefix="roleacl",
    )
    company = await Company.get(company_id)
    assert company is not None

    role_binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.ROLE,
            user_id=None,
            local_part=f"sup{unique_id[:8]}",
            password="mailbox-pass",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    assert role_binding.kind == MailboxBindingKind.ROLE

    member_user_id = f"member_{unique_id}"
    outsider_user_id = f"out_{unique_id}"
    added = await mail_service.add_binding_member(
        role_binding.mailbox_binding_id,
        MailboxBindingMemberPayload(
            user_id=member_user_id,
            role=MailboxBindingMemberRole.MEMBER,
        ),
        company_id=company_id,
    )
    assert added.user_id == member_user_id
    members = await mail_service.list_binding_members_by_user_id_asc(
        role_binding.mailbox_binding_id,
        company_id=company_id,
    )
    assert any(item.user_id == member_user_id for item in members)

    recording_mail_port.inbox = [
        inbox_message(uid="1", unique_id=unique_id, subject="role-inbox"),
    ]
    synced = await mail_service.sync_binding(role_binding, max_new_messages=50)
    assert synced.skipped_reason is None
    stored = await StoredMailMessage.by_binding_folder_uid(
        role_binding.mailbox_binding_id, folder=INBOX_FOLDER, uid=1
    )
    assert stored is not None
    assert stored.rag_namespace == f"mail-{role_binding.mailbox_binding_id}"

    _ = await _switch_context(
        di,
        company=company,
        user_id=member_user_id,
        roles=["member"],
    )
    mine = await mail_service.list_my_bindings(company_id=company_id)
    assert any(item.mailbox_binding_id == role_binding.mailbox_binding_id for item in mine)
    listed = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=role_binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            limit=20,
        ),
        company_id=company_id,
    )
    assert len(listed.items) == 1

    _ = await _switch_context(
        di,
        company=company,
        user_id=outsider_user_id,
        roles=["member"],
    )
    with pytest.raises(MailPermissionError):
        _ = await mail_service.list_messages(
            MailMessageListPayload(
                mailbox_binding_id=role_binding.mailbox_binding_id,
                folder=INBOX_FOLDER,
                limit=20,
            ),
            company_id=company_id,
        )

    _ = await _switch_context(
        di,
        company=company,
        user_id=admin_user_id,
        roles=["owner", "admin"],
    )
    admin_list = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=role_binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            limit=20,
        ),
        company_id=company_id,
    )
    assert len(admin_list.items) == 1

    await mail_service.remove_binding_member(
        role_binding.mailbox_binding_id,
        member_user_id,
        company_id=company_id,
    )
    members_after = await mail_service.list_binding_members_by_user_id_asc(
        role_binding.mailbox_binding_id,
        company_id=company_id,
    )
    assert all(item.user_id != member_user_id for item in members_after)
