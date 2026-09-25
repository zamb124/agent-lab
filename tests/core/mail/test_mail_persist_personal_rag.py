"""E2E: mail_messages persist + personal namespace RAG metadata (RecordingMailServerPort DI)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    InboundMailMessage,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailMessageFlagPayload,
    MailProvider,
    StoredMailMessage,
)
from core.mail.service import MailService
from core.models.identity_models import Company, NamespaceKind, User
from core.namespace import personal_namespace_name
from tests.core.mail.fakes import RecordingMailServerPort

MailMemberSeed = Callable[..., Awaitable[tuple[Company, User]]]


@pytest.mark.asyncio
async def test_sync_bootstrap_persists_inbox_into_mail_messages_and_personal_ns(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    di,
    unique_id: str,
) -> None:
    company_id = f"mailpersist_{unique_id}"
    user_id = f"upu_{unique_id}"
    display = f"Persist User {unique_id}"
    _company, user = await mail_member_context(
        company_id=company_id,
        user_id=user_id,
        display_name=display,
    )
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.persist.example.com",
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company_id,
    )
    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_id,
            local_part=f"p{unique_id[:8]}",
            password="test-pass-1",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    recording_mail_port.uidvalidity = 5
    recording_mail_port.inbox = [
        InboundMailMessage(
            uid="21",
            message_id="<persist-a@example.com>",
            subject="Persist A",
            from_address="a@example.com",
            body_text="Hello persist body A",
            unread=True,
        ),
        InboundMailMessage(
            uid="22",
            message_id="<persist-b@example.com>",
            subject="Persist B",
            from_address="b@example.com",
            body_text="Hello persist body B",
            unread=False,
        ),
    ]

    result = await mail_service.sync_user_inbox(binding, max_new_messages=20)
    assert result.bootstrap is True
    assert result.new_messages == []

    stored = await StoredMailMessage.list_folder(
        binding.mailbox_binding_id,
        folder="INBOX",
        limit=50,
    )
    assert len(stored) == 2
    by_uid = {item.uid: item for item in stored}
    assert by_uid[21].subject == "Persist A"
    assert by_uid[21].unread is True
    assert by_uid[21].user_id == user_id
    assert by_uid[21].mailbox_binding_id == binding.mailbox_binding_id
    assert by_uid[21].rag_namespace == personal_namespace_name(user_id)
    assert by_uid[22].subject == "Persist B"
    assert by_uid[22].unread is False

    personal = await di.namespace_service.get(personal_namespace_name(user_id))
    assert personal is not None
    assert personal.kind == NamespaceKind.PERSONAL
    assert personal.owner_user_id == user_id
    assert personal.description == display


@pytest.mark.asyncio
async def test_sync_incremental_persists_new_inbox_message(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    unique_id: str,
) -> None:
    company_id = f"mailinc_{unique_id}"
    user_id = f"uiu_{unique_id}"
    _ = await mail_member_context(company_id=company_id, user_id=user_id)
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.inc.example.com",
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company_id,
    )
    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_id,
            local_part=f"i{unique_id[:8]}",
            password="test-pass-1",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    recording_mail_port.uidvalidity = 8
    recording_mail_port.inbox = [
        InboundMailMessage(
            uid="1",
            subject="seed",
            from_address="a@example.com",
            body_text="seed",
        ),
    ]
    _ = await mail_service.sync_user_inbox(binding, max_new_messages=20)

    recording_mail_port.inbox.append(
        InboundMailMessage(
            uid="2",
            subject="Incremental",
            from_address="c@example.com",
            body_text="Incremental body",
            unread=True,
        )
    )
    second = await mail_service.sync_user_inbox(binding, max_new_messages=20)
    assert second.bootstrap is False
    assert len(second.new_messages) == 1

    stored = await StoredMailMessage.list_folder(
        binding.mailbox_binding_id,
        folder="INBOX",
        limit=50,
    )
    uids = {item.uid for item in stored}
    assert 2 in uids
    incremental = next(item for item in stored if item.uid == 2)
    assert incremental.subject == "Incremental"
    assert incremental.rag_namespace == personal_namespace_name(user_id)
    assert incremental.snippet != ""


@pytest.mark.asyncio
async def test_sync_sent_persists_without_inbox_notify(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    unique_id: str,
) -> None:
    company_id = f"mailsentp_{unique_id}"
    user_id = f"usu_{unique_id}"
    _ = await mail_member_context(company_id=company_id, user_id=user_id)
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.sentp.example.com",
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company_id,
    )
    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_id,
            local_part=f"t{unique_id[:8]}",
            password="test-pass-1",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    recording_mail_port.uidvalidity = 2
    recording_mail_port.mailbox_messages["Sent"] = [
        InboundMailMessage(
            uid="7",
            subject="Outbox",
            from_address="me@example.com",
            body_text="sent body",
        ),
    ]
    first = await mail_service.sync_user_inbox(binding, max_new_messages=20)
    assert first.bootstrap is True
    assert first.new_messages == []

    sent_rows = await StoredMailMessage.list_folder(
        binding.mailbox_binding_id,
        folder="Sent",
        limit=20,
    )
    assert len(sent_rows) == 1
    assert sent_rows[0].uid == 7
    assert sent_rows[0].rag_namespace == personal_namespace_name(user_id)


@pytest.mark.asyncio
async def test_mark_seen_unseen_updates_local_mail_messages(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    unique_id: str,
) -> None:
    company_id = f"mailflags_{unique_id}"
    user_id = f"ufu_{unique_id}"
    _ = await mail_member_context(company_id=company_id, user_id=user_id)
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.flags.example.com",
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company_id,
    )
    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_id,
            local_part=f"g{unique_id[:8]}",
            password="test-pass-1",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    recording_mail_port.uidvalidity = 4
    recording_mail_port.inbox = [
        InboundMailMessage(
            uid="9",
            subject="Flag me",
            from_address="a@example.com",
            body_text="flag body",
            unread=True,
        ),
    ]
    _ = await mail_service.sync_user_inbox(binding, max_new_messages=20)

    seen = await mail_service.mark_message_seen(
        MailMessageFlagPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="INBOX",
            uid="9",
        ),
        company_id=company_id,
    )
    assert seen.unread is False
    assert len(recording_mail_port.mark_seen_calls) == 1
    row_seen = await StoredMailMessage.by_binding_folder_uid(
        binding.mailbox_binding_id, folder="INBOX", uid=9
    )
    assert row_seen is not None
    assert row_seen.unread is False

    unseen = await mail_service.mark_message_unseen(
        MailMessageFlagPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="INBOX",
            uid="9",
        ),
        company_id=company_id,
    )
    assert unseen.unread is True
    assert len(recording_mail_port.mark_unseen_calls) == 1
    row_unseen = await StoredMailMessage.by_binding_folder_uid(
        binding.mailbox_binding_id, folder="INBOX", uid=9
    )
    assert row_unseen is not None
    assert row_unseen.unread is True
