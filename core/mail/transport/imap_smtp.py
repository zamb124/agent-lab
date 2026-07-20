"""IMAP/SMTP transport поверх aioimaplib и aiosmtplib."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Sequence
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Final, Protocol, cast, final

import aioimaplib
import aiosmtplib

from core.mail.exceptions import (
    MailFolderCreateError,
    MailMailboxNotFoundError,
    MailTransportError,
    MailUidNotFoundError,
)
from core.mail.imap_folders import (
    STANDARD_ENSURE_ROLES,
    build_mail_folder_list_result,
    is_imap_already_exists_response,
    parse_imap_list_lines,
    parse_namespace_personal_prefix,
    special_use_flag_for_role,
    standard_folder_name,
)
from core.mail.mime_parse import parse_inbound_rfc822, strip_attachment_payloads
from core.mail.models import (
    InboundMailMessage,
    MailAppendResult,
    MailboxSecret,
    MailFetchQuery,
    MailFolder,
    MailFolderListResult,
    MailFolderRole,
    MailMessageFlags,
    MailSendResult,
    MailUidBatch,
    MailUidMoveResult,
    MailUidSearchCriteria,
    OutboundMailMessage,
)
from core.mail.threads import message_belongs_to_thread_ids
from core.mail.transport.idle_session import MailIdleSession


class _ImapCommandResponse(Protocol):
    result: str
    lines: list[object]


class _ImapListClient(Protocol):
    def list(self, reference_name: str, mailbox_pattern: str) -> Awaitable[_ImapCommandResponse]: ...


class _ImapNamespaceClient(Protocol):
    def namespace(self) -> Awaitable[_ImapCommandResponse]: ...


class _ImapCreateClient(Protocol):
    def create(self, mailbox_name: str) -> Awaitable[_ImapCommandResponse]: ...


class _ImapStatusClient(Protocol):
    def status(self, mailbox: str, names: str) -> Awaitable[_ImapCommandResponse]: ...


class _ImapProtocolCapabilities(Protocol):
    capabilities: set[str] | frozenset[str] | list[str] | tuple[str, ...]


class _ImapCapabilityClient(Protocol):
    def has_capability(self, capability: str) -> bool: ...

    @property
    def protocol(self) -> _ImapProtocolCapabilities: ...


class _ImapTimeoutClient(Protocol):
    timeout: float


class _ImapExpungeClient(Protocol):
    def expunge(self) -> Awaitable[_ImapCommandResponse]: ...


_HEADER_FETCH = (
    "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT MESSAGE-ID TO DATE IN-REPLY-TO REFERENCES)] UID)"
)
# BODY.PEEK[] — не RFC822: FETCH без PEEK на многих серверах ставит \Seen,
# и list_messages помечает всю папку прочитанной ещё до открытия письма.
_BODY_FETCH = "(FLAGS BODY.PEEK[])"
_MAX_THREAD_SEARCH_IDS = 16


def _imap_quoted_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _build_thread_header_search_criteria(message_ids: Sequence[str]) -> str:
    if not message_ids:
        raise ValueError("message_ids required for thread SEARCH")
    limited = list(message_ids)[:_MAX_THREAD_SEARCH_IDS]
    keys: list[str] = []
    for message_id in limited:
        quoted = _imap_quoted_string(message_id)
        keys.append(f"HEADER Message-ID {quoted}")
        keys.append(f"HEADER In-Reply-To {quoted}")
        keys.append(f"HEADER References {quoted}")
    expression = keys[-1]
    for key in reversed(keys[:-1]):
        expression = f"OR {key} {expression}"
    return expression


def _parse_message_flags_blob(flags_blob: str) -> MailMessageFlags:
    tokens = {token.upper().lstrip("\\") for token in flags_blob.replace("\\", " \\").split()}
    tokens = {token for token in tokens if token}
    return MailMessageFlags(
        unread="SEEN" not in tokens,
        flagged="FLAGGED" in tokens,
        answered="ANSWERED" in tokens,
        draft="DRAFT" in tokens,
        deleted="DELETED" in tokens,
    )


def _extract_flags_blob_from_fetch(fetch_lines: Sequence[object]) -> str | None:
    for item in fetch_lines:
        text = _decode_imap_line(item).upper()
        marker = "FLAGS"
        idx = text.find(marker)
        if idx < 0:
            continue
        rest = text[idx + len(marker) :].lstrip()
        if not rest.startswith("("):
            continue
        depth = 0
        end = -1
        for pos, char in enumerate(rest):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = pos
                    break
        if end < 0:
            continue
        return rest[1:end]
    return None


def _extract_message_flags_from_fetch(fetch_lines: Sequence[object]) -> MailMessageFlags:
    """FLAGS из FETCH. Нет FLAGS → unread=True (не угадываем Seen)."""
    blob = _extract_flags_blob_from_fetch(fetch_lines)
    if blob is None:
        return MailMessageFlags()
    return _parse_message_flags_blob(blob)


def _apply_flags_to_inbound(
    inbound: InboundMailMessage,
    flags: MailMessageFlags,
) -> InboundMailMessage:
    return inbound.model_copy(
        update={
            "unread": flags.unread,
            "flagged": flags.flagged,
            "answered": flags.answered,
            "draft": flags.draft,
        }
    )


def _build_uid_search_criteria(criteria: MailUidSearchCriteria) -> str:
    parts: list[str] = []
    if criteria.all_messages:
        parts.append("ALL")
    if criteria.uid_set is not None and criteria.uid_set.strip():
        parts.append(f"UID {criteria.uid_set.strip()}")
    if criteria.text is not None and criteria.text.strip():
        parts.append(f"TEXT {_imap_quoted_string(criteria.text.strip())}")
    if criteria.from_address is not None and criteria.from_address.strip():
        parts.append(f"FROM {_imap_quoted_string(criteria.from_address.strip())}")
    if criteria.subject is not None and criteria.subject.strip():
        parts.append(f"SUBJECT {_imap_quoted_string(criteria.subject.strip())}")
    if (
        criteria.header_name is not None
        and criteria.header_name.strip()
        and criteria.header_value is not None
    ):
        header_name = criteria.header_name.strip()
        header_value = _imap_quoted_string(criteria.header_value)
        parts.append(f"HEADER {header_name} {header_value}")
    if not parts:
        raise ValueError("MailUidSearchCriteria requires at least one criterion")
    return " ".join(parts)


def _parse_copyuid_destination(response_text: str) -> str | None:
    """Parse COPYUID / MOVEUID: `OK [COPYUID uidvalidity srcset destset]`."""
    upper = response_text.upper()
    for marker in ("COPYUID ", "MOVEUID "):
        idx = upper.find(marker)
        if idx < 0:
            continue
        rest = response_text[idx + len(marker) :].strip().rstrip("]")
        tokens = rest.split()
        if len(tokens) < 3:
            continue
        dest = tokens[2]
        if ":" in dest:
            dest = dest.split(":", 1)[1]
        if "," in dest:
            dest = dest.split(",")[-1]
        if dest.isdigit():
            return dest
    return None


def _format_flags_paren(flags: list[str]) -> str:
    if not flags:
        raise ValueError("flags list is required")
    return "(" + " ".join(flags) + ")"


_FLAGS_FETCH = "(FLAGS UID)"
_UID_FETCH_BATCH = 50


def _parse_status_attr_blob(blob: str) -> tuple[int, int] | None:
    """`(MESSAGES n UNSEEN m …)` → counts. Нет обоих ключей → None."""
    tokens = blob.upper().split()
    messages: int | None = None
    unseen: int | None = None
    token_index = 0
    while token_index < len(tokens) - 1:
        key = tokens[token_index]
        value_text = tokens[token_index + 1]
        if not value_text.isdigit():
            token_index += 1
            continue
        value = int(value_text)
        if key == "MESSAGES":
            messages = value
        elif key == "UNSEEN":
            unseen = value
        token_index += 2
    if messages is None or unseen is None:
        return None
    return messages, unseen


def _parse_status_counts(lines: Sequence[object]) -> tuple[int, int]:
    """Из строк STATUS → (MESSAGES, UNSEEN).

    aioimaplib часто отдаёт untagged без `* STATUS ` — только
    `INBOX (MESSAGES 10 UNSEEN 2)` или `"Sent" (MESSAGES 0 UNSEEN 0)`.
    """
    for item in lines:
        text = _decode_imap_line(item).strip()
        if not text:
            continue
        upper = text.upper()
        if upper.startswith("OK ") or upper.endswith(" COMPLETED"):
            continue
        # Ищем attr-list с MESSAGES (не первое `(attrs)` у LIST).
        search_from = 0
        while True:
            paren = upper.find("(", search_from)
            if paren < 0:
                break
            end = upper.find(")", paren)
            if end < 0:
                break
            blob = upper[paren + 1 : end]
            if "MESSAGES" in blob.split() or "UNSEEN" in blob.split():
                parsed = _parse_status_attr_blob(blob)
                if parsed is not None:
                    return parsed
            search_from = end + 1
    raise ValueError("IMAP STATUS response missing MESSAGES/UNSEEN")


def _quote_mailbox_name(name: str) -> str:
    if name.casefold() == "inbox":
        return "INBOX"
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _client_capabilities(client: aioimaplib.IMAP4_SSL) -> list[str]:
    capability_client = cast(_ImapCapabilityClient, cast(object, client))
    raw_caps = capability_client.protocol.capabilities
    return sorted(str(item) for item in raw_caps)

def _decode_imap_line(line: object) -> str:
    if isinstance(line, bytes):
        return line.decode("utf-8", errors="replace")
    if isinstance(line, str):
        return line
    return str(line)


def _parse_uidvalidity(select_lines: list[object]) -> int:
    for line in select_lines:
        text = _decode_imap_line(line).upper()
        marker = "UIDVALIDITY "
        idx = text.find(marker)
        if idx < 0:
            continue
        rest = text[idx + len(marker) :]
        digits: list[str] = []
        for char in rest:
            if char.isdigit():
                digits.append(char)
            elif digits:
                break
        if digits:
            return int("".join(digits))
    raise RuntimeError("IMAP SELECT response missing UIDVALIDITY")


def _parse_uid_list(search_lines: list[object]) -> list[str]:
    uids: list[str] = []
    for line in search_lines:
        text = _decode_imap_line(line)
        for part in text.split():
            if part.isdigit():
                uids.append(part)
    return uids


class _ImapAppendClient(Protocol):
    def append(
        self,
        message_bytes: bytes,
        mailbox: str = "INBOX",
        flags: str | None = None,
        date: object | None = None,
    ) -> Awaitable[_ImapCommandResponse]: ...


def _extract_header_bytes(fetch_lines: Sequence[object]) -> bytes | None:
    for item in fetch_lines:
        if not isinstance(item, (bytes, bytearray)):
            continue
        payload = bytes(item)
        if payload.startswith(b"Fetch ") or b"FETCH (" in payload[:96]:
            continue
        if (
            b"From:" in payload
            or b"Subject:" in payload
            or b"Message-ID:" in payload
            or b"\n\n" in payload
        ):
            return payload
        if len(payload) > 40 and (b"@" in payload or b":" in payload):
            return payload
    return None


def _extract_rfc822_bytes(fetch_lines: Sequence[object]) -> bytes | None:
    raw_bytes: bytes | None = None
    for item in fetch_lines:
        if not isinstance(item, (bytes, bytearray)):
            continue
        payload = bytes(item)
        if payload.startswith(b"Fetch ") or b"FETCH (" in payload[:96]:
            continue
        if (
            b"From:" in payload
            or b"Subject:" in payload
            or b"Return-path:" in payload
            or b"\n\n" in payload
        ):
            raw_bytes = payload
            break
        if len(payload) > 200 and b"@" in payload:
            raw_bytes = payload
            break
    return raw_bytes


@final
class ImapSmtpTransport:
    def __init__(
        self,
        *,
        imap_host: str,
        imap_port: int,
        smtp_host: str,
        smtp_port: int,
        use_ssl: bool = True,
    ) -> None:
        self._imap_host: Final[str] = imap_host
        self._imap_port: Final[int] = imap_port
        self._smtp_host: Final[str] = smtp_host
        self._smtp_port: Final[int] = smtp_port
        self._use_ssl: Final[bool] = use_ssl

    async def _connect_smtp(self, *, timeout: float = 30.0) -> aiosmtplib.SMTP:
        last_error: Exception | None = None
        for attempt in range(3):
            smtp = aiosmtplib.SMTP(
                hostname=self._smtp_host,
                port=self._smtp_port,
                use_tls=self._use_ssl,
                timeout=timeout,
            )
            try:
                _ = await smtp.connect()
                return smtp
            except (TimeoutError, OSError, aiosmtplib.SMTPException) as exc:
                last_error = exc
                await asyncio.sleep(1.5 * float(attempt + 1))
        if last_error is None:
            raise MailTransportError("SMTP connect failed without error")
        raise MailTransportError(f"SMTP connect failed: {last_error}") from last_error

    async def _connect_imap(self, *, timeout: float = 30.0) -> aioimaplib.IMAP4_SSL:
        last_error: Exception | None = None
        for attempt in range(3):
            client = aioimaplib.IMAP4_SSL(host=self._imap_host, port=self._imap_port)
            cast(_ImapTimeoutClient, cast(object, client)).timeout = timeout
            try:
                await client.wait_hello_from_server()
                return client
            except (TimeoutError, OSError) as exc:
                last_error = exc
                await asyncio.sleep(1.5 * float(attempt + 1))
        if last_error is None:
            raise MailTransportError("IMAP connect failed without error")
        raise MailTransportError(f"IMAP connect failed: {last_error}") from last_error

    async def _login_imap(self, binding_secret: MailboxSecret) -> aioimaplib.IMAP4_SSL:
        client = await self._connect_imap()
        try:
            login_response = await client.login(
                binding_secret.email_address,
                binding_secret.password,
            )
        except (TimeoutError, OSError) as exc:
            raise MailTransportError(
                f"IMAP login failed for {binding_secret.email_address}: {exc}"
            ) from exc
        if login_response.result != "OK":
            _ = await client.logout()
            raise MailTransportError(
                f"IMAP login failed for {binding_secret.email_address}: {login_response}"
            )
        return client

    async def check_imap_hello(self) -> None:
        client = await self._connect_imap(timeout=15.0)
        _ = await client.logout()

    async def check_smtp_connect(self) -> None:
        smtp = await self._connect_smtp(timeout=15.0)
        _ = await smtp.quit()

    async def check_imap_login(self, secret: MailboxSecret) -> None:
        client = await self._login_imap(secret)
        _ = await client.logout()

    async def check_smtp(self, secret: MailboxSecret) -> None:
        smtp = await self._connect_smtp()
        try:
            _ = await smtp.login(secret.email_address, secret.password)
        finally:
            _ = await smtp.quit()
    async def send_message(
        self,
        binding_secret: MailboxSecret,
        message: OutboundMailMessage,
    ) -> MailSendResult:
        from_address = message.from_address
        if from_address is None:
            from_address = binding_secret.email_address
        message_id = message.message_id
        if message_id is None:
            message_id = make_msgid(domain=from_address.split("@", 1)[1])

        mime = EmailMessage()
        mime["From"] = from_address
        mime["To"] = ", ".join(message.to_addresses)
        mime["Subject"] = message.subject
        mime["Message-ID"] = message_id
        mime["Date"] = formatdate(localtime=True)
        if message.in_reply_to is not None:
            mime["In-Reply-To"] = message.in_reply_to
        if message.references is not None:
            mime["References"] = message.references
        if message.body_html is not None and message.body_html.strip():
            mime.set_content(message.body_text)
            mime.add_alternative(message.body_html, subtype="html")
        else:
            mime.set_content(message.body_text)
        for attachment in message.attachments:
            if not attachment.content:
                raise MailTransportError(
                    f"outbound attachment content required filename={attachment.filename!r}"
                )
            maintype, _, subtype = attachment.content_type.partition("/")
            if not subtype:
                maintype = "application"
                subtype = "octet-stream"
            mime.add_attachment(
                attachment.content,
                maintype=maintype,
                subtype=subtype,
                filename=attachment.filename,
            )

        smtp = await self._connect_smtp()
        try:
            _ = await smtp.login(binding_secret.email_address, binding_secret.password)
            errors, response = await smtp.send_message(mime)
            if errors:
                raise MailTransportError(
                    f"SMTP recipients refused for {from_address}: {errors!r} response={response!r}"
                )
        finally:
            _ = await smtp.quit()

        await self._append_sent_copy(binding_secret, mime.as_bytes())
        return MailSendResult(message_id=message_id, accepted=list(message.to_addresses))

    async def _resolve_sent_mailbox_name(
        self,
        client: aioimaplib.IMAP4_SSL,
    ) -> str:
        folders = await self._list_folders_on_client(client)
        for folder in folders.folders:
            if folder.role == MailFolderRole.SENT and folder.selectable:
                return folder.name
        sent_name = standard_folder_name(
            role=MailFolderRole.SENT,
            namespace_prefix=folders.namespace_prefix,
        )
        await self._create_folder_on_client(
            client,
            name=sent_name,
            role=MailFolderRole.SENT,
        )
        return sent_name

    async def _append_sent_copy(
        self,
        binding_secret: MailboxSecret,
        raw_message: bytes,
    ) -> None:
        client = await self._login_imap(binding_secret)
        try:
            sent_name = await self._resolve_sent_mailbox_name(client)
            append_client = cast(_ImapAppendClient, cast(object, client))
            append_response = await append_client.append(
                raw_message,
                mailbox=_quote_mailbox_name(sent_name),
                flags=r"(\Seen)",
            )
            if append_response.result != "OK":
                raise MailTransportError(
                    f"IMAP APPEND to Sent failed for mailbox={sent_name!r}: {append_response}"
                )
        finally:
            _ = await client.logout()

    async def _select_exact(
        self,
        client: aioimaplib.IMAP4_SSL,
        mailbox_name: str,
    ) -> _ImapCommandResponse:
        select_response = cast(
            _ImapCommandResponse,
            cast(object, await client.select(_quote_mailbox_name(mailbox_name))),
        )
        if select_response.result != "OK":
            raise MailMailboxNotFoundError(folder_name=mailbox_name)
        return select_response

    async def _list_folders_on_client(self, client: aioimaplib.IMAP4_SSL) -> MailFolderListResult:
        capabilities = _client_capabilities(client)
        namespace_prefix = ""
        namespace_delimiter: str | None = None
        capability_client = cast(_ImapCapabilityClient, cast(object, client))
        if capability_client.has_capability("NAMESPACE"):
            ns_client = cast(_ImapNamespaceClient, cast(object, client))
            ns_response = await ns_client.namespace()
            if ns_response.result == "OK":
                namespace_prefix, namespace_delimiter = parse_namespace_personal_prefix(
                    list(ns_response.lines)
                )
        list_client = cast(_ImapListClient, cast(object, client))
        list_response = await list_client.list('""', "*")
        if list_response.result != "OK":
            raise MailTransportError(f"IMAP LIST failed: {list_response}")
        entries = parse_imap_list_lines(list(list_response.lines))
        if not entries:
            list_percent = await list_client.list('""', "%")
            if list_percent.result == "OK":
                entries = parse_imap_list_lines(list(list_percent.lines))
        base = build_mail_folder_list_result(
            list_entries=entries,
            namespace_prefix=namespace_prefix,
            namespace_delimiter=namespace_delimiter,
            capabilities=capabilities,
        )
        return await self._enrich_folder_counts(client, base)

    async def _status_counts(
        self,
        client: aioimaplib.IMAP4_SSL,
        mailbox_name: str,
    ) -> tuple[int, int]:
        status_client = cast(_ImapStatusClient, cast(object, client))
        status_response = await status_client.status(
            _quote_mailbox_name(mailbox_name),
            "(MESSAGES UNSEEN)",
        )
        if status_response.result != "OK":
            raise MailTransportError(
                f"IMAP STATUS failed for mailbox={mailbox_name!r}: {status_response}"
            )
        try:
            return _parse_status_counts(list(status_response.lines))
        except ValueError as exc:
            raise MailTransportError(
                f"IMAP STATUS parse failed for mailbox={mailbox_name!r}"
            ) from exc

    async def _enrich_folder_counts(
        self,
        client: aioimaplib.IMAP4_SSL,
        result: MailFolderListResult,
    ) -> MailFolderListResult:
        enriched: list[MailFolder] = []
        for folder in result.folders:
            if not folder.selectable:
                enriched.append(folder)
                continue
            message_count, unseen_count = await self._status_counts(client, folder.name)
            enriched.append(
                folder.model_copy(
                    update={
                        "message_count": message_count,
                        "unseen_count": unseen_count,
                    }
                )
            )
        return result.model_copy(update={"folders": enriched})

    async def _create_folder_on_client(
        self,
        client: aioimaplib.IMAP4_SSL,
        *,
        name: str,
        role: MailFolderRole | None,
    ) -> None:
        create_client = cast(_ImapCreateClient, cast(object, client))
        capability_client = cast(_ImapCapabilityClient, cast(object, client))
        quoted = _quote_mailbox_name(name)
        create_arg = quoted
        if role is not None and capability_client.has_capability("SPECIAL-USE"):
            use_flag = special_use_flag_for_role(role)
            if use_flag is not None:
                create_arg = f"{quoted} (USE ({use_flag}))"
        create_response = await create_client.create(create_arg)
        if create_response.result == "OK":
            return
        if is_imap_already_exists_response(create_response):
            return
        raise MailFolderCreateError(
            folder_name=name,
            role=role.value if role is not None else None,
            detail=str(create_response),
        )

    async def list_imap_folders(self, binding_secret: MailboxSecret) -> MailFolderListResult:
        client = await self._login_imap(binding_secret)
        try:
            return await self._list_folders_on_client(client)
        finally:
            _ = await client.logout()

    async def create_imap_folder(
        self,
        binding_secret: MailboxSecret,
        *,
        name: str,
        role: MailFolderRole | None = None,
    ) -> None:
        if not name.strip():
            raise ValueError("IMAP folder name is required")
        client = await self._login_imap(binding_secret)
        try:
            await self._create_folder_on_client(client, name=name, role=role)
        finally:
            _ = await client.logout()

    async def ensure_standard_imap_folders(
        self,
        binding_secret: MailboxSecret,
    ) -> MailFolderListResult:
        """LIST + CREATE missing sent/drafts/trash + LIST в одной IMAP-сессии."""
        client = await self._login_imap(binding_secret)
        try:
            current = await self._list_folders_on_client(client)
            existing_names = {folder.name for folder in current.folders}
            for role in STANDARD_ENSURE_ROLES:
                if role not in current.missing_standard_roles:
                    continue
                folder_name = standard_folder_name(
                    role=role,
                    namespace_prefix=current.namespace_prefix,
                )
                if folder_name in existing_names:
                    continue
                await self._create_folder_on_client(client, name=folder_name, role=role)
                existing_names.add(folder_name)
            return await self._list_folders_on_client(client)
        finally:
            _ = await client.logout()

    async def fetch_messages(
        self,
        binding_secret: MailboxSecret,
        query: MailFetchQuery,
    ) -> list[InboundMailMessage]:
        client = await self._login_imap(binding_secret)
        try:
            _ = await self._select_exact(client, query.mailbox)

            search_response = await client.uid_search("ALL")
            if search_response.result != "OK":
                raise RuntimeError(f"IMAP UID SEARCH failed: {search_response}")
            uids = _parse_uid_list(list(search_response.lines))
            uids = uids[-max(query.limit * 5, query.limit) :]
            messages: list[InboundMailMessage] = []
            fetch_item = _BODY_FETCH if query.include_bodies else _HEADER_FETCH
            for uid in uids:
                fetch_response = await client.uid("fetch", uid, fetch_item)
                if fetch_response.result != "OK":
                    messages.append(
                        InboundMailMessage(
                            uid=uid,
                            message_id=None,
                            subject=None,
                            from_address=None,
                            unread=True,
                        )
                    )
                    continue
                fetch_lines = list(fetch_response.lines)
                flags = _extract_message_flags_from_fetch(fetch_lines)
                raw_bytes = (
                    _extract_rfc822_bytes(fetch_lines)
                    if query.include_bodies
                    else _extract_header_bytes(fetch_lines)
                )
                if raw_bytes is None:
                    messages.append(
                        InboundMailMessage(
                            uid=uid,
                            message_id=None,
                            subject=None,
                            from_address=None,
                            unread=flags.unread,
                            flagged=flags.flagged,
                            answered=flags.answered,
                            draft=flags.draft,
                        )
                    )
                    continue
                inbound = parse_inbound_rfc822(uid, raw_bytes)
                inbound = _apply_flags_to_inbound(inbound, flags)
                if not query.include_bodies:
                    # List: без тел и без байтов вложений; метаданные вложений сохраняем
                    # если HEADER/парсер их когда-либо отдаст (BODYSTRUCTURE — отдельно).
                    inbound = strip_attachment_payloads(inbound)
                    inbound = inbound.model_copy(update={"body_text": None})
                if query.subject_contains is not None:
                    if inbound.subject is None or query.subject_contains not in inbound.subject:
                        continue
                if query.message_id is not None:
                    if inbound.message_id is None or query.message_id not in inbound.message_id:
                        continue
                messages.append(inbound)
            # IMAP UID ascending → UI newest first
            newest_first = list(reversed(messages[-query.limit :]))
            return newest_first
        finally:
            _ = await client.logout()

    async def fetch_message_by_uid(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
    ) -> InboundMailMessage:
        if not uid.strip():
            raise ValueError("uid is required")
        client = await self._login_imap(binding_secret)
        try:
            _ = await self._select_exact(client, mailbox)
            fetch_response = await client.uid("fetch", uid, _BODY_FETCH)
            if fetch_response.result != "OK":
                raise MailUidNotFoundError(mailbox=mailbox, uid=uid)
            fetch_lines = list(fetch_response.lines)
            raw_bytes = _extract_rfc822_bytes(fetch_lines)
            if raw_bytes is None:
                raise MailUidNotFoundError(mailbox=mailbox, uid=uid)
            inbound = parse_inbound_rfc822(uid, raw_bytes)
            flags = _extract_message_flags_from_fetch(fetch_lines)
            inbound = _apply_flags_to_inbound(inbound, flags)
            return inbound
        finally:
            _ = await client.logout()

    async def search_messages_by_thread_ids(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        message_ids: set[str],
        subject_key: str | None = None,
        limit: int = 100,
    ) -> list[InboundMailMessage]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        resolved_subject = subject_key.strip() if subject_key is not None else ""
        if not message_ids and not resolved_subject:
            raise ValueError("message_ids or subject_key required for thread search")
        client = await self._login_imap(binding_secret)
        try:
            _ = await self._select_exact(client, mailbox)
            uids: list[str] = []
            if message_ids:
                criteria = _build_thread_header_search_criteria(sorted(message_ids))
                search_response = await client.uid_search(criteria)
                if search_response.result != "OK":
                    raise MailTransportError(
                        f"IMAP UID SEARCH thread headers failed: {search_response}"
                    )
                uids = _parse_uid_list(list(search_response.lines))
            if resolved_subject:
                all_response = await client.uid_search("ALL")
                if all_response.result != "OK":
                    raise MailTransportError(
                        f"IMAP UID SEARCH ALL failed: {all_response}"
                    )
                known = set(uids)
                for uid in _parse_uid_list(list(all_response.lines))[-max(limit * 3, limit) :]:
                    if uid not in known:
                        uids.append(uid)
                        known.add(uid)
            messages: list[InboundMailMessage] = []
            for uid in uids:
                fetch_response = await client.uid("fetch", uid, _BODY_FETCH)
                if fetch_response.result != "OK":
                    continue
                fetch_lines = list(fetch_response.lines)
                raw_bytes = _extract_rfc822_bytes(fetch_lines)
                if raw_bytes is None:
                    continue
                inbound = parse_inbound_rfc822(uid, raw_bytes)
                flags = _extract_message_flags_from_fetch(fetch_lines)
                inbound = _apply_flags_to_inbound(inbound, flags)
                if not message_belongs_to_thread_ids(
                    inbound,
                    thread_ids=message_ids,
                    subject_key=resolved_subject if resolved_subject else None,
                ):
                    continue
                messages.append(inbound)
                if len(messages) >= limit:
                    break
            return messages
        finally:
            _ = await client.logout()

    async def mark_message_seen(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
    ) -> None:
        if not uid.strip():
            raise ValueError("uid is required")
        client = await self._login_imap(binding_secret)
        try:
            _ = await self._select_exact(client, mailbox)
            store_response = await client.uid("store", uid, "+FLAGS", r"(\Seen)")
            if store_response.result != "OK":
                raise MailTransportError(
                    f"IMAP UID STORE +FLAGS (\\Seen) failed for uid={uid}: {store_response}"
                )
        finally:
            _ = await client.logout()

    async def mark_message_unseen(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
    ) -> None:
        if not uid.strip():
            raise ValueError("uid is required")
        client = await self._login_imap(binding_secret)
        try:
            _ = await self._select_exact(client, mailbox)
            store_response = await client.uid("store", uid, "-FLAGS", r"(\Seen)")
            if store_response.result != "OK":
                raise MailTransportError(
                    f"IMAP UID STORE -FLAGS (\\Seen) failed for uid={uid}: {store_response}"
                )
        finally:
            _ = await client.logout()

    async def fetch_uids_since(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        since_uid: int,
        limit: int,
    ) -> MailUidBatch:
        if since_uid < 0:
            raise ValueError("since_uid must be >= 0")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        client = await self._login_imap(binding_secret)
        try:
            select_response = await self._select_exact(client, mailbox)
            uidvalidity = _parse_uidvalidity(list(select_response.lines))

            search_response = await client.uid_search("ALL")
            if search_response.result != "OK":
                raise RuntimeError(f"IMAP UID SEARCH failed: {search_response}")
            all_uids = _parse_uid_list(list(search_response.lines))
            max_uid = max((int(uid) for uid in all_uids), default=0)

            # Bootstrap / empty since: только состояние mailbox, без header fetch.
            if since_uid <= 0:
                return MailUidBatch(uidvalidity=uidvalidity, max_uid=max_uid, messages=[])

            new_uids = sorted(
                (uid for uid in all_uids if int(uid) > since_uid),
                key=int,
            )[:limit]
            messages: list[InboundMailMessage] = []
            for uid in new_uids:
                fetch_response = await client.uid("fetch", uid, _HEADER_FETCH)
                if fetch_response.result != "OK":
                    raise RuntimeError(f"IMAP UID FETCH failed for uid={uid}: {fetch_response}")
                fetch_lines = list(fetch_response.lines)
                flags = _extract_message_flags_from_fetch(fetch_lines)
                raw_bytes = _extract_header_bytes(fetch_lines)
                if raw_bytes is None:
                    messages.append(
                        InboundMailMessage(
                            uid=uid,
                            message_id=None,
                            subject=None,
                            from_address=None,
                            unread=flags.unread,
                            flagged=flags.flagged,
                            answered=flags.answered,
                            draft=flags.draft,
                        )
                    )
                    continue
                inbound = parse_inbound_rfc822(uid, raw_bytes)
                messages.append(_apply_flags_to_inbound(inbound, flags))
            return MailUidBatch(
                uidvalidity=uidvalidity,
                max_uid=max_uid,
                messages=messages,
            )
        finally:
            _ = await client.logout()

    async def uid_store_flags(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
        add_flags: list[str],
        remove_flags: list[str],
    ) -> None:
        if not uid.strip():
            raise ValueError("uid is required")
        if not add_flags and not remove_flags:
            raise ValueError("add_flags or remove_flags required")
        client = await self._login_imap(binding_secret)
        try:
            _ = await self._select_exact(client, mailbox)
            if add_flags:
                store_response = await client.uid(
                    "store", uid, "+FLAGS", _format_flags_paren(add_flags)
                )
                if store_response.result != "OK":
                    raise MailTransportError(
                        f"IMAP UID STORE +FLAGS failed for uid={uid}: {store_response}"
                    )
            if remove_flags:
                store_response = await client.uid(
                    "store", uid, "-FLAGS", _format_flags_paren(remove_flags)
                )
                if store_response.result != "OK":
                    raise MailTransportError(
                        f"IMAP UID STORE -FLAGS failed for uid={uid}: {store_response}"
                    )
        finally:
            _ = await client.logout()

    async def uid_move(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str,
        destination_folder: str,
    ) -> MailUidMoveResult:
        if not uid.strip():
            raise ValueError("uid is required")
        if not destination_folder.strip():
            raise ValueError("destination_folder is required")
        client = await self._login_imap(binding_secret)
        try:
            _ = await self._select_exact(client, mailbox)
            capability_client = cast(_ImapCapabilityClient, cast(object, client))
            dest_quoted = _quote_mailbox_name(destination_folder)
            destination_uid: str | None = None
            if capability_client.has_capability("MOVE"):
                move_response = await client.uid("move", uid, dest_quoted)
                if move_response.result != "OK":
                    raise MailTransportError(
                        f"IMAP UID MOVE failed uid={uid} dest={destination_folder!r}: {move_response}"
                    )
                response_text = " ".join(
                    _decode_imap_line(line) for line in move_response.lines
                )
                destination_uid = _parse_copyuid_destination(response_text)
            else:
                copy_response = await client.uid("copy", uid, dest_quoted)
                if copy_response.result != "OK":
                    raise MailTransportError(
                        f"IMAP UID COPY failed uid={uid} dest={destination_folder!r}: {copy_response}"
                    )
                response_text = " ".join(
                    _decode_imap_line(line) for line in copy_response.lines
                )
                destination_uid = _parse_copyuid_destination(response_text)
                store_response = await client.uid(
                    "store", uid, "+FLAGS", r"(\Deleted)"
                )
                if store_response.result != "OK":
                    raise MailTransportError(
                        f"IMAP UID STORE \\Deleted failed uid={uid}: {store_response}"
                    )
                expunge_response = await client.uid("expunge", uid)
                if expunge_response.result != "OK":
                    expunge_client = cast(_ImapExpungeClient, cast(object, client))
                    expunge_all = await expunge_client.expunge()
                    if expunge_all.result != "OK":
                        raise MailTransportError(
                            f"IMAP EXPUNGE failed after COPY uid={uid}: {expunge_all}"
                        )
            return MailUidMoveResult(
                source_uid=uid,
                destination_folder=destination_folder,
                destination_uid=destination_uid,
            )
        finally:
            _ = await client.logout()

    async def uid_expunge(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uid: str | None = None,
    ) -> None:
        client = await self._login_imap(binding_secret)
        try:
            _ = await self._select_exact(client, mailbox)
            if uid is not None and uid.strip():
                store_response = await client.uid(
                    "store", uid, "+FLAGS", r"(\Deleted)"
                )
                if store_response.result != "OK":
                    raise MailTransportError(
                        f"IMAP UID STORE \\Deleted failed uid={uid}: {store_response}"
                    )
                expunge_response = await client.uid("expunge", uid)
                if expunge_response.result != "OK":
                    expunge_client = cast(_ImapExpungeClient, cast(object, client))
                    expunge_all = await expunge_client.expunge()
                    if expunge_all.result != "OK":
                        raise MailTransportError(
                            f"IMAP EXPUNGE failed uid={uid}: {expunge_all}"
                        )
                return
            expunge_client = cast(_ImapExpungeClient, cast(object, client))
            expunge_all = await expunge_client.expunge()
            if expunge_all.result != "OK":
                raise MailTransportError(f"IMAP EXPUNGE failed: {expunge_all}")
        finally:
            _ = await client.logout()

    async def append_message(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        raw_message: bytes,
        flags: str | None = None,
    ) -> MailAppendResult:
        if not mailbox.strip():
            raise ValueError("mailbox is required")
        if not raw_message:
            raise ValueError("raw_message is required")
        client = await self._login_imap(binding_secret)
        try:
            append_client = cast(_ImapAppendClient, cast(object, client))
            append_response = await append_client.append(
                raw_message,
                mailbox=_quote_mailbox_name(mailbox),
                flags=flags,
            )
            if append_response.result != "OK":
                raise MailTransportError(
                    f"IMAP APPEND failed mailbox={mailbox!r}: {append_response}"
                )
            message_id: str | None = None
            for line in raw_message.split(b"\n"):
                if line.lower().startswith(b"message-id:"):
                    message_id = line.split(b":", 1)[1].decode("utf-8", errors="replace").strip()
                    break
            uid: str | None = None
            if message_id is not None:
                _ = await self._select_exact(client, mailbox)
                search_response = await client.uid_search(
                    f"HEADER Message-ID {_imap_quoted_string(message_id)}"
                )
                if search_response.result == "OK":
                    found = _parse_uid_list(list(search_response.lines))
                    if found:
                        uid = found[-1]
            return MailAppendResult(folder=mailbox, uid=uid, message_id=message_id)
        finally:
            _ = await client.logout()

    async def uid_search(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        criteria: MailUidSearchCriteria,
    ) -> list[str]:
        client = await self._login_imap(binding_secret)
        try:
            _ = await self._select_exact(client, mailbox)
            criteria_text = _build_uid_search_criteria(criteria)
            search_response = await client.uid_search(criteria_text)
            if search_response.result != "OK":
                raise MailTransportError(
                    f"IMAP UID SEARCH failed: {search_response}"
                )
            return _parse_uid_list(list(search_response.lines))
        finally:
            _ = await client.logout()

    async def fetch_flags_for_uids(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
        uids: list[str],
    ) -> dict[str, MailMessageFlags]:
        if not uids:
            return {}
        client = await self._login_imap(binding_secret)
        try:
            _ = await self._select_exact(client, mailbox)
            result: dict[str, MailMessageFlags] = {}
            for offset in range(0, len(uids), _UID_FETCH_BATCH):
                batch = uids[offset : offset + _UID_FETCH_BATCH]
                uid_set = ",".join(batch)
                fetch_response = await client.uid("fetch", uid_set, _FLAGS_FETCH)
                if fetch_response.result != "OK":
                    raise MailTransportError(
                        f"IMAP UID FETCH FLAGS failed: {fetch_response}"
                    )
                # Per-UID: parse lines; map by UID token in FETCH
                current_uid: str | None = None
                for item in fetch_response.lines:
                    text = _decode_imap_line(item)
                    upper = text.upper()
                    uid_marker = "UID "
                    uid_idx = upper.find(uid_marker)
                    if uid_idx >= 0:
                        rest = upper[uid_idx + len(uid_marker) :]
                        digits: list[str] = []
                        for char in rest:
                            if char.isdigit():
                                digits.append(char)
                            elif digits:
                                break
                        if digits:
                            current_uid = "".join(digits)
                    if current_uid is None:
                        continue
                    flags_blob = _extract_flags_blob_from_fetch([item])
                    if flags_blob is None:
                        continue
                    result[current_uid] = _parse_message_flags_blob(flags_blob)
                for uid in batch:
                    if uid not in result:
                        # batch FETCH omitted this UID — load flags with a per-UID FETCH
                        one = await client.uid("fetch", uid, _FLAGS_FETCH)
                        if one.result == "OK":
                            result[uid] = _extract_message_flags_from_fetch(list(one.lines))
            return result
        finally:
            _ = await client.logout()

    async def open_idle_session(
        self,
        binding_secret: MailboxSecret,
        *,
        mailbox: str,
    ) -> MailIdleSession:
        if not mailbox.strip():
            raise ValueError("mailbox is required")
        client = await self._login_imap(binding_secret)
        try:
            _ = await self._select_exact(client, mailbox)
        except Exception:
            _ = await client.logout()
            raise
        return MailIdleSession(client, mailbox=mailbox)
