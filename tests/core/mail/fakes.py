"""In-process MailServerPort для offline-тестов (DI, не patch service)."""

from __future__ import annotations

from core.mail.exceptions import (
    MailError,
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
    MailAppendResult,
    MailboxEnsureSpec,
    MailboxInfo,
    MailboxSecret,
    MailFetchQuery,
    MailFolder,
    MailFolderListResult,
    MailFolderRole,
    MailIdleWake,
    MailIdleWakeKind,
    MailMessageFlags,
    MailProvider,
    MailSendResult,
    MailServerHealth,
    MailUidBatch,
    MailUidMoveResult,
    MailUidSearchCriteria,
    OutboundMailMessage,
)
from core.mail.threads import message_belongs_to_thread_ids


class _FakeIdleSession:
    def __init__(self, *, mailbox: str, wake: MailIdleWake | None = None) -> None:
        self.mailbox = mailbox
        self._wake = wake if wake is not None else MailIdleWake(kind=MailIdleWakeKind.TIMEOUT)

    async def wait_wake(self, *, timeout_seconds: float) -> MailIdleWake:
        _ = timeout_seconds
        return self._wake

    async def aclose(self) -> None:
        return None


class RecordingMailServerPort:
    def __init__(self, *, supports_provision: bool = True) -> None:
        self.supports_provision = supports_provision
        self.mailboxes: dict[str, MailboxInfo] = {}
        self.mailbox_passwords: dict[str, str] = {}
        self.sent: list[tuple[str, OutboundMailMessage]] = []
        self.inbox: list[InboundMailMessage] = []
        self.mailbox_messages: dict[str, list[InboundMailMessage]] = {}
        self.ensure_calls: list[MailboxEnsureSpec] = []
        self.set_password_calls: list[MailboxEnsureSpec] = []
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
        self.capabilities: list[str] = ["IMAP4rev1", "SPECIAL-USE", "NAMESPACE", "MOVE"]
        self.create_imap_folder_calls: list[tuple[str, MailFolderRole | None]] = []
        self.select_fail_names: set[str] = set()
        self.uid_store_flags_calls: list[tuple[str, str, list[str], list[str]]] = []
        self.uid_move_calls: list[tuple[str, str, str]] = []
        self.uid_expunge_calls: list[tuple[str, str | None]] = []
        self.append_message_calls: list[tuple[str, str]] = []
        self.idle_wake: MailIdleWake | None = None

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
        existing = self.mailboxes.get(email_address)
        if existing is not None:
            return existing
        info = MailboxInfo(
            email_address=email_address,
            local_part=spec.local_part.lower(),
            mail_domain=spec.mail_domain.lower(),
        )
        self.mailboxes[email_address] = info
        self.mailbox_passwords[email_address] = spec.password
        return info

    async def set_mailbox_password(self, spec: MailboxEnsureSpec) -> None:
        if not self.supports_provision:
            raise MailProvisionUnsupportedError(MailProvider.GENERIC_IMAP_SMTP.value)
        self.set_password_calls.append(spec)
        email_address = f"{spec.local_part}@{spec.mail_domain}".lower()
        if email_address not in self.mailboxes:
            raise MailError(f"Mailbox not found for password set: {email_address}")
        self.mailbox_passwords[email_address] = spec.password

    async def delete_mailbox(self, email_address: str) -> None:
        if not self.supports_provision:
            raise MailProvisionUnsupportedError(MailProvider.GENERIC_IMAP_SMTP.value)
        normalized = email_address.lower()
        self.delete_calls.append(normalized)
        _ = self.mailboxes.pop(normalized, None)
        _ = self.mailbox_passwords.pop(normalized, None)

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

    def _messages_for_mailbox(self, mailbox: str) -> list[InboundMailMessage]:
        if mailbox.casefold() == "inbox":
            return list(self.inbox)
        return list(self.mailbox_messages.get(mailbox, []))

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
        folder_items = self._messages_for_mailbox(mailbox)
        max_uid = max((int(item.uid) for item in folder_items), default=0)
        if since_uid <= 0:
            return MailUidBatch(
                uidvalidity=self.uidvalidity,
                max_uid=max_uid,
                messages=[],
            )
        new_messages = sorted(
            (item for item in folder_items if int(item.uid) > since_uid),
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

    def _mutate_message_flags(
        self,
        mailbox: str,
        uid: str,
        *,
        unread: bool | None = None,
        flagged: bool | None = None,
        answered: bool | None = None,
        draft: bool | None = None,
    ) -> InboundMailMessage:
        if mailbox.casefold() == "inbox":
            collection = self.inbox
        else:
            collection = self.mailbox_messages.setdefault(mailbox, [])
        for index, message in enumerate(collection):
            if message.uid != uid:
                continue
            updates: dict[str, bool] = {}
            if unread is not None:
                updates["unread"] = unread
            if flagged is not None:
                updates["flagged"] = flagged
            if answered is not None:
                updates["answered"] = answered
            if draft is not None:
                updates["draft"] = draft
            updated = message.model_copy(update=updates)
            collection[index] = updated
            return updated
        raise MailUidNotFoundError(mailbox=mailbox, uid=uid)

    async def uid_store_flags(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
        add_flags: list[str],
        remove_flags: list[str],
    ) -> None:
        _ = binding_secret
        self.uid_store_flags_calls.append((mailbox, uid, list(add_flags), list(remove_flags)))
        unread: bool | None = None
        flagged: bool | None = None
        answered: bool | None = None
        draft: bool | None = None
        normalized_add = {flag.upper().lstrip("\\") for flag in add_flags}
        normalized_remove = {flag.upper().lstrip("\\") for flag in remove_flags}
        if "SEEN" in normalized_add:
            unread = False
        if "SEEN" in normalized_remove:
            unread = True
        if "FLAGGED" in normalized_add:
            flagged = True
        if "FLAGGED" in normalized_remove:
            flagged = False
        if "ANSWERED" in normalized_add:
            answered = True
        if "ANSWERED" in normalized_remove:
            answered = False
        if "DRAFT" in normalized_add:
            draft = True
        if "DRAFT" in normalized_remove:
            draft = False
        if "DELETED" in normalized_add:
            await self.uid_expunge(binding_secret, mailbox=mailbox, uid=uid)
            return
        _ = self._mutate_message_flags(
            mailbox,
            uid,
            unread=unread,
            flagged=flagged,
            answered=answered,
            draft=draft,
        )

    async def uid_move(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
        destination_folder: str,
    ) -> MailUidMoveResult:
        _ = binding_secret
        self.uid_move_calls.append((mailbox, uid, destination_folder))
        message = await self.fetch_message_by_uid(
            binding_secret, mailbox=mailbox, uid=uid
        )
        if mailbox.casefold() == "inbox":
            self.inbox = [item for item in self.inbox if item.uid != uid]
        else:
            items = self.mailbox_messages.get(mailbox, [])
            self.mailbox_messages[mailbox] = [item for item in items if item.uid != uid]
        dest_items = self.mailbox_messages.setdefault(destination_folder, [])
        new_uid = str(max((int(item.uid) for item in dest_items), default=0) + 1)
        dest_items.append(message.model_copy(update={"uid": new_uid}))
        return MailUidMoveResult(
            source_uid=uid,
            destination_folder=destination_folder,
            destination_uid=new_uid,
        )

    async def uid_expunge(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str | None = None,
    ) -> None:
        _ = binding_secret
        self.uid_expunge_calls.append((mailbox, uid))
        if uid is None:
            if mailbox.casefold() == "inbox":
                self.inbox = []
            else:
                self.mailbox_messages[mailbox] = []
            return
        if mailbox.casefold() == "inbox":
            self.inbox = [item for item in self.inbox if item.uid != uid]
        else:
            items = self.mailbox_messages.get(mailbox, [])
            self.mailbox_messages[mailbox] = [item for item in items if item.uid != uid]

    async def append_message(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        raw_message: bytes,
        flags: str | None = None,
    ) -> MailAppendResult:
        _ = binding_secret
        self.append_message_calls.append((mailbox, flags if flags is not None else ""))
        items = self.mailbox_messages.setdefault(mailbox, [])
        new_uid = str(max((int(item.uid) for item in items), default=0) + 1)
        message_id = f"append-{new_uid}@fake.local"
        subject = "appended"
        for line in raw_message.split(b"\n"):
            lower = line.lower()
            if lower.startswith(b"message-id:"):
                message_id = line.split(b":", 1)[1].decode("utf-8", errors="replace").strip()
            elif lower.startswith(b"subject:"):
                subject = line.split(b":", 1)[1].decode("utf-8", errors="replace").strip()
        draft = flags is not None and "DRAFT" in flags.upper()
        unread = flags is None or "SEEN" not in flags.upper()
        items.append(
            InboundMailMessage(
                uid=new_uid,
                message_id=message_id,
                subject=subject,
                from_address=binding_secret.email_address,
                body_text=raw_message.decode("utf-8", errors="replace"),
                unread=unread,
                draft=draft,
            )
        )
        return MailAppendResult(folder=mailbox, uid=new_uid, message_id=message_id)

    async def uid_search(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        criteria: MailUidSearchCriteria,
    ) -> list[str]:
        _ = binding_secret
        items = self._messages_for_mailbox(mailbox)
        if criteria.uid_set is not None and criteria.uid_set.strip():
            wanted = {part.strip() for part in criteria.uid_set.replace(":", ",").split(",") if part.strip()}
            return [item.uid for item in items if item.uid in wanted]
        if criteria.all_messages:
            return [item.uid for item in items]
        matched = items
        if criteria.subject is not None:
            needle = criteria.subject.casefold()
            matched = [
                item
                for item in matched
                if item.subject is not None and needle in item.subject.casefold()
            ]
        if criteria.from_address is not None:
            needle = criteria.from_address.casefold()
            matched = [
                item
                for item in matched
                if item.from_address is not None and needle in item.from_address.casefold()
            ]
        if criteria.text is not None:
            needle = criteria.text.casefold()
            matched = [
                item
                for item in matched
                if (item.body_text is not None and needle in item.body_text.casefold())
                or (item.subject is not None and needle in item.subject.casefold())
            ]
        return [item.uid for item in matched]

    async def fetch_flags_for_uids(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uids: list[str],
    ) -> dict[str, MailMessageFlags]:
        _ = binding_secret
        result: dict[str, MailMessageFlags] = {}
        for uid in uids:
            try:
                message = await self.fetch_message_by_uid(
                    binding_secret, mailbox=mailbox, uid=uid
                )
            except MailUidNotFoundError:
                continue
            result[uid] = MailMessageFlags(
                unread=message.unread,
                flagged=message.flagged,
                answered=message.answered,
                draft=message.draft,
            )
        return result

    async def open_idle_session(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
    ) -> _FakeIdleSession:
        _ = binding_secret
        return _FakeIdleSession(mailbox=mailbox, wake=self.idle_wake)
