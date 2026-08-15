"""Personal mailbox: unified connection scope + sync candidates."""

from __future__ import annotations

import pytest

from core.mail.exceptions import MailPermissionError
from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    MailboxBindingCreatePayload,
    MailboxBindingHealthcheckPayload,
    MailboxBindingKind,
    MailboxBindingPatchPayload,
    MailConnectionScope,
    MailProvider,
    MailSendPayload,
    PersonalMailboxConnectPayload,
)
from core.mail.service import MailService
from tests.core.mail.conftest import seed_mail_company_member
from tests.core.mail.fakes import RecordingMailServerPort


@pytest.mark.asyncio
async def test_connect_personal_without_company_connection(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    container,
    unique_id: str,
) -> None:
    company_id = f"mailpers_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await seed_mail_company_member(
        container,
        company_id=company_id,
        user_id=user_id,
        unique_id=unique_id,
    )
    assert await mail_service.get_connection(company_id=company_id) is None

    binding = await mail_service.connect_personal_mailbox(
        PersonalMailboxConnectPayload(
            email_address=f"me.{unique_id}@gmail.com",
            password="app-password-1",
            imap_host="imap.gmail.com",
            imap_port=993,
            smtp_host="smtp.gmail.com",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company_id,
    )
    assert binding.email_address == f"me.{unique_id}@gmail.com"
    assert binding.user_id == user_id
    assert binding.is_default is True
    assert binding.kind == MailboxBindingKind.USER

    connection = await mail_service._connection_for_binding(binding)
    assert connection is not None
    assert connection.scope == MailConnectionScope.PERSONAL
    assert connection.owner_user_id == user_id
    assert connection.imap_host == "imap.gmail.com"
    assert await mail_service.get_connection(company_id=company_id) is None

    candidates = await mail_service.list_sync_candidates(
        limit=10_000,
        auth_error_cooldown_seconds=0,
    )
    assert any(item.mailbox_binding_id == binding.mailbox_binding_id for item in candidates)

    sync_result = await mail_service.sync_binding(binding, max_new_messages=10)
    assert sync_result.skipped_reason is None
    assert len(recording_mail_port.fetch_uids_since_calls) >= 1

    public = await mail_service.public_binding(binding)
    assert public.connection_scope == MailConnectionScope.PERSONAL
    assert public.imap_host == "imap.gmail.com"

    folders = await mail_service.list_folders(
        binding.mailbox_binding_id,
        company_id=company_id,
    )
    assert folders.needs_sync is False
    assert any(folder.name == "INBOX" for folder in folders.folders)


@pytest.mark.asyncio
async def test_company_and_personal_share_sync_candidates(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    container,
    unique_id: str,
) -> None:
    _ = recording_mail_port
    company_id = f"mailboth_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await seed_mail_company_member(
        container,
        company_id=company_id,
        user_id=user_id,
        unique_id=unique_id,
    )
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.example.com",
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host="imap.company.example",
            imap_port=993,
            smtp_host="smtp.company.example",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company_id,
    )
    company_binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_id,
            local_part=f"work.{unique_id}",
            password="company-pass",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    personal_binding = await mail_service.connect_personal_mailbox(
        PersonalMailboxConnectPayload(
            email_address=f"home.{unique_id}@yandex.ru",
            password="yandex-pass",
            imap_host="imap.yandex.com",
            imap_port=993,
            smtp_host="smtp.yandex.com",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company_id,
    )
    candidates = await mail_service.list_sync_candidates(
        limit=10_000,
        auth_error_cooldown_seconds=0,
    )
    ids = {item.mailbox_binding_id for item in candidates}
    assert company_binding.mailbox_binding_id in ids
    assert personal_binding.mailbox_binding_id in ids


@pytest.mark.asyncio
async def test_personal_unbind_by_owner_deletes_connection(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    container,
    unique_id: str,
) -> None:
    _ = recording_mail_port
    company_id = f"mailunbind_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await seed_mail_company_member(
        container,
        company_id=company_id,
        user_id=user_id,
        unique_id=unique_id,
    )
    binding = await mail_service.connect_personal_mailbox(
        PersonalMailboxConnectPayload(
            email_address=f"solo.{unique_id}@gmail.com",
            password="pass",
            imap_host="imap.gmail.com",
            imap_port=993,
            smtp_host="smtp.gmail.com",
            smtp_port=465,
        ),
        company_id=company_id,
    )
    connection_id = binding.company_mail_connection_id
    await mail_service.unbind_mailbox(
        binding.mailbox_binding_id,
        company_id=company_id,
    )
    assert await mail_service._connection_repository.get(connection_id) is None
    assert (
        await mail_service._binding_repository.get(binding.mailbox_binding_id, company_id)
        is None
    )


@pytest.mark.asyncio
async def test_non_owner_cannot_unbind_personal(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    container,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = recording_mail_port
    company_id = f"mailacl_{unique_id}"
    owner_id = f"owner_{unique_id}"
    other_id = f"other_{unique_id}"
    _ = await seed_mail_company_member(
        container,
        company_id=company_id,
        user_id=owner_id,
        unique_id=unique_id,
    )
    binding = await mail_service.connect_personal_mailbox(
        PersonalMailboxConnectPayload(
            email_address=f"priv.{unique_id}@gmail.com",
            password="pass",
            imap_host="imap.gmail.com",
            imap_port=993,
            smtp_host="smtp.gmail.com",
            smtp_port=465,
        ),
        company_id=company_id,
    )
    monkeypatch.setattr(mail_service, "_active_user_id", lambda: other_id)
    async def _deny_admin(_company_id: str) -> bool:
        return False

    monkeypatch.setattr(mail_service, "_is_company_admin", _deny_admin)
    with pytest.raises(MailPermissionError):
        await mail_service.unbind_mailbox(
            binding.mailbox_binding_id,
            company_id=company_id,
        )


@pytest.mark.asyncio
async def test_personal_allocate_message_id_without_company_connection(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    container,
    unique_id: str,
) -> None:
    _ = recording_mail_port
    company_id = f"mailmsgid_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await seed_mail_company_member(
        container,
        company_id=company_id,
        user_id=user_id,
        unique_id=unique_id,
    )
    assert await mail_service.get_connection(company_id=company_id) is None
    binding = await mail_service.connect_personal_mailbox(
        PersonalMailboxConnectPayload(
            email_address=f"send.{unique_id}@mail.ru",
            password="pass",
            imap_host="imap.mail.ru",
            imap_port=993,
            smtp_host="smtp.mail.ru",
            smtp_port=465,
        ),
        company_id=company_id,
    )
    message_id = await mail_service.allocate_outbound_message_id(
        binding.mailbox_binding_id,
        company_id=company_id,
    )
    assert message_id.startswith("<")
    assert message_id.endswith("@mail.ru>")
    assert await mail_service.get_connection(company_id=company_id) is None

    prepared = await mail_service.prepare_send_local(
        MailSendPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            to_addresses=["peer@example.com"],
            subject="personal outbound",
            body_text="hello personal",
        ),
        company_id=company_id,
    )
    assert prepared.message_id.endswith("@mail.ru>")


@pytest.mark.asyncio
async def test_personal_healthcheck_binding_uses_stored_password(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    container,
    unique_id: str,
) -> None:
    company_id = f"mailhc_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await seed_mail_company_member(
        container,
        company_id=company_id,
        user_id=user_id,
        unique_id=unique_id,
    )
    binding = await mail_service.connect_personal_mailbox(
        PersonalMailboxConnectPayload(
            email_address=f"hc.{unique_id}@mail.ru",
            password="stored-pass",
            imap_host="imap.mail.ru",
            imap_port=993,
            smtp_host="smtp.mail.ru",
            smtp_port=465,
        ),
        company_id=company_id,
    )
    health = await mail_service.healthcheck_binding(
        binding.mailbox_binding_id,
        MailboxBindingHealthcheckPayload(),
        company_id=company_id,
    )
    assert health.imap_ok is True
    assert health.smtp_ok is True
    assert recording_mail_port.healthcheck_with_credentials_calls
    last_secret = recording_mail_port.healthcheck_with_credentials_calls[-1]
    assert last_secret.email_address == f"hc.{unique_id}@mail.ru"
    assert last_secret.password == "stored-pass"

    patched = await mail_service.patch_binding(
        binding.mailbox_binding_id,
        MailboxBindingPatchPayload(
            imap_host="imap2.mail.ru",
            smtp_host="smtp2.mail.ru",
        ),
        company_id=company_id,
    )
    connection = await mail_service._connection_for_binding(patched)
    assert connection is not None
    assert connection.imap_host == "imap2.mail.ru"
    assert connection.smtp_host == "smtp2.mail.ru"


@pytest.mark.asyncio
async def test_personal_healthcheck_binding_forbidden_for_non_owner(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    container,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = recording_mail_port
    company_id = f"mailhcacl_{unique_id}"
    owner_id = f"owner_{unique_id}"
    other_id = f"other_{unique_id}"
    _ = await seed_mail_company_member(
        container,
        company_id=company_id,
        user_id=owner_id,
        unique_id=unique_id,
    )
    binding = await mail_service.connect_personal_mailbox(
        PersonalMailboxConnectPayload(
            email_address=f"acl.{unique_id}@mail.ru",
            password="pass",
            imap_host="imap.mail.ru",
            imap_port=993,
            smtp_host="smtp.mail.ru",
            smtp_port=465,
        ),
        company_id=company_id,
    )
    monkeypatch.setattr(mail_service, "_active_user_id", lambda: other_id)
    async def _deny_admin(_company_id: str) -> bool:
        return False

    monkeypatch.setattr(mail_service, "_is_company_admin", _deny_admin)
    with pytest.raises(MailPermissionError):
        await mail_service.healthcheck_binding(
            binding.mailbox_binding_id,
            MailboxBindingHealthcheckPayload(),
            company_id=company_id,
        )
