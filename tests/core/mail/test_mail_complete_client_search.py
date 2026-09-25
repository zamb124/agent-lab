"""Offline integration: CursorPage list/search + needs_sync."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from core.mail.models import INBOX_FOLDER, MailMessageListPayload, MailMessageSearchPayload
from core.mail.service import MailService
from core.models.identity_models import Company, User
from tests.core.mail.complete_client_helpers import (
    inbox_message,
    seed_connected_user_binding,
)
from tests.core.mail.fakes import RecordingMailServerPort

MailMemberSeed = Callable[..., Awaitable[tuple[Company, User]]]


@pytest.mark.asyncio
async def test_list_messages_cursor_pagination(
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
        prefix="cursor",
    )
    recording_mail_port.inbox = [
        inbox_message(uid=str(i), unique_id=unique_id, subject=f"msg-{i}")
        for i in range(1, 8)
    ]
    _ = await mail_service.sync_binding(binding, max_new_messages=50)

    page1 = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            limit=3,
        ),
        company_id=company_id,
    )
    assert len(page1.items) == 3
    assert page1.has_more is True
    assert page1.next_cursor is not None

    page2 = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            limit=3,
            cursor=page1.next_cursor,
        ),
        company_id=company_id,
    )
    assert len(page2.items) == 3
    assert page2.has_more is True
    uids_page1 = {item.uid for item in page1.items}
    uids_page2 = {item.uid for item in page2.items}
    assert uids_page1.isdisjoint(uids_page2)

    page3 = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            limit=3,
            cursor=page2.next_cursor,
        ),
        company_id=company_id,
    )
    assert len(page3.items) == 1
    assert page3.has_more is False
    assert page3.next_cursor is None
    assert page3.needs_sync is False


@pytest.mark.asyncio
async def test_search_messages_filters_subject_and_body(
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
        prefix="search",
    )
    recording_mail_port.inbox = [
        inbox_message(
            uid="1",
            unique_id=unique_id,
            subject="Alpha invoice",
            body="pay now",
        ),
        inbox_message(
            uid="2",
            unique_id=unique_id,
            subject="Beta note",
            body="invoice buried in body",
        ),
        inbox_message(
            uid="3",
            unique_id=unique_id,
            subject="Gamma",
            body="unrelated",
        ),
    ]
    _ = await mail_service.sync_binding(binding, max_new_messages=50)

    found = await mail_service.search_messages(
        MailMessageSearchPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            q="invoice",
            limit=50,
        ),
        company_id=company_id,
    )
    assert {item.uid for item in found.items} == {"1", "2"}
    assert found.has_more is False


@pytest.mark.asyncio
async def test_search_from_address_and_folder_scope(
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
        prefix="searchfrom",
    )
    recording_mail_port.inbox = [
        inbox_message(uid="1", unique_id=unique_id, subject="alpha", body="x"),
    ]
    recording_mail_port.mailbox_messages["Sent"] = [
        inbox_message(uid="10", unique_id=unique_id, subject="alpha-sent", body="y"),
    ]
    recording_mail_port.mailbox_messages["Sent"][0] = recording_mail_port.mailbox_messages[
        "Sent"
    ][0].model_copy(update={"from_address": "sender@example.com"})
    _ = await mail_service.sync_binding(binding, max_new_messages=50)

    scoped = await mail_service.search_messages(
        MailMessageSearchPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="Sent",
            q="alpha",
            limit=50,
        ),
        company_id=company_id,
    )
    assert {item.uid for item in scoped.items} == {"10"}

    by_from = await mail_service.search_messages(
        MailMessageSearchPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            q="sender@example.com",
            limit=50,
        ),
        company_id=company_id,
    )
    assert any(item.uid == "10" for item in by_from.items)


@pytest.mark.asyncio
async def test_empty_folder_list_sets_needs_sync(
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
        prefix="needsync",
    )
    listed = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder=INBOX_FOLDER,
            limit=20,
        ),
        company_id=company_id,
    )
    assert listed.items == []
    assert listed.needs_sync is True
