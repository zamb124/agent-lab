"""MailServerPort без provision API (только IMAP/SMTP)."""

from __future__ import annotations

from typing import Final, final

from core.mail.exceptions import MailProvisionUnsupportedError
from core.mail.models import (
    InboundMailMessage,
    MailboxEnsureSpec,
    MailboxInfo,
    MailboxSecret,
    MailFetchQuery,
    MailFolderListResult,
    MailFolderRole,
    MailProvider,
    MailSendResult,
    MailServerHealth,
    MailUidBatch,
    OutboundMailMessage,
)
from core.mail.transport.imap_smtp import ImapSmtpTransport


@final
class GenericImapSmtpMailServerPort:
    def __init__(self, transport: ImapSmtpTransport) -> None:
        self._transport: Final[ImapSmtpTransport] = transport

    async def healthcheck(self) -> MailServerHealth:
        imap_ok = False
        smtp_ok = False
        detail_parts: list[str] = ["provision unsupported"]
        try:
            await self._transport.check_imap_hello()
            imap_ok = True
        except Exception as exc:
            detail_parts.append(f"imap: {exc}")
        try:
            await self._transport.check_smtp_connect()
            smtp_ok = True
        except Exception as exc:
            detail_parts.append(f"smtp: {exc}")
        return MailServerHealth(
            provider=MailProvider.GENERIC_IMAP_SMTP,
            provision_ok=False,
            imap_ok=imap_ok,
            smtp_ok=smtp_ok,
            detail="; ".join(detail_parts),
        )

    async def healthcheck_with_credentials(self, secret: MailboxSecret) -> MailServerHealth:
        base = await self.healthcheck()
        imap_ok = False
        smtp_ok = False
        detail_parts: list[str] = []
        if base.detail is not None:
            detail_parts.append(base.detail)
        try:
            await self._transport.check_imap_login(secret)
            imap_ok = True
        except Exception as exc:
            detail_parts.append(f"imap_login: {exc}")
        try:
            await self._transport.check_smtp(secret)
            smtp_ok = True
        except Exception as exc:
            detail_parts.append(f"smtp_login: {exc}")
        return MailServerHealth(
            provider=MailProvider.GENERIC_IMAP_SMTP,
            provision_ok=False,
            imap_ok=imap_ok,
            smtp_ok=smtp_ok,
            detail="; ".join(detail_parts) if detail_parts else None,
        )

    async def list_mailboxes(self, mail_domain: str) -> list[MailboxInfo]:
        _ = mail_domain
        raise MailProvisionUnsupportedError(MailProvider.GENERIC_IMAP_SMTP.value)

    async def ensure_mailbox(self, spec: MailboxEnsureSpec) -> MailboxInfo:
        _ = spec
        raise MailProvisionUnsupportedError(MailProvider.GENERIC_IMAP_SMTP.value)

    async def delete_mailbox(self, email_address: str) -> None:
        _ = email_address
        raise MailProvisionUnsupportedError(MailProvider.GENERIC_IMAP_SMTP.value)

    async def send_message(
        self,
        binding_secret: MailboxSecret,
        message: OutboundMailMessage,
    ) -> MailSendResult:
        return await self._transport.send_message(binding_secret, message)

    async def fetch_messages(
        self,
        binding_secret: MailboxSecret,
        query: MailFetchQuery,
    ) -> list[InboundMailMessage]:
        return await self._transport.fetch_messages(binding_secret, query)

    async def fetch_message_by_uid(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
    ) -> InboundMailMessage:
        return await self._transport.fetch_message_by_uid(
            binding_secret,
            mailbox=mailbox,
            uid=uid,
        )

    async def search_messages_by_thread_ids(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        message_ids: set[str],
        subject_key: str | None = None,
        limit: int = 100,
    ) -> list[InboundMailMessage]:
        return await self._transport.search_messages_by_thread_ids(
            binding_secret,
            mailbox=mailbox,
            message_ids=message_ids,
            subject_key=subject_key,
            limit=limit,
        )

    async def mark_message_seen(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
    ) -> None:
        await self._transport.mark_message_seen(
            binding_secret,
            mailbox=mailbox,
            uid=uid,
        )

    async def mark_message_unseen(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
    ) -> None:
        await self._transport.mark_message_unseen(
            binding_secret,
            mailbox=mailbox,
            uid=uid,
        )

    async def fetch_uids_since(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        since_uid: int,
        limit: int,
    ) -> MailUidBatch:
        return await self._transport.fetch_uids_since(
            binding_secret,
            mailbox=mailbox,
            since_uid=since_uid,
            limit=limit,
        )

    async def list_imap_folders(self, binding_secret: MailboxSecret) -> MailFolderListResult:
        return await self._transport.list_imap_folders(binding_secret)

    async def create_imap_folder(
        self,
        binding_secret: MailboxSecret,
        *,
        name: str,
        role: MailFolderRole | None = None,
    ) -> None:
        await self._transport.create_imap_folder(binding_secret, name=name, role=role)

    async def ensure_standard_imap_folders(
        self,
        binding_secret: MailboxSecret,
    ) -> MailFolderListResult:
        return await self._transport.ensure_standard_imap_folders(binding_secret)
