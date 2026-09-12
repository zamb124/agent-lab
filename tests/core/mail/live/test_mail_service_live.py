"""Live MailService: real Postgres + real ISPmanager/IMAP/SMTP."""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timezone

import pytest

from core.config.models import MailConfig
from core.mail.exceptions import MailSystemConnectionReadOnlyError
from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailFetchQuery,
    MailProvider,
    OutboundMailMessage,
)
from core.mail.ports import MailServerPort
from core.mail.service import MailService

pytestmark = [pytest.mark.network, pytest.mark.timeout(180)]


@pytest.mark.asyncio
async def test_ensure_system_connection_and_roles_idempotent(
    mail_live_service: MailService,
    mail_live_settings: MailConfig,
) -> None:
    first_conn = await mail_live_service.ensure_system_mail_connection()
    assert first_conn is not None
    assert first_conn.mail_domain == mail_live_settings.system.mail_domain

    roles_first = await mail_live_service.ensure_system_role_mailboxes()
    roles_second = await mail_live_service.ensure_system_role_mailboxes()
    assert sorted(roles_first.ensured) == sorted(roles_second.ensured)
    for local_part in mail_live_settings.system.role_mailboxes:
        assert f"{local_part}@{mail_live_settings.system.mail_domain}".lower() in {
            item.lower() for item in roles_second.ensured
        }

    second_conn = await mail_live_service.ensure_system_mail_connection()
    assert second_conn is not None
    assert second_conn.company_mail_connection_id == first_conn.company_mail_connection_id

    bindings = await mail_live_service.list_bindings(company_id="system")
    role_emails = {
        binding.email_address
        for binding in bindings
        if binding.kind == MailboxBindingKind.ROLE
    }
    for local_part in mail_live_settings.system.role_mailboxes:
        assert f"{local_part}@{mail_live_settings.system.mail_domain}".lower() in role_emails


@pytest.mark.asyncio
async def test_system_connection_put_forbidden_after_ensure(
    mail_live_service: MailService,
) -> None:
    connection = await mail_live_service.ensure_system_mail_connection()
    assert connection is not None
    with pytest.raises(MailSystemConnectionReadOnlyError):
        _ = await mail_live_service.upsert_connection(
            CompanyMailConnectionUpsertPayload(
                mail_domain=connection.mail_domain,
                provider=MailProvider.GENERIC_IMAP_SMTP,
                imap_host=connection.imap_host,
                imap_port=connection.imap_port,
                smtp_host=connection.smtp_host,
                smtp_port=connection.smtp_port,
            ),
            company_id="system",
        )


@pytest.mark.asyncio
async def test_bind_user_provision_send_fetch(
    mail_live_service: MailService,
    mail_live_port: MailServerPort,
    mail_live_settings: MailConfig,
    unique_id: str,
) -> None:
    company_id = f"mail_live_{unique_id}"
    system = mail_live_settings.system
    isp = system.ispmanager
    if (
        system.imap_host is None
        or system.smtp_host is None
        or isp.base_url is None
        or isp.authinfo_user is None
        or isp.authinfo_password is None
    ):
        raise RuntimeError("mail.system incomplete for live service bind test")

    prefix = mail_live_settings.live_test.mailbox_prefix
    local_part = f"{prefix}{unique_id}-svc".lower().replace("_", "-")[:64]
    password = secrets.token_urlsafe(20)
    email_address = f"{local_part}@{system.mail_domain}".lower()

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

    binding = await mail_live_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=f"user_{unique_id}",
            local_part=local_part,
            password=password,
            provision=True,
        ),
        company_id=company_id,
    )
    assert binding.email_address == email_address

    message_id = f"<plt-svc-{unique_id}@linnex.io>"
    subject = f"platform-mail-svc-{unique_id}"
    try:
        send_result = await mail_live_service.send_from_binding(
            binding.mailbox_binding_id,
            OutboundMailMessage(
                to_addresses=[email_address],
                subject=subject,
                body_text=f"svc live {unique_id} at {datetime.now(timezone.utc).isoformat()}",
                message_id=message_id,
            ),
            company_id=company_id,
        )
        assert send_result.message_id == message_id

        found = False
        deadline = asyncio.get_running_loop().time() + 90.0
        while asyncio.get_running_loop().time() < deadline:
            fetched = await mail_live_service.fetch_for_binding(
                binding.mailbox_binding_id,
                MailFetchQuery(subject_contains=subject, limit=50),
                company_id=company_id,
            )
            if any(item.subject == subject for item in fetched):
                found = True
                break
            await asyncio.sleep(2.0)
        assert found is True
    finally:
        await mail_live_service.unbind_mailbox(
            binding.mailbox_binding_id,
            company_id=company_id,
        )
        await mail_live_port.delete_mailbox(email_address)
