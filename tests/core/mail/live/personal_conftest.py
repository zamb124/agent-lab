"""Live-фикстуры: fixed personal IMAP/SMTP (Mail.ru) без provision/delete ящиков."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import datetime, timezone

import pytest

from core.authz.factory import build_authz_service
from core.config import get_settings
from core.config.models import MailConfig, MailLivePersonalConfig
from core.context import clear_context, set_context
from core.mail.exceptions import MailError, MailTransportError
from core.mail.factory import build_mail_server_port
from core.mail.models import (
    CompanyMailConnection,
    MailboxBinding,
    MailboxSecret,
    MailboxSyncCursor,
    MailConnectionScope,
    MailConnectionStatus,
    MailFetchQuery,
    MailProvider,
    PersonalMailboxConnectPayload,
    StoredMailboxFolder,
    StoredMailMessage,
)
from core.mail.ports import MailServerPort
from core.mail.service import MailService
from core.models.context_models import Context
from core.models.identity_models import Company, User
from tests.core.mail.conftest import seed_mail_company_member

_SWEEP_FOLDERS = ("INBOX", "Sent", "Drafts", "Trash", "Spam", "Junk", "Archive")


def _require_password(mail: MailConfig, email_address: str) -> str:
    key = email_address.strip().lower()
    password = mail.local_dev.mailbox_passwords.get(key)
    if password is None or not password.strip():
        pytest.skip(f"mail.local_dev.mailbox_passwords[{key!r}] missing")
    return password


@pytest.fixture()
def mail_personal_live_settings() -> MailConfig:
    settings = get_settings()
    mail = settings.mail
    personal = mail.live_test.personal
    if not personal.enabled:
        pytest.skip("mail.live_test.personal.enabled=false")
    if not personal.account_a.strip() or not personal.account_b.strip():
        pytest.skip("mail.live_test.personal.account_a/account_b required")
    if not personal.imap_host.strip() or not personal.smtp_host.strip():
        pytest.skip("mail.live_test.personal imap/smtp host required")
    _ = _require_password(mail, personal.account_a)
    _ = _require_password(mail, personal.account_b)
    return mail


@pytest.fixture()
def mail_personal_cfg(
    mail_personal_live_settings: MailConfig,
) -> MailLivePersonalConfig:
    return mail_personal_live_settings.live_test.personal


@pytest.fixture()
def mail_personal_pair(
    mail_personal_live_settings: MailConfig,
    mail_personal_cfg: MailLivePersonalConfig,
) -> tuple[MailboxSecret, MailboxSecret]:
    secret_a = MailboxSecret(
        email_address=mail_personal_cfg.account_a.strip().lower(),
        password=_require_password(
            mail_personal_live_settings, mail_personal_cfg.account_a
        ),
    )
    secret_b = MailboxSecret(
        email_address=mail_personal_cfg.account_b.strip().lower(),
        password=_require_password(
            mail_personal_live_settings, mail_personal_cfg.account_b
        ),
    )
    return secret_a, secret_b


@pytest.fixture()
def mail_personal_port(mail_personal_cfg: MailLivePersonalConfig) -> MailServerPort:
    now = datetime.now(timezone.utc)
    connection = CompanyMailConnection(
        company_mail_connection_id="live-personal-port",
        company_id="system",
        scope=MailConnectionScope.PERSONAL,
        owner_user_id="live-personal",
        mail_domain=mail_personal_cfg.account_a.split("@", 1)[1],
        provider=MailProvider.GENERIC_IMAP_SMTP,
        imap_host=mail_personal_cfg.imap_host,
        imap_port=mail_personal_cfg.imap_port,
        smtp_host=mail_personal_cfg.smtp_host,
        smtp_port=mail_personal_cfg.smtp_port,
        use_ssl=mail_personal_cfg.use_ssl,
        supports_provision=False,
        status=MailConnectionStatus.ACTIVE,
        ispmanager=None,
        created_at=now,
        updated_at=now,
    )
    return build_mail_server_port(
        connection,
        protected_local_parts=frozenset(),
        delete_prefix_required=None,
        allow_delete=False,
    )


@pytest.fixture()
def mail_personal_service(
    mail_personal_live_settings: MailConfig,
    di,
) -> MailService:
    settings = get_settings()
    shared_url = settings.database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен для personal live tests")
    return MailService(
        authz=build_authz_service(),
        namespace_service=di.namespace_service,
        mail_config=mail_personal_live_settings,
        port_override=None,
    )


@pytest.fixture()
def mail_subject_marker(unique_id: str) -> str:
    return f"plt-pers-{unique_id}"


@pytest.fixture()
async def mail_personal_company_ctx(
    di,
    unique_id: str,
) -> AsyncIterator[tuple[str, str, Company, User]]:
    company_id = f"mailpers_live_{unique_id}"[:64]
    user_id = f"upers_{unique_id}"[:64]
    company, user = await seed_mail_company_member(
        di,
        company_id=company_id,
        user_id=user_id,
        unique_id=unique_id,
    )
    try:
        yield company_id, user_id, company, user
    finally:
        clear_context()


async def _wipe_local_binding_state(
    *,
    mailbox_binding_id: str,
) -> None:
    folders = await StoredMailboxFolder.list_for_binding(mailbox_binding_id)
    folder_names = {item.folder_name for item in folders} | set(_SWEEP_FOLDERS)
    for folder_name in folder_names:
        _ = await StoredMailMessage.delete_folder(
            mailbox_binding_id, folder=folder_name
        )
        _ = await MailboxSyncCursor.delete_by_mailbox_binding_and_folder(
            mailbox_binding_id, folder=folder_name
        )
    _ = await StoredMailboxFolder.replace_for_binding(
        mailbox_binding_id,
        company_id="wipe",
        folders=[],
    )


async def _sweep_marker_messages(
    port: MailServerPort,
    secret: MailboxSecret,
    *,
    marker: str,
) -> None:
    folders_result = await port.list_imap_folders(secret)
    folder_names = {folder.name for folder in folders_result.folders} | set(_SWEEP_FOLDERS)
    for folder_name in folder_names:
        with suppress(MailError, MailTransportError, ValueError, OSError):
            messages = await port.fetch_messages(
                secret,
                MailFetchQuery(
                    mailbox=folder_name,
                    subject_contains=marker,
                    limit=50,
                    include_bodies=False,
                ),
            )
            for item in messages:
                if item.subject is None or marker not in item.subject:
                    continue
                with suppress(MailError, MailTransportError, ValueError, OSError):
                    await port.uid_expunge(
                        secret,
                        mailbox=folder_name,
                        uid=item.uid,
                    )


@pytest.fixture()
async def mail_personal_message_sweeper(
    mail_personal_port: MailServerPort,
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_subject_marker: str,
) -> AsyncIterator[str]:
    marker = mail_subject_marker
    try:
        yield marker
    finally:
        secret_a, secret_b = mail_personal_pair
        await _sweep_marker_messages(
            mail_personal_port, secret_a, marker=marker
        )
        await _sweep_marker_messages(
            mail_personal_port, secret_b, marker=marker
        )


@pytest.fixture()
async def mail_personal_bindings(
    mail_personal_service: MailService,
    mail_personal_cfg: MailLivePersonalConfig,
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_personal_company_ctx: tuple[str, str, Company, User],
    mail_personal_message_sweeper: str,
) -> AsyncIterator[tuple[str, MailboxBinding, MailboxBinding]]:
    _ = mail_personal_message_sweeper
    company_id, user_id, company, user = mail_personal_company_ctx
    secret_a, secret_b = mail_personal_pair
    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )
    binding_a = await mail_personal_service.connect_personal_mailbox(
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
    binding_b = await mail_personal_service.connect_personal_mailbox(
        PersonalMailboxConnectPayload(
            email_address=secret_b.email_address,
            password=secret_b.password,
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
        yield company_id, binding_a, binding_b
    finally:
        for binding in (binding_a, binding_b):
            with suppress(MailError, ValueError):
                await _wipe_local_binding_state(
                    mailbox_binding_id=binding.mailbox_binding_id,
                )
            with suppress(MailError, ValueError):
                set_context(
                    Context(
                        user=user,
                        active_company=company,
                        user_companies=[company],
                        channel="test",
                    )
                )
                await mail_personal_service.unbind_mailbox(
                    binding.mailbox_binding_id,
                    company_id=company_id,
                )
        _ = user_id
        clear_context()
