"""Multi-mailbox per user: list_by_user, is_default, API /bindings/me."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.ai.company_settings import encrypt_secret
from core.mail.models import (
    CompanyMailConnection,
    IspmanagerProvisionConfig,
    MailboxBinding,
    MailboxBindingKind,
    MailConnectionStatus,
    MailProvider,
)


@pytest.mark.asyncio
async def test_list_by_user_and_default(unique_id: str) -> None:
    company_id = f"mail_multi_{unique_id}"
    user_id = f"user_{unique_id}"
    now = datetime.now(timezone.utc)
    _ = await CompanyMailConnection.upsert_by_company_mail_connection_id(
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
    first = await MailboxBinding.upsert_by_company_and_email(
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
    second = await MailboxBinding.upsert_by_company_and_email(
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
    listed = await MailboxBinding.list_user_kind_by_default_desc_and_email_asc(company_id, user_id)
    assert len(listed) == 2
    assert listed[0].mailbox_binding_id == first.mailbox_binding_id
    by_user = await MailboxBinding.find_default_or_first_by_email_for_user(company_id, user_id)
    assert by_user is not None
    assert by_user.mailbox_binding_id == first.mailbox_binding_id

    await MailboxBinding.clear_defaults_for_user(company_id, user_id)
    promoted = second.model_copy(update={"is_default": True})
    _ = await MailboxBinding.upsert_by_company_and_email(promoted)
    by_user2 = await MailboxBinding.find_default_or_first_by_email_for_user(company_id, user_id)
    assert by_user2 is not None
    assert by_user2.mailbox_binding_id == second.mailbox_binding_id
    assert await MailboxBinding.find_default_or_first_by_email_for_user(company_id, f"missing_{unique_id}") is None
    with pytest.raises(ValueError, match="user_id cannot be empty"):
        _ = await MailboxBinding.find_default_or_first_by_email_for_user(company_id, "")


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
    now = datetime.now(timezone.utc)
    existing = await CompanyMailConnection.for_company("system")
    connection_id = (
        existing.company_mail_connection_id
        if existing is not None
        else f"mailconn_api_me_{unique_id}"
    )
    _ = await CompanyMailConnection.upsert_by_company_mail_connection_id(
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
