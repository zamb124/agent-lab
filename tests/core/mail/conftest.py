"""Фикстуры offline-тестов почты."""

from __future__ import annotations

import pytest

from core.config import get_settings
from core.config.models import MailConfig
from core.context import clear_context, set_context
from core.mail.repositories import (
    CompanyMailConnectionRepository,
    MailboxBindingMemberRepository,
    MailboxBindingRepository,
    MailboxFolderRepository,
    MailboxSyncCursorRepository,
    MailMessageRepository,
)
from core.mail.service import MailService
from core.models.context_models import Context
from core.models.identity_models import Company, User, UserStatus
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
def mailbox_folder_repository(app) -> MailboxFolderRepository:
    _ = app
    shared_url = get_settings().database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен для mail tests")
    return MailboxFolderRepository(db_url=shared_url)


@pytest.fixture()
def mailbox_binding_member_repository(app) -> MailboxBindingMemberRepository:
    _ = app
    shared_url = get_settings().database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен для mail tests")
    return MailboxBindingMemberRepository(db_url=shared_url)


@pytest.fixture()
def mail_message_repository(app) -> MailMessageRepository:
    _ = app
    shared_url = get_settings().database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен для mail tests")
    return MailMessageRepository(db_url=shared_url)


@pytest.fixture()
def recording_mail_port() -> RecordingMailServerPort:
    return RecordingMailServerPort(supports_provision=True)


@pytest.fixture()
def mail_service(
    mail_connection_repository: CompanyMailConnectionRepository,
    mailbox_binding_repository: MailboxBindingRepository,
    mailbox_sync_cursor_repository: MailboxSyncCursorRepository,
    mailbox_folder_repository: MailboxFolderRepository,
    mail_message_repository: MailMessageRepository,
    mailbox_binding_member_repository: MailboxBindingMemberRepository,
    recording_mail_port: RecordingMailServerPort,
    container,
) -> MailService:
    return MailService(
        connection_repository=mail_connection_repository,
        binding_repository=mailbox_binding_repository,
        sync_cursor_repository=mailbox_sync_cursor_repository,
        folder_repository=mailbox_folder_repository,
        message_repository=mail_message_repository,
        member_repository=mailbox_binding_member_repository,
        namespace_service=container.namespace_service,
        company_repository=container.company_repository,
        user_repository=container.user_repository,
        mail_config=MailConfig(),
        port_override=recording_mail_port,
    )


async def seed_mail_company_member(
    container,
    *,
    company_id: str,
    user_id: str,
    unique_id: str,
    display_name: str | None = None,
) -> tuple[Company, User]:
    """Создаёт company+user в shared DB и Context для mail sync / personal ns."""
    name = display_name if display_name is not None else f"Mail User {unique_id}"
    user = User(
        user_id=user_id,
        name=name,
        status=UserStatus.ACTIVE,
        emails=[f"{user_id}@mail.test"],
        companies={company_id: ["owner", "admin"]},
        active_company_id=company_id,
    )
    company = Company(
        company_id=company_id,
        name=f"Mail Co {unique_id}",
        subdomain=f"m{unique_id}"[:32],
        owner_user_id=user_id,
        members={user_id: ["owner", "admin"]},
    )
    await container.user_repository.set(user)
    await container.company_repository.set(company)
    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )
    return company, user


@pytest.fixture()
def mail_member_context(container, unique_id: str):
    """Function-scoped helper: seed + context; clears context on teardown."""

    async def _seed(*, company_id: str, user_id: str, display_name: str | None = None):
        return await seed_mail_company_member(
            container,
            company_id=company_id,
            user_id=user_id,
            unique_id=unique_id,
            display_name=display_name,
        )

    yield _seed
    clear_context()
