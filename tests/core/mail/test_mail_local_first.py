"""Local-first mail: folders cache, list/thread from DB, upsert reducer."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    InboundMailMessage,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailMessageListPayload,
    MailProvider,
    MailThreadPayload,
)
from core.mail.service import MailService
from tests.core.mail.fakes import RecordingMailServerPort


@pytest.mark.asyncio
async def test_get_thread_reads_local_bodies(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context,
    unique_id: str,
) -> None:
    company_id = f"mailthr_{unique_id}"
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
            local_part=f"thr.{unique_id}",
            password="mailbox-pass",
            provision=False,
        ),
        company_id=company_id,
    )
    recording_mail_port.inbox.append(
        InboundMailMessage(
            uid="9",
            message_id=f"<thr-{unique_id}@example.com>",
            subject=f"thread-{unique_id}",
            from_address="peer@example.com",
            to_addresses=[binding.email_address],
            body_text="hello local thread",
            body_html="<p>hello local thread</p>",
            date=datetime(2025, 3, 1, tzinfo=timezone.utc),
        )
    )
    _ = await mail_service.sync_user_inbox(binding, max_new_messages=20)
    thread = await mail_service.get_thread(
        MailThreadPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="INBOX",
            uid="9",
        ),
        company_id=company_id,
    )
    assert len(thread.items) == 1
    assert thread.items[0].body_text == "hello local thread"
    assert thread.items[0].body_html == "<p>hello local thread</p>"
    listed = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="INBOX",
            limit=10,
        ),
        company_id=company_id,
    )
    assert listed.items[0].unread is False
