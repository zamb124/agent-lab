"""Offline integration: sync fidelity (bootstrap, wipe, reconcile, flags, sync-now)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from core.mail.models import MailMessageListPayload, MailSyncNowPayload
from core.mail.repositories import INBOX_FOLDER, MailboxSyncCursorRepository
from core.mail.service import MailService
from core.models.identity_models import Company, User
from tests.core.mail.complete_client_helpers import (
    inbox_message,
    seed_connected_user_binding,
)
from tests.core.mail.fakes import RecordingMailServerPort

MailMemberSeed = Callable[..., Awaitable[tuple[Company, User]]]


@pytest.mark.asyncio
async def test_sync_bootstrap_then_incremental_and_uidvalidity_wipe(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mailbox_sync_cursor_repository: MailboxSyncCursorRepository,
    mail_member_context: MailMemberSeed,
    unique_id: str,
) -> None:
    company_id, _user_id, binding = await seed_connected_user_binding(
        mail_service,
        mail_member_context,
        recording_mail_port,
        unique_id=unique_id,
        prefix="syncwipe",
    )
    recording_mail_port.uidvalidity = 100
    recording_mail_port.inbox = [
        inbox_message(uid="1", unique_id=unique_id, subject="first", body="a"),
        inbox_message(uid="2", unique_id=unique_id, subject="second", body="b"),
    ]
    bootstrap = await mail_service.sync_binding(binding, max_new_messages=50)
    assert bootstrap.bootstrap is True
    listed = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            limit=50,
        ),
        company_id=company_id,
    )
    assert {item.uid for item in listed.items} == {"1", "2"}
    cursor = await mailbox_sync_cursor_repository.get(
        binding.mailbox_binding_id, folder=INBOX_FOLDER
    )
    assert cursor is not None
    assert cursor.uidvalidity == 100
    assert cursor.last_uid == 2

    recording_mail_port.inbox.append(
        inbox_message(uid="3", unique_id=unique_id, subject="third", body="c")
    )
    incr = await mail_service.sync_binding(binding, max_new_messages=50)
    assert incr.bootstrap is False
    assert any(msg.uid == "3" for msg in incr.new_messages)

    recording_mail_port.uidvalidity = 200
    recording_mail_port.inbox = [
        inbox_message(uid="10", unique_id=unique_id, subject="after-wipe", body="z"),
    ]
    wiped = await mail_service.sync_binding(binding, max_new_messages=50)
    assert wiped.bootstrap is True
    after = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            limit=50,
        ),
        company_id=company_id,
    )
    assert [item.uid for item in after.items] == ["10"]
    assert after.needs_sync is False


@pytest.mark.asyncio
async def test_sync_reconcile_deletes_local_orphans(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    unique_id: str,
) -> None:
    company_id, _user_id, binding = await seed_connected_user_binding(
        mail_service,
        mail_member_context,
        recording_mail_port,
        unique_id=unique_id,
        prefix="reconcile",
    )
    recording_mail_port.inbox = [
        inbox_message(uid="1", unique_id=unique_id, subject="keep"),
        inbox_message(uid="2", unique_id=unique_id, subject="orphan-soon"),
    ]
    _ = await mail_service.sync_binding(binding, max_new_messages=50)
    recording_mail_port.inbox = [
        inbox_message(uid="1", unique_id=unique_id, subject="keep"),
    ]
    _ = await mail_service.sync_binding(binding, max_new_messages=50)
    listed = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            limit=50,
        ),
        company_id=company_id,
    )
    assert [item.uid for item in listed.items] == ["1"]


@pytest.mark.asyncio
async def test_sync_flag_refresh_updates_unread_and_flagged(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    unique_id: str,
) -> None:
    company_id, _user_id, binding = await seed_connected_user_binding(
        mail_service,
        mail_member_context,
        recording_mail_port,
        unique_id=unique_id,
        prefix="flagsync",
    )
    recording_mail_port.inbox = [
        inbox_message(
            uid="5",
            unique_id=unique_id,
            subject="flag-me",
            unread=True,
            flagged=False,
        ),
    ]
    _ = await mail_service.sync_binding(binding, max_new_messages=50)
    recording_mail_port.inbox[0] = inbox_message(
        uid="5",
        unique_id=unique_id,
        subject="flag-me",
        unread=False,
        flagged=True,
    )
    _ = await mail_service.sync_binding(binding, max_new_messages=50)
    listed = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            limit=50,
        ),
        company_id=company_id,
    )
    assert listed.items[0].uid == "5"
    assert listed.items[0].unread is False
    assert listed.items[0].flagged is True


@pytest.mark.asyncio
async def test_sync_now_refreshes_folders_and_enqueues(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id, _user_id, binding = await seed_connected_user_binding(
        mail_service,
        mail_member_context,
        recording_mail_port,
        unique_id=unique_id,
        prefix="syncnow",
    )
    enqueued: list[tuple[str, str]] = []

    async def _fake_enqueue(*, company_id: str, mailbox_binding_id: str) -> None:
        enqueued.append((company_id, mailbox_binding_id))

    monkeypatch.setattr(
        "core.mail.service.enqueue_mail_sync_binding",
        _fake_enqueue,
    )
    result = await mail_service.request_sync_now(
        MailSyncNowPayload(mailbox_binding_id=binding.mailbox_binding_id),
        company_id=company_id,
    )
    assert result.accepted is True
    assert enqueued == [(company_id, binding.mailbox_binding_id)]
    folders = await mail_service.list_folders(
        binding.mailbox_binding_id, company_id=company_id
    )
    names = {folder.name for folder in folders.folders}
    assert "INBOX" in names
    assert "Sent" in names


@pytest.mark.asyncio
async def test_sync_backfill_advances_oldest_uid(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mailbox_sync_cursor_repository: MailboxSyncCursorRepository,
    mail_member_context: MailMemberSeed,
    unique_id: str,
) -> None:
    company_id, _user_id, binding = await seed_connected_user_binding(
        mail_service,
        mail_member_context,
        recording_mail_port,
        unique_id=unique_id,
        prefix="backfill",
    )
    recording_mail_port.inbox = [
        inbox_message(uid=str(i), unique_id=unique_id, subject=f"old-{i}")
        for i in range(1, 6)
    ]
    first = await mail_service.sync_binding(binding, max_new_messages=2, backfill_batch_size=2)
    assert first.bootstrap is True
    cursor = await mailbox_sync_cursor_repository.get(
        binding.mailbox_binding_id, folder=INBOX_FOLDER
    )
    assert cursor is not None
    assert cursor.backfill_completed is False
    assert cursor.oldest_uid is not None
    assert cursor.oldest_uid > 1

    second = await mail_service.sync_binding(binding, max_new_messages=50, backfill_batch_size=2)
    _ = company_id
    _ = second
    cursor2 = await mailbox_sync_cursor_repository.get(
        binding.mailbox_binding_id, folder=INBOX_FOLDER
    )
    assert cursor2 is not None
    listed = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            limit=50,
        ),
        company_id=company_id,
    )
    assert len(listed.items) >= 2
    # Continue until backfill completes.
    for _ in range(5):
        cursor2 = await mailbox_sync_cursor_repository.get(
            binding.mailbox_binding_id, folder=INBOX_FOLDER
        )
        assert cursor2 is not None
        if cursor2.backfill_completed:
            break
        _ = await mail_service.sync_binding(
            binding, max_new_messages=50, backfill_batch_size=2
        )
    cursor_final = await mailbox_sync_cursor_repository.get(
        binding.mailbox_binding_id, folder=INBOX_FOLDER
    )
    assert cursor_final is not None
    assert cursor_final.backfill_completed is True
