"""E2e: mail inbound → file_id → Files download; send rejects raw content."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from core.mail.models import InboundMailMessage, MailAttachment
from core.mail.repositories import INBOX_FOLDER
from core.mail.service import MailService
from core.models.identity_models import Company, User
from core.types import JsonObject, require_json_array, require_json_object
from core.utils.tokens import get_token_service
from tests.core.mail.complete_client_helpers import seed_connected_user_binding
from tests.core.mail.fakes import RecordingMailServerPort
from tests.files.chunked_upload_helpers import (
    chunked_upload_file,
    platform_auxiliary_upload_spec_json,
)

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
    container = frontend_app.state.container
    previous = container.__dict__.get("_cached_mail_service")
    container.__dict__["_cached_mail_service"] = mail_service
    yield mail_service
    if previous is None:
        container.__dict__.pop("_cached_mail_service", None)
    else:
        container.__dict__["_cached_mail_service"] = previous


@pytest.mark.asyncio
async def test_inbound_attachment_file_id_download(
    frontend_client: AsyncClient,
    inject_mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    unique_id: str,
) -> None:
    mail_service = inject_mail_service
    company_id, user_id, binding = await seed_connected_user_binding(
        mail_service,
        mail_member_context,
        recording_mail_port,
        unique_id=unique_id,
        prefix="mailfid",
    )
    headers = _auth_headers(user_id=user_id, company_id=company_id)
    payload_bytes = f"mail-att-{unique_id}".encode("utf-8")
    recording_mail_port.inbox = [
        InboundMailMessage(
            uid="41",
            message_id=f"<mail-fid-{unique_id}@example.com>",
            subject=f"fid-{unique_id}",
            from_address="peer@example.com",
            to_addresses=[binding.email_address],
            body_text="see file",
            attachments=[
                MailAttachment(
                    filename="report.txt",
                    content_type="text/plain",
                    content=payload_bytes,
                    size=len(payload_bytes),
                    available=True,
                )
            ],
        )
    ]
    _ = await mail_service.sync_binding(binding, max_new_messages=20)

    opened = await mail_service.get_message(
        mailbox_binding_id=binding.mailbox_binding_id,
        uid="41",
        folder=INBOX_FOLDER,
        company_id=company_id,
    )
    assert len(opened.attachments) == 1
    attachment = opened.attachments[0]
    assert attachment.file_id is not None
    assert attachment.available is True
    assert "content_base64" not in attachment.model_dump()

    get_resp = await frontend_client.get(
        "/frontend/api/mail/messages/41",
        headers=headers,
        params={
            "mailbox_binding_id": binding.mailbox_binding_id,
            "folder": INBOX_FOLDER,
        },
    )
    assert get_resp.status_code == 200, get_resp.text
    response_payload = require_json_object(get_resp.json(), "get_mail_message")
    api_attachments = require_json_array(response_payload["attachments"], "attachments")
    assert len(api_attachments) == 1
    api_attachment = require_json_object(api_attachments[0], "attachment")
    assert api_attachment["file_id"] == attachment.file_id
    assert "content_base64" not in api_attachment

    download = await frontend_client.get(
        f"/frontend/api/v1/files/download/{attachment.file_id}",
        headers=headers,
    )
    assert download.status_code == 200, download.text
    assert download.content == payload_bytes


@pytest.mark.asyncio
async def test_send_rejects_content_without_file_id(
    frontend_client: AsyncClient,
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
        prefix="mailrej",
    )
    headers = _auth_headers(user_id=user_id, company_id=company_id)

    reject = await frontend_client.post(
        "/frontend/api/mail/messages/send",
        headers=headers,
        json={
            "mailbox_binding_id": binding.mailbox_binding_id,
            "to_addresses": ["peer@example.com"],
            "subject": "no-file-id",
            "body_text": "x",
            "attachments": [
                {
                    "filename": "raw.txt",
                    "content_type": "text/plain",
                    "content": "cmF3",
                }
            ],
        },
    )
    assert reject.status_code == 422, reject.text

    reject_base64 = await frontend_client.post(
        "/frontend/api/mail/messages/send",
        headers=headers,
        json={
            "mailbox_binding_id": binding.mailbox_binding_id,
            "to_addresses": ["peer@example.com"],
            "subject": "no-file-id-b64",
            "body_text": "x",
            "attachments": [
                {
                    "filename": "raw.txt",
                    "content_type": "text/plain",
                    "content_base64": "cmF3",
                }
            ],
        },
    )
    assert reject_base64.status_code == 422, reject_base64.text

    upload = await chunked_upload_file(
        frontend_client,
        headers,
        content=b"ok-via-chunked",
        original_name="ok.txt",
        content_type="text/plain",
        spec_json=platform_auxiliary_upload_spec_json(),
        files_api_prefix="/frontend/api/v1/files",
    )
    assert upload.status_code == 200, upload.text
    upload_payload = require_json_object(upload.json(), "chunked_upload_complete")
    file_id = upload_payload["file_id"]
    if not isinstance(file_id, str) or file_id.strip() == "":
        raise AssertionError("chunked upload must return file_id")

    enqueued: list[JsonObject] = []

    async def _capture_send(*, company_id: str, payload: JsonObject) -> None:
        _ = company_id
        enqueued.append(payload)

    monkeypatch.setattr("core.api.mail.enqueue_mail_send", _capture_send)

    ok = await frontend_client.post(
        "/frontend/api/mail/messages/send",
        headers=headers,
        json={
            "mailbox_binding_id": binding.mailbox_binding_id,
            "to_addresses": ["peer@example.com"],
            "subject": "with-file-id",
            "body_text": "ok",
            "attachments": [
                {
                    "filename": "ok.txt",
                    "content_type": "text/plain",
                    "file_id": file_id,
                }
            ],
        },
    )
    assert ok.status_code == 200, ok.text
    assert len(enqueued) == 1
    send_attachments = require_json_array(enqueued[0]["attachments"], "send.attachments")
    send_attachment = require_json_object(send_attachments[0], "send.attachment")
    assert send_attachment["file_id"] == file_id
