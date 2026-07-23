"""Multi-mailbox per user: list_by_user, is_default, API /bindings/me."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.ai.company_settings import encrypt_secret
from core.config import get_settings
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
async def test_list_by_user_and_default(unique_id: str) -> None:
    company_id = f"mail_multi_{unique_id}"
    user_id = f"user_{unique_id}"
    shared_url = get_settings().database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен")
    conn_repo = CompanyMailConnectionRepository(db_url=shared_url)
    bind_repo = MailboxBindingRepository(db_url=shared_url)
    now = datetime.now(timezone.utc)
    _ = await conn_repo.upsert(
        CompanyMailConnection(
            company_mail_connection_id=f"mailconn_multi_{unique_id}",
            company_id=company_id,
            mail_domain=f"multi-{unique_id}.example.com",
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
    first = await bind_repo.upsert(
        MailboxBinding(
            mailbox_binding_id=f"mailbind_a_{unique_id}",
            company_id=company_id,
            company_mail_connection_id=f"mailconn_multi_{unique_id}",
            user_id=user_id,
            kind=MailboxBindingKind.USER,
            email_address=f"a.{unique_id}@multi-{unique_id}.example.com",
            local_part=f"a.{unique_id}",
            sync_enabled=True,
            is_default=True,
            password_encrypted="enc-a",
            created_at=now,
            updated_at=now,
        )
    )
    second = await bind_repo.upsert(
        MailboxBinding(
            mailbox_binding_id=f"mailbind_b_{unique_id}",
            company_id=company_id,
            company_mail_connection_id=f"mailconn_multi_{unique_id}",
            user_id=user_id,
            kind=MailboxBindingKind.USER,
            email_address=f"b.{unique_id}@multi-{unique_id}.example.com",
            local_part=f"b.{unique_id}",
            sync_enabled=True,
            is_default=False,
            password_encrypted="enc-b",
            created_at=now,
            updated_at=now,
        )
    )
    listed = await bind_repo.list_by_user(company_id, user_id)
    assert len(listed) == 2
    assert listed[0].mailbox_binding_id == first.mailbox_binding_id
    by_user = await bind_repo.get_by_user(company_id, user_id)
    assert by_user is not None
    assert by_user.mailbox_binding_id == first.mailbox_binding_id

    await bind_repo.clear_defaults_for_user(company_id, user_id)
    promoted = second.model_copy(update={"is_default": True})
    _ = await bind_repo.upsert(promoted)
    by_user2 = await bind_repo.get_by_user(company_id, user_id)
    assert by_user2 is not None
    assert by_user2.mailbox_binding_id == second.mailbox_binding_id


@pytest.mark.asyncio
async def test_mail_api_bindings_me_and_admin_list(
    frontend_client,
    auth_headers_system,
    unique_id: str,
) -> None:
    """API list bindings: company connection для system (partial unique на scope=company).

    Upsert по PK не конфликтует с uq_company_mail_connections_company_scope:
    если company-scope уже есть — обновляем существующую запись, иначе создаём.
    """
    shared_url = get_settings().database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен")
    repo = CompanyMailConnectionRepository(db_url=shared_url)
    now = datetime.now(timezone.utc)
    existing = await repo.get_by_company("system")
    connection_id = (
        existing.company_mail_connection_id
        if existing is not None
        else f"mailconn_api_me_{unique_id}"
    )
    _ = await repo.upsert(
        CompanyMailConnection(
            company_mail_connection_id=connection_id,
            company_id="system",
            mail_domain="linnex.io",
            provider=MailProvider.ISPMANAGER,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
            supports_provision=True,
            status=MailConnectionStatus.ACTIVE,
            ispmanager=IspmanagerProvisionConfig(
                base_url="https://panel.example.com/ispmgr",
                authinfo_user="admin",
                authinfo_password_encrypted=encrypt_secret(f"pass-{unique_id}"),
            ),
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
    )

    me_response = await frontend_client.get(
        "/frontend/api/mail/bindings/me",
        headers=auth_headers_system,
    )
    assert me_response.status_code == 200, me_response.text
    assert "items" in me_response.json()

    list_admin = await frontend_client.get(
        "/frontend/api/mail/bindings",
        headers=auth_headers_system,
    )
    assert list_admin.status_code == 200
