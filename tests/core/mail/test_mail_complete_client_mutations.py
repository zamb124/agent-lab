"""Offline integration: triage mutations + optimistic local + draft/send."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from pydantic import ValidationError

from core.mail.models import (
    INBOX_FOLDER,
    MailAttachment,
    MailDraftSavePayload,
    MailMessageFlagPayload,
    MailMessageListPayload,
    MailMessageMovePayload,
    MailMessageStarPayload,
    MailSendPayload,
    StoredMailMessage,
)
from core.mail.service import MailService
from core.models.identity_models import Company, User
from tests.core.mail.complete_client_helpers import (
    inbox_message,
    seed_connected_user_binding,
)
from tests.core.mail.fakes import RecordingMailServerPort

MailMemberSeed = Callable[..., Awaitable[tuple[Company, User]]]


@pytest.mark.asyncio
async def test_move_updates_local_and_imap(
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
        prefix="move",
    )
    recording_mail_port.inbox = [
        inbox_message(uid="11", unique_id=unique_id, subject="to-archive"),
    ]
    _ = await mail_service.sync_binding(binding, max_new_messages=50)
    moved = await mail_service.move_message(
        MailMessageMovePayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid="11",
            destination_folder="Archive",
        ),
        company_id=company_id,
    )
    assert moved.destination_folder == "Archive"
    assert moved.destination_uid is not None
    assert (INBOX_FOLDER, "11", "Archive") in recording_mail_port.uid_move_calls
    assert (
        await StoredMailMessage.by_binding_folder_uid(
            binding.mailbox_binding_id, folder=INBOX_FOLDER, uid=11
        )
        is None
    )
    archived = await StoredMailMessage.by_binding_folder_uid(
        binding.mailbox_binding_id, folder="Archive", uid=int(moved.destination_uid)
    )
    assert archived is not None
    assert archived.subject == "to-archive"


@pytest.mark.asyncio
async def test_trash_archive_delete_star_roundtrip(
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
        prefix="triage",
    )
    recording_mail_port.inbox = [
        inbox_message(uid="21", unique_id=unique_id, subject="trash-me"),
        inbox_message(uid="22", unique_id=unique_id, subject="archive-me"),
        inbox_message(uid="23", unique_id=unique_id, subject="delete-me"),
        inbox_message(uid="24", unique_id=unique_id, subject="star-me"),
    ]
    _ = await mail_service.sync_binding(binding, max_new_messages=50)

    trash = await mail_service.trash_message(
        MailMessageFlagPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid="21",
        ),
        company_id=company_id,
    )
    assert trash.destination_folder == "Trash"
    assert (INBOX_FOLDER, "21", "Trash") in recording_mail_port.uid_move_calls

    archive = await mail_service.archive_message(
        MailMessageFlagPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid="22",
        ),
        company_id=company_id,
    )
    assert archive.destination_folder == "Archive"
    assert (INBOX_FOLDER, "22", "Archive") in recording_mail_port.uid_move_calls

    delete = await mail_service.delete_message(
        MailMessageFlagPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid="23",
        ),
        company_id=company_id,
    )
    assert delete.uid == "23"
    assert (INBOX_FOLDER, "23") in recording_mail_port.uid_expunge_calls
    assert (
        await StoredMailMessage.by_binding_folder_uid(
            binding.mailbox_binding_id, folder=INBOX_FOLDER, uid=23
        )
        is None
    )

    star = await mail_service.star_message(
        MailMessageStarPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid="24",
            flagged=True,
        ),
        company_id=company_id,
    )
    assert star.flagged is True
    assert any(
        mailbox == INBOX_FOLDER and uid == "24" and "\\Flagged" in add_flags
        for mailbox, uid, add_flags, _remove in recording_mail_port.uid_store_flags_calls
    )
    starred = await StoredMailMessage.by_binding_folder_uid(
        binding.mailbox_binding_id, folder=INBOX_FOLDER, uid=24
    )
    assert starred is not None
    assert starred.flagged is True

    unstar = await mail_service.star_message(
        MailMessageStarPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid="24",
            flagged=False,
        ),
        company_id=company_id,
    )
    assert unstar.flagged is False
    unstarred = await StoredMailMessage.by_binding_folder_uid(
        binding.mailbox_binding_id, folder=INBOX_FOLDER, uid=24
    )
    assert unstarred is not None
    assert unstarred.flagged is False


@pytest.mark.asyncio
async def test_draft_save_append_replace_and_list_in_drafts(
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
        prefix="draft",
    )
    saved = await mail_service.save_draft(
        MailDraftSavePayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            to_addresses=["peer@example.com"],
            subject="draft subject",
            body_text="draft body",
        ),
        company_id=company_id,
    )
    assert saved.folder == "Drafts"
    assert saved.uid
    assert ("Drafts", r"(\Draft \Seen)") in recording_mail_port.append_message_calls
    drafts = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="Drafts",
            limit=50,
        ),
        company_id=company_id,
    )
    assert any(item.subject == "draft subject" for item in drafts.items)

    replaced = await mail_service.save_draft(
        MailDraftSavePayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            to_addresses=["peer@example.com"],
            subject="draft subject v2",
            body_text="draft body v2",
            uid=saved.uid,
        ),
        company_id=company_id,
    )
    assert replaced.folder == "Drafts"
    assert ("Drafts", saved.uid) in recording_mail_port.uid_expunge_calls
    assert len(recording_mail_port.append_message_calls) >= 2
    drafts2 = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="Drafts",
            limit=50,
        ),
        company_id=company_id,
    )
    subjects = {item.subject for item in drafts2.items}
    assert "draft subject v2" in subjects
    assert "draft subject" not in subjects


@pytest.mark.asyncio
async def test_prepare_send_local_creates_temp_sent_then_send_completes(
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
        prefix="send",
    )
    enqueued_syncs: list[str] = []

    async def _fake_enqueue_sync(*, company_id: str, mailbox_binding_id: str) -> None:
        _ = company_id
        enqueued_syncs.append(mailbox_binding_id)

    monkeypatch.setattr(
        "core.mail.service.enqueue_mail_sync_binding",
        _fake_enqueue_sync,
    )
    message_id = f"<send-{unique_id}@example.com>"
    prepared = await mail_service.prepare_send_local(
        MailSendPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            to_addresses=["peer@example.com"],
            subject="outbound",
            body_text="hello",
            message_id=message_id,
        ),
        company_id=company_id,
    )
    assert prepared.message_id == message_id
    assert prepared.accepted == ["peer@example.com"]
    sent_rows = await StoredMailMessage.list_for_folder_by_date_at_and_uid_desc(
        binding.mailbox_binding_id,
        folder="Sent",
        limit=50,
    )
    temps = [msg for msg in sent_rows if msg.uid < 0]
    assert len(temps) == 1
    assert temps[0].subject == "outbound"

    sent = await mail_service.send_message(
        MailSendPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            to_addresses=["peer@example.com"],
            subject="outbound-direct",
            body_text="hello2",
            message_id=f"<send-direct-{unique_id}@example.com>",
        ),
        company_id=company_id,
    )
    assert sent.message_id
    assert len(recording_mail_port.sent) >= 1
    assert any(folder == "Sent" for _email, folder in recording_mail_port.append_sent_calls)
    assert enqueued_syncs == [binding.mailbox_binding_id]


@pytest.mark.asyncio
async def test_send_rejects_attachment_without_file_id(
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
        prefix="attach",
    )
    _ = company_id
    with pytest.raises(ValidationError, match="file_id"):
        _ = MailSendPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            to_addresses=["peer@example.com"],
            subject="bad",
            body_text="x",
            attachments=[
                MailAttachment(
                    filename="empty.txt",
                    content_type="text/plain",
                    content=b"",
                )
            ],
        )
    with pytest.raises(ValidationError, match="file_id|content"):
        _ = MailSendPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            to_addresses=["peer@example.com"],
            subject="bad",
            body_text="x",
            attachments=[
                MailAttachment(
                    filename="raw.txt",
                    content_type="text/plain",
                    content=b"raw-bytes",
                )
            ],
        )
