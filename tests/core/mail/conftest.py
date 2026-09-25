"""Фикстуры offline-тестов почты."""


from __future__ import annotations

import pytest

from core.config.models import MailConfig
from core.context import clear_context, set_context
from core.mail.attachment_index import MailAttachmentFileIndex
from core.mail.service import MailService
from core.models.context_models import Context
from core.models.identity_models import Company, User, UserStatus
from tests.core.mail.fakes import RecordingMailServerPort
from tests.fixtures.auth import set_test_company_member_roles


@pytest.fixture()
def recording_mail_port() -> RecordingMailServerPort:
    return RecordingMailServerPort(supports_provision=True)


@pytest.fixture()
def mail_service(
    recording_mail_port: RecordingMailServerPort,
    di,
) -> MailService:
    return MailService(
        authz=di.authz_service,
        namespace_service=di.namespace_service,
        mail_config=MailConfig(),
        port_override=recording_mail_port,
        files_service=di.files_service,
        attachment_file_index=MailAttachmentFileIndex(di.shared_storage),
    )


async def seed_mail_company_member(
    di,
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
    await User.set(user)
    await Company.set(company)
    await set_test_company_member_roles(
        di.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=["owner", "admin"],
    )
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
def mail_member_context(di, unique_id: str):
    """Function-scoped helper: seed + context; clears context on teardown."""

    async def _seed(*, company_id: str, user_id: str, display_name: str | None = None):
        return await seed_mail_company_member(
            di,
            company_id=company_id,
            user_id=user_id,
            unique_id=unique_id,
            display_name=display_name,
        )

    yield _seed
    clear_context()
