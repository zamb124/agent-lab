"""Строгие live-тесты personal IMAP/SMTP (Mail.ru A↔B) без provision/delete ящиков."""

from __future__ import annotations

from contextlib import suppress

import pytest

from core.config.models import MailConfig, MailLivePersonalConfig
from core.context import set_context
from core.mail.exceptions import MailError, MailTransportError
from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    MailAttachment,
    MailboxBinding,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailboxSecret,
    MailConnectionScope,
    MailDraftSavePayload,
    MailFolderRole,
    MailMessageFlagPayload,
    MailMessageListItem,
    MailMessageListPayload,
    MailMessageSearchPayload,
    MailMessageStarPayload,
    MailProvider,
    MailSendPayload,
    MailSyncNowPayload,
    MailThreadPayload,
    OutboundMailMessage,
    PersonalMailboxConnectPayload,
    PersonalMailboxHealthcheckPayload,
)
from core.mail.ports import MailServerPort
from core.mail.repositories import INBOX_FOLDER
from core.mail.service import MailService
from core.models.context_models import Context
from core.models.identity_models import Company, User
from tests.core.mail.live.poll import poll_fetch_message

pytestmark = [pytest.mark.network, pytest.mark.timeout(240)]

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _find_local_by_subject(
    service: MailService,
    binding: MailboxBinding,
    *,
    subject: str,
    folder: str = INBOX_FOLDER,
    company_id: str,
) -> MailMessageListItem:
    listed = await service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=folder,
            limit=50,
        ),
        company_id=company_id,
    )
    matched = next((item for item in listed.items if item.subject == subject), None)
    if matched is None:
        raise AssertionError(f"local message subject={subject!r} not found in {folder}")
    return matched


@pytest.mark.asyncio
async def test_personal_healthcheck_a_and_b(
    mail_personal_service: MailService,
    mail_personal_cfg: MailLivePersonalConfig,
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_personal_company_ctx: tuple[str, str, Company, User],
) -> None:
    company_id, _user_id, company, user = mail_personal_company_ctx
    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )
    secret_a, secret_b = mail_personal_pair
    for secret in (secret_a, secret_b):
        health = await mail_personal_service.healthcheck_personal_credentials(
            PersonalMailboxHealthcheckPayload(
                email_address=secret.email_address,
                password=secret.password,
                imap_host=mail_personal_cfg.imap_host,
                imap_port=mail_personal_cfg.imap_port,
                smtp_host=mail_personal_cfg.smtp_host,
                smtp_port=mail_personal_cfg.smtp_port,
                use_ssl=mail_personal_cfg.use_ssl,
            )
        )
        assert health.imap_ok is True, f"imap_ok failed for {secret.email_address}"
        assert health.smtp_ok is True, f"smtp_ok failed for {secret.email_address}"
    _ = company_id


@pytest.mark.asyncio
async def test_personal_connect_scope_and_candidates(
    mail_personal_service: MailService,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
) -> None:
    company_id, binding_a, binding_b = mail_personal_bindings
    conn_a = await mail_personal_service._connection_for_binding(binding_a)
    conn_b = await mail_personal_service._connection_for_binding(binding_b)
    assert conn_a is not None and conn_a.scope == MailConnectionScope.PERSONAL
    assert conn_b is not None and conn_b.scope == MailConnectionScope.PERSONAL
    assert binding_a.is_default is True
    assert binding_b.is_default is False
    candidates = await mail_personal_service.list_sync_candidates(
        limit=100,
        auth_error_cooldown_seconds=0,
    )
    ids = {item.mailbox_binding_id for item in candidates}
    assert binding_a.mailbox_binding_id in ids
    assert binding_b.mailbox_binding_id in ids
    _ = company_id


@pytest.mark.asyncio
async def test_personal_folders_ensure(
    mail_personal_service: MailService,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
) -> None:
    company_id, binding_a, _binding_b = mail_personal_bindings
    folders = await mail_personal_service.ensure_standard_folders(
        binding_a.mailbox_binding_id,
        company_id=company_id,
    )
    by_role = {folder.role: folder for folder in folders.folders if folder.selectable}
    for role in (
        MailFolderRole.INBOX,
        MailFolderRole.SENT,
        MailFolderRole.DRAFTS,
        MailFolderRole.TRASH,
    ):
        assert role in by_role, f"selectable folder role={role} missing"


@pytest.mark.asyncio
async def test_personal_a_to_b_plain(
    mail_personal_service: MailService,
    mail_personal_port: MailServerPort,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_subject_marker: str,
) -> None:
    company_id, binding_a, binding_b = mail_personal_bindings
    secret_a, secret_b = mail_personal_pair
    subject = f"{mail_subject_marker}-plain"
    message_id = f"<plt-pers-plain-{mail_subject_marker}@mail.ru>"
    body = f"plain-body-{mail_subject_marker}"
    send_result = await mail_personal_port.send_message(
        secret_a,
        OutboundMailMessage(
            to_addresses=[binding_b.email_address],
            subject=subject,
            body_text=body,
            message_id=message_id,
        ),
    )
    assert binding_b.email_address in send_result.accepted
    found = await poll_fetch_message(
        mail_personal_port,
        secret_b,
        message_id=message_id,
        subject=subject,
    )
    assert found is not None
    assert found.subject == subject
    synced = await mail_personal_service.sync_binding(binding_b, max_new_messages=50)
    assert synced.skipped_reason is None
    local = await _find_local_by_subject(
        mail_personal_service,
        binding_b,
        subject=subject,
        company_id=company_id,
    )
    assert local.from_address is not None
    assert binding_a.email_address in local.from_address.lower()
    assert binding_b.email_address in {addr.lower() for addr in local.to_addresses}
    detail = await mail_personal_service.get_message(
        mailbox_binding_id=binding_b.mailbox_binding_id,
        uid=local.uid,
        folder=INBOX_FOLDER,
        company_id=company_id,
    )
    assert detail.body_text is not None
    assert body in detail.body_text


@pytest.mark.asyncio
async def test_personal_b_to_a_reply_thread(
    mail_personal_service: MailService,
    mail_personal_port: MailServerPort,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_subject_marker: str,
) -> None:
    company_id, binding_a, binding_b = mail_personal_bindings
    secret_a, secret_b = mail_personal_pair
    parent_subject = f"{mail_subject_marker}-parent"
    parent_id = f"<plt-pers-parent-{mail_subject_marker}@mail.ru>"
    _ = await mail_personal_port.send_message(
        secret_a,
        OutboundMailMessage(
            to_addresses=[binding_b.email_address],
            subject=parent_subject,
            body_text="parent",
            message_id=parent_id,
        ),
    )
    parent = await poll_fetch_message(
        mail_personal_port, secret_b, message_id=parent_id, subject=parent_subject
    )
    assert parent is not None
    parent_message_id = parent.message_id if parent.message_id else parent_id
    reply_subject = f"Re: {parent_subject}"
    reply_id = f"<plt-pers-reply-{mail_subject_marker}@mail.ru>"
    _ = await mail_personal_port.send_message(
        secret_b,
        OutboundMailMessage(
            to_addresses=[binding_a.email_address],
            subject=reply_subject,
            body_text="reply",
            message_id=reply_id,
            in_reply_to=parent_message_id,
            references=parent_message_id,
        ),
    )
    reply = await poll_fetch_message(
        mail_personal_port, secret_a, message_id=reply_id, subject=reply_subject
    )
    assert reply is not None
    assert reply.in_reply_to == parent_message_id or (
        reply.references is not None and parent_message_id in reply.references
    )
    _ = await mail_personal_service.sync_binding(binding_a, max_new_messages=50)
    _ = await mail_personal_service.sync_binding(binding_b, max_new_messages=50)
    local_reply = await _find_local_by_subject(
        mail_personal_service,
        binding_a,
        subject=reply_subject,
        company_id=company_id,
    )
    assert local_reply.in_reply_to == parent_message_id or (
        local_reply.references is not None and parent_message_id in local_reply.references
    )
    thread = await mail_personal_service.get_thread(
        MailThreadPayload(
            mailbox_binding_id=binding_a.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid=local_reply.uid,
        ),
        company_id=company_id,
    )
    assert any(item.uid == local_reply.uid for item in thread.items)
    assert len(thread.items) >= 1


@pytest.mark.asyncio
async def test_personal_attachment_txt(
    mail_personal_port: MailServerPort,
    mail_personal_service: MailService,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_subject_marker: str,
) -> None:
    company_id, _binding_a, binding_b = mail_personal_bindings
    secret_a, secret_b = mail_personal_pair
    subject = f"{mail_subject_marker}-attach-txt"
    message_id = f"<plt-pers-att-{mail_subject_marker}@mail.ru>"
    payload = f"attach-{mail_subject_marker}".encode("utf-8")
    filename = f"note-{mail_subject_marker}.txt"
    _ = await mail_personal_port.send_message(
        secret_a,
        OutboundMailMessage(
            to_addresses=[binding_b.email_address],
            subject=subject,
            body_text="with txt",
            message_id=message_id,
            attachments=[
                MailAttachment(
                    filename=filename,
                    content_type="text/plain",
                    content=payload,
                )
            ],
        ),
    )
    found = await poll_fetch_message(
        mail_personal_port, secret_b, message_id=message_id, subject=subject
    )
    assert found is not None
    matched = next(
        (item for item in found.attachments if item.filename == filename),
        None,
    )
    assert matched is not None
    assert matched.content == payload
    synced = await mail_personal_service.sync_binding(binding_b, max_new_messages=50)
    assert synced.skipped_reason is None
    local = await _find_local_by_subject(
        mail_personal_service,
        binding_b,
        subject=subject,
        company_id=company_id,
    )
    assert local.attachment_count >= 1
    detail = await mail_personal_service.get_message(
        mailbox_binding_id=binding_b.mailbox_binding_id,
        uid=local.uid,
        folder=INBOX_FOLDER,
        company_id=company_id,
    )
    assert any(item.filename == filename for item in detail.attachments)
    assert any(item.size == len(payload) for item in detail.attachments)


@pytest.mark.asyncio
async def test_personal_multi_attach(
    mail_personal_port: MailServerPort,
    mail_personal_service: MailService,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_subject_marker: str,
) -> None:
    company_id, binding_a, binding_b = mail_personal_bindings
    secret_a, secret_b = mail_personal_pair
    subject = f"{mail_subject_marker}-multi"
    message_id = f"<plt-pers-multi-{mail_subject_marker}@mail.ru>"
    txt_payload = f"multi-{mail_subject_marker}".encode("utf-8")
    txt_name = f"a-{mail_subject_marker}.txt"
    png_name = f"dot-{mail_subject_marker}.png"
    _ = await mail_personal_port.send_message(
        secret_a,
        OutboundMailMessage(
            to_addresses=[binding_b.email_address],
            subject=subject,
            body_text="multi",
            message_id=message_id,
            attachments=[
                MailAttachment(
                    filename=txt_name,
                    content_type="text/plain",
                    content=txt_payload,
                ),
                MailAttachment(
                    filename=png_name,
                    content_type="image/png",
                    content=_TINY_PNG,
                ),
            ],
        ),
    )
    found = await poll_fetch_message(
        mail_personal_port, secret_b, message_id=message_id, subject=subject
    )
    assert found is not None
    by_name = {item.filename: item for item in found.attachments}
    assert txt_name in by_name
    assert png_name in by_name
    assert by_name[txt_name].content == txt_payload
    assert by_name[png_name].content == _TINY_PNG
    assert len(by_name[txt_name].content) == len(txt_payload)
    assert len(by_name[png_name].content) == len(_TINY_PNG)
    _ = await mail_personal_service.sync_binding(binding_b, max_new_messages=50)
    local = await _find_local_by_subject(
        mail_personal_service,
        binding_b,
        subject=subject,
        company_id=company_id,
    )
    assert local.attachment_count >= 2
    _ = binding_a


@pytest.mark.asyncio
async def test_personal_unicode_roundtrip(
    mail_personal_port: MailServerPort,
    mail_personal_service: MailService,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_subject_marker: str,
) -> None:
    company_id, _binding_a, binding_b = mail_personal_bindings
    secret_a, secret_b = mail_personal_pair
    subject = f"{mail_subject_marker}-письмо-проверка"
    body = f"Кириллица body {mail_subject_marker}"
    message_id = f"<plt-pers-ru-{mail_subject_marker}@mail.ru>"
    _ = await mail_personal_port.send_message(
        secret_a,
        OutboundMailMessage(
            to_addresses=[binding_b.email_address],
            subject=subject,
            body_text=body,
            message_id=message_id,
        ),
    )
    found = await poll_fetch_message(
        mail_personal_port, secret_b, message_id=message_id, subject=subject
    )
    assert found is not None
    assert found.subject == subject
    assert found.body_text is not None
    assert mail_subject_marker in found.body_text
    _ = await mail_personal_service.sync_binding(binding_b, max_new_messages=50)
    local = await _find_local_by_subject(
        mail_personal_service,
        binding_b,
        subject=subject,
        company_id=company_id,
    )
    detail = await mail_personal_service.get_message(
        mailbox_binding_id=binding_b.mailbox_binding_id,
        uid=local.uid,
        folder=INBOX_FOLDER,
        company_id=company_id,
    )
    assert detail.subject == subject
    assert detail.body_text is not None
    assert mail_subject_marker in detail.body_text


@pytest.mark.asyncio
async def test_personal_sync_incremental(
    mail_personal_port: MailServerPort,
    mail_personal_service: MailService,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_subject_marker: str,
) -> None:
    company_id, binding_a, binding_b = mail_personal_bindings
    secret_a, secret_b = mail_personal_pair
    first_subject = f"{mail_subject_marker}-inc-1"
    second_subject = f"{mail_subject_marker}-inc-2"
    first_id = f"<plt-pers-inc1-{mail_subject_marker}@mail.ru>"
    second_id = f"<plt-pers-inc2-{mail_subject_marker}@mail.ru>"
    _ = await mail_personal_port.send_message(
        secret_a,
        OutboundMailMessage(
            to_addresses=[binding_b.email_address],
            subject=first_subject,
            body_text="one",
            message_id=first_id,
        ),
    )
    assert (
        await poll_fetch_message(
            mail_personal_port, secret_b, message_id=first_id, subject=first_subject
        )
        is not None
    )
    _ = await mail_personal_service.sync_binding(binding_b, max_new_messages=50)
    _ = await _find_local_by_subject(
        mail_personal_service,
        binding_b,
        subject=first_subject,
        company_id=company_id,
    )
    _ = await mail_personal_port.send_message(
        secret_a,
        OutboundMailMessage(
            to_addresses=[binding_b.email_address],
            subject=second_subject,
            body_text="two",
            message_id=second_id,
        ),
    )
    assert (
        await poll_fetch_message(
            mail_personal_port, secret_b, message_id=second_id, subject=second_subject
        )
        is not None
    )
    _ = await mail_personal_service.sync_binding(binding_b, max_new_messages=50)
    _ = await _find_local_by_subject(
        mail_personal_service,
        binding_b,
        subject=first_subject,
        company_id=company_id,
    )
    _ = await _find_local_by_subject(
        mail_personal_service,
        binding_b,
        subject=second_subject,
        company_id=company_id,
    )
    _ = binding_a


@pytest.mark.asyncio
async def test_personal_mark_seen_unseen(
    mail_personal_port: MailServerPort,
    mail_personal_service: MailService,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_subject_marker: str,
) -> None:
    company_id, binding_a, binding_b = mail_personal_bindings
    secret_a, secret_b = mail_personal_pair
    subject = f"{mail_subject_marker}-seen"
    message_id = f"<plt-pers-seen-{mail_subject_marker}@mail.ru>"
    _ = await mail_personal_port.send_message(
        secret_a,
        OutboundMailMessage(
            to_addresses=[binding_b.email_address],
            subject=subject,
            body_text="seen",
            message_id=message_id,
        ),
    )
    found = await poll_fetch_message(
        mail_personal_port, secret_b, message_id=message_id, subject=subject
    )
    assert found is not None
    _ = await mail_personal_service.sync_binding(binding_b, max_new_messages=50)
    local = await _find_local_by_subject(
        mail_personal_service,
        binding_b,
        subject=subject,
        company_id=company_id,
    )
    seen = await mail_personal_service.mark_message_seen(
        MailMessageFlagPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid=local.uid,
        ),
        company_id=company_id,
    )
    assert seen.unread is False
    flags = await mail_personal_port.fetch_flags_for_uids(
        secret_b,
        mailbox=INBOX_FOLDER,
        uids=[local.uid],
    )
    assert local.uid in flags
    assert flags[local.uid].unread is False
    unseen = await mail_personal_service.mark_message_unseen(
        MailMessageFlagPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid=local.uid,
        ),
        company_id=company_id,
    )
    assert unseen.unread is True
    flags2 = await mail_personal_port.fetch_flags_for_uids(
        secret_b,
        mailbox=INBOX_FOLDER,
        uids=[local.uid],
    )
    assert flags2[local.uid].unread is True
    _ = binding_a


@pytest.mark.asyncio
async def test_personal_star_unstar(
    mail_personal_port: MailServerPort,
    mail_personal_service: MailService,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_subject_marker: str,
) -> None:
    company_id, binding_a, binding_b = mail_personal_bindings
    secret_a, secret_b = mail_personal_pair
    subject = f"{mail_subject_marker}-star"
    message_id = f"<plt-pers-star-{mail_subject_marker}@mail.ru>"
    _ = await mail_personal_port.send_message(
        secret_a,
        OutboundMailMessage(
            to_addresses=[binding_b.email_address],
            subject=subject,
            body_text="star",
            message_id=message_id,
        ),
    )
    found = await poll_fetch_message(
        mail_personal_port, secret_b, message_id=message_id, subject=subject
    )
    assert found is not None
    _ = await mail_personal_service.sync_binding(binding_b, max_new_messages=50)
    local = await _find_local_by_subject(
        mail_personal_service,
        binding_b,
        subject=subject,
        company_id=company_id,
    )
    starred = await mail_personal_service.star_message(
        MailMessageStarPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid=local.uid,
            flagged=True,
        ),
        company_id=company_id,
    )
    assert starred.flagged is True
    flags = await mail_personal_port.fetch_flags_for_uids(
        secret_b,
        mailbox=INBOX_FOLDER,
        uids=[local.uid],
    )
    assert flags[local.uid].flagged is True
    unstarred = await mail_personal_service.star_message(
        MailMessageStarPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid=local.uid,
            flagged=False,
        ),
        company_id=company_id,
    )
    assert unstarred.flagged is False
    flags2 = await mail_personal_port.fetch_flags_for_uids(
        secret_b,
        mailbox=INBOX_FOLDER,
        uids=[local.uid],
    )
    assert flags2[local.uid].flagged is False
    _ = binding_a


@pytest.mark.asyncio
async def test_personal_trash_and_delete_forever(
    mail_personal_port: MailServerPort,
    mail_personal_service: MailService,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_subject_marker: str,
) -> None:
    company_id, binding_a, binding_b = mail_personal_bindings
    secret_a, secret_b = mail_personal_pair
    subject = f"{mail_subject_marker}-trash"
    message_id = f"<plt-pers-trash-{mail_subject_marker}@mail.ru>"
    _ = await mail_personal_port.send_message(
        secret_a,
        OutboundMailMessage(
            to_addresses=[binding_b.email_address],
            subject=subject,
            body_text="trash",
            message_id=message_id,
        ),
    )
    found = await poll_fetch_message(
        mail_personal_port, secret_b, message_id=message_id, subject=subject
    )
    assert found is not None
    _ = await mail_personal_service.sync_binding(binding_b, max_new_messages=50)
    local = await _find_local_by_subject(
        mail_personal_service,
        binding_b,
        subject=subject,
        company_id=company_id,
    )
    trashed = await mail_personal_service.trash_message(
        MailMessageFlagPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid=local.uid,
        ),
        company_id=company_id,
    )
    assert trashed.destination_folder
    trash_folder = trashed.destination_folder
    inbox_after = await mail_personal_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            folder=INBOX_FOLDER,
            limit=50,
        ),
        company_id=company_id,
    )
    assert all(item.uid != local.uid for item in inbox_after.items)
    found_trash = await poll_fetch_message(
        mail_personal_port,
        secret_b,
        message_id=message_id,
        subject=subject,
        mailbox=trash_folder,
    )
    assert found_trash is not None
    if trashed.destination_uid is not None:
        trash_list = await mail_personal_service.list_messages(
            MailMessageListPayload(
                mailbox_binding_id=binding_b.mailbox_binding_id,
                folder=trash_folder,
                limit=50,
            ),
            company_id=company_id,
        )
        assert any(
            item.uid == trashed.destination_uid or item.subject == subject
            for item in trash_list.items
        )
    delete_uid = trashed.destination_uid if trashed.destination_uid else found_trash.uid
    _ = await mail_personal_service.delete_message(
        MailMessageFlagPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            folder=trash_folder,
            uid=delete_uid,
        ),
        company_id=company_id,
    )
    after_local = await mail_personal_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            folder=trash_folder,
            limit=50,
        ),
        company_id=company_id,
    )
    assert all(item.uid != delete_uid for item in after_local.items)
    gone = await poll_fetch_message(
        mail_personal_port,
        secret_b,
        message_id=message_id,
        subject=subject,
        mailbox=trash_folder,
        deadline_sec=15.0,
    )
    assert gone is None
    _ = binding_a


@pytest.mark.asyncio
async def test_personal_archive_if_available(
    mail_personal_port: MailServerPort,
    mail_personal_service: MailService,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_subject_marker: str,
) -> None:
    company_id, binding_a, binding_b = mail_personal_bindings
    secret_a, secret_b = mail_personal_pair
    folders = await mail_personal_service.ensure_standard_folders(
        binding_b.mailbox_binding_id,
        company_id=company_id,
    )
    archive = next(
        (folder for folder in folders.folders if folder.role == MailFolderRole.ARCHIVE),
        None,
    )
    if archive is None or not archive.selectable:
        pytest.skip("SPECIAL-USE Archive folder not available on mailbox")
    subject = f"{mail_subject_marker}-archive"
    message_id = f"<plt-pers-arch-{mail_subject_marker}@mail.ru>"
    _ = await mail_personal_port.send_message(
        secret_a,
        OutboundMailMessage(
            to_addresses=[binding_b.email_address],
            subject=subject,
            body_text="archive",
            message_id=message_id,
        ),
    )
    found = await poll_fetch_message(
        mail_personal_port, secret_b, message_id=message_id, subject=subject
    )
    assert found is not None
    _ = await mail_personal_service.sync_binding(binding_b, max_new_messages=50)
    local = await _find_local_by_subject(
        mail_personal_service,
        binding_b,
        subject=subject,
        company_id=company_id,
    )
    archived = await mail_personal_service.archive_message(
        MailMessageFlagPayload(
            mailbox_binding_id=binding_b.mailbox_binding_id,
            folder=INBOX_FOLDER,
            uid=local.uid,
        ),
        company_id=company_id,
    )
    assert archived.destination_folder == archive.name
    _ = binding_a


@pytest.mark.asyncio
async def test_personal_draft_save_and_replace(
    mail_personal_service: MailService,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
    mail_subject_marker: str,
) -> None:
    company_id, binding_a, binding_b = mail_personal_bindings
    draft = await mail_personal_service.save_draft(
        MailDraftSavePayload(
            mailbox_binding_id=binding_a.mailbox_binding_id,
            to_addresses=[binding_b.email_address],
            subject=f"{mail_subject_marker}-draft",
            body_text="draft-v1",
        ),
        company_id=company_id,
    )
    assert draft.uid
    drafts = await mail_personal_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding_a.mailbox_binding_id,
            folder=draft.folder,
            limit=20,
        ),
        company_id=company_id,
    )
    assert any(item.uid == draft.uid for item in drafts.items)
    replaced = await mail_personal_service.save_draft(
        MailDraftSavePayload(
            mailbox_binding_id=binding_a.mailbox_binding_id,
            to_addresses=[binding_b.email_address],
            subject=f"{mail_subject_marker}-draft",
            body_text="draft-v2",
            uid=draft.uid,
        ),
        company_id=company_id,
    )
    assert replaced.uid
    detail = await mail_personal_service.get_message(
        mailbox_binding_id=binding_a.mailbox_binding_id,
        uid=replaced.uid,
        folder=replaced.folder,
        company_id=company_id,
    )
    assert detail.body_text is not None
    assert "draft-v2" in detail.body_text


@pytest.mark.asyncio
async def test_personal_prepare_send_and_send(
    mail_personal_service: MailService,
    mail_personal_port: MailServerPort,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_subject_marker: str,
) -> None:
    company_id, binding_a, binding_b = mail_personal_bindings
    _secret_a, secret_b = mail_personal_pair
    subject = f"{mail_subject_marker}-svc-send"
    message_id = f"<plt-pers-svc-{mail_subject_marker}@mail.ru>"
    payload = MailSendPayload(
        mailbox_binding_id=binding_a.mailbox_binding_id,
        to_addresses=[binding_b.email_address],
        subject=subject,
        body_text=f"svc-send-{mail_subject_marker}",
        message_id=message_id,
    )
    prepared = await mail_personal_service.prepare_send_local(
        payload,
        company_id=company_id,
    )
    assert prepared.message_id == message_id
    sent = await mail_personal_service.send_message(payload, company_id=company_id)
    assert binding_b.email_address in sent.accepted
    found = await poll_fetch_message(
        mail_personal_port,
        secret_b,
        message_id=message_id,
        subject=subject,
    )
    assert found is not None
    _ = await mail_personal_service.sync_binding(binding_a, max_new_messages=50)
    _ = await mail_personal_service.sync_binding(binding_b, max_new_messages=50)
    _ = await _find_local_by_subject(
        mail_personal_service,
        binding_b,
        subject=subject,
        company_id=company_id,
    )
    sent_folder = await mail_personal_service.resolve_folder_name_for_role(
        binding_a.mailbox_binding_id,
        MailFolderRole.SENT,
        company_id=company_id,
    )
    sent_list = await mail_personal_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding_a.mailbox_binding_id,
            folder=sent_folder,
            limit=50,
        ),
        company_id=company_id,
    )
    assert any(item.subject == subject for item in sent_list.items)


@pytest.mark.asyncio
async def test_personal_search_local(
    mail_personal_port: MailServerPort,
    mail_personal_service: MailService,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_subject_marker: str,
) -> None:
    company_id, binding_a, binding_b = mail_personal_bindings
    secret_a, secret_b = mail_personal_pair
    subject = f"{mail_subject_marker}-search"
    body = f"search-body-{mail_subject_marker}"
    message_id = f"<plt-pers-search-{mail_subject_marker}@mail.ru>"
    _ = await mail_personal_port.send_message(
        secret_a,
        OutboundMailMessage(
            to_addresses=[binding_b.email_address],
            subject=subject,
            body_text=body,
            message_id=message_id,
        ),
    )
    assert (
        await poll_fetch_message(
            mail_personal_port, secret_b, message_id=message_id, subject=subject
        )
        is not None
    )
    _ = await mail_personal_service.sync_binding(binding_b, max_new_messages=50)
    local = await _find_local_by_subject(
        mail_personal_service,
        binding_b,
        subject=subject,
        company_id=company_id,
    )
    for query in (mail_subject_marker, "search-body", binding_a.email_address.split("@")[0]):
        searched = await mail_personal_service.search_messages(
            MailMessageSearchPayload(
                mailbox_binding_id=binding_b.mailbox_binding_id,
                q=query,
                folder=INBOX_FOLDER,
                limit=20,
            ),
            company_id=company_id,
        )
        assert any(item.uid == local.uid for item in searched.items), query


@pytest.mark.asyncio
async def test_personal_sync_now(
    mail_personal_service: MailService,
    mail_personal_port: MailServerPort,
    mail_personal_bindings: tuple[str, MailboxBinding, MailboxBinding],
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_subject_marker: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id, binding_a, binding_b = mail_personal_bindings
    secret_a, secret_b = mail_personal_pair
    subject = f"{mail_subject_marker}-syncnow"
    message_id = f"<plt-pers-syncnow-{mail_subject_marker}@mail.ru>"
    _ = await mail_personal_port.send_message(
        secret_a,
        OutboundMailMessage(
            to_addresses=[binding_b.email_address],
            subject=subject,
            body_text="syncnow",
            message_id=message_id,
        ),
    )
    assert (
        await poll_fetch_message(
            mail_personal_port, secret_b, message_id=message_id, subject=subject
        )
        is not None
    )
    enqueued: list[tuple[str, str]] = []

    async def _fake_enqueue(*, company_id: str, mailbox_binding_id: str) -> None:
        enqueued.append((company_id, mailbox_binding_id))

    monkeypatch.setattr(
        "core.mail.service.enqueue_mail_sync_binding",
        _fake_enqueue,
    )
    sync_now = await mail_personal_service.request_sync_now(
        MailSyncNowPayload(mailbox_binding_id=binding_b.mailbox_binding_id),
        company_id=company_id,
    )
    assert sync_now.accepted is True
    assert enqueued == [(company_id, binding_b.mailbox_binding_id)]
    # Eventual local: sync directly (worker not required in unit process).
    _ = await mail_personal_service.sync_binding(binding_b, max_new_messages=50)
    _ = await _find_local_by_subject(
        mail_personal_service,
        binding_b,
        subject=subject,
        company_id=company_id,
    )
    _ = binding_a


@pytest.mark.asyncio
async def test_personal_unbind_a(
    mail_personal_service: MailService,
    mail_personal_cfg: MailLivePersonalConfig,
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_personal_company_ctx: tuple[str, str, Company, User],
) -> None:
    company_id, _user_id, company, user = mail_personal_company_ctx
    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )
    secret_a, _secret_b = mail_personal_pair
    binding = await mail_personal_service.connect_personal_mailbox(
        PersonalMailboxConnectPayload(
            email_address=secret_a.email_address,
            password=secret_a.password,
            imap_host=mail_personal_cfg.imap_host,
            imap_port=mail_personal_cfg.imap_port,
            smtp_host=mail_personal_cfg.smtp_host,
            smtp_port=mail_personal_cfg.smtp_port,
            use_ssl=mail_personal_cfg.use_ssl,
        ),
        company_id=company_id,
    )
    connection_id = binding.company_mail_connection_id
    await mail_personal_service.unbind_mailbox(
        binding.mailbox_binding_id,
        company_id=company_id,
    )
    assert await mail_personal_service._connection_repository.get(connection_id) is None
    candidates = await mail_personal_service.list_sync_candidates(
        limit=100,
        auth_error_cooldown_seconds=0,
    )
    assert all(
        item.mailbox_binding_id != binding.mailbox_binding_id for item in candidates
    )


@pytest.mark.asyncio
async def test_personal_company_coexistence(
    mail_personal_service: MailService,
    mail_personal_cfg: MailLivePersonalConfig,
    mail_personal_pair: tuple[MailboxSecret, MailboxSecret],
    mail_personal_company_ctx: tuple[str, str, Company, User],
    mail_live_settings: MailConfig,
    mail_live_port: MailServerPort,
    mail_quota_sweeper: list[str],
) -> None:
    system = mail_live_settings.system
    isp = system.ispmanager
    if (
        system.imap_host is None
        or system.smtp_host is None
        or isp.base_url is None
        or isp.authinfo_user is None
        or isp.authinfo_password is None
    ):
        pytest.skip("mail.system ISP incomplete for coexistence test")

    company_id, user_id, company, user = mail_personal_company_ctx
    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )
    secret_a, _secret_b = mail_personal_pair
    _ = await mail_personal_service.upsert_connection(
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
    local_part = (
        f"{mail_live_settings.live_test.mailbox_prefix}{company_id[-12:]}"
        .lower()
        .replace("_", "-")[:64]
    )
    company_binding = await mail_personal_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_id,
            local_part=local_part,
            password="coexist-temp-pass",
            provision=True,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    mail_quota_sweeper.append(company_binding.email_address)
    personal_binding = await mail_personal_service.connect_personal_mailbox(
        PersonalMailboxConnectPayload(
            email_address=secret_a.email_address,
            password=secret_a.password,
            imap_host=mail_personal_cfg.imap_host,
            imap_port=mail_personal_cfg.imap_port,
            smtp_host=mail_personal_cfg.smtp_host,
            smtp_port=mail_personal_cfg.smtp_port,
            use_ssl=mail_personal_cfg.use_ssl,
        ),
        company_id=company_id,
    )
    try:
        candidates = await mail_personal_service.list_sync_candidates(
            limit=100,
            auth_error_cooldown_seconds=0,
        )
        ids = {item.mailbox_binding_id for item in candidates}
        assert company_binding.mailbox_binding_id in ids
        assert personal_binding.mailbox_binding_id in ids
    finally:
        with suppress(MailError, ValueError):
            await mail_personal_service.unbind_mailbox(
                personal_binding.mailbox_binding_id,
                company_id=company_id,
            )
        with suppress(MailError, ValueError):
            await mail_personal_service.unbind_mailbox(
                company_binding.mailbox_binding_id,
                company_id=company_id,
            )
        with suppress(MailError, MailTransportError, ValueError):
            await mail_live_port.delete_mailbox(company_binding.email_address)
            if company_binding.email_address in mail_quota_sweeper:
                mail_quota_sweeper.remove(company_binding.email_address)
