"""Live-интеграция с купленной почтой (ISPmanager + IMAP/SMTP)."""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timezone

import pytest

from core.config.models import MailConfig
from core.mail.exceptions import MailDeleteDeniedError
from core.mail.models import (
    InboundMailMessage,
    MailboxEnsureSpec,
    MailboxInfo,
    MailboxSecret,
    MailFetchQuery,
    OutboundMailMessage,
)
from core.mail.ports import MailServerPort

pytestmark = [pytest.mark.network, pytest.mark.timeout(120)]


async def _poll_fetch_message(
    port: MailServerPort,
    secret: MailboxSecret,
    *,
    message_id: str,
    subject: str,
    deadline_sec: float = 90.0,
) -> InboundMailMessage | None:
    """Shared hosting может переписать Message-Id — матчим subject (+ id если сохранился)."""
    deadline = asyncio.get_running_loop().time() + deadline_sec
    while asyncio.get_running_loop().time() < deadline:
        messages = await port.fetch_messages(
            secret,
            MailFetchQuery(subject_contains=subject, limit=50),
        )
        for item in messages:
            if item.subject == subject:
                return item
            if item.message_id == message_id:
                return item
        all_recent = await port.fetch_messages(secret, MailFetchQuery(limit=50))
        for item in all_recent:
            if item.subject == subject or item.message_id == message_id:
                return item
        await asyncio.sleep(2.0)
    return None


@pytest.mark.asyncio
async def test_healthcheck_full(
    mail_live_port: MailServerPort,
    mail_live_mailbox: tuple[MailboxInfo, MailboxSecret, list[str]],
) -> None:
    _info, secret, _created = mail_live_mailbox
    health = await mail_live_port.healthcheck()
    assert health.provision_ok is True
    assert health.imap_ok is True
    assert health.smtp_ok is True

    authed = await mail_live_port.healthcheck_with_credentials(secret)
    assert authed.provision_ok is True
    assert authed.imap_ok is True
    assert authed.smtp_ok is True


@pytest.mark.asyncio
async def test_ensure_list_contains(
    mail_live_port: MailServerPort,
    mail_live_mailbox: tuple[MailboxInfo, MailboxSecret, list[str]],
) -> None:
    info, _secret, _created = mail_live_mailbox
    listed = await mail_live_port.list_mailboxes(info.mail_domain)
    assert any(item.email_address == info.email_address for item in listed)


@pytest.mark.asyncio
async def test_loopback_send_fetch(
    mail_live_port: MailServerPort,
    mail_live_mailbox: tuple[MailboxInfo, MailboxSecret, list[str]],
    unique_id: str,
) -> None:
    info, secret, _created = mail_live_mailbox
    message_id = f"<plt-live-{unique_id}@linnex.io>"
    subject = f"platform-mail-live-{unique_id}"
    send_result = await mail_live_port.send_message(
        secret,
        OutboundMailMessage(
            to_addresses=[info.email_address],
            subject=subject,
            body_text=f"live body {unique_id} at {datetime.now(timezone.utc).isoformat()}",
            message_id=message_id,
        ),
    )
    assert send_result.message_id == message_id
    found = await _poll_fetch_message(
        mail_live_port,
        secret,
        message_id=message_id,
        subject=subject,
    )
    assert found is not None
    assert found.subject == subject
    assert found.body_text is not None
    assert unique_id in found.body_text


@pytest.mark.asyncio
async def test_send_between_two_plt_mailboxes(
    mail_live_port: MailServerPort,
    mail_live_settings: MailConfig,
    unique_id: str,
) -> None:
    prefix = mail_live_settings.live_test.mailbox_prefix
    domain = mail_live_settings.system.mail_domain
    local_a = f"{prefix}{unique_id}-a".lower().replace("_", "-")[:64]
    local_b = f"{prefix}{unique_id}-b".lower().replace("_", "-")[:64]
    password_a = secrets.token_urlsafe(20)
    password_b = secrets.token_urlsafe(20)
    created: list[str] = []
    try:
        info_a = await mail_live_port.ensure_mailbox(
            MailboxEnsureSpec(mail_domain=domain, local_part=local_a, password=password_a)
        )
        created.append(info_a.email_address)
        info_b = await mail_live_port.ensure_mailbox(
            MailboxEnsureSpec(mail_domain=domain, local_part=local_b, password=password_b)
        )
        created.append(info_b.email_address)
        secret_a = MailboxSecret(email_address=info_a.email_address, password=password_a)
        secret_b = MailboxSecret(email_address=info_b.email_address, password=password_b)
        message_id = f"<plt-ab-{unique_id}@linnex.io>"
        subject = f"platform-mail-ab-{unique_id}"
        _ = await mail_live_port.send_message(
            secret_a,
            OutboundMailMessage(
                to_addresses=[info_b.email_address],
                subject=subject,
                body_text=f"ab {unique_id}",
                message_id=message_id,
            ),
        )
        assert await _poll_fetch_message(
            mail_live_port,
            secret_b,
            message_id=message_id,
            subject=subject,
        ) is not None
    finally:
        for email_address in created:
            await mail_live_port.delete_mailbox(email_address)


@pytest.mark.asyncio
async def test_ensure_idempotent_no_password_reset(
    mail_live_port: MailServerPort,
    mail_live_settings: MailConfig,
    unique_id: str,
) -> None:
    prefix = mail_live_settings.live_test.mailbox_prefix
    domain = mail_live_settings.system.mail_domain
    local_part = f"{prefix}{unique_id}-idem".lower().replace("_", "-")[:64]
    password = secrets.token_urlsafe(20)
    other_password = secrets.token_urlsafe(20)
    created: list[str] = []
    try:
        first = await mail_live_port.ensure_mailbox(
            MailboxEnsureSpec(mail_domain=domain, local_part=local_part, password=password)
        )
        created.append(first.email_address)
        second = await mail_live_port.ensure_mailbox(
            MailboxEnsureSpec(mail_domain=domain, local_part=local_part, password=other_password)
        )
        assert first.email_address == second.email_address
        secret = MailboxSecret(email_address=first.email_address, password=password)
        await mail_live_port.healthcheck_with_credentials(secret)
        authed = await mail_live_port.healthcheck_with_credentials(secret)
        assert authed.imap_ok is True
        assert authed.smtp_ok is True
    finally:
        for email_address in created:
            await mail_live_port.delete_mailbox(email_address)


@pytest.mark.asyncio
async def test_ensure_role_mailboxes_idempotent(
    mail_live_port: MailServerPort,
    mail_live_settings: MailConfig,
) -> None:
    """Idempotent ensure role locals: create-if-missing, без delete и без смены пароля существующих."""
    domain = mail_live_settings.system.mail_domain
    password = secrets.token_urlsafe(20)
    for local_part in mail_live_settings.system.role_mailboxes:
        first = await mail_live_port.ensure_mailbox(
            MailboxEnsureSpec(mail_domain=domain, local_part=local_part, password=password)
        )
        second = await mail_live_port.ensure_mailbox(
            MailboxEnsureSpec(mail_domain=domain, local_part=local_part, password=password)
        )
        assert first.email_address == second.email_address
    listed = await mail_live_port.list_mailboxes(domain)
    addresses = {item.email_address for item in listed}
    for local_part in mail_live_settings.system.role_mailboxes:
        assert f"{local_part}@{domain}".lower() in addresses


@pytest.mark.asyncio
async def test_delete_denied_protected_local(
    mail_live_port: MailServerPort,
    mail_live_settings: MailConfig,
) -> None:
    domain = mail_live_settings.system.mail_domain
    with pytest.raises(MailDeleteDeniedError):
        await mail_live_port.delete_mailbox(f"support@{domain}")


@pytest.mark.asyncio
async def test_delete_denied_without_prefix(
    mail_live_port: MailServerPort,
    mail_live_settings: MailConfig,
) -> None:
    domain = mail_live_settings.system.mail_domain
    with pytest.raises(MailDeleteDeniedError):
        await mail_live_port.delete_mailbox(f"no-prefix-live@{domain}")
