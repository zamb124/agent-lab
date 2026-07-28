"""
Live CalDAV Mail.ru: реальный ящик из mail.live_test.personal.

Пароль почты берётся из mail.local_dev.mailbox_passwords, пароль календаря —
из mail.live_test.personal.calendar_app_password_a: Mail.ru выдаёт пароль
внешнего приложения отдельно для календаря, почтовый пароль CalDAV отклоняет.

Запуск: uv run pytest -q tests/core/calendar/live -m network
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.calendar.caldav_discovery import CaldavAutolinkKind, resolve_caldav_target
from core.calendar.service import CalDavClient
from core.config import get_settings
from core.config.models import MailConfig, MailLivePersonalConfig
from core.context import set_context
from core.mail.models import MailboxSecret, PersonalMailboxConnectPayload
from core.mail.repositories import (
    CompanyMailConnectionRepository,
    MailboxBindingMemberRepository,
    MailboxBindingRepository,
    MailboxFolderRepository,
    MailboxSyncCursorRepository,
    MailMessageRepository,
)
from core.mail.service import MailService
from core.models import (
    CalendarAutolinkStatus,
    CalendarEventSource,
    CalendarIntegrationConnectPayload,
    CalendarProvider,
)
from core.models.context_models import Context
from core.models.identity_models import Company, User

pytestmark = pytest.mark.network


@pytest.fixture()
def mail_personal_service_with_calendar(
    mail_personal_live_settings: MailConfig,
    container,
) -> MailService:
    shared_url = get_settings().database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен для live calendar tests")
    return MailService(
        connection_repository=CompanyMailConnectionRepository(db_url=shared_url),
        binding_repository=MailboxBindingRepository(db_url=shared_url),
        sync_cursor_repository=MailboxSyncCursorRepository(db_url=shared_url),
        folder_repository=MailboxFolderRepository(db_url=shared_url),
        message_repository=MailMessageRepository(db_url=shared_url),
        member_repository=MailboxBindingMemberRepository(db_url=shared_url),
        namespace_service=container.namespace_service,
        company_repository=container.company_repository,
        user_repository=container.user_repository,
        mail_config=mail_personal_live_settings,
        port_override=None,
        calendar_bridge=container.calendar_service,
    )


def _calendar_app_password(cfg: MailLivePersonalConfig) -> str:
    password = cfg.calendar_app_password_a.strip()
    if not password:
        pytest.skip(
            "mail.live_test.personal.calendar_app_password_a не задан: "
            "создайте в Mail.ru пароль внешнего приложения для календаря"
        )
    return password


@pytest.mark.asyncio
async def test_mailru_caldav_endpoint_resolves_from_mail_domain(
    mail_personal_cfg: MailLivePersonalConfig,
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
) -> None:
    """Домен ящика Mail.ru резолвится в CalDAV-эндпоинт провайдера."""
    secret_a, _ = mail_personal_pair
    resolution = await resolve_caldav_target(
        mail_domain=secret_a.email_address.split("@", 1)[1],
        imap_host=mail_personal_cfg.imap_host,
    )
    assert resolution.kind == CaldavAutolinkKind.CALDAV
    provider, base_url = resolution.require_target()
    assert provider == CalendarProvider.MAILRU
    assert base_url == "https://calendar.mail.ru"


@pytest.mark.asyncio
async def test_mail_only_password_yields_needs_password_status(
    mail_personal_service_with_calendar: MailService,
    mail_personal_cfg: MailLivePersonalConfig,
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_personal_company_ctx: tuple[str, str, Company, User],
    container,
) -> None:
    """
    Почтовый пароль Mail.ru CalDAV отклоняет: ящик подключается, календарь
    помечается needs_password, интеграция не создаётся.
    """
    if mail_personal_cfg.calendar_app_password_a.strip():
        pytest.skip("calendar_app_password_a задан: почтовый пароль не проверяем")
    company_id, user_id, company, user = mail_personal_company_ctx
    secret_a, _ = mail_personal_pair
    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )

    binding = await mail_personal_service_with_calendar.connect_personal_mailbox(
        PersonalMailboxConnectPayload(
            email_address=secret_a.email_address,
            password=secret_a.password,
            imap_host=mail_personal_cfg.imap_host,
            imap_port=mail_personal_cfg.imap_port,
            smtp_host=mail_personal_cfg.smtp_host,
            smtp_port=mail_personal_cfg.smtp_port,
            use_ssl=mail_personal_cfg.use_ssl,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    try:
        assert binding.calendar_autolink_status == CalendarAutolinkStatus.NEEDS_PASSWORD
        assert binding.calendar_autolink_detail is not None
        assert "app password" in binding.calendar_autolink_detail

        integrations = await container.calendar_service.list_integrations(
            user_id=user_id,
            company_id=company_id,
        )
        assert integrations == []
    finally:
        await mail_personal_service_with_calendar.unbind_mailbox(
            binding.mailbox_binding_id,
            company_id=company_id,
        )


@pytest.mark.asyncio
async def test_caldav_discovery_reads_real_calendar_events(
    mail_personal_cfg: MailLivePersonalConfig,
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
) -> None:
    """RFC 6764/4791 discovery + чтение реальных событий календаря Mail.ru."""
    secret_a, _ = mail_personal_pair
    calendar_password = _calendar_app_password(mail_personal_cfg)

    client = CalDavClient("https://calendar.mail.ru")
    calendar_id = await client.discover_default_calendar_id(
        username=secret_a.email_address,
        app_password=calendar_password,
    )
    assert calendar_id.strip()

    now = datetime.now(timezone.utc)
    events = await client.list_events(
        username=secret_a.email_address,
        app_password=calendar_password,
        calendar_id=calendar_id,
        start_at=now - timedelta(days=365),
        end_at=now + timedelta(days=365),
    )
    assert len(events) > 0, (
        f"В календаре {secret_a.email_address} нет событий в окне +-1 год: "
        "добавьте событие или поправьте mail.live_test.personal.account_a"
    )
    first = events[0]
    assert first.start_at < first.end_at
    assert first.summary.strip()


@pytest.mark.asyncio
async def test_manual_calendar_password_links_mailbox_and_imports_events(
    mail_personal_service_with_calendar: MailService,
    mail_personal_cfg: MailLivePersonalConfig,
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_personal_company_ctx: tuple[str, str, Company, User],
    container,
) -> None:
    """
    Путь из настроек: пользователь вводит календарный пароль для своего ящика,
    интеграция привязывается к mailbox_binding_id и импортирует события.
    """
    company_id, user_id, company, user = mail_personal_company_ctx
    secret_a, _ = mail_personal_pair
    calendar_password = _calendar_app_password(mail_personal_cfg)
    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )

    binding = await mail_personal_service_with_calendar.connect_personal_mailbox(
        PersonalMailboxConnectPayload(
            email_address=secret_a.email_address,
            password=secret_a.password,
            imap_host=mail_personal_cfg.imap_host,
            imap_port=mail_personal_cfg.imap_port,
            smtp_host=mail_personal_cfg.smtp_host,
            smtp_port=mail_personal_cfg.smtp_port,
            use_ssl=mail_personal_cfg.use_ssl,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    try:
        integration = await container.calendar_service.connect_integration(
            user_id=user_id,
            company_id=company_id,
            payload=CalendarIntegrationConnectPayload(
                provider=CalendarProvider.MAILRU,
                mailbox_binding_id=binding.mailbox_binding_id,
                username=secret_a.email_address,
                access_token=calendar_password,
                sync_outbound_enabled=False,
            ),
        )
        assert integration.mailbox_binding_id == binding.mailbox_binding_id
        assert integration.settings.caldav_base_url == "https://calendar.mail.ru"
        assert integration.settings.default_calendar_id

        now = datetime.now(timezone.utc)
        result = await container.calendar_service.run_sync(
            user_id=user_id,
            company_id=company_id,
            start_at=now - timedelta(days=365),
            end_at=now + timedelta(days=365),
            integration_id=integration.integration_id,
        )
        assert result["imported"] > 0

        events = await container.calendar_service.list_events(
            company_id=company_id,
            user_id=user_id,
            start_at=now - timedelta(days=365),
            end_at=now + timedelta(days=365),
            include_sources={CalendarEventSource.MAILRU},
            limit=1000,
        )
        assert len(events) > 0
        assert all(item.mailbox_binding_id == binding.mailbox_binding_id for item in events)
    finally:
        await mail_personal_service_with_calendar.unbind_mailbox(
            binding.mailbox_binding_id,
            company_id=company_id,
        )

    remaining = await container.calendar_service.list_integrations(
        user_id=user_id,
        company_id=company_id,
    )
    assert remaining == []
