"""Live complete mail client: sync / triage / drafts / search / role / sync-now."""


from __future__ import annotations

from tests.fixtures.auth import set_test_company_member_roles  # noqa: F401
import secrets
from contextlib import suppress

import pytest

from core.config import get_settings
from core.config.models import MailConfig
from core.context import set_context
from core.mail.exceptions import (
    MailDeleteDeniedError,
    MailError,
    MailPermissionError,
    MailTransportError,
)
from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailboxBindingMemberPayload,
    MailboxBindingMemberRole,
    MailDraftSavePayload,
    MailMessageFlagPayload,
    MailMessageListPayload,
    MailMessageSearchPayload,
    MailMessageStarPayload,
    MailProvider,
    MailSyncNowPayload,
    OutboundMailMessage,
)
from core.mail.ports import MailServerPort
from core.mail.repositories import INBOX_FOLDER, MailMessageRepository
from core.mail.service import MailService
from core.models.context_models import Context
from core.models.identity_models import Company, User, UserStatus
from tests.core.mail.live.poll import poll_fetch_message as _poll_fetch_message

pytestmark = [pytest.mark.network, pytest.mark.timeout(240)]


async def _seed_live_company_binding(
    mail_live_service: MailService,
    mail_live_settings: MailConfig,
    mail_quota_sweeper: list[str],
    container,
    *,
    unique_id: str,
    suffix: str,
) -> tuple[str, str, object]:
    system = mail_live_settings.system
    isp = system.ispmanager
    if (
        system.imap_host is None
        or system.smtp_host is None
        or isp.base_url is None
        or isp.authinfo_user is None
        or isp.authinfo_password is None
    ):
        raise RuntimeError("mail.system incomplete for live complete-client test")

    company_id = f"mail_cc_live_{unique_id}_{suffix}"[:64]
    user_id = f"u_{unique_id}_{suffix}"[:64]
    user = User(
        user_id=user_id,
        name=f"Live Mail {unique_id}",
        status=UserStatus.ACTIVE,
        emails=[f"{user_id}@mail.test"],
        companies={company_id: ["owner", "admin"]},
        active_company_id=company_id,
    )
    company = Company(
        company_id=company_id,
        name=f"Mail Live {unique_id}",
        subdomain=f"ml{unique_id}{suffix}"[:32],
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

    prefix = mail_live_settings.live_test.mailbox_prefix
    local_part = f"{prefix}{unique_id}-{suffix}".lower().replace("_", "-")[:64]
    password = secrets.token_urlsafe(20)
    _ = await mail_live_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=system.mail_domain,
            provider=MailProvider.ISPMANAGER,
            imap_host=system.imap_host,
            imap_port=system.imap_port,
            smtp_host=system.smtp_host,
            smtp_port=system.smtp_port,
            use_ssl=system.use_ssl,
            ispmanager_base_url=isp.base_url,
            ispmanager_authinfo_user=isp.authinfo_user,
            ispmanager_authinfo_password=isp.authinfo_password,
        ),
        company_id=company_id,
    )
    binding = await mail_live_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_id,
            local_part=local_part,
            password=password,
            provision=True,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    mail_quota_sweeper.append(binding.email_address)
    return company_id, user_id, binding


@pytest.mark.asyncio
async def test_live_complete_client_sync_triage_search_drafts_role(
    mail_live_service: MailService,
    mail_live_port: MailServerPort,
    mail_live_settings: MailConfig,
    mail_quota_sweeper: list[str],
    container,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id, user_id, binding_a = await _seed_live_company_binding(
        mail_live_service,
        mail_live_settings,
        mail_quota_sweeper,
        container,
        unique_id=unique_id,
        suffix="a",
    )
    _company_b, _user_b, binding_b = await _seed_live_company_binding(
        mail_live_service,
        mail_live_settings,
        mail_quota_sweeper,
        container,
        unique_id=unique_id,
        suffix="b",
    )
    # Restore context to A (seed B overwrote it).
    company_a = await container.company_repository.get(company_id)
    user_a = await container.user_repository.get(user_id)
    assert company_a is not None and user_a is not None
    set_context(
        Context(
            user=user_a,
            active_company=company_a,
            user_companies=[company_a],
            channel="test",
        )
    )

    subject = f"platform-mail-cc-{unique_id}"
    message_id = f"<plt-cc-{unique_id}@linnex.io>"
    secret_a = mail_live_service.binding_secret(binding_a)
    _ = await mail_live_port.send_message(
        secret_a,
        OutboundMailMessage(
            to_addresses=[binding_b.email_address],
            subject=subject,
            body_text=f"body-{unique_id}",
            message_id=message_id,
        ),
    )
    found = await _poll_fetch_message(
        mail_live_port,
        mail_live_service.binding_secret(binding_b),
        message_id=message_id,
        subject=subject,
    )
    assert found is not None

    # Context for B company to sync/search.
    company_b = await container.company_repository.get(binding_b.company_id)
    user_b = await container.user_repository.get(binding_b.user_id or "")
    assert company_b is not None and user_b is not None
    set_context(
        Context(
            user=user_b,
            active_company=company_b,
            user_companies=[company_b],
            channel="test",
        )
    )

    synced = await mail_live_service.sync_binding(binding_b, max_new_messages=50)
    assert synced.skipped_reason is None
    listed = await mail_live_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            folder=INBOX_FOLDER,
            limit=50,
        ),
        company_id=binding_b.company_id,
    )
    assert any(item.subject == subject for item in listed.items)
    target = next(item for item in listed.items if item.subject == subject)

    searched = await mail_live_service.search_messages(
        MailMessageSearchPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            q=unique_id,
            folder=INBOX_FOLDER,
            limit=20,
        ),
        company_id=binding_b.company_id,
    )
    assert any(item.uid == target.uid for item in searched.items)

    starred = await mail_live_service.star_message(
        MailMessageStarPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid=target.uid,
            flagged=True,
        ),
        company_id=binding_b.company_id,
    )
    assert starred.flagged is True

    trashed = await mail_live_service.trash_message(
        MailMessageFlagPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid=target.uid,
        ),
        company_id=binding_b.company_id,
    )
    assert trashed.destination_folder
    after_trash = await mail_live_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            folder=INBOX_FOLDER,
            limit=50,
        ),
        company_id=binding_b.company_id,
    )
    assert all(item.uid != target.uid for item in after_trash.items)

    draft = await mail_live_service.save_draft(
        MailDraftSavePayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            to_addresses=[binding_a.email_address],
            subject=f"draft-{unique_id}",
            body_text="draft body",
        ),
        company_id=binding_b.company_id,
    )
    assert draft.uid
    drafts = await mail_live_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            folder=draft.folder,
            limit=20,
        ),
        company_id=binding_b.company_id,
    )
    assert any(item.uid == draft.uid for item in drafts.items)

    enqueued: list[tuple[str, str]] = []

    async def _fake_enqueue(*, company_id: str, mailbox_binding_id: str) -> None:
        enqueued.append((company_id, mailbox_binding_id))

    monkeypatch.setattr(
        "core.mail.service.enqueue_mail_sync_binding",
        _fake_enqueue,
    )
    sync_now = await mail_live_service.request_sync_now(
        MailSyncNowPayload(mailbox_binding_id=binding_b.mailbox_binding_id),
        company_id=binding_b.company_id,
    )
    assert sync_now.accepted is True
    assert enqueued == [(binding_b.company_id, binding_b.mailbox_binding_id)]

    # Role mailbox ACL (no provision/delete of role boxes — bind with provision=True
    # on a plt-* local_part under the same company).
    role_local = f"{mail_live_settings.live_test.mailbox_prefix}{unique_id}-role"
    role_local = role_local.lower().replace("_", "-")[:64]
    role_password = secrets.token_urlsafe(20)
    role_binding = await mail_live_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.ROLE,
            user_id=None,
            local_part=role_local,
            password=role_password,
            provision=True,
            sync_enabled=True,
        ),
        company_id=binding_b.company_id,
    )
    mail_quota_sweeper.append(role_binding.email_address)
    member_id = f"member_{unique_id}"
    _ = await mail_live_service.add_binding_member(
        role_binding.mailbox_binding_id,
        MailboxBindingMemberPayload(
            user_id=member_id,
            role=MailboxBindingMemberRole.MEMBER,
        ),
        company_id=binding_b.company_id,
    )
    outsider = User(
        user_id=f"out_{unique_id}",
        name="Outsider",
        status=UserStatus.ACTIVE,
        emails=[f"out_{unique_id}@mail.test"],
        companies={binding_b.company_id: ["member"]},
        active_company_id=binding_b.company_id,
    )
    await container.user_repository.set(outsider)
    company_b.members[outsider.user_id] = ["member"]
    await container.company_repository.set(company_b)
    set_context(
        Context(
            user=outsider,
            active_company=company_b,
            user_companies=[company_b],
            channel="test",
        )
    )
    with pytest.raises(MailPermissionError):
        _ = await mail_live_service.list_messages(
            MailMessageListPayload(
                mailbox_binding_id=role_binding.mailbox_binding_id,
                folder=INBOX_FOLDER,
                limit=10,
            ),
            company_id=binding_b.company_id,
        )

    # Local wipe simulates orphan cleanup; resync is best-effort (IMAP login limits).
    set_context(
        Context(
            user=user_b,
            active_company=company_b,
            user_companies=[company_b],
            channel="test",
        )
    )
    shared_url = get_settings().database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен")
    message_repo = MailMessageRepository(db_url=shared_url)
    _ = await message_repo.delete_folder(
        binding_b.mailbox_binding_id, folder=INBOX_FOLDER
    )
    wiped_local = await mail_live_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            folder=INBOX_FOLDER,
            limit=50,
        ),
        company_id=binding_b.company_id,
    )
    assert wiped_local.items == []
    with suppress(MailError, MailTransportError, TimeoutError):
        resync = await mail_live_service.sync_binding(binding_b, max_new_messages=50)
        assert resync.skipped_reason is None

    # Best-effort cleanup of provisioned role box (may be denied by policy).
    with suppress(MailError, MailDeleteDeniedError, ValueError):
        await mail_live_port.delete_mailbox(role_binding.email_address)
        if role_binding.email_address in mail_quota_sweeper:
            mail_quota_sweeper.remove(role_binding.email_address)
