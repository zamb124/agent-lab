"""Offline: sync_user_inbox + fetch_uids_since на RecordingMailServerPort."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import pytest

from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    InboundMailMessage,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailboxSecret,
    MailboxSyncCursor,
    MailProvider,
    MailSyncErrorKind,
)
from core.mail.service import MailService
from core.models.identity_models import Company, User
from tests.core.mail.fakes import RecordingMailServerPort

MailMemberSeed = Callable[..., Awaitable[tuple[Company, User]]]


@pytest.mark.asyncio
async def test_sync_user_inbox_bootstrap_then_incremental_notify_payload(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    unique_id: str,
) -> None:
    company_id = f"mailsync_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await mail_member_context(company_id=company_id, user_id=user_id)
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.example.com",
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
            local_part=f"u{unique_id[:8]}",
            password="test-pass-1",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    recording_mail_port.uidvalidity = 42
    recording_mail_port.inbox = [
        InboundMailMessage(
            uid="10",
            message_id="<old@example.com>",
            subject="Old",
            from_address="a@example.com",
            body_text="Old body",
        ),
        InboundMailMessage(
            uid="11",
            message_id="<also-old@example.com>",
            subject="Also old",
            from_address="b@example.com",
            body_text="Also old body",
        ),
    ]

    first = await mail_service.sync_user_inbox(binding, max_new_messages=20)
    assert first.bootstrap is True
    assert first.new_messages == []
    cursor = await MailboxSyncCursor.by_binding_folder(binding.mailbox_binding_id)
    assert cursor is not None
    assert cursor.uidvalidity == 42
    assert cursor.last_uid == 11
    sent_cursor = await MailboxSyncCursor.by_binding_folder(
        binding.mailbox_binding_id, folder="Sent"
    )
    assert sent_cursor is not None

    recording_mail_port.inbox.append(
        InboundMailMessage(
            uid="12",
            message_id="<new@example.com>",
            subject="New mail",
            from_address="c@example.com",
            body_text="New body text",
        )
    )
    second = await mail_service.sync_user_inbox(binding, max_new_messages=20)
    assert second.bootstrap is False
    assert len(second.new_messages) == 1
    assert second.new_messages[0].uid == "12"
    assert second.new_messages[0].subject == "New mail"

    cursor2 = await MailboxSyncCursor.by_binding_folder(binding.mailbox_binding_id)
    assert cursor2 is not None
    assert cursor2.last_uid == 12


@pytest.mark.asyncio
async def test_sync_user_inbox_uidvalidity_reset_no_notify(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    unique_id: str,
) -> None:
    company_id = f"mailsyncv_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await mail_member_context(company_id=company_id, user_id=user_id)
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.v.example.com",
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
            local_part=f"v{unique_id[:8]}",
            password="test-pass-1",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    recording_mail_port.uidvalidity = 1
    recording_mail_port.inbox = [
        InboundMailMessage(
            uid="5",
            subject="x",
            from_address="a@example.com",
            body_text="x",
        ),
    ]
    _ = await mail_service.sync_user_inbox(binding, max_new_messages=20)

    recording_mail_port.uidvalidity = 99
    recording_mail_port.inbox = [
        InboundMailMessage(
            uid="1",
            subject="reset",
            from_address="a@example.com",
            body_text="reset",
        ),
        InboundMailMessage(
            uid="2",
            subject="reset2",
            from_address="a@example.com",
            body_text="reset2",
        ),
    ]
    result = await mail_service.sync_user_inbox(binding, max_new_messages=20)
    assert result.bootstrap is True
    assert result.new_messages == []
    cursor = await MailboxSyncCursor.by_binding_folder(binding.mailbox_binding_id)
    assert cursor is not None
    assert cursor.uidvalidity == 99
    assert cursor.last_uid == 2


@pytest.mark.asyncio
async def test_recording_port_fetch_uids_since_bootstrap_empty_messages(
    recording_mail_port: RecordingMailServerPort,
) -> None:
    recording_mail_port.uidvalidity = 7
    recording_mail_port.inbox = [
        InboundMailMessage(uid="3", subject="a", from_address="a@example.com"),
        InboundMailMessage(uid="9", subject="b", from_address="b@example.com"),
    ]
    secret = MailboxSecret(email_address="u@example.com", password="p")
    batch = await recording_mail_port.fetch_uids_since(
        secret, mailbox="INBOX", since_uid=0, limit=10
    )
    assert batch.uidvalidity == 7
    assert batch.max_uid == 9
    assert batch.messages == []

    batch2 = await recording_mail_port.fetch_uids_since(
        secret, mailbox="INBOX", since_uid=3, limit=10
    )
    assert [item.uid for item in batch2.messages] == ["9"]


@pytest.mark.asyncio
async def test_sync_sent_folder_incremental_does_not_notify(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    unique_id: str,
) -> None:
    company_id = f"mailsent_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await mail_member_context(company_id=company_id, user_id=user_id)
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.sent.example.com",
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
            local_part=f"s{unique_id[:8]}",
            password="test-pass-1",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    recording_mail_port.uidvalidity = 3
    recording_mail_port.mailbox_messages["Sent"] = [
        InboundMailMessage(
            uid="1",
            subject="sent-old",
            from_address="me@example.com",
            body_text="sent old",
        ),
    ]
    first = await mail_service.sync_user_inbox(binding, max_new_messages=20)
    assert first.bootstrap is True
    sent_cursor = await MailboxSyncCursor.by_binding_folder(
        binding.mailbox_binding_id, folder="Sent"
    )
    assert sent_cursor is not None
    assert sent_cursor.last_uid == 1

    recording_mail_port.mailbox_messages["Sent"].append(
        InboundMailMessage(
            uid="2",
            subject="sent-new",
            from_address="me@example.com",
            body_text="sent new",
        ),
    )
    second = await mail_service.sync_user_inbox(binding, max_new_messages=20)
    assert second.bootstrap is False
    assert second.new_messages == []
    sent_cursor2 = await MailboxSyncCursor.by_binding_folder(
        binding.mailbox_binding_id, folder="Sent"
    )
    assert sent_cursor2 is not None
    assert sent_cursor2.last_uid == 2


@pytest.mark.asyncio
async def test_record_sync_failure_sets_auth_kind(
    mail_service: MailService,
    mail_member_context: MailMemberSeed,
    unique_id: str,
) -> None:
    company_id = f"mailfail_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await mail_member_context(company_id=company_id, user_id=user_id)
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.fail.example.com",
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
            local_part=f"f{unique_id[:8]}",
            password="test-pass-1",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    await mail_service.record_sync_failure(
        binding,
        error_kind=MailSyncErrorKind.AUTH,
        error_message="IMAP login failed",
    )
    cursor = await MailboxSyncCursor.by_binding_folder(binding.mailbox_binding_id)
    assert cursor is not None
    assert cursor.last_error_kind == MailSyncErrorKind.AUTH
    assert cursor.last_error_at is not None
    assert cursor.last_error_at.tzinfo is not None
    assert cursor.last_error_at <= datetime.now(timezone.utc)
