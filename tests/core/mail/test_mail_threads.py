"""Offline: thread_id helpers + MailService.get_thread (INBOX + Sent)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    InboundMailMessage,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailProvider,
    MailThreadPayload,
)
from core.mail.service import MailService
from core.mail.threads import (
    collect_thread_message_ids,
    normalize_mail_subject,
    thread_id_for_message,
)
from tests.core.mail.fakes import RecordingMailServerPort


def test_normalize_mail_subject_strips_reply_prefixes() -> None:
    assert normalize_mail_subject("Re: Re: Hello") == "hello"
    assert normalize_mail_subject("Fwd: Hello") == "hello"
    assert normalize_mail_subject("Ответ: Hello") == "hello"


def test_thread_id_prefers_references_root() -> None:
    message = InboundMailMessage(
        uid="9",
        message_id="<c@example.com>",
        in_reply_to="<b@example.com>",
        references="<a@example.com> <b@example.com>",
        subject="Re: topic",
    )
    assert thread_id_for_message(message) == "<a@example.com>"
    assert collect_thread_message_ids(message) == {
        "<a@example.com>",
        "<b@example.com>",
        "<c@example.com>",
    }


@pytest.mark.asyncio
async def test_get_thread_merges_inbox_and_sent_marks_inbox_seen(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    unique_id: str,
) -> None:
    company_id = f"mailthr_{unique_id}"
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
            local_part=f"thr.{unique_id}",
            password="mailbox-pass-thread",
            provision=False,
        ),
        company_id=company_id,
    )
    t0 = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 7, 19, 10, 5, tzinfo=timezone.utc)
    t2 = datetime(2026, 7, 19, 10, 10, tzinfo=timezone.utc)
    recording_mail_port.inbox.extend(
        [
            InboundMailMessage(
                uid="1",
                message_id="<root@example.com>",
                subject="topic",
                from_address="peer@example.com",
                to_addresses=[binding.email_address],
                body_text="hello",
                unread=True,
                date=t0,
            ),
            InboundMailMessage(
                uid="3",
                message_id="<reply2@example.com>",
                in_reply_to="<mine@example.com>",
                references="<root@example.com> <mine@example.com>",
                subject="Re: topic",
                from_address="peer@example.com",
                to_addresses=[binding.email_address],
                body_text="ok",
                unread=True,
                date=t2,
            ),
        ]
    )
    recording_mail_port.mailbox_messages["Sent"] = [
        InboundMailMessage(
            uid="10",
            message_id="<mine@example.com>",
            in_reply_to="<root@example.com>",
            references="<root@example.com>",
            subject="Re: topic",
            from_address=binding.email_address,
            to_addresses=["peer@example.com"],
            body_text="my reply",
            unread=False,
            date=t1,
        )
    ]

    result = await mail_service.get_thread(
        MailThreadPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="INBOX",
            uid="3",
        ),
        company_id=company_id,
    )

    assert result.thread_id == "<root@example.com>"
    assert len(result.items) == 3
    assert [item.uid for item in result.items] == ["1", "10", "3"]
    assert [item.folder for item in result.items] == ["INBOX", "Sent", "INBOX"]
    assert all(item.unread is False for item in result.items if item.folder == "INBOX")
    seen_uids = {call[2] for call in recording_mail_port.mark_seen_calls}
    assert seen_uids == {"1", "3"}
    assert "10" not in seen_uids
