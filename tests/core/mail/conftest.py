"""Фикстуры offline-тестов почты."""

from __future__ import annotations

import pytest

from core.config import get_settings
from core.config.models import MailConfig
from core.mail.repositories import (
    CompanyMailConnectionRepository,
    MailboxBindingRepository,
    MailboxSyncCursorRepository,
)
from core.mail.service import MailService
from tests.core.mail.fakes import RecordingMailServerPort


@pytest.fixture()
def mail_connection_repository(app) -> CompanyMailConnectionRepository:
    _ = app
    shared_url = get_settings().database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен для mail tests")
    return CompanyMailConnectionRepository(db_url=shared_url)


@pytest.fixture()
def mailbox_binding_repository(app) -> MailboxBindingRepository:
    _ = app
    shared_url = get_settings().database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен для mail tests")
    return MailboxBindingRepository(db_url=shared_url)


@pytest.fixture()
def mailbox_sync_cursor_repository(app) -> MailboxSyncCursorRepository:
    _ = app
    shared_url = get_settings().database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен для mail tests")
    return MailboxSyncCursorRepository(db_url=shared_url)


@pytest.fixture()
def recording_mail_port() -> RecordingMailServerPort:
    return RecordingMailServerPort(supports_provision=True)


@pytest.fixture()
def mail_service(
    mail_connection_repository: CompanyMailConnectionRepository,
    mailbox_binding_repository: MailboxBindingRepository,
    mailbox_sync_cursor_repository: MailboxSyncCursorRepository,
    recording_mail_port: RecordingMailServerPort,
    container,
) -> MailService:
    return MailService(
        connection_repository=mail_connection_repository,
        binding_repository=mailbox_binding_repository,
        sync_cursor_repository=mailbox_sync_cursor_repository,
        company_repository=container.company_repository,
        user_repository=container.user_repository,
        mail_config=MailConfig(),
        port_override=recording_mail_port,
    )
