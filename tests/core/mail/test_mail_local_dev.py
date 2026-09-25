"""mail.local_dev: пароли из conf, без remote password mutation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.ai.company_settings import encrypt_secret
from core.authz.factory import build_authz_service
from core.config import get_settings
from core.config.models import (
    MailConfig,
    MailLiveTestConfig,
    MailLocalDevConfig,
    MailSystemConfig,
)
from core.mail.exceptions import MailConfigError
from core.mail.models import (
    CompanyMailConnection,
    MailboxBinding,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailboxInfo,
    MailConnectionStatus,
    MailProvider,
)
from core.mail.service import MailService
from tests.core.mail.fakes import RecordingMailServerPort


def _make_service(
    *,
    recording_mail_port: RecordingMailServerPort,
    mailbox_passwords: dict[str, str],
) -> MailService:
    shared_url = get_settings().database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен для mail tests")
    return MailService(
        authz=build_authz_service(),
        mail_config=MailConfig(
            system=MailSystemConfig(enabled=False),
            live_test=MailLiveTestConfig(enabled=False),
            local_dev=MailLocalDevConfig(
                enabled=True,
                mutate_remote_passwords=False,
                mailbox_passwords=mailbox_passwords,
            ),
        ),
        port_override=recording_mail_port,
    )


@pytest.mark.asyncio
async def test_local_dev_binding_secret_uses_conf_password(
    recording_mail_port: RecordingMailServerPort,
    di,
    unique_id: str,
) -> None:
    now = datetime.now(timezone.utc)
    company_id = f"maillocal_{unique_id}"
    email = f"user@{company_id}.example.com"
    conn_id = f"mailconn_{unique_id}"
    _ = await CompanyMailConnection.upsert_by_company_mail_connection_id(
        CompanyMailConnection(
            company_mail_connection_id=conn_id,
            company_id=company_id,
            mail_domain=f"{company_id}.example.com",
            provider=MailProvider.ISPMANAGER,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
            supports_provision=True,
            status=MailConnectionStatus.ACTIVE,
            ispmanager=None,
            created_at=now,
            updated_at=now,
        )
    )
    binding = await MailboxBinding.upsert_by_email(
        MailboxBinding(
            mailbox_binding_id=f"mailbind_{unique_id}",
            company_id=company_id,
            company_mail_connection_id=conn_id,
            user_id=f"user_{unique_id}",
            kind=MailboxBindingKind.USER,
            email_address=email,
            local_part="user",
            sync_enabled=True,
            password_encrypted=encrypt_secret("stale-db-password"),
            created_at=now,
            updated_at=now,
        )
    )
    service = _make_service(
        recording_mail_port=recording_mail_port,
        mailbox_passwords={email: "from-conf-local"},
    )
    secret = service.binding_secret(binding)
    assert secret.password == "from-conf-local"


@pytest.mark.asyncio
async def test_local_dev_bind_existing_mailbox_skips_set_password(
    recording_mail_port: RecordingMailServerPort,
    di,
    unique_id: str,
) -> None:
    now = datetime.now(timezone.utc)
    company_id = f"maillocal2_{unique_id}"
    domain = f"{company_id}.example.com"
    email = f"desk@{domain}"
    conn_id = f"mailconn2_{unique_id}"
    _ = await CompanyMailConnection.upsert_by_company_mail_connection_id(
        CompanyMailConnection(
            company_mail_connection_id=conn_id,
            company_id=company_id,
            mail_domain=domain,
            provider=MailProvider.ISPMANAGER,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
            supports_provision=True,
            status=MailConnectionStatus.ACTIVE,
            ispmanager=None,
            created_at=now,
            updated_at=now,
        )
    )
    recording_mail_port.mailboxes[email] = MailboxInfo(
        email_address=email,
        local_part="desk",
        mail_domain=domain,
    )
    recording_mail_port.mailbox_passwords[email] = "server-password-unchanged"

    service = _make_service(
        recording_mail_port=recording_mail_port,
        mailbox_passwords={email: "from-conf-local"},
    )
    binding = await service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=f"user_{unique_id}",
            local_part="desk",
            provision=True,
        ),
        company_id=company_id,
    )
    assert binding.email_address == email
    assert recording_mail_port.set_password_calls == []
    assert recording_mail_port.mailbox_passwords[email] == "server-password-unchanged"
    assert service.binding_secret(binding).password == "from-conf-local"


@pytest.mark.asyncio
async def test_local_dev_bind_existing_mailbox_without_conf_password_raises(
    recording_mail_port: RecordingMailServerPort,
    di,
    unique_id: str,
) -> None:
    now = datetime.now(timezone.utc)
    company_id = f"maillocal3_{unique_id}"
    domain = f"{company_id}.example.com"
    email = f"desk@{domain}"
    conn_id = f"mailconn3_{unique_id}"
    _ = await CompanyMailConnection.upsert_by_company_mail_connection_id(
        CompanyMailConnection(
            company_mail_connection_id=conn_id,
            company_id=company_id,
            mail_domain=domain,
            provider=MailProvider.ISPMANAGER,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
            supports_provision=True,
            status=MailConnectionStatus.ACTIVE,
            ispmanager=None,
            created_at=now,
            updated_at=now,
        )
    )
    recording_mail_port.mailboxes[email] = MailboxInfo(
        email_address=email,
        local_part="desk",
        mail_domain=domain,
    )
    recording_mail_port.mailbox_passwords[email] = "server-password-unchanged"
    service = _make_service(
        recording_mail_port=recording_mail_port,
        mailbox_passwords={},
    )
    with pytest.raises(MailConfigError, match="mailbox_passwords"):
        _ = await service.bind_mailbox(
            MailboxBindingCreatePayload(
                kind=MailboxBindingKind.USER,
                user_id=f"user_{unique_id}",
                local_part="desk",
                provision=True,
            ),
            company_id=company_id,
        )
    assert recording_mail_port.set_password_calls == []
    assert recording_mail_port.mailbox_passwords[email] == "server-password-unchanged"
