"""Offline: изоляция company_id и ensure_system через fake port."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.authz.company_sync import remove_company_member, sync_company_member_roles
from core.authz.factory import build_authz_service
from core.config import get_settings
from core.config.models import (
    MailConfig,
    MailIspmanagerConfig,
    MailLiveTestConfig,
    MailLocalDevConfig,
    MailSystemConfig,
)
from core.identity.flow_employee import flow_employee_user_id
from core.mail.exceptions import MailConnectionNotFoundError
from core.mail.models import (
    CompanyMailConnection,
    MailboxBinding,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailboxInfo,
    MailConnectionStatus,
    MailProvider,
)
from core.mail.service import MailService, _slug_local_part
from core.models.identity_models import SYSTEM_COMPANY_ID, Company, User, UserStatus
from tests.core.mail.fakes import RecordingMailServerPort


async def _put_system_member(di, user_id: str) -> None:
    _ = await Company.put_member_roles(
        SYSTEM_COMPANY_ID, user_id, ["member"]
    )


async def _discard_system_member(di, user_id: str) -> None:
    _ = await Company.discard_member(SYSTEM_COMPANY_ID, user_id)


@pytest.mark.asyncio
async def test_bindings_isolated_by_company(
    unique_id: str,
) -> None:
    now = datetime.now(timezone.utc)
    company_a = f"mailiso_a_{unique_id}"
    company_b = f"mailiso_b_{unique_id}"
    for company_id, conn_id in (
        (company_a, f"mailconn_a_{unique_id}"),
        (company_b, f"mailconn_b_{unique_id}"),
    ):
        _ = await CompanyMailConnection.upsert_by_company_mail_connection_id(
            CompanyMailConnection(
                company_mail_connection_id=conn_id,
                company_id=company_id,
                mail_domain=f"{company_id}.example.com",
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
            mailbox_binding_id=f"mailbind_a_{unique_id}",
            company_id=company_a,
            company_mail_connection_id=f"mailconn_a_{unique_id}",
            user_id=f"user_a_{unique_id}",
            kind=MailboxBindingKind.USER,
            email_address=f"a@{company_a}.example.com",
            local_part="a",
            sync_enabled=True,
            password_encrypted="enc-a",
            created_at=now,
            updated_at=now,
        )
    )
    listed_b = await MailboxBinding.list_by_email_address_for_company(company_b)
    assert listed_b == []
    listed_a = await MailboxBinding.list_by_email_address_for_company(company_a)
    assert len(listed_a) == 1
    assert listed_a[0].mailbox_binding_id == f"mailbind_a_{unique_id}"


@pytest.mark.asyncio
async def test_ensure_system_with_fake_port(
    recording_mail_port: RecordingMailServerPort,
    di,
    unique_id: str,
) -> None:
    _ = unique_id
    mail_config = MailConfig(
        system=MailSystemConfig(
            enabled=True,
            mail_domain="linnex.io",
            provider="ispmanager",
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
            ispmanager=MailIspmanagerConfig(
                base_url="https://panel.example.com:1500/ispmgr",
                authinfo_user="admin",
                authinfo_password="panel-secret",
            ),
            role_mailboxes=["support", "hr"],
            protected_local_parts=["support", "hr"],
        ),
        live_test=MailLiveTestConfig(enabled=False),
    )
    shared_url = get_settings().database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен для mail tests")
    service = MailService(
        authz=build_authz_service(),
        mail_config=mail_config,
        port_override=recording_mail_port,
    )
    connection = await service.ensure_system_mail_connection()
    assert connection is not None
    assert connection.company_id == "system"
    assert connection.mail_domain == "linnex.io"

    roles = await service.ensure_system_role_mailboxes()
    assert "support@linnex.io" in roles.ensured
    assert "hr@linnex.io" in roles.ensured
    assert len(recording_mail_port.ensure_calls) >= 2

    again = await service.ensure_system_mail_connection()
    assert again is not None
    assert again.company_mail_connection_id == connection.company_mail_connection_id


def _offline_system_mail_service(
    *,
    recording_mail_port: RecordingMailServerPort,
    di,
    role_mailboxes: list[str] | None = None,
    local_dev: MailLocalDevConfig,
) -> MailService:
    shared_url = get_settings().database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен для mail tests")
    roles = [] if role_mailboxes is None else role_mailboxes
    mail_config = MailConfig(
        system=MailSystemConfig(
            enabled=True,
            mail_domain="linnex.io",
            provider="ispmanager",
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
            ispmanager=MailIspmanagerConfig(
                base_url="https://panel.example.com:1500/ispmgr",
                authinfo_user="admin",
                authinfo_password="panel-secret",
            ),
            role_mailboxes=roles,
            protected_local_parts=roles,
        ),
        live_test=MailLiveTestConfig(enabled=False),
        local_dev=local_dev,
    )
    return MailService(
        authz=build_authz_service(),
        mail_config=mail_config,
        port_override=recording_mail_port,
    )


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_ensure_system_user_bindings_creates_flow_employee_mailbox(
    recording_mail_port: RecordingMailServerPort,
    di,
    unique_id: str,
) -> None:
    employee_user_id = flow_employee_user_id(f"mailbind_{unique_id}")
    company = await Company.get(SYSTEM_COMPANY_ID)
    assert company is not None

    await User.set(
        User(
            user_id=employee_user_id,
            name=f"Mail Emp {unique_id}",
            status=UserStatus.ACTIVE,
            emails=[f"{employee_user_id}@linnex.io"],
            companies={SYSTEM_COMPANY_ID: ["member"]},
            active_company_id=SYSTEM_COMPANY_ID,
        )
    )
    await _put_system_member(di, employee_user_id)
    await sync_company_member_roles(
        di.authz_service,
        company_id=SYSTEM_COMPANY_ID,
        user_id=employee_user_id,
        roles=["member"],
    )

    service = _offline_system_mail_service(
        recording_mail_port=recording_mail_port,
        di=di,
        local_dev=MailLocalDevConfig(enabled=False),
    )
    try:
        _ = await service.ensure_system_mail_connection()
        _ = await service.ensure_system_user_bindings()
        employee_binding = await MailboxBinding.preferred_for_user(
            SYSTEM_COMPANY_ID, employee_user_id
        )
        assert employee_binding is not None
        assert employee_binding.kind == MailboxBindingKind.USER
        assert employee_binding.user_id == employee_user_id
    finally:
        leftover = await MailboxBinding.preferred_for_user(
            SYSTEM_COMPANY_ID, employee_user_id
        )
        if leftover is not None:
            await service.unbind_mailbox(
                leftover.mailbox_binding_id,
                company_id=SYSTEM_COMPANY_ID,
                acting_as_admin=True,
            )
        restored = await Company.get(SYSTEM_COMPANY_ID)
        if restored is None:
            raise RuntimeError("system company missing after employee mailbox test")
        await _discard_system_member(di, employee_user_id)
        await remove_company_member(
            di.authz_service,
            company_id=SYSTEM_COMPANY_ID,
            user_id=employee_user_id,
        )
        await User.delete_by_id(employee_user_id)


@pytest.mark.asyncio
async def test_ensure_system_user_bindings_unbinds_leftover_without_membership(
    recording_mail_port: RecordingMailServerPort,
    di,
    unique_id: str,
) -> None:
    leftover_user_id = f"mail_leftover_{unique_id}"
    local_part = f"lf{unique_id.replace('-', '')[:10]}"
    company = await Company.get(SYSTEM_COMPANY_ID)
    assert company is not None
    assert leftover_user_id not in company.members

    await User.set(
        User(
            user_id=leftover_user_id,
            name=f"Leftover {unique_id}",
            status=UserStatus.INACTIVE,
            emails=[f"{leftover_user_id}@linnex.io"],
            companies={},
            active_company_id=SYSTEM_COMPANY_ID,
        )
    )
    service = _offline_system_mail_service(
        recording_mail_port=recording_mail_port,
        di=di,
        local_dev=MailLocalDevConfig(
            enabled=True,
            mutate_remote_passwords=False,
            mailbox_passwords={},
        ),
    )
    try:
        _ = await service.ensure_system_mail_connection()
        leftover_binding = await service.bind_mailbox(
            MailboxBindingCreatePayload(
                user_id=leftover_user_id,
                kind=MailboxBindingKind.USER,
                local_part=local_part,
                provision=True,
                sync_enabled=True,
            ),
            company_id=SYSTEM_COMPANY_ID,
        )
        assert leftover_binding.user_id == leftover_user_id
        _ = await service.ensure_system_user_bindings()
        unbound = await MailboxBinding.preferred_for_user(
            SYSTEM_COMPANY_ID, leftover_user_id
        )
        assert unbound is None
    finally:
        still_bound = await MailboxBinding.preferred_for_user(
            SYSTEM_COMPANY_ID, leftover_user_id
        )
        if still_bound is not None:
            await service.unbind_mailbox(
                still_bound.mailbox_binding_id,
                company_id=SYSTEM_COMPANY_ID,
                acting_as_admin=True,
            )
        await User.delete_by_id(leftover_user_id)


@pytest.mark.asyncio
async def test_ensure_system_user_bindings_local_dev_missing_password_does_not_bind(
    recording_mail_port: RecordingMailServerPort,
    di,
    unique_id: str,
) -> None:
    member_user_id = f"mail_inv_{unique_id}"
    company = await Company.get(SYSTEM_COMPANY_ID)
    assert company is not None
    await User.set(
        User(
            user_id=member_user_id,
            name=f"Inv {unique_id}",
            status=UserStatus.ACTIVE,
            emails=[f"{member_user_id}@linnex.io"],
            companies={SYSTEM_COMPANY_ID: ["member"]},
            active_company_id=SYSTEM_COMPANY_ID,
        )
    )
    stored_user = await User.get(member_user_id)
    assert stored_user is not None
    email_address = f"{_slug_local_part(stored_user)}@linnex.io"
    await _put_system_member(di, member_user_id)
    await sync_company_member_roles(
        di.authz_service,
        company_id=SYSTEM_COMPANY_ID,
        user_id=member_user_id,
        roles=["member"],
    )
    recording_mail_port.mailboxes[email_address] = MailboxInfo(
        email_address=email_address,
        local_part=_slug_local_part(stored_user),
        mail_domain="linnex.io",
    )
    recording_mail_port.mailbox_passwords[email_address] = "isp-password-must-stay"
    service = _offline_system_mail_service(
        recording_mail_port=recording_mail_port,
        di=di,
        local_dev=MailLocalDevConfig(
            enabled=True,
            mutate_remote_passwords=False,
            mailbox_passwords={},
        ),
    )
    try:
        _ = await service.ensure_system_mail_connection()
        result = await service.ensure_system_user_bindings()
        assert email_address in result.missing_password
        assert await MailboxBinding.preferred_for_user(
            SYSTEM_COMPANY_ID, member_user_id
        ) is None
        assert recording_mail_port.set_password_calls == []
        assert recording_mail_port.ensure_calls == []
        assert recording_mail_port.mailbox_passwords[email_address] == "isp-password-must-stay"
    finally:
        leftover = await MailboxBinding.preferred_for_user(
            SYSTEM_COMPANY_ID, member_user_id
        )
        if leftover is not None:
            await service.unbind_mailbox(
                leftover.mailbox_binding_id,
                company_id=SYSTEM_COMPANY_ID,
                acting_as_admin=True,
            )
        restored = await Company.get(SYSTEM_COMPANY_ID)
        if restored is None:
            raise RuntimeError("system company missing after local_dev inventory test")
        await _discard_system_member(di, member_user_id)
        await remove_company_member(
            di.authz_service,
            company_id=SYSTEM_COMPANY_ID,
            user_id=member_user_id,
        )
        await User.delete_by_id(member_user_id)


@pytest.mark.asyncio
async def test_ensure_system_user_bindings_local_dev_binds_from_mailbox_passwords(
    recording_mail_port: RecordingMailServerPort,
    di,
    unique_id: str,
) -> None:
    member_user_id = f"mail_known_{unique_id}"
    company = await Company.get(SYSTEM_COMPANY_ID)
    assert company is not None
    await User.set(
        User(
            user_id=member_user_id,
            name=f"Known {unique_id}",
            status=UserStatus.ACTIVE,
            emails=[f"{member_user_id}@linnex.io"],
            companies={SYSTEM_COMPANY_ID: ["member"]},
            active_company_id=SYSTEM_COMPANY_ID,
        )
    )
    stored_user = await User.get(member_user_id)
    assert stored_user is not None
    local_part = _slug_local_part(stored_user)
    email_address = f"{local_part}@linnex.io"
    await _put_system_member(di, member_user_id)
    await sync_company_member_roles(
        di.authz_service,
        company_id=SYSTEM_COMPANY_ID,
        user_id=member_user_id,
        roles=["member"],
    )
    recording_mail_port.mailboxes[email_address] = MailboxInfo(
        email_address=email_address,
        local_part=local_part,
        mail_domain="linnex.io",
    )
    recording_mail_port.mailbox_passwords[email_address] = "isp-password-must-stay"
    service = _offline_system_mail_service(
        recording_mail_port=recording_mail_port,
        di=di,
        local_dev=MailLocalDevConfig(
            enabled=True,
            mutate_remote_passwords=False,
            mailbox_passwords={email_address: "from-conf-local"},
        ),
    )
    try:
        _ = await service.ensure_system_mail_connection()
        result = await service.ensure_system_user_bindings()
        assert email_address in result.ensured
        assert email_address not in result.missing_password
        binding = await MailboxBinding.preferred_for_user(
            SYSTEM_COMPANY_ID, member_user_id
        )
        assert binding is not None
        assert service.binding_secret(binding).password == "from-conf-local"
        assert recording_mail_port.set_password_calls == []
        assert recording_mail_port.ensure_calls == []
        assert recording_mail_port.mailbox_passwords[email_address] == "isp-password-must-stay"
    finally:
        leftover = await MailboxBinding.preferred_for_user(
            SYSTEM_COMPANY_ID, member_user_id
        )
        if leftover is not None:
            await service.unbind_mailbox(
                leftover.mailbox_binding_id,
                company_id=SYSTEM_COMPANY_ID,
                acting_as_admin=True,
            )
        restored = await Company.get(SYSTEM_COMPANY_ID)
        if restored is None:
            raise RuntimeError("system company missing after local_dev known-password test")
        await _discard_system_member(di, member_user_id)
        await remove_company_member(
            di.authz_service,
            company_id=SYSTEM_COMPANY_ID,
            user_id=member_user_id,
        )
        await User.delete_by_id(member_user_id)


@pytest.mark.asyncio
async def test_bind_without_connection_raises(
    mail_service: MailService,
    unique_id: str,
) -> None:
    with pytest.raises(MailConnectionNotFoundError):
        _ = await mail_service.bind_mailbox(
            MailboxBindingCreatePayload(
                kind=MailboxBindingKind.USER,
                user_id=f"user_{unique_id}",
                local_part=f"u.{unique_id}",
                password="secret",
            ),
            company_id=f"missing_mail_{unique_id}",
        )
