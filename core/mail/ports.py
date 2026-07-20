"""Protocol почтового сервера компании."""

from __future__ import annotations

from typing import Protocol

from core.mail.models import (
    InboundMailMessage,
    MailAppendResult,
    MailboxEnsureSpec,
    MailboxInfo,
    MailboxSecret,
    MailFetchQuery,
    MailFolderListResult,
    MailFolderRole,
    MailIdleWake,
    MailMessageFlags,
    MailSendResult,
    MailServerHealth,
    MailUidBatch,
    MailUidMoveResult,
    MailUidSearchCriteria,
    OutboundMailMessage,
)
from core.mail.transport.idle_session import MailIdleSession


class MailServerPort(Protocol):
    async def healthcheck(self) -> MailServerHealth: ...

    async def list_mailboxes(self, mail_domain: str) -> list[MailboxInfo]: ...

    async def ensure_mailbox(self, spec: MailboxEnsureSpec) -> MailboxInfo: ...

    async def set_mailbox_password(self, spec: MailboxEnsureSpec) -> None: ...

    async def delete_mailbox(self, email_address: str) -> None: ...

    async def send_message(
        self,
        binding_secret: MailboxSecret,
        message: OutboundMailMessage,
    ) -> MailSendResult: ...

    async def fetch_messages(
        self,
        binding_secret: MailboxSecret,
        query: MailFetchQuery,
    ) -> list[InboundMailMessage]: ...

    async def fetch_message_by_uid(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
    ) -> InboundMailMessage: ...

    async def search_messages_by_thread_ids(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        message_ids: set[str],
        subject_key: str | None = None,
        limit: int = 100,
    ) -> list[InboundMailMessage]: ...

    async def mark_message_seen(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
    ) -> None: ...

    async def mark_message_unseen(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
    ) -> None: ...

    async def uid_store_flags(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
        add_flags: list[str],
        remove_flags: list[str],
    ) -> None: ...

    async def uid_move(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
        destination_folder: str,
    ) -> MailUidMoveResult: ...

    async def uid_expunge(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str | None = None,
    ) -> None: ...

    async def append_message(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        raw_message: bytes,
        flags: str | None = None,
    ) -> MailAppendResult: ...

    async def uid_search(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        criteria: MailUidSearchCriteria,
    ) -> list[str]: ...

    async def fetch_flags_for_uids(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uids: list[str],
    ) -> dict[str, MailMessageFlags]: ...

    async def open_idle_session(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
    ) -> MailIdleSession: ...

    async def fetch_uids_since(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        since_uid: int,
        limit: int,
    ) -> MailUidBatch: ...

    async def list_imap_folders(self, binding_secret: MailboxSecret) -> MailFolderListResult: ...

    async def create_imap_folder(
        self,
        binding_secret: MailboxSecret,
        *,
        name: str,
        role: MailFolderRole | None = None,
    ) -> None: ...

    async def ensure_standard_imap_folders(
        self,
        binding_secret: MailboxSecret,
    ) -> MailFolderListResult: ...

    async def healthcheck_with_credentials(self, secret: MailboxSecret) -> MailServerHealth: ...


# Re-export for callers that import wake types from ports.
__all__ = [
    "MailIdleSession",
    "MailIdleWake",
    "MailServerPort",
]
