"""Авто-привязка календаря к ящику: статус на binding и снятие интеграции при unbind."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.config import get_settings
from core.config.models import MailConfig
from core.integrations.models import IntegrationCredential, IntegrationProvider
from core.mail.models import (
    MailboxBinding,
    MailboxBindingKind,
    PersonalMailboxConnectPayload,
)
from core.mail.service import MailService
from core.models import CalendarAutolinkStatus
from tests.core.mail.conftest import seed_mail_company_member
from tests.core.mail.fakes import RecordingMailServerPort


@pytest.fixture()
def mail_service_with_calendar(
    recording_mail_port: RecordingMailServerPort,
    di,
) -> MailService:
    """MailService с настоящим CalendarService как мостом mail -> calendar."""
    return MailService(
        authz=di.authz_service,
        namespace_service=di.namespace_service,
        mail_config=MailConfig(),
        port_override=recording_mail_port,
        calendar_bridge=di.calendar_service,
    )


async def _calendar_credentials(company_id: str, user_id: str) -> list[IntegrationCredential]:
    credentials = await IntegrationCredential.list_by_user(company_id, user_id)
    return [item for item in credentials if item.service == "calendar"]


@pytest.mark.asyncio
async def test_autolink_marks_unsupported_domain_without_creating_integration(
    mail_service_with_calendar: MailService,
    di,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Домен без CalDAV: почта подключена, календарь помечен unsupported."""
    monkeypatch.setattr(
        get_settings().calendar_sync, "autolink_well_known_probe_enabled", False
    )
    company_id = f"mailcalu_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await seed_mail_company_member(
        di,
        company_id=company_id,
        user_id=user_id,
        unique_id=unique_id,
    )

    binding = await mail_service_with_calendar.connect_personal_mailbox(
        PersonalMailboxConnectPayload(
            email_address=f"me.{unique_id}@corp.example",
            password="app-password-1",
            imap_host="imap.corp.example",
            imap_port=993,
            smtp_host="smtp.corp.example",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company_id,
    )

    assert binding.kind == MailboxBindingKind.USER
    assert binding.calendar_autolink_status == CalendarAutolinkStatus.UNSUPPORTED
    assert binding.calendar_autolink_detail is not None
    assert "corp.example" in binding.calendar_autolink_detail
    assert await _calendar_credentials(company_id, user_id) == []

    public = await mail_service_with_calendar.public_binding(binding)
    assert public.calendar_autolink_status == CalendarAutolinkStatus.UNSUPPORTED


@pytest.mark.asyncio
async def test_autolink_marks_gmail_as_oauth_only(
    mail_service_with_calendar: MailService,
    di,
    unique_id: str,
) -> None:
    """Gmail: парольного CalDAV нет, статус needs_oauth без сетевых проб."""
    company_id = f"mailcalg_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await seed_mail_company_member(
        di,
        company_id=company_id,
        user_id=user_id,
        unique_id=unique_id,
    )

    binding = await mail_service_with_calendar.connect_personal_mailbox(
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

    assert binding.calendar_autolink_status == CalendarAutolinkStatus.NEEDS_OAUTH
    assert await _calendar_credentials(company_id, user_id) == []


@pytest.mark.asyncio
async def test_unbind_removes_mailbox_calendar_integration(
    mail_service_with_calendar: MailService,
    di,
    unique_id: str,
) -> None:
    """Отвязка ящика снимает его календарную интеграцию, не оставляя висячих credentials."""
    company_id = f"mailcald_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await seed_mail_company_member(
        di,
        company_id=company_id,
        user_id=user_id,
        unique_id=unique_id,
    )
    binding = await mail_service_with_calendar.connect_personal_mailbox(
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

    now = datetime.now(timezone.utc)
    await IntegrationCredential.upsert_by_credential_id(
        IntegrationCredential(
            credential_id=f"cred_{unique_id}",
            company_id=company_id,
            user_id=user_id,
            provider=IntegrationProvider.MAILRU,
            service="calendar",
            mailbox_binding_id=binding.mailbox_binding_id,
            access_token="app-password-1",
            metadata={
                "username": binding.email_address,
                "calendar_settings": {"default_calendar_id": "default"},
            },
            created_at=now,
            updated_at=now,
        )
    )
    assert len(await _calendar_credentials(company_id, user_id)) == 1

    await mail_service_with_calendar.unbind_mailbox(
        binding.mailbox_binding_id,
        company_id=company_id,
    )

    assert await _calendar_credentials(company_id, user_id) == []


@pytest.mark.asyncio
async def test_unlink_mailbox_calendar_keeps_mailbox_and_resets_status(
    mail_service_with_calendar: MailService,
    di,
    unique_id: str,
) -> None:
    """Отключение календаря из настроек: ящик остаётся, статус становится disabled."""
    company_id = f"mailcalx_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await seed_mail_company_member(
        di,
        company_id=company_id,
        user_id=user_id,
        unique_id=unique_id,
    )
    binding = await mail_service_with_calendar.connect_personal_mailbox(
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
    assert binding.calendar_autolink_status == CalendarAutolinkStatus.NEEDS_OAUTH

    now = datetime.now(timezone.utc)
    await IntegrationCredential.upsert_by_credential_id(
        IntegrationCredential(
            credential_id=f"cred_{unique_id}",
            company_id=company_id,
            user_id=user_id,
            provider=IntegrationProvider.CALDAV,
            service="calendar",
            mailbox_binding_id=binding.mailbox_binding_id,
            access_token="app-password-1",
            metadata={
                "username": binding.email_address,
                "calendar_settings": {
                    "default_calendar_id": "default",
                    "caldav_base_url": "https://dav.example.com",
                },
            },
            created_at=now,
            updated_at=now,
        )
    )

    updated = await mail_service_with_calendar.unlink_mailbox_calendar(
        binding.mailbox_binding_id,
        company_id=company_id,
    )

    assert updated.calendar_autolink_status == CalendarAutolinkStatus.DISABLED
    assert updated.calendar_autolink_detail == "disconnected by user"
    assert await _calendar_credentials(company_id, user_id) == []
    stored = await MailboxBinding.find_in_company(company_id, binding.mailbox_binding_id)
    assert stored is not None
    assert stored.calendar_autolink_status == CalendarAutolinkStatus.DISABLED
