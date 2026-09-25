"""CRUD репозиториев почты на реальной shared БД."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.mail.models import (
    CompanyMailConnection,
    IspmanagerProvisionConfig,
    MailboxBinding,
    MailboxBindingKind,
    MailboxSyncCursor,
    MailConnectionStatus,
    MailProvider,
    StoredMailMessage,
)


@pytest.mark.asyncio
async def test_company_mail_connection_upsert_and_get(
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
    stored = await CompanyMailConnection.upsert_by_company_mail_connection_id(connection)
    assert stored.company_id == company_id
    assert stored.mail_domain == f"{unique_id}.example.com"
    assert stored.ispmanager is not None
    assert stored.ispmanager.authinfo_user == "admin"

    loaded = await CompanyMailConnection.for_company(company_id)
    assert loaded is not None
    assert loaded.company_mail_connection_id == f"mailconn_{unique_id}"
    assert loaded.provider == MailProvider.ISPMANAGER
    assert await CompanyMailConnection.for_company(f"missing_{unique_id}") is None

    replaced = await CompanyMailConnection.upsert_by_company_mail_connection_id(
        connection.model_copy(
            update={
                "company_mail_connection_id": f"other_{unique_id}",
                "imap_host": "imap2.example.com",
            }
        )
    )
    assert replaced.company_mail_connection_id == f"mailconn_{unique_id}"
    assert replaced.created_at == stored.created_at
    assert replaced.imap_host == "imap2.example.com"
    assert await CompanyMailConnection.get(f"other_{unique_id}") is None


@pytest.mark.asyncio
async def test_by_email_returns_own_row_and_hides_other_company(unique_id: str) -> None:
    company_id = f"mailco_{unique_id}"
    other_company_id = f"mailco_other_{unique_id}"
    now = datetime.now(timezone.utc)
    email_address = f"user.{unique_id}@{unique_id}.example.com"
    _ = await CompanyMailConnection.upsert_by_company_mail_connection_id(
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
    _ = await MailboxBinding.upsert_by_email(
        MailboxBinding(
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
    )

    found = await MailboxBinding.by_email(company_id, email_address)
    assert found is not None
    assert found.mailbox_binding_id == f"mailbind_{unique_id}"
    assert await MailboxBinding.by_email(other_company_id, email_address) is None
    assert await MailboxBinding.by_email(company_id, f"missing.{unique_id}@example.com") is None
    with pytest.raises(ValueError, match="email_address cannot be empty"):
        _ = await MailboxBinding.by_email(company_id, "")
    with pytest.raises(ValueError, match="company_id cannot be empty"):
        _ = await MailboxBinding.by_email("", email_address)

    binding_id = f"mailbind_{unique_id}"
    stored_cursor = await MailboxSyncCursor.upsert_by_binding_folder(
        MailboxSyncCursor(
            mailbox_binding_id=binding_id,
            folder="INBOX",
            company_id=company_id,
            uidvalidity=1,
            last_uid=0,
        )
    )
    stored_cursor.last_uid = 4
    updated_cursor = await MailboxSyncCursor.upsert_by_binding_folder(stored_cursor)
    assert updated_cursor.mailbox_sync_cursor_id == stored_cursor.mailbox_sync_cursor_id
    assert updated_cursor.last_uid == 4
    found_cursor = await MailboxSyncCursor.by_binding_folder(binding_id)
    assert found_cursor is not None
    assert found_cursor.mailbox_sync_cursor_id == stored_cursor.mailbox_sync_cursor_id
    assert found_cursor.last_uid == 4
    assert await MailboxSyncCursor.by_binding_folder(binding_id, folder="Sent") is None

    stored_message = await StoredMailMessage.upsert_by_binding_folder_uid(
        StoredMailMessage(
            mail_message_id=f"mm_{unique_id}",
            company_id=company_id,
            mailbox_binding_id=binding_id,
            folder="INBOX",
            uid=7,
            thread_id=f"th_{unique_id}",
            synced_at=now,
            created_at=now,
        )
    )
    found_message = await StoredMailMessage.by_binding_folder_uid(
        binding_id, folder="INBOX", uid=7
    )
    assert found_message is not None
    assert found_message.mail_message_id == stored_message.mail_message_id
    updated_message = await StoredMailMessage.upsert_by_binding_folder_uid(
        stored_message.model_copy(update={"subject": "Updated", "mail_message_id": f"other_{unique_id}"})
    )
    assert updated_message.mail_message_id == stored_message.mail_message_id
    assert updated_message.subject == "Updated"
    assert updated_message.created_at == stored_message.created_at
    assert await StoredMailMessage.by_binding_folder_uid(
        binding_id, folder="INBOX", uid=8
    ) is None

    missing_binding_id = f"missing_bind_{unique_id}"
    assert await MailboxSyncCursor.by_binding_folder(missing_binding_id) is None
    with pytest.raises(ValueError, match="mailbox_binding_id cannot be empty"):
        _ = await MailboxSyncCursor.by_binding_folder("")
    with pytest.raises(ValueError, match="folder cannot be empty"):
        _ = await MailboxSyncCursor.by_binding_folder(missing_binding_id, folder="")

    assert await StoredMailMessage.by_binding_folder_uid(
        missing_binding_id, folder="INBOX", uid=1
    ) is None
    with pytest.raises(ValueError, match="folder cannot be empty"):
        _ = await StoredMailMessage.by_binding_folder_uid(
            missing_binding_id, folder="", uid=1
        )
    with pytest.raises(ValueError, match="company_id cannot be empty"):
        _ = await CompanyMailConnection.for_company("")


@pytest.mark.asyncio
async def test_mailbox_binding_upsert_list_delete(
    unique_id: str,
) -> None:
    company_id = f"mailco_{unique_id}"
    now = datetime.now(timezone.utc)
    _ = await CompanyMailConnection.upsert_by_company_mail_connection_id(
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
    stored = await MailboxBinding.upsert_by_email(binding)
    assert stored.email_address == email_address

    listed = await MailboxBinding.list_by_company(company_id)
    assert len(listed) == 1
    assert listed[0].mailbox_binding_id == f"mailbind_{unique_id}"

    by_user = await MailboxBinding.preferred_for_user(company_id, f"user_{unique_id}")
    assert by_user is not None
    assert by_user.email_address == email_address

    deleted = await MailboxBinding.delete_in_company(company_id, f"mailbind_{unique_id}")
    assert deleted is True
    assert await MailboxBinding.find_in_company(company_id, f"mailbind_{unique_id}") is None


@pytest.mark.asyncio
async def test_upsert_by_email_updates_fields_and_can_replace_id(unique_id: str) -> None:
    company_id = f"mailup_{unique_id}"
    now = datetime.now(timezone.utc)
    email_address = f"up.{unique_id}@example.com"
    created = await MailboxBinding.upsert_by_email(
        MailboxBinding(
            mailbox_binding_id=f"old_{unique_id}",
            company_id=company_id,
            company_mail_connection_id=f"conn_{unique_id}",
            user_id=f"user_{unique_id}",
            kind=MailboxBindingKind.USER,
            email_address=email_address,
            local_part=f"up.{unique_id}",
            sync_enabled=True,
            password_encrypted="enc-pass",
            created_at=now,
            updated_at=now,
        )
    )
    updated = await MailboxBinding.upsert_by_email(
        created.model_copy(update={"sync_enabled": False, "password_encrypted": "enc-next"})
    )
    assert updated.mailbox_binding_id == created.mailbox_binding_id
    assert updated.created_at == created.created_at
    assert updated.sync_enabled is False
    replaced = await MailboxBinding.upsert_by_email(
        updated.model_copy(update={"mailbox_binding_id": f"new_{unique_id}"})
    )
    assert replaced.mailbox_binding_id == f"new_{unique_id}"
    assert replaced.created_at == created.created_at
    assert await MailboxBinding.by_email(company_id, email_address) is not None
    assert await MailboxBinding.find_in_company(company_id, f"old_{unique_id}") is None
