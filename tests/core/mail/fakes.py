"""In-process MailServerPort для offline-тестов (DI, не patch service)."""

from __future__ import annotations

from core.mail.exceptions import (
    MailMailboxNotFoundError,
    MailProvisionUnsupportedError,
    MailUidNotFoundError,
)
from core.mail.imap_folders import (
    STANDARD_ENSURE_ROLES,
    ParsedImapListEntry,
    build_mail_folder_list_result,
    standard_folder_name,
)
from core.mail.mime_parse import strip_attachment_payloads
from core.mail.models import (
    InboundMailMessage,
    MailboxEnsureSpec,
    MailboxInfo,
    MailboxSecret,
    MailFetchQuery,
    MailFolder,
    MailFolderListResult,
    MailFolderRole,
    MailProvider,
    MailSendResult,
    MailServerHealth,
    MailUidBatch,
    OutboundMailMessage,
)
from core.mail.threads import message_belongs_to_thread_ids


class RecordingMailServerPort:
    def __init__(self, *, supports_provision: bool = True) -> None:
        self.supports_provision = supports_provision
        self.mailboxes: dict[str, MailboxInfo] = {}
        self.sent: list[tuple[str, OutboundMailMessage]] = []
        self.inbox: list[InboundMailMessage] = []
        self.mailbox_messages: dict[str, list[InboundMailMessage]] = {}
        self.ensure_calls: list[MailboxEnsureSpec] = []
        self.delete_calls: list[str] = []
        self.uidvalidity: int = 1
        self.fetch_uids_since_calls: list[tuple[str, int, int]] = []
        self.fetch_messages_calls: list[tuple[str, str, bool]] = []
        self.mark_seen_calls: list[tuple[str, str, str]] = []
        self.mark_unseen_calls: list[tuple[str, str, str]] = []
        self.imap_folders: list[MailFolder] = [
            MailFolder(name="INBOX", delimiter="/", flags=[], role=MailFolderRole.INBOX, selectable=True),
            MailFolder(
                name="Sent",
                delimiter="/",
                flags=["\\Sent"],
                role=MailFolderRole.SENT,
                selectable=True,
            ),
        ]
        self.append_sent_calls: list[tuple[str, str]] = []
        self.last_sent_body_html: str | None = None
        self.namespace_prefix: str = ""
        self.delimiter: str | None = "/"
        self.capabilities: list[str] = ["IMAP4rev1", "SPECIAL-USE", "NAMESPACE"]
        self.create_imap_folder_calls: list[tuple[str, MailFolderRole | None]] = []
        self.select_fail_names: set[str] = set()

    async def healthcheck(self) -> MailServerHealth:
        return MailServerHealth(
            provider=MailProvider.ISPMANAGER if self.supports_provision else MailProvider.GENERIC_IMAP_SMTP,
            provision_ok=self.supports_provision,
            imap_ok=True,
            smtp_ok=True,
            detail="recording",
        )

    async def healthcheck_with_credentials(self, secret: MailboxSecret) -> MailServerHealth:
        _ = secret
        return await self.healthcheck()

    async def list_mailboxes(self, mail_domain: str) -> list[MailboxInfo]:
        return [
            item
            for item in self.mailboxes.values()
            if item.mail_domain == mail_domain.lower()
        ]

    async def ensure_mailbox(self, spec: MailboxEnsureSpec) -> MailboxInfo:
        if not self.supports_provision:
            raise MailProvisionUnsupportedError(MailProvider.GENERIC_IMAP_SMTP.value)
        self.ensure_calls.append(spec)
        email_address = f"{spec.local_part}@{spec.mail_domain}".lower()
        info = MailboxInfo(
            email_address=email_address,
            local_part=spec.local_part.lower(),
            mail_domain=spec.mail_domain.lower(),
        )
        self.mailboxes[email_address] = info
        return info

    async def delete_mailbox(self, email_address: str) -> None:
        if not self.supports_provision:
            raise MailProvisionUnsupportedError(MailProvider.GENERIC_IMAP_SMTP.value)
        normalized = email_address.lower()
        self.delete_calls.append(normalized)
        _ = self.mailboxes.pop(normalized, None)

    async def send_message(
        self,
        binding_secret: MailboxSecret,
        message: OutboundMailMessage,
    ) -> MailSendResult:
        self.sent.append((binding_secret.email_address, message))
        message_id = message.message_id if message.message_id is not None else f"msg-{len(self.sent)}"
        folders = await self.list_imap_folders(binding_secret)
        sent_folder = next(
            (folder for folder in folders.folders if folder.role == MailFolderRole.SENT and folder.selectable),
            None,
        )
        if sent_folder is None:
            sent_name = standard_folder_name(
                role=MailFolderRole.SENT,
                namespace_prefix=folders.namespace_prefix,
            )
            await self.create_imap_folder(
                binding_secret,
                name=sent_name,
                role=MailFolderRole.SENT,
            )
        else:
            sent_name = sent_folder.name
        stored_body = message.body_text
        if message.body_html is not None and message.body_html.strip():
            stored_body = f"{message.body_text}\n\n{message.body_html}"
        stored = InboundMailMessage(
            uid=str(len(self.mailbox_messages.get(sent_name, [])) + 1),
            message_id=message_id,
            subject=message.subject,
            from_address=binding_secret.email_address,
            to_addresses=list(message.to_addresses),
            body_text=stored_body,
            in_reply_to=message.in_reply_to,
            references=message.references,
            attachments=list(message.attachments),
        )
        self.last_sent_body_html = message.body_html
        self.mailbox_messages.setdefault(sent_name, []).append(stored)
        self.append_sent_calls.append((binding_secret.email_address, sent_name))
        return MailSendResult(message_id=message_id, accepted=list(message.to_addresses))

    async def fetch_messages(
        self,
        binding_secret: MailboxSecret,
        query: MailFetchQuery,
    ) -> list[InboundMailMessage]:
        _ = binding_secret
        self.fetch_messages_calls.append(
            (binding_secret.email_address, query.mailbox, query.include_bodies)
        )
        if query.mailbox in self.select_fail_names:
            raise MailMailboxNotFoundError(folder_name=query.mailbox)
        if query.mailbox.casefold() == "inbox":
            items = list(self.inbox)
        else:
            items = list(self.mailbox_messages.get(query.mailbox, []))
        if query.subject_contains is not None:
            items = [
                item
                for item in items
                if item.subject is not None and query.subject_contains in item.subject
            ]
        if query.message_id is not None:
            items = [item for item in items if item.message_id == query.message_id]
        if not query.include_bodies:
            items = [
                strip_attachment_payloads(item).model_copy(update={"body_text": None})
                for item in items
            ]
        limited = items[-query.limit :]
        return list(reversed(limited))

    async def fetch_message_by_uid(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
    ) -> InboundMailMessage:
        _ = binding_secret
        if mailbox in self.select_fail_names:
            raise MailMailboxNotFoundError(folder_name=mailbox)
        if mailbox.casefold() == "inbox":
            items = list(self.inbox)
        else:
            items = list(self.mailbox_messages.get(mailbox, []))
        for message in items:
            if message.uid == uid:
                return message
        raise MailUidNotFoundError(mailbox=mailbox, uid=uid)

    async def search_messages_by_thread_ids(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        message_ids: set[str],
        subject_key: str | None = None,
        limit: int = 100,
    ) -> list[InboundMailMessage]:
        _ = binding_secret
        if limit < 1:
            raise ValueError("limit must be >= 1")
        resolved_subject = subject_key.strip() if subject_key is not None else ""
        if not message_ids and not resolved_subject:
            raise ValueError("message_ids or subject_key required for thread search")
        if mailbox in self.select_fail_names:
            raise MailMailboxNotFoundError(folder_name=mailbox)
        if mailbox.casefold() == "inbox":
            items = list(self.inbox)
        else:
            items = list(self.mailbox_messages.get(mailbox, []))
        matched = [
            item
            for item in items
            if message_belongs_to_thread_ids(
                item,
                thread_ids=message_ids,
                subject_key=resolved_subject if resolved_subject else None,
            )
        ]
        return matched[:limit]

    async def mark_message_seen(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
    ) -> None:
        self.mark_seen_calls.append((binding_secret.email_address, mailbox, uid))
        if mailbox.casefold() == "inbox":
            collection = self.inbox
        else:
            collection = self.mailbox_messages.get(mailbox, [])
        for index, message in enumerate(collection):
            if message.uid == uid:
                collection[index] = message.model_copy(update={"unread": False})
                return
        raise MailUidNotFoundError(mailbox=mailbox, uid=uid)

    async def mark_message_unseen(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
    ) -> None:
        self.mark_unseen_calls.append((binding_secret.email_address, mailbox, uid))
        if mailbox.casefold() == "inbox":
            collection = self.inbox
        else:
            collection = self.mailbox_messages.get(mailbox, [])
        for index, message in enumerate(collection):
            if message.uid == uid:
                collection[index] = message.model_copy(update={"unread": True})
                return
        raise MailUidNotFoundError(mailbox=mailbox, uid=uid)

    def _folder_message_counts(self, folder_name: str) -> tuple[int, int]:
        if folder_name.casefold() == "inbox":
            items = list(self.inbox)
        else:
            items = list(self.mailbox_messages.get(folder_name, []))
        unseen = sum(1 for item in items if item.unread)
        return len(items), unseen

    async def fetch_uids_since(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        since_uid: int,
        limit: int,
    ) -> MailUidBatch:
        _ = binding_secret
        self.fetch_uids_since_calls.append((mailbox, since_uid, limit))
        if mailbox in self.select_fail_names:
            raise MailMailboxNotFoundError(folder_name=mailbox)
        max_uid = max((int(item.uid) for item in self.inbox), default=0)
        if since_uid <= 0:
            return MailUidBatch(
                uidvalidity=self.uidvalidity,
                max_uid=max_uid,
                messages=[],
            )
        new_messages = sorted(
            (item for item in self.inbox if int(item.uid) > since_uid),
            key=lambda item: int(item.uid),
        )[:limit]
        return MailUidBatch(
            uidvalidity=self.uidvalidity,
            max_uid=max_uid,
            messages=list(new_messages),
        )

    async def list_imap_folders(self, binding_secret: MailboxSecret) -> MailFolderListResult:
        _ = binding_secret
        entries = [
            ParsedImapListEntry(
                name=folder.name,
                attributes=frozenset(flag.upper() for flag in folder.flags),
                delimiter=folder.delimiter,
            )
            for folder in self.imap_folders
        ]
        # Preserve explicit roles from seed folders (not only flags).
        result = build_mail_folder_list_result(
            list_entries=entries,
            namespace_prefix=self.namespace_prefix,
            namespace_delimiter=self.delimiter,
            capabilities=list(self.capabilities),
        )
        by_name = {folder.name: folder for folder in self.imap_folders}
        merged: list[MailFolder] = []
        for folder in result.folders:
            seeded = by_name.get(folder.name)
            base = seeded if seeded is not None else folder
            message_count, unseen_count = self._folder_message_counts(base.name)
            merged.append(
                base.model_copy(
                    update={
                        "message_count": message_count,
                        "unseen_count": unseen_count,
                    }
                )
            )
        present_roles = {folder.role for folder in merged}
        missing = [role for role in STANDARD_ENSURE_ROLES if role not in present_roles]
        return MailFolderListResult(
            folders=merged,
            namespace_prefix=self.namespace_prefix,
            delimiter=self.delimiter,
            capabilities=list(self.capabilities),
            missing_standard_roles=missing,
        )

    async def create_imap_folder(
        self,
        binding_secret: MailboxSecret,
        *,
        name: str,
        role: MailFolderRole | None = None,
    ) -> None:
        _ = binding_secret
        self.create_imap_folder_calls.append((name, role))
        flags: list[str] = []
        if role == MailFolderRole.SENT:
            flags = ["\\Sent"]
        elif role == MailFolderRole.DRAFTS:
            flags = ["\\Drafts"]
        elif role == MailFolderRole.TRASH:
            flags = ["\\Trash"]
        folder_role = role if role is not None else MailFolderRole.OTHER
        self.imap_folders.append(
            MailFolder(
                name=name,
                delimiter=self.delimiter,
                flags=flags,
                role=folder_role,
                selectable=True,
            )
        )

    async def ensure_standard_imap_folders(
        self,
        binding_secret: MailboxSecret,
    ) -> MailFolderListResult:
        current = await self.list_imap_folders(binding_secret)
        for role in STANDARD_ENSURE_ROLES:
            if role not in current.missing_standard_roles:
                continue
            folder_name = standard_folder_name(
                role=role,
                namespace_prefix=current.namespace_prefix,
            )
            await self.create_imap_folder(binding_secret, name=folder_name, role=role)
        return await self.list_imap_folders(binding_secret)
