"""HTTP API зеркала complete mail client (frontend /frontend/api/mail)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from apps.frontend.di import FrontendDi
from core.di import require_di
from core.mail.models import (
    INBOX_FOLDER,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    StoredMailMessage,
)
from core.mail.service import MailService
from core.models.identity_models import Company, User
from core.types import JsonObject
from core.utils.tokens import get_token_service
from tests.core.mail.complete_client_helpers import (
    inbox_message,
    seed_connected_user_binding,
)
from tests.core.mail.fakes import RecordingMailServerPort

MailMemberSeed = Callable[..., Awaitable[tuple[Company, User]]]


def _auth_headers(*, user_id: str, company_id: str) -> dict[str, str]:
    token = get_token_service().create_token(
        user_id,
        company_id=company_id,
        roles=["owner", "admin"],
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def inject_mail_service(frontend_app, mail_service: MailService):
    di = require_di(frontend_app, FrontendDi)
    previous = di.mail_service
    object.__setattr__(di, "mail_service", mail_service)
    yield mail_service
    object.__setattr__(di, "mail_service", previous)


@pytest.mark.asyncio
async def test_api_sync_search_triage_and_members(
    frontend_client,
    inject_mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mail_service = inject_mail_service
    company_id, user_id, binding = await seed_connected_user_binding(
        mail_service,
        mail_member_context,
        recording_mail_port,
        unique_id=unique_id,
        prefix="api",
    )
    headers = _auth_headers(user_id=user_id, company_id=company_id)
    recording_mail_port.inbox = [
        inbox_message(uid="1", unique_id=unique_id, subject="api-invoice"),
        inbox_message(uid="2", unique_id=unique_id, subject="api-other"),
        inbox_message(uid="3", unique_id=unique_id, subject="api-star"),
    ]
    _ = await mail_service.sync_binding(binding, max_new_messages=50)

    enqueued: list[tuple[str, str]] = []

    async def _capture_enqueue(*, company_id: str, mailbox_binding_id: str) -> None:
        enqueued.append((company_id, mailbox_binding_id))

    async def _capture_mutation(*, company_id: str, payload: JsonObject) -> None:
        _ = company_id
        _ = payload

    monkeypatch.setattr("core.mail.service.enqueue_mail_sync_binding", _capture_enqueue)
    monkeypatch.setattr("core.api.mail.enqueue_mail_trash", _capture_mutation)
    monkeypatch.setattr("core.api.mail.enqueue_mail_archive", _capture_mutation)
    monkeypatch.setattr("core.api.mail.enqueue_mail_delete", _capture_mutation)
    monkeypatch.setattr("core.api.mail.enqueue_mail_star", _capture_mutation)
    monkeypatch.setattr("core.api.mail.enqueue_mail_move", _capture_mutation)

    sync_resp = await frontend_client.post(
        "/frontend/api/mail/sync",
        headers=headers,
        json={"mailbox_binding_id": binding.mailbox_binding_id},
    )
    assert sync_resp.status_code == 200, sync_resp.text
    assert sync_resp.json()["accepted"] is True
    assert enqueued == [(company_id, binding.mailbox_binding_id)]

    search_resp = await frontend_client.post(
        "/frontend/api/mail/messages/search",
        headers=headers,
        json={
            "mailbox_binding_id": binding.mailbox_binding_id,
            "q": "invoice",
            "folder": INBOX_FOLDER,
            "limit": 20,
        },
    )
    assert search_resp.status_code == 200, search_resp.text
    assert {item["uid"] for item in search_resp.json()["items"]} == {"1"}

    trash_resp = await frontend_client.post(
        "/frontend/api/mail/messages/trash",
        headers=headers,
        json={
            "mailbox_binding_id": binding.mailbox_binding_id,
            "folder": INBOX_FOLDER,
            "uid": "1",
        },
    )
    assert trash_resp.status_code == 200, trash_resp.text
    assert trash_resp.json()["destination_folder"] == "Trash"
    assert (
        await StoredMailMessage.by_binding_folder_uid(
            binding.mailbox_binding_id, folder=INBOX_FOLDER, uid=1
        )
        is None
    )

    archive_resp = await frontend_client.post(
        "/frontend/api/mail/messages/archive",
        headers=headers,
        json={
            "mailbox_binding_id": binding.mailbox_binding_id,
            "folder": INBOX_FOLDER,
            "uid": "2",
        },
    )
    assert archive_resp.status_code == 200, archive_resp.text
    assert archive_resp.json()["destination_folder"] == "Archive"

    star_resp = await frontend_client.post(
        "/frontend/api/mail/messages/star",
        headers=headers,
        json={
            "mailbox_binding_id": binding.mailbox_binding_id,
            "folder": INBOX_FOLDER,
            "uid": "3",
            "flagged": True,
        },
    )
    assert star_resp.status_code == 200, star_resp.text
    assert star_resp.json()["flagged"] is True
    starred = await StoredMailMessage.by_binding_folder_uid(
        binding.mailbox_binding_id, folder=INBOX_FOLDER, uid=3
    )
    assert starred is not None
    assert starred.flagged is True

    recording_mail_port.inbox.append(
        inbox_message(uid="4", unique_id=unique_id, subject="api-delete")
    )
    _ = await mail_service.sync_binding(binding, max_new_messages=50)
    delete_resp = await frontend_client.post(
        "/frontend/api/mail/messages/delete",
        headers=headers,
        json={
            "mailbox_binding_id": binding.mailbox_binding_id,
            "folder": INBOX_FOLDER,
            "uid": "4",
        },
    )
    assert delete_resp.status_code == 200, delete_resp.text
    assert (
        await StoredMailMessage.by_binding_folder_uid(
            binding.mailbox_binding_id, folder=INBOX_FOLDER, uid=4
        )
        is None
    )

    move_resp = await frontend_client.post(
        "/frontend/api/mail/messages/move",
        headers=headers,
        json={
            "mailbox_binding_id": binding.mailbox_binding_id,
            "folder": INBOX_FOLDER,
            "uid": "3",
            "destination_folder": "Archive",
        },
    )
    assert move_resp.status_code == 200, move_resp.text
    assert move_resp.json()["destination_folder"] == "Archive"

    draft_resp = await frontend_client.post(
        "/frontend/api/mail/messages/drafts",
        headers=headers,
        json={
            "mailbox_binding_id": binding.mailbox_binding_id,
            "to_addresses": ["peer@example.com"],
            "subject": "api-draft",
            "body_text": "draft body",
        },
    )
    assert draft_resp.status_code == 200, draft_resp.text
    assert draft_resp.json()["folder"] == "Drafts"
    assert ("Drafts", r"(\Draft \Seen)") in recording_mail_port.append_message_calls

    role_binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.ROLE,
            user_id=None,
            local_part=f"apirole{unique_id[:6]}",
            password="mailbox-pass",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    member_user_id = f"apimember_{unique_id}"
    add_member = await frontend_client.post(
        f"/frontend/api/mail/bindings/{role_binding.mailbox_binding_id}/members",
        headers=headers,
        json={"user_id": member_user_id, "role": "member"},
    )
    assert add_member.status_code == 200, add_member.text
    list_members = await frontend_client.get(
        f"/frontend/api/mail/bindings/{role_binding.mailbox_binding_id}/members",
        headers=headers,
    )
    assert list_members.status_code == 200, list_members.text
    assert any(
        item["user_id"] == member_user_id for item in list_members.json()["items"]
    )
