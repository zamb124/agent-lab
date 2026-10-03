"""Date header parse + IMAP STATUS counts + mark unseen."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.mail.mime_parse import parse_inbound_rfc822, parse_mail_date_header
from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    InboundMailMessage,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailFolderRole,
    MailMessageFlagPayload,
    MailProvider,
)
from core.mail.service import MailService
from core.mail.transport.imap_smtp import _parse_status_counts
from tests.core.mail.fakes import RecordingMailServerPort


def test_parse_mail_date_header_rfc2822() -> None:
    parsed = parse_mail_date_header("Tue, 15 Jul 2025 12:34:56 +0300")
    assert parsed is not None
    assert parsed == datetime(2025, 7, 15, 9, 34, 56, tzinfo=timezone.utc)


def test_parse_mail_date_header_invalid() -> None:
    assert parse_mail_date_header(None) is None
    assert parse_mail_date_header("") is None
    assert parse_mail_date_header("not-a-date") is None


def test_parse_inbound_rfc822_sets_date() -> None:
    raw = (
        b"From: a@example.com\r\n"
        b"To: b@example.com\r\n"
        b"Subject: hi\r\n"
        b"Date: Wed, 01 Jan 2025 00:00:00 +0000\r\n"
        b"Message-ID: <x@example.com>\r\n"
        b"\r\n"
        b"body\r\n"
    )
    message = parse_inbound_rfc822("42", raw)
    assert message.date == datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def test_parse_status_counts() -> None:
    lines = [b'* STATUS "INBOX" (MESSAGES 2564 UNSEEN 818)']
    assert _parse_status_counts(lines) == (2564, 818)


def test_parse_status_counts_aioimaplib_stripped_prefix() -> None:
    # aioimaplib часто отдаёт untagged без "* STATUS ".
    assert _parse_status_counts([b'INBOX (MESSAGES 10 UNSEEN 2)']) == (10, 2)
    assert _parse_status_counts([b'"Sent" (MESSAGES 0 UNSEEN 0)']) == (0, 0)
    assert _parse_status_counts([b'STATUS INBOX (MESSAGES 3 UNSEEN 1)']) == (3, 1)


def test_parse_status_counts_missing_raises() -> None:
    with pytest.raises(ValueError, match="MESSAGES/UNSEEN"):
        _ = _parse_status_counts([b"* OK done"])
    with pytest.raises(ValueError, match="MESSAGES/UNSEEN"):
        _ = _parse_status_counts([b'(\\HasNoChildren) "/" INBOX'])


@pytest.mark.asyncio
async def test_list_folders_includes_unseen_counts(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context,
    unique_id: str,
) -> None:
    company_id = f"mailcnt_{unique_id}"
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
        ),
        company_id=company_id,
    )
    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_id,
            local_part=f"cnt.{unique_id}",
            password="mailbox-pass",
            provision=False,
        ),
        company_id=company_id,
    )
    recording_mail_port.inbox.append(
        InboundMailMessage(
            uid="1",
            subject="unread",
            from_address="a@example.com",
            unread=True,
        )
    )
    recording_mail_port.inbox.append(
        InboundMailMessage(
            uid="2",
            subject="read",
            from_address="a@example.com",
            unread=False,
        )
    )
    stale = await mail_service.list_folders(
        binding.mailbox_binding_id,
        company_id=company_id,
    )
    assert stale.folders == []
    assert stale.stale is True
    assert stale.needs_sync is True

    _ = await mail_service.sync_user_inbox(binding, max_new_messages=20)
    folders = await mail_service.list_folders(
        binding.mailbox_binding_id,
        company_id=company_id,
    )
    assert folders.stale is False
    inbox = next(folder for folder in folders.folders if folder.role == MailFolderRole.INBOX)
    assert inbox.message_count == 2
    assert inbox.unseen_count == 1


@pytest.mark.asyncio
async def test_mark_message_unseen(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    unique_id: str,
) -> None:
    company_id = f"mailuns_{unique_id}"
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.example.com",
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
        ),
        company_id=company_id,
    )
    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id="test_user",
            local_part=f"uns.{unique_id}",
            password="mailbox-pass",
            provision=False,
        ),
        company_id=company_id,
    )
    recording_mail_port.inbox.append(
        InboundMailMessage(
            uid="77",
            subject="seen",
            from_address="a@example.com",
            unread=False,
        )
    )
    result = await mail_service.mark_message_unseen(
        MailMessageFlagPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="INBOX",
            uid="77",
        ),
        company_id=company_id,
    )
    assert result.uid == "77"
    assert result.unread is True
    assert recording_mail_port.inbox[0].unread is True
    assert len(recording_mail_port.mark_unseen_calls) == 1
