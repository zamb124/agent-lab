"""TaskIQ mutation path: worker handlers + IMAP RecordingPort + send_failed push."""


from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from apps.idle.tasks.mail_mutation_tasks import (
    mail_send_task,
    mail_star_task,
    mail_trash_task,
)
from core.mail.models import (
    INBOX_FOLDER,
    MailMessageFlagPayload,
    MailMessageMovePayload,
    MailMessageStarPayload,
    StoredMailMessage,
)
from core.mail.service import MailService
from core.models.identity_models import Company, User
from core.types import JsonObject
from tests.core.mail.complete_client_helpers import (
    inbox_message,
    seed_connected_user_binding,
)
from tests.core.mail.fakes import RecordingMailServerPort

MailMemberSeed = Callable[..., Awaitable[tuple[Company, User]]]


def _bind_recording_port(
    mail_service: MailService,
    port: RecordingMailServerPort,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mail_service, "_port_for", lambda _connection: port)


@pytest.mark.asyncio
async def test_mail_trash_task_moves_on_imap(
    recording_mail_port: RecordingMailServerPort,
    di,
    mail_member_context: MailMemberSeed,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mail_service = di.mail_service
    _bind_recording_port(mail_service, recording_mail_port, monkeypatch)
    company_id, _user_id, binding = await seed_connected_user_binding(
        mail_service,
        mail_member_context,
        recording_mail_port,
        unique_id=unique_id,
        prefix="tqi",
    )
    recording_mail_port.inbox = [
        inbox_message(uid="11", unique_id=unique_id, subject="taskiq-trash"),
    ]
    _ = await mail_service.sync_binding(binding, max_new_messages=50)
    _ = await mail_service.move_message_local(
        MailMessageMovePayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid="11",
            destination_folder="Trash",
        ),
        company_id=company_id,
    )
    recording_mail_port.inbox = [
        inbox_message(uid="11", unique_id=unique_id, subject="taskiq-trash"),
    ]

    pushes: list[tuple[str, str, JsonObject]] = []

    async def _fake_publish(
        user_ids: list[str],
        event_type: str,
        payload: JsonObject,
        **_kwargs: object,
    ) -> None:
        for user_id in user_ids:
            pushes.append((user_id, event_type, payload))

    monkeypatch.setattr(
        "apps.idle.tasks.mail_mutation_tasks.publish_event_to_users",
        _fake_publish,
    )
    await mail_trash_task(
        company_id=company_id,
        payload=MailMessageFlagPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid="11",
        ).model_dump(mode="json"),
        di=di,
    )
    assert (INBOX_FOLDER, "11", "Trash") in recording_mail_port.uid_move_calls
    assert any(event_type == "mail/message/moved" for _uid, event_type, _p in pushes)


@pytest.mark.asyncio
async def test_mail_star_task_stores_flags(
    recording_mail_port: RecordingMailServerPort,
    di,
    mail_member_context: MailMemberSeed,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mail_service = di.mail_service
    _bind_recording_port(mail_service, recording_mail_port, monkeypatch)
    company_id, _user_id, binding = await seed_connected_user_binding(
        mail_service,
        mail_member_context,
        recording_mail_port,
        unique_id=unique_id,
        prefix="tqistar",
    )
    recording_mail_port.inbox = [
        inbox_message(uid="22", unique_id=unique_id, subject="taskiq-star"),
    ]
    _ = await mail_service.sync_binding(binding, max_new_messages=50)

    await mail_star_task(
        company_id=company_id,
        payload=MailMessageStarPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid="22",
            flagged=True,
        ).model_dump(mode="json"),
        di=di,
    )
    assert any(
        mailbox == INBOX_FOLDER and uid == "22" and "\\Flagged" in add_flags
        for mailbox, uid, add_flags, _remove in recording_mail_port.uid_store_flags_calls
    )
    stored = await StoredMailMessage.by_binding_folder_uid(
        binding.mailbox_binding_id, folder=INBOX_FOLDER, uid=22
    )
    assert stored is not None
    assert stored.flagged is True


@pytest.mark.asyncio
async def test_mail_send_task_failure_publishes_send_failed(
    recording_mail_port: RecordingMailServerPort,
    di,
    mail_member_context: MailMemberSeed,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mail_service = di.mail_service
    _bind_recording_port(mail_service, recording_mail_port, monkeypatch)
    company_id, user_id, binding = await seed_connected_user_binding(
        mail_service,
        mail_member_context,
        recording_mail_port,
        unique_id=unique_id,
        prefix="tqisend",
    )

    async def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("smtp down")

    monkeypatch.setattr(mail_service, "send_message", _boom)
    pushes: list[tuple[str, str, JsonObject]] = []

    async def _fake_publish(
        user_ids: list[str],
        event_type: str,
        payload: JsonObject,
        **_kwargs: object,
    ) -> None:
        for uid in user_ids:
            pushes.append((uid, event_type, payload))

    monkeypatch.setattr(
        "apps.idle.tasks.mail_mutation_tasks.publish_event_to_users",
        _fake_publish,
    )

    with pytest.raises(RuntimeError, match="smtp down"):
        await mail_send_task(
            company_id=company_id,
            payload={
                "mailbox_binding_id": binding.mailbox_binding_id,
                "to_addresses": ["peer@example.com"],
                "subject": "fail",
                "body_text": "x",
                "message_id": f"<fail-{unique_id}@example.com>",
            },
            di=di,
        )
    assert any(
        uid == user_id and event_type == "mail/message/send_failed"
        for uid, event_type, _payload in pushes
    )
