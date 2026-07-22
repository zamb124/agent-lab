"""Live-фикстуры: реальный ISPmanager + IMAP/SMTP из conf.local + quota sweeper."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator, Iterator
from contextlib import suppress
from datetime import datetime, timezone

import pytest

from core.ai.company_settings import encrypt_secret
from core.config import get_settings
from core.config.models import MailConfig
from core.mail.exceptions import MailDeleteDeniedError, MailError
from core.mail.factory import build_mail_server_port
from core.mail.models import (
    CompanyMailConnection,
    IspmanagerProvisionConfig,
    MailboxEnsureSpec,
    MailboxInfo,
    MailboxSecret,
    MailConnectionScope,
    MailConnectionStatus,
    MailProvider,
)
from core.mail.ports import MailServerPort
from core.mail.repositories import (
    CompanyMailConnectionRepository,
    MailboxBindingMemberRepository,
    MailboxBindingRepository,
    MailboxFolderRepository,
    MailboxSyncCursorRepository,
    MailMessageRepository,
)
from core.mail.service import MailService

pytest_plugins = ["tests.core.mail.live.personal_conftest"]

_LIVE_PLACEHOLDERS = frozenset({"", "null", "changeme", "YOUR_PASSWORD", "placeholder"})


def _is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    stripped = value.strip()
    if not stripped:
        return True
    if stripped in _LIVE_PLACEHOLDERS:
        return True
    return stripped.startswith("YOUR_")


@pytest.fixture()
def mail_live_settings() -> MailConfig:
    settings = get_settings()
    mail = settings.mail
    if not mail.live_test.enabled:
        pytest.skip("mail.live_test.enabled=false")
    system = mail.system
    if _is_placeholder(system.imap_host) or _is_placeholder(system.smtp_host):
        pytest.skip("mail.system imap/smtp host not configured")
    if system.provider != "ispmanager":
        pytest.skip("live suite requires mail.system.provider=ispmanager")
    isp = system.ispmanager
    if _is_placeholder(isp.base_url) or _is_placeholder(isp.authinfo_user):
        pytest.skip("mail.system.ispmanager credentials missing")
    if _is_placeholder(isp.authinfo_password):
        pytest.skip("mail.system.ispmanager.authinfo_password missing in conf.local")
    return mail


@pytest.fixture()
def mail_live_port(mail_live_settings: MailConfig) -> MailServerPort:
    system = mail_live_settings.system
    isp = system.ispmanager
    if system.imap_host is None or system.smtp_host is None:
        raise RuntimeError("mail.system imap/smtp host required")
    if isp.base_url is None or isp.authinfo_user is None or isp.authinfo_password is None:
        raise RuntimeError("mail.system.ispmanager incomplete")
    now = datetime.now(timezone.utc)
    connection = CompanyMailConnection(
        company_mail_connection_id="live-test-connection",
        company_id="system",
        scope=MailConnectionScope.COMPANY,
        owner_user_id=None,
        mail_domain=system.mail_domain,
        provider=MailProvider.ISPMANAGER,
        imap_host=system.imap_host,
        imap_port=system.imap_port,
        smtp_host=system.smtp_host,
        smtp_port=system.smtp_port,
        use_ssl=system.use_ssl,
        supports_provision=True,
        status=MailConnectionStatus.ACTIVE,
        ispmanager=IspmanagerProvisionConfig(
            base_url=isp.base_url,
            authinfo_user=isp.authinfo_user,
            authinfo_password_encrypted=encrypt_secret(isp.authinfo_password),
        ),
        created_at=now,
        updated_at=now,
    )
    return build_mail_server_port(
        connection,
        protected_local_parts=frozenset(
            part.strip().lower() for part in system.protected_local_parts if part.strip()
        ),
        delete_prefix_required=mail_live_settings.live_test.mailbox_prefix,
        allow_delete=mail_live_settings.live_test.allow_delete,
    )


@pytest.fixture()
def mail_live_service(
    mail_live_settings: MailConfig,
    container,
) -> MailService:
    settings = get_settings()
    shared_url = settings.database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен для mail live service tests")
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
        mail_config=mail_live_settings,
        port_override=None,
    )


@pytest.fixture()
def mail_created_addresses() -> Iterator[list[str]]:
    """Реестр ящиков suite для квоты: finalizer удаляет всё созданное."""
    created: list[str] = []
    yield created


@pytest.fixture()
async def mail_quota_sweeper(
    mail_live_port: MailServerPort,
    mail_created_addresses: list[str],
) -> AsyncIterator[list[str]]:
    try:
        yield mail_created_addresses
    finally:
        remaining = list(dict.fromkeys(mail_created_addresses))
        for email_address in remaining:
            with suppress(MailError, MailDeleteDeniedError, ValueError):
                await mail_live_port.delete_mailbox(email_address)
        mail_created_addresses.clear()


@pytest.fixture()
async def mail_live_mailbox(
    mail_live_port: MailServerPort,
    mail_live_settings: MailConfig,
    mail_quota_sweeper: list[str],
    unique_id: str,
) -> AsyncIterator[tuple[MailboxInfo, MailboxSecret, list[str]]]:
    prefix = mail_live_settings.live_test.mailbox_prefix
    local_part = f"{prefix}{unique_id}".lower().replace("_", "-")[:64]
    password = secrets.token_urlsafe(20)
    spec = MailboxEnsureSpec(
        mail_domain=mail_live_settings.system.mail_domain,
        local_part=local_part,
        password=password,
    )
    info = await mail_live_port.ensure_mailbox(spec)
    secret = MailboxSecret(email_address=info.email_address, password=password)
    created: list[str] = [info.email_address]
    mail_quota_sweeper.append(info.email_address)
    try:
        yield info, secret, created
    finally:
        for email_address in created:
            with suppress(MailError, MailDeleteDeniedError, ValueError):
                await mail_live_port.delete_mailbox(email_address)
            if email_address in mail_quota_sweeper:
                mail_quota_sweeper.remove(email_address)
