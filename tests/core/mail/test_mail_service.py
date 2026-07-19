"""MailService offline: real DB + RecordingMailServerPort через DI."""

from __future__ import annotations

import pytest

from core.mail.exceptions import MailMessageNotFoundError, MailSystemConnectionReadOnlyError
from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    InboundMailMessage,
    MailAttachment,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailFetchQuery,
    MailMessageListPayload,
    MailProvider,
    OutboundMailMessage,
)
from core.mail.service import MailService
from tests.core.mail.fakes import RecordingMailServerPort


@pytest.mark.asyncio
async def test_upsert_connection_bind_send_fetch(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    unique_id: str,
) -> None:
    company_id = f"mailsvc_{unique_id}"
    connection = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.example.com",
            provider=MailProvider.ISPMANAGER,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
            ispmanager_base_url="https://panel.example.com:1500/ispmgr",
            ispmanager_authinfo_user="admin",
            ispmanager_authinfo_password="secret-pass",
        ),
        company_id=company_id,
    )
    assert connection.supports_provision is True
    assert connection.mail_domain == f"{unique_id}.example.com"

    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=f"user_{unique_id}",
            local_part=f"alice.{unique_id}",
            password="mailbox-pass-1",
            provision=True,
        ),
        company_id=company_id,
    )
    assert binding.email_address == f"alice.{unique_id}@{unique_id}.example.com"
    assert len(recording_mail_port.ensure_calls) == 1

    subject = f"hello-{unique_id}"
    send_result = await mail_service.send_from_binding(
        binding.mailbox_binding_id,
        OutboundMailMessage(
            to_addresses=[binding.email_address],
            subject=subject,
            body_text="body",
            message_id=f"<msg-{unique_id}@example.com>",
        ),
        company_id=company_id,
    )
    assert send_result.message_id == f"<msg-{unique_id}@example.com>"

    fetched = await mail_service.fetch_for_binding(
        binding.mailbox_binding_id,
        MailFetchQuery(mailbox="Sent", subject_contains=unique_id),
        company_id=company_id,
    )
    assert len(fetched) == 1
    assert fetched[0].subject == subject


@pytest.mark.asyncio
async def test_system_connection_put_forbidden(
    mail_service: MailService,
    unique_id: str,
) -> None:
    _ = unique_id
    with pytest.raises(MailSystemConnectionReadOnlyError):
        _ = await mail_service.upsert_connection(
            CompanyMailConnectionUpsertPayload(
                mail_domain="linnex.io",
                provider=MailProvider.GENERIC_IMAP_SMTP,
                imap_host="imap.example.com",
                imap_port=993,
                smtp_host="smtp.example.com",
                smtp_port=465,
            ),
            company_id="system",
        )


@pytest.mark.asyncio
async def test_healthcheck_uses_recording_port(
    mail_service: MailService,
    unique_id: str,
) -> None:
    company_id = f"mailhc_{unique_id}"
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
    health = await mail_service.healthcheck(company_id=company_id)
    assert health.imap_ok is True
    assert health.smtp_ok is True


@pytest.mark.asyncio
async def test_list_and_get_message_with_attachment_and_stub(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    unique_id: str,
) -> None:
    company_id = f"mailatt_{unique_id}"
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
            local_part=f"bob.{unique_id}",
            password="mailbox-pass-2",
            provision=False,
        ),
        company_id=company_id,
    )
    recording_mail_port.inbox.append(
        InboundMailMessage(
            uid="101",
            message_id=f"<att-{unique_id}@example.com>",
            subject=f"attach-{unique_id}",
            from_address="peer@example.com",
            to_addresses=[binding.email_address],
            body_text="see attach",
            attachments=[
                MailAttachment(
                    filename="ok.txt",
                    content_type="text/plain",
                    content=b"payload-ok",
                    size=10,
                    available=True,
                ),
                MailAttachment(
                    filename="broken.bin",
                    content_type="application/octet-stream",
                    content=b"",
                    size=0,
                    available=False,
                    parse_error="payload_decode_failed:ValueError",
                ),
            ],
        )
    )

    listed = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="INBOX",
            limit=50,
        ),
        company_id=company_id,
    )
    assert len(listed) == 1
    assert listed[0].uid == "101"
    assert listed[0].subject == f"attach-{unique_id}"
    assert listed[0].attachment_count == 2

    opened = await mail_service.get_message(
        mailbox_binding_id=binding.mailbox_binding_id,
        uid="101",
        folder="INBOX",
        company_id=company_id,
    )
    assert opened.subject == f"attach-{unique_id}"
    assert len(opened.attachments) == 2
    assert opened.attachments[0].filename == "ok.txt"
    assert opened.attachments[0].available is True
    assert opened.attachments[0].content_base64 is not None
    assert opened.attachments[1].filename == "broken.bin"
    assert opened.attachments[1].available is False
    assert opened.attachments[1].parse_error == "payload_decode_failed:ValueError"
    assert opened.attachments[1].content_base64 is None
    assert opened.unread is False
    assert len(recording_mail_port.mark_seen_calls) == 1
    assert recording_mail_port.mark_seen_calls[0][2] == "101"

    listed_after = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="INBOX",
            limit=50,
        ),
        company_id=company_id,
    )
    assert listed_after[0].unread is False

    with pytest.raises(MailMessageNotFoundError):
        _ = await mail_service.get_message(
            mailbox_binding_id=binding.mailbox_binding_id,
            uid="missing-uid",
            folder="INBOX",
            company_id=company_id,
        )


@pytest.mark.asyncio
async def test_list_messages_fetches_bodies_for_attachment_count(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    unique_id: str,
) -> None:
    company_id = f"mailhdr_{unique_id}"
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
            local_part=f"cara.{unique_id}",
            password="mailbox-pass-3",
            provision=False,
        ),
        company_id=company_id,
    )
    recording_mail_port.inbox.append(
        InboundMailMessage(
            uid="5",
            subject="hdr",
            from_address="x@example.com",
            body_text="should-not-matter-for-list",
        )
    )
    _ = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="INBOX",
            limit=10,
        ),
        company_id=company_id,
    )
    assert recording_mail_port.fetch_messages_calls[-1][2] is True


@pytest.mark.asyncio
async def test_list_messages_newest_first(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    unique_id: str,
) -> None:
    company_id = f"mailord_{unique_id}"
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
            local_part=f"dana.{unique_id}",
            password="mailbox-pass-4",
            provision=False,
        ),
        company_id=company_id,
    )
    recording_mail_port.inbox.extend(
        [
            InboundMailMessage(
                uid="1",
                subject="older",
                from_address="a@example.com",
                body_text="old",
                unread=False,
            ),
            InboundMailMessage(
                uid="2",
                subject="newer",
                from_address="b@example.com",
                body_text="new",
                unread=True,
            ),
        ]
    )
    listed = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="INBOX",
            limit=50,
        ),
        company_id=company_id,
    )
    assert [item.uid for item in listed] == ["2", "1"]
    assert listed[0].unread is True
    assert listed[1].unread is False
