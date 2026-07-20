"""Общие хелперы offline complete-client интеграций."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    InboundMailMessage,
    MailboxBinding,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailFolder,
    MailFolderRole,
    MailProvider,
)
from core.mail.service import MailService
from core.models.identity_models import Company, User
from tests.core.mail.fakes import RecordingMailServerPort

MailMemberSeed = Callable[..., Awaitable[tuple[Company, User]]]


STANDARD_FOLDERS: list[MailFolder] = [
    MailFolder(name="INBOX", delimiter="/", flags=[], role=MailFolderRole.INBOX, selectable=True),
    MailFolder(
        name="Sent",
        delimiter="/",
        flags=["\\Sent"],
        role=MailFolderRole.SENT,
        selectable=True,
    ),
    MailFolder(
        name="Drafts",
        delimiter="/",
        flags=["\\Drafts"],
        role=MailFolderRole.DRAFTS,
        selectable=True,
    ),
    MailFolder(
        name="Trash",
        delimiter="/",
        flags=["\\Trash"],
        role=MailFolderRole.TRASH,
        selectable=True,
    ),
    MailFolder(
        name="Archive",
        delimiter="/",
        flags=["\\Archive"],
        role=MailFolderRole.ARCHIVE,
        selectable=True,
    ),
]


async def seed_connected_user_binding(
    mail_service: MailService,
    mail_member_context: MailMemberSeed,
    recording_mail_port: RecordingMailServerPort,
    *,
    unique_id: str,
    prefix: str = "cci",
) -> tuple[str, str, MailboxBinding]:
    company_id = f"{prefix}_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await mail_member_context(company_id=company_id, user_id=user_id)
    recording_mail_port.imap_folders = list(STANDARD_FOLDERS)
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.example.com",
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company_id,
    )
    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_id,
            local_part=f"u{unique_id[:10]}",
            password="mailbox-pass",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    _ = await mail_service.refresh_folders_from_imap(
        binding.mailbox_binding_id,
        company_id=company_id,
    )
    return company_id, user_id, binding


def inbox_message(
    *,
    uid: str,
    unique_id: str,
    subject: str,
    body: str = "body",
    unread: bool = True,
    flagged: bool = False,
) -> InboundMailMessage:
    return InboundMailMessage(
        uid=uid,
        message_id=f"<cci-{unique_id}-{uid}@example.com>",
        subject=subject,
        from_address="peer@example.com",
        to_addresses=["box@example.com"],
        body_text=body,
        unread=unread,
        flagged=flagged,
        date=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
    )
