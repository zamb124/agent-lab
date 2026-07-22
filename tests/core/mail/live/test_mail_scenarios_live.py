"""Live: attachments, unicode, reply headers, lazy bind, iMIP→calendar."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import pytest

from core.config.models import MailConfig
from core.mail.imip import (
    build_outbound_imip_invite,
    calendar_upsert_payload_from_imip,
    extract_imip_ics,
)
from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    MailAttachment,
    MailboxEnsureSpec,
    MailboxInfo,
    MailboxSecret,
    MailProvider,
    OutboundMailMessage,
)
from core.mail.ports import MailServerPort
from core.mail.service import MailService
from tests.core.mail.live.poll import poll_fetch_message as _poll_fetch_message

pytestmark = [pytest.mark.network, pytest.mark.timeout(180)]


@pytest.mark.asyncio
async def test_attachment_roundtrip(
    mail_live_port: MailServerPort,
    mail_live_mailbox: tuple[MailboxInfo, MailboxSecret, list[str]],
    unique_id: str,
) -> None:
    info, secret, _created = mail_live_mailbox
    subject = f"platform-mail-attach-{unique_id}"
    payload = f"hello-attach-{unique_id}".encode("utf-8")
    message_id = f"<plt-att-{unique_id}@linnex.io>"
    _ = await mail_live_port.send_message(
        secret,
        OutboundMailMessage(
            to_addresses=[info.email_address],
            subject=subject,
            body_text=f"with attachment {unique_id}",
            message_id=message_id,
            attachments=[
                MailAttachment(
                    filename=f"note-{unique_id}.txt",
                    content_type="text/plain",
                    content=payload,
                )
            ],
        ),
    )
    found = await _poll_fetch_message(
        mail_live_port, secret, message_id=message_id, subject=subject
    )
    assert found is not None
    assert len(found.attachments) >= 1
    matched = next(
        (item for item in found.attachments if item.filename.endswith(".txt")),
        None,
    )
    assert matched is not None
    assert matched.content == payload


@pytest.mark.asyncio
async def test_unicode_subject_and_body(
    mail_live_port: MailServerPort,
    mail_live_mailbox: tuple[MailboxInfo, MailboxSecret, list[str]],
    unique_id: str,
) -> None:
    info, secret, _created = mail_live_mailbox
    subject = f"Письмо-{unique_id}-проверка"
    body = f"Текст с кириллицей {unique_id}"
    message_id = f"<plt-ru-{unique_id}@linnex.io>"
    _ = await mail_live_port.send_message(
        secret,
        OutboundMailMessage(
            to_addresses=[info.email_address],
            subject=subject,
            body_text=body,
            message_id=message_id,
        ),
    )
    found = await _poll_fetch_message(
        mail_live_port, secret, message_id=message_id, subject=subject
    )
    assert found is not None
    assert found.subject == subject
    assert found.body_text is not None
    assert unique_id in found.body_text


@pytest.mark.asyncio
async def test_reply_headers_roundtrip(
    mail_live_port: MailServerPort,
    mail_live_mailbox: tuple[MailboxInfo, MailboxSecret, list[str]],
    unique_id: str,
) -> None:
    info, secret, _created = mail_live_mailbox
    parent_subject = f"platform-mail-parent-{unique_id}"
    parent_id = f"<plt-parent-{unique_id}@linnex.io>"
    _ = await mail_live_port.send_message(
        secret,
        OutboundMailMessage(
            to_addresses=[info.email_address],
            subject=parent_subject,
            body_text="parent",
            message_id=parent_id,
        ),
    )
    parent = await _poll_fetch_message(
        mail_live_port, secret, message_id=parent_id, subject=parent_subject
    )
    assert parent is not None
    reply_subject = f"Re: platform-mail-parent-{unique_id}"
    reply_id = f"<plt-reply-{unique_id}@linnex.io>"
    # Shared hosting may rewrite Message-Id — reply to whatever landed
    parent_mid = parent.message_id if parent.message_id is not None else parent_id
    _ = await mail_live_port.send_message(
        secret,
        OutboundMailMessage(
            to_addresses=[info.email_address],
            subject=reply_subject,
            body_text="reply",
            message_id=reply_id,
            in_reply_to=parent_mid,
            references=parent_mid,
        ),
    )
    reply = await _poll_fetch_message(
        mail_live_port, secret, message_id=reply_id, subject=reply_subject
    )
    assert reply is not None
    assert reply.in_reply_to is not None
    assert parent_mid in reply.in_reply_to or parent_mid.strip("<>") in reply.in_reply_to


@pytest.mark.asyncio
async def test_lazy_get_or_create_user_binding(
    mail_live_service: MailService,
    mail_live_port: MailServerPort,
    mail_live_settings: MailConfig,
    mail_quota_sweeper: list[str],
    unique_id: str,
) -> None:
    company_id = f"mail_lazy_{unique_id}"
    system = mail_live_settings.system
    isp = system.ispmanager
    if (
        system.imap_host is None
        or system.smtp_host is None
        or isp.base_url is None
        or isp.authinfo_user is None
        or isp.authinfo_password is None
    ):
        raise RuntimeError("mail.system incomplete")
    prefix = mail_live_settings.live_test.mailbox_prefix
    local_part = f"{prefix}{unique_id}-lazy".lower().replace("_", "-")[:64]
    email_address = f"{local_part}@{system.mail_domain}".lower()
    mail_quota_sweeper.append(email_address)

    _ = await mail_live_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=system.mail_domain,
            provider=MailProvider.ISPMANAGER,
            imap_host=system.imap_host,
            imap_port=system.imap_port,
            smtp_host=system.smtp_host,
            smtp_port=system.smtp_port,
            use_ssl=system.use_ssl,
            ispmanager_base_url=isp.base_url,
            ispmanager_authinfo_user=isp.authinfo_user,
            ispmanager_authinfo_password=isp.authinfo_password,
        ),
        company_id=company_id,
    )
    user_id = f"user_lazy_{unique_id}"
    first = await mail_live_service.get_or_create_user_binding(
        user_id,
        company_id=company_id,
        local_part=local_part,
    )
    second = await mail_live_service.get_or_create_user_binding(
        user_id,
        company_id=company_id,
        local_part=local_part,
    )
    assert first.mailbox_binding_id == second.mailbox_binding_id
    assert first.email_address == email_address
    listed = await mail_live_port.list_mailboxes(system.mail_domain)
    assert any(item.email_address == email_address for item in listed)
    await mail_live_service.unbind_mailbox(first.mailbox_binding_id, company_id=company_id)
    await mail_live_port.delete_mailbox(email_address)
    if email_address in mail_quota_sweeper:
        mail_quota_sweeper.remove(email_address)


@pytest.mark.asyncio
async def test_imip_invite_creates_calendar_event(
    mail_live_port: MailServerPort,
    mail_live_settings: MailConfig,
    mail_quota_sweeper: list[str],
    container,
    unique_id: str,
) -> None:
    prefix = mail_live_settings.live_test.mailbox_prefix
    domain = mail_live_settings.system.mail_domain
    local_org = f"{prefix}{unique_id}-org".lower().replace("_", "-")[:64]
    local_att = f"{prefix}{unique_id}-att".lower().replace("_", "-")[:64]
    password_org = secrets.token_urlsafe(20)
    password_att = secrets.token_urlsafe(20)
    created: list[str] = []
    try:
        org = await mail_live_port.ensure_mailbox(
            MailboxEnsureSpec(mail_domain=domain, local_part=local_org, password=password_org)
        )
        att = await mail_live_port.ensure_mailbox(
            MailboxEnsureSpec(mail_domain=domain, local_part=local_att, password=password_att)
        )
        created.extend([org.email_address, att.email_address])
        mail_quota_sweeper.extend(created)
        secret_org = MailboxSecret(email_address=org.email_address, password=password_org)
        secret_att = MailboxSecret(email_address=att.email_address, password=password_att)

        start_at = datetime.now(timezone.utc) + timedelta(days=1)
        end_at = start_at + timedelta(hours=1)
        title = f"Mail meet {unique_id}"
        invite, event_uid = build_outbound_imip_invite(
            to_address=att.email_address,
            organizer_email=org.email_address,
            title=title,
            description=f"desc {unique_id}",
            start_at=start_at,
            end_at=end_at,
        )
        _ = await mail_live_port.send_message(secret_org, invite)
        found = await _poll_fetch_message(
            mail_live_port,
            secret_att,
            message_id=invite.message_id or "",
            subject=invite.subject,
        )
        assert found is not None
        ics = extract_imip_ics(found)
        assert ics is not None
        assert "METHOD:REQUEST" in ics
        payload = calendar_upsert_payload_from_imip(
            ics,
            attendee_email=att.email_address,
            mailbox_binding_id=att.mailbox_binding_id,
        )
        assert payload.title == title
        assert payload.metadata["imip_uid"] == event_uid
        assert payload.mailbox_binding_id == att.mailbox_binding_id

        company_id = "system"
        event = await container.calendar_service.upsert_event(
            event_id=None,
            payload=payload,
            user_id=f"organizer_{unique_id}",
            company_id=company_id,
        )
        assert event.title == title
        assert event.metadata.get("imip_uid") == event_uid
    finally:
        for email_address in created:
            await mail_live_port.delete_mailbox(email_address)
            if email_address in mail_quota_sweeper:
                mail_quota_sweeper.remove(email_address)
