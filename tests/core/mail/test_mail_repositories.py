"""CRUD репозиториев почты на реальной shared БД."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.mail.models import (
    CompanyMailConnection,
    IspmanagerProvisionConfig,
    MailboxBinding,
    MailboxBindingKind,
    MailConnectionStatus,
    MailProvider,
)
from core.mail.repositories import CompanyMailConnectionRepository, MailboxBindingRepository


@pytest.mark.asyncio
async def test_company_mail_connection_upsert_and_get(
    mail_connection_repository: CompanyMailConnectionRepository,
    unique_id: str,
) -> None:
    company_id = f"mailco_{unique_id}"
    now = datetime.now(timezone.utc)
    connection = CompanyMailConnection(
        company_mail_connection_id=f"mailconn_{unique_id}",
        company_id=company_id,
        mail_domain=f"{unique_id}.example.com",
        provider=MailProvider.ISPMANAGER,
        imap_host="imap.example.com",
        imap_port=993,
        smtp_host="smtp.example.com",
        smtp_port=465,
        use_ssl=True,
        supports_provision=True,
        status=MailConnectionStatus.ACTIVE,
        ispmanager=IspmanagerProvisionConfig(
            base_url="https://panel.example.com:1500/ispmgr",
            authinfo_user="admin",
            authinfo_password_encrypted="enc-token",
        ),
        created_at=now,
        updated_at=now,
    )
    stored = await mail_connection_repository.upsert(connection)
    assert stored.company_id == company_id
    assert stored.mail_domain == f"{unique_id}.example.com"
    assert stored.ispmanager is not None
    assert stored.ispmanager.authinfo_user == "admin"

    loaded = await mail_connection_repository.get_by_company(company_id)
    assert loaded is not None
    assert loaded.company_mail_connection_id == f"mailconn_{unique_id}"
    assert loaded.provider == MailProvider.ISPMANAGER


@pytest.mark.asyncio
async def test_mailbox_binding_upsert_list_delete(
    mail_connection_repository: CompanyMailConnectionRepository,
    mailbox_binding_repository: MailboxBindingRepository,
    unique_id: str,
) -> None:
    company_id = f"mailco_{unique_id}"
    now = datetime.now(timezone.utc)
    _ = await mail_connection_repository.upsert(
        CompanyMailConnection(
            company_mail_connection_id=f"mailconn_{unique_id}",
            company_id=company_id,
            mail_domain=f"{unique_id}.example.com",
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
            supports_provision=False,
            status=MailConnectionStatus.ACTIVE,
            ispmanager=None,
            created_at=now,
            updated_at=now,
        )
    )
    email_address = f"user.{unique_id}@{unique_id}.example.com"
    binding = MailboxBinding(
        mailbox_binding_id=f"mailbind_{unique_id}",
        company_id=company_id,
        company_mail_connection_id=f"mailconn_{unique_id}",
        user_id=f"user_{unique_id}",
        kind=MailboxBindingKind.USER,
        email_address=email_address,
        local_part=f"user.{unique_id}",
        sync_enabled=True,
        password_encrypted="enc-pass",
        created_at=now,
        updated_at=now,
    )
    stored = await mailbox_binding_repository.upsert(binding)
    assert stored.email_address == email_address

    listed = await mailbox_binding_repository.list_by_company(company_id)
    assert len(listed) == 1
    assert listed[0].mailbox_binding_id == f"mailbind_{unique_id}"

    by_user = await mailbox_binding_repository.get_by_user(company_id, f"user_{unique_id}")
    assert by_user is not None
    assert by_user.email_address == email_address

    deleted = await mailbox_binding_repository.delete(f"mailbind_{unique_id}", company_id)
    assert deleted is True
    assert await mailbox_binding_repository.get(f"mailbind_{unique_id}", company_id) is None
