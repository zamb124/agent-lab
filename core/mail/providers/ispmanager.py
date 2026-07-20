"""ISPmanager MailServerPort: provision API + IMAP/SMTP transport."""

from __future__ import annotations

from typing import Final, final
from urllib.parse import urlencode
from xml.etree import ElementTree

from core.http import get_httpx_client
from core.http.client import ProxyStrategy
from core.mail.delete_policy import assert_mailbox_delete_allowed
from core.mail.exceptions import MailError
from core.mail.models import (
    InboundMailMessage,
    MailAppendResult,
    MailboxEnsureSpec,
    MailboxInfo,
    MailboxSecret,
    MailFetchQuery,
    MailFolderListResult,
    MailFolderRole,
    MailMessageFlags,
    MailProvider,
    MailSendResult,
    MailServerHealth,
    MailUidBatch,
    MailUidMoveResult,
    MailUidSearchCriteria,
    OutboundMailMessage,
)
from core.mail.transport.idle_session import MailIdleSession
from core.mail.transport.imap_smtp import ImapSmtpTransport


@final
class IspmanagerMailServerPort:
    def __init__(
        self,
        *,
        base_url: str,
        authinfo_user: str,
        authinfo_password: str,
        transport: ImapSmtpTransport,
        protected_local_parts: frozenset[str],
        delete_prefix_required: str | None = None,
        allow_delete: bool = True,
    ) -> None:
        if not base_url.strip():
            raise ValueError("IspmanagerMailServerPort: base_url is required")
        if not authinfo_user.strip():
            raise ValueError("IspmanagerMailServerPort: authinfo_user is required")
        if not authinfo_password.strip():
            raise ValueError("IspmanagerMailServerPort: authinfo_password is required")
        self._base_url: Final[str] = base_url.rstrip("/")
        self._authinfo_user: Final[str] = authinfo_user
        self._authinfo_password: Final[str] = authinfo_password
        self._transport: Final[ImapSmtpTransport] = transport
        self._protected_local_parts: Final[frozenset[str]] = protected_local_parts
        self._delete_prefix_required: Final[str | None] = delete_prefix_required
        self._allow_delete: Final[bool] = allow_delete

    async def _call(self, func: str, params: dict[str, str]) -> ElementTree.Element:
        query = {
            "authinfo": f"{self._authinfo_user}:{self._authinfo_password}",
            "out": "xml",
            "func": func,
            **params,
        }
        url = f"{self._base_url}?{urlencode(query)}"
        try:
            async with get_httpx_client(
                timeout=60.0,
                strategy=ProxyStrategy.DIRECT_ONLY,
            ) as client:
                response = await client.get(url)
                _ = response.raise_for_status()
                content = str(response.text)
        except Exception as exc:
            raise MailError(f"ISPmanager HTTP failed func={func}: {exc}") from exc
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError as exc:
            raise MailError(f"ISPmanager XML parse failed func={func}") from exc
        error_node = root.find("error")
        if error_node is not None:
            raise MailError(
                f"ISPmanager error func={func}: {error_node.text or ElementTree.tostring(error_node, encoding='unicode')}"
            )
        return root

    async def healthcheck(self) -> MailServerHealth:
        provision_ok = False
        imap_ok = False
        smtp_ok = False
        detail_parts: list[str] = []
        try:
            _ = await self._call("email", {})
            provision_ok = True
        except MailError as exc:
            detail_parts.append(f"provision: {exc}")
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
        detail: str | None = None
        if detail_parts:
            detail = "; ".join(detail_parts)
        return MailServerHealth(
            provider=MailProvider.ISPMANAGER,
            provision_ok=provision_ok,
            imap_ok=imap_ok,
            smtp_ok=smtp_ok,
            detail=detail,
        )

    async def list_mailboxes(self, mail_domain: str) -> list[MailboxInfo]:
        root = await self._call("email", {})
        mailboxes: list[MailboxInfo] = []
        for elem in root.findall("elem"):
            name_node = elem.find("name")
            if name_node is None or name_node.text is None:
                continue
            email_address = name_node.text.strip()
            if "@" not in email_address:
                continue
            local_part, domain = email_address.split("@", 1)
            if domain.lower() != mail_domain.lower():
                continue
            mailboxes.append(
                MailboxInfo(
                    email_address=email_address.lower(),
                    local_part=local_part.lower(),
                    mail_domain=domain.lower(),
                )
            )
        return mailboxes

    async def ensure_mailbox(self, spec: MailboxEnsureSpec) -> MailboxInfo:
        email_address = f"{spec.local_part}@{spec.mail_domain}".lower()
        existing = await self.list_mailboxes(spec.mail_domain)
        for item in existing:
            if item.email_address == email_address:
                return item
        _ = await self._call(
            "email.edit",
            {
                "domainname": spec.mail_domain,
                "name": spec.local_part,
                "passwd": spec.password,
                "confirm": spec.password,
                "plid": spec.mail_domain,
                "sok": "ok",
            },
        )
        return MailboxInfo(
            email_address=email_address,
            local_part=spec.local_part.lower(),
            mail_domain=spec.mail_domain.lower(),
        )

    async def set_mailbox_password(self, spec: MailboxEnsureSpec) -> None:
        if not spec.password.strip():
            raise ValueError("MailboxEnsureSpec.password is required")
        email_address = f"{spec.local_part}@{spec.mail_domain}".lower()
        _ = await self._call(
            "email.edit",
            {
                "elid": email_address,
                "passwd": spec.password,
                "confirm": spec.password,
                "sok": "ok",
            },
        )

    async def delete_mailbox(self, email_address: str) -> None:
        assert_mailbox_delete_allowed(
            email_address,
            protected_local_parts=self._protected_local_parts,
            allow_delete=self._allow_delete,
            delete_prefix_required=self._delete_prefix_required,
        )
        normalized = email_address.strip().lower()
        _ = await self._call(
            "email.delete",
            {
                "elid": normalized,
                "sok": "ok",
            },
        )

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

    async def uid_store_flags(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
        add_flags: list[str],
        remove_flags: list[str],
    ) -> None:
        await self._transport.uid_store_flags(
            binding_secret,
            mailbox=mailbox,
            uid=uid,
            add_flags=add_flags,
            remove_flags=remove_flags,
        )

    async def uid_move(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
        destination_folder: str,
    ) -> MailUidMoveResult:
        return await self._transport.uid_move(
            binding_secret,
            mailbox=mailbox,
            uid=uid,
            destination_folder=destination_folder,
        )

    async def uid_expunge(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str | None = None,
    ) -> None:
        await self._transport.uid_expunge(
            binding_secret,
            mailbox=mailbox,
            uid=uid,
        )

    async def append_message(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        raw_message: bytes,
        flags: str | None = None,
    ) -> MailAppendResult:
        return await self._transport.append_message(
            binding_secret,
            mailbox=mailbox,
            raw_message=raw_message,
            flags=flags,
        )

    async def uid_search(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        criteria: MailUidSearchCriteria,
    ) -> list[str]:
        return await self._transport.uid_search(
            binding_secret,
            mailbox=mailbox,
            criteria=criteria,
        )

    async def fetch_flags_for_uids(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uids: list[str],
    ) -> dict[str, MailMessageFlags]:
        return await self._transport.fetch_flags_for_uids(
            binding_secret,
            mailbox=mailbox,
            uids=uids,
        )

    async def open_idle_session(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
    ) -> MailIdleSession:
        return await self._transport.open_idle_session(
            binding_secret,
            mailbox=mailbox,
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
            detail_parts.append(f"imap: {exc}")
        try:
            await self._transport.check_smtp(secret)
            smtp_ok = True
        except Exception as exc:
            detail_parts.append(f"smtp: {exc}")
        detail: str | None = None
        if detail_parts:
            detail = "; ".join(detail_parts)
        return MailServerHealth(
            provider=MailProvider.ISPMANAGER,
            provision_ok=base.provision_ok,
            imap_ok=imap_ok,
            smtp_ok=smtp_ok,
            detail=detail,
        )
