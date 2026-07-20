"""MailService: connection, bindings, system ensure/reconcile."""

from __future__ import annotations

import base64
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final, final

from core.ai.company_settings import decrypt_secret, encrypt_secret
from core.clients.rag_client import RagClient
from core.config.models import MailConfig
from core.context import get_context
from core.db.repositories.company_repository import CompanyRepository
from core.db.repositories.user_repository import UserRepository
from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.registry import default_retention_for_source
from core.files.service import FilesService
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.logging import get_logger
from core.mail.attachment_index import MailAttachmentFileIndex
from core.mail.calendar_colors import default_calendar_color, require_mail_calendar_color
from core.mail.enqueue import enqueue_mail_sync_binding
from core.mail.exceptions import (
    MailBindingNotFoundError,
    MailConfigError,
    MailConnectionNotFoundError,
    MailMessageNotFoundError,
    MailPermissionError,
    MailSecretMissingError,
    MailSystemConnectionReadOnlyError,
    MailUidNotFoundError,
)
from core.mail.factory import build_mail_server_port
from core.mail.models import (
    CompanyMailConnection,
    CompanyMailConnectionPublic,
    CompanyMailConnectionUpsertPayload,
    InboundMailMessage,
    InboundMailMessagePublic,
    IspmanagerProvisionConfig,
    MailAttachmentPublic,
    MailboxBinding,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailboxBindingMember,
    MailboxBindingMemberPayload,
    MailboxBindingPatchPayload,
    MailboxBindingPublic,
    MailboxEnsureSpec,
    MailboxSecret,
    MailboxSyncCursor,
    MailConnectionStatus,
    MailDraftSavePayload,
    MailDraftSaveResult,
    MailFetchQuery,
    MailFolder,
    MailFolderListResult,
    MailFolderRole,
    MailImapSystemFlag,
    MailMessageFlagPayload,
    MailMessageFlagResult,
    MailMessageListItem,
    MailMessageListPayload,
    MailMessageListResult,
    MailMessageMovePayload,
    MailMessageMoveResult,
    MailMessageSearchPayload,
    MailMessageStarPayload,
    MailMessageStarResult,
    MailProvider,
    MailReconcileResult,
    MailSendPayload,
    MailSendResult,
    MailServerHealth,
    MailSyncBindingResult,
    MailSyncErrorKind,
    MailSyncLagStats,
    MailSyncNowPayload,
    MailSyncNowResult,
    MailThreadMessagePublic,
    MailThreadPayload,
    MailThreadResult,
    MailUidSearchCriteria,
    OutboundMailMessage,
    StoredMailAttachmentRef,
    StoredMailboxFolder,
    StoredMailMessage,
)
from core.mail.mutations import build_rfc822_bytes
from core.mail.ports import MailServerPort
from core.mail.repositories import (
    INBOX_FOLDER,
    CompanyMailConnectionRepository,
    MailboxBindingMemberRepository,
    MailboxBindingRepository,
    MailboxFolderRepository,
    MailboxSyncCursorRepository,
    MailMessageRepository,
)
from core.mail.threads import thread_id_for_message
from core.models.identity_models import NamespaceKind, User
from core.namespace import (
    NamespaceService,
    ensure_personal_namespace_for_user,
    personal_namespace_name,
)
from core.pagination import decode_cursor, encode_cursor
from core.rag.models import RAGMetadata

logger = get_logger(__name__)

_LOCAL_PART_RE = re.compile(r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")


@dataclass(frozen=True, slots=True)
class _BackfillResult:
    oldest_uid: int
    completed: bool


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _slug_local_part(user: User) -> str:
    seed = user.name.strip().lower() if user.name and user.name.strip() else user.user_id.lower()
    slug = re.sub(r"[^a-z0-9]+", ".", seed)
    slug = slug.strip(".")
    if not slug:
        slug = f"user.{user.user_id.lower()}"
    slug = slug[:64].strip(".")
    if not _LOCAL_PART_RE.match(slug):
        slug = f"u.{re.sub(r'[^a-z0-9]', '', user.user_id.lower())[:40]}"
    if not _LOCAL_PART_RE.match(slug):
        raise ValueError(f"Cannot derive local_part for user_id={user.user_id}")
    return slug


def to_public_connection(connection: CompanyMailConnection) -> CompanyMailConnectionPublic:
    has_ispmanager_auth = (
        connection.ispmanager is not None
        and connection.ispmanager.authinfo_password_encrypted is not None
        and bool(connection.ispmanager.authinfo_password_encrypted.strip())
    )
    return CompanyMailConnectionPublic(
        company_mail_connection_id=connection.company_mail_connection_id,
        company_id=connection.company_id,
        mail_domain=connection.mail_domain,
        provider=connection.provider,
        imap_host=connection.imap_host,
        imap_port=connection.imap_port,
        smtp_host=connection.smtp_host,
        smtp_port=connection.smtp_port,
        use_ssl=connection.use_ssl,
        supports_provision=connection.supports_provision,
        status=connection.status,
        has_ispmanager_auth=has_ispmanager_auth,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


def to_public_binding(binding: MailboxBinding) -> MailboxBindingPublic:
    return MailboxBindingPublic(
        mailbox_binding_id=binding.mailbox_binding_id,
        company_id=binding.company_id,
        company_mail_connection_id=binding.company_mail_connection_id,
        user_id=binding.user_id,
        kind=binding.kind,
        email_address=binding.email_address,
        local_part=binding.local_part,
        sync_enabled=binding.sync_enabled,
        is_default=binding.is_default,
        calendar_color=binding.calendar_color,
        has_password=bool(binding.password_encrypted and binding.password_encrypted.strip()),
        created_at=binding.created_at,
        updated_at=binding.updated_at,
    )


def to_public_inbound(
    message: InboundMailMessage,
    *,
    include_attachment_content: bool,
    file_ids_by_index: dict[int, str] | None = None,
) -> InboundMailMessagePublic:
    attachments: list[MailAttachmentPublic] = []
    for index, item in enumerate(message.attachments):
        size = item.size if item.size > 0 else len(item.content)
        file_id: str | None = None
        if file_ids_by_index is not None and index in file_ids_by_index:
            file_id = file_ids_by_index[index]
        content_base64: str | None = None
        if include_attachment_content and item.available and item.content:
            content_base64 = base64.b64encode(item.content).decode("ascii")
        attachments.append(
            MailAttachmentPublic(
                filename=item.filename,
                content_type=item.content_type,
                size=size,
                available=item.available and (file_id is not None or bool(item.content)),
                parse_error=item.parse_error,
                file_id=file_id,
                content_base64=content_base64 if file_id is None else None,
            )
        )
    return InboundMailMessagePublic(
        uid=message.uid,
        message_id=message.message_id,
        subject=message.subject,
        from_address=message.from_address,
        to_addresses=list(message.to_addresses),
        body_text=message.body_text,
        body_html=message.body_html,
        unread=message.unread,
        date=message.date,
        in_reply_to=message.in_reply_to,
        references=message.references,
        attachments=attachments,
    )


def to_message_list_item(message: InboundMailMessage) -> MailMessageListItem:
    snippet: str | None = None
    if message.body_text is not None and message.body_text.strip():
        text = " ".join(message.body_text.split())
        snippet = text if len(text) <= 160 else f"{text[:157]}..."
    return MailMessageListItem(
        uid=message.uid,
        message_id=message.message_id,
        subject=message.subject,
        from_address=message.from_address,
        to_addresses=list(message.to_addresses),
        snippet=snippet,
        attachment_count=len(message.attachments),
        unread=message.unread,
        flagged=message.flagged,
        date=message.date,
        in_reply_to=message.in_reply_to,
        references=message.references,
    )


def stored_to_list_item(stored: StoredMailMessage) -> MailMessageListItem:
    return MailMessageListItem(
        uid=str(stored.uid),
        message_id=stored.message_id,
        subject=stored.subject if stored.subject.strip() else None,
        from_address=stored.from_address if stored.from_address.strip() else None,
        to_addresses=list(stored.to_addresses),
        snippet=stored.snippet if stored.snippet.strip() else None,
        attachment_count=len(stored.attachments) if stored.attachments else (
            1 if stored.has_attachments else 0
        ),
        unread=stored.unread,
        flagged=stored.flagged,
        date=stored.date_at,
        in_reply_to=stored.in_reply_to,
        references=stored.references,
    )


def encode_mail_list_cursor(*, date_at: datetime | None, uid: int) -> str:
    ts = date_at.isoformat() if date_at is not None else ""
    return encode_cursor(
        date_at if date_at is not None else datetime.fromtimestamp(0, tz=timezone.utc),
        str(uid) if ts else f"null:{uid}",
    )


def decode_mail_list_cursor(cursor: str) -> tuple[datetime | None, int]:
    created_at, entity_id = decode_cursor(cursor)
    if entity_id.startswith("null:"):
        return None, int(entity_id.removeprefix("null:"))
    return created_at, int(entity_id)


def to_thread_message_public(
    message: InboundMailMessagePublic,
    *,
    folder: str,
) -> MailThreadMessagePublic:
    return MailThreadMessagePublic(
        folder=folder,
        uid=message.uid,
        message_id=message.message_id,
        subject=message.subject,
        from_address=message.from_address,
        to_addresses=list(message.to_addresses),
        body_text=message.body_text,
        body_html=message.body_html,
        unread=message.unread,
        date=message.date,
        in_reply_to=message.in_reply_to,
        references=message.references,
        attachments=list(message.attachments),
    )


def _parse_email_address(raw: str | None) -> str | None:
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    if "<" in stripped and ">" in stripped:
        inner = stripped[stripped.rindex("<") + 1 : stripped.rindex(">")].strip()
        if inner:
            return inner.casefold()
    return stripped.casefold()


@final
class MailService:
    def __init__(
        self,
        *,
        connection_repository: CompanyMailConnectionRepository,
        binding_repository: MailboxBindingRepository,
        sync_cursor_repository: MailboxSyncCursorRepository,
        folder_repository: MailboxFolderRepository | None = None,
        message_repository: MailMessageRepository | None = None,
        member_repository: MailboxBindingMemberRepository | None = None,
        namespace_service: NamespaceService | None = None,
        rag_client: RagClient | None = None,
        company_repository: CompanyRepository,
        user_repository: UserRepository,
        mail_config: MailConfig,
        port_override: MailServerPort | None = None,
        files_service: FilesService | None = None,
        attachment_file_index: MailAttachmentFileIndex | None = None,
        mail_sync_backfill_batch_size: int = 50,
        mail_sync_reconcile_every_n: int = 1,
    ) -> None:
        self._connection_repository: Final[CompanyMailConnectionRepository] = connection_repository
        self._binding_repository: Final[MailboxBindingRepository] = binding_repository
        self._sync_cursor_repository: Final[MailboxSyncCursorRepository] = sync_cursor_repository
        self._folder_repository: Final[MailboxFolderRepository | None] = folder_repository
        self._message_repository: Final[MailMessageRepository | None] = message_repository
        self._member_repository: Final[MailboxBindingMemberRepository | None] = member_repository
        self._namespace_service: Final[NamespaceService | None] = namespace_service
        self._rag_client: Final[RagClient | None] = rag_client
        self._company_repository: Final[CompanyRepository] = company_repository
        self._user_repository: Final[UserRepository] = user_repository
        self._mail_config: Final[MailConfig] = mail_config
        self._port_override: Final[MailServerPort | None] = port_override
        self._files_service: Final[FilesService | None] = files_service
        self._attachment_file_index: Final[MailAttachmentFileIndex | None] = attachment_file_index
        self._backfill_batch_size: Final[int] = mail_sync_backfill_batch_size
        self._reconcile_every_n: Final[int] = mail_sync_reconcile_every_n
        self._sync_pass_counters: dict[str, int] = {}

    def _active_company_id(self) -> str:
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise MailConfigError("active_company is required for mail operations")
        return ctx.active_company.company_id

    def _protected_local_parts(self) -> frozenset[str]:
        return frozenset(
            part.strip().lower()
            for part in self._mail_config.system.protected_local_parts
            if part.strip()
        )

    def _port_for(self, connection: CompanyMailConnection) -> MailServerPort:
        if self._port_override is not None:
            return self._port_override
        live = self._mail_config.live_test
        delete_prefix: str | None = None
        if live.enabled:
            delete_prefix = live.mailbox_prefix
        return build_mail_server_port(
            connection,
            protected_local_parts=self._protected_local_parts(),
            delete_prefix_required=delete_prefix,
            allow_delete=live.allow_delete if live.enabled else True,
        )

    def port_for_connection(self, connection: CompanyMailConnection) -> MailServerPort:
        return self._port_for(connection)

    async def get_connection(self, company_id: str | None = None) -> CompanyMailConnection | None:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        return await self._connection_repository.get_by_company(resolved_company_id)

    async def upsert_connection(
        self,
        payload: CompanyMailConnectionUpsertPayload,
        *,
        company_id: str | None = None,
    ) -> CompanyMailConnection:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        if resolved_company_id == SYSTEM_COMPANY_ID:
            raise MailSystemConnectionReadOnlyError()

        existing = await self._connection_repository.get_by_company(resolved_company_id)
        now = _utcnow()
        connection_id = (
            existing.company_mail_connection_id
            if existing is not None
            else f"mailconn_{uuid.uuid4().hex}"
        )
        supports_provision = payload.provider == MailProvider.ISPMANAGER
        ispmanager: IspmanagerProvisionConfig | None = None
        if payload.provider == MailProvider.ISPMANAGER:
            if payload.ispmanager_base_url is None or not payload.ispmanager_base_url.strip():
                raise MailConfigError("ispmanager_base_url is required for provider=ispmanager")
            if payload.ispmanager_authinfo_user is None or not payload.ispmanager_authinfo_user.strip():
                raise MailConfigError("ispmanager_authinfo_user is required for provider=ispmanager")
            password_encrypted: str | None = None
            if payload.ispmanager_authinfo_password is not None:
                if not payload.ispmanager_authinfo_password.strip():
                    raise MailConfigError("ispmanager_authinfo_password must not be empty")
                password_encrypted = encrypt_secret(payload.ispmanager_authinfo_password)
            elif (
                existing is not None
                and existing.ispmanager is not None
                and existing.ispmanager.authinfo_password_encrypted is not None
            ):
                password_encrypted = existing.ispmanager.authinfo_password_encrypted
            else:
                raise MailConfigError("ispmanager_authinfo_password is required")
            ispmanager = IspmanagerProvisionConfig(
                base_url=payload.ispmanager_base_url.strip(),
                authinfo_user=payload.ispmanager_authinfo_user.strip(),
                authinfo_password_encrypted=password_encrypted,
            )

        connection = CompanyMailConnection(
            company_mail_connection_id=connection_id,
            company_id=resolved_company_id,
            mail_domain=payload.mail_domain.strip().lower(),
            provider=payload.provider,
            imap_host=payload.imap_host.strip(),
            imap_port=payload.imap_port,
            smtp_host=payload.smtp_host.strip(),
            smtp_port=payload.smtp_port,
            use_ssl=payload.use_ssl,
            supports_provision=supports_provision,
            status=payload.status,
            ispmanager=ispmanager,
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        return await self._connection_repository.upsert(connection)

    def _active_user_id(self) -> str:
        ctx = get_context()
        if ctx is None:
            raise MailConfigError("authenticated user is required for mail operations")
        return ctx.user.user_id

    def _is_company_admin(self, company_id: str) -> bool:
        ctx = get_context()
        if ctx is None:
            return False
        roles = ctx.user.companies.get(company_id, [])
        return "admin" in roles

    def require_company_admin(self, company_id: str | None = None) -> None:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        if not self._is_company_admin(resolved_company_id):
            raise MailPermissionError(
                f"admin role required for company_id={resolved_company_id}"
            )

    async def _require_binding_access(
        self,
        binding: MailboxBinding,
        *,
        company_id: str,
    ) -> None:
        user_id = self._active_user_id()
        if binding.user_id == user_id:
            return
        if self._is_company_admin(company_id):
            return
        if (
            binding.kind == MailboxBindingKind.ROLE
            and self._member_repository is not None
            and await self._member_repository.is_member(binding.mailbox_binding_id, user_id)
        ):
            return
        raise MailPermissionError(
            f"no access to mailbox_binding_id={binding.mailbox_binding_id}"
        )

    async def list_my_bindings(self, company_id: str | None = None) -> list[MailboxBinding]:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        user_id = self._active_user_id()
        return await self._binding_repository.list_accessible_bindings(
            resolved_company_id, user_id
        )

    async def list_bindings(self, company_id: str | None = None) -> list[MailboxBinding]:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        return await self._binding_repository.list_by_company(resolved_company_id)

    async def get_or_create_user_binding(
        self,
        user_id: str,
        *,
        company_id: str | None = None,
        local_part: str | None = None,
    ) -> MailboxBinding:
        """Lazy mailbox: если bindings есть — default/первый; иначе provision."""
        if not user_id.strip():
            raise ValueError("user_id is required")
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        existing_list = await self._binding_repository.list_by_user(
            resolved_company_id, user_id
        )
        if existing_list:
            for binding in existing_list:
                if binding.is_default:
                    return binding
            primary = existing_list[0]
            if not primary.is_default:
                return await self.set_default_binding(
                    primary.mailbox_binding_id,
                    company_id=resolved_company_id,
                    acting_as_admin=True,
                )
            return primary
        return await self.bind_mailbox(
            MailboxBindingCreatePayload(
                user_id=user_id,
                kind=MailboxBindingKind.USER,
                local_part=local_part,
                provision=True,
                sync_enabled=True,
                is_default=True,
            ),
            company_id=resolved_company_id,
        )

    async def set_default_binding(
        self,
        mailbox_binding_id: str,
        *,
        company_id: str | None = None,
        acting_as_admin: bool = False,
    ) -> MailboxBinding:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(mailbox_binding_id, resolved_company_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        if binding.kind != MailboxBindingKind.USER or binding.user_id is None:
            raise ValueError("only user bindings can be default")
        if not acting_as_admin:
            user_id = self._active_user_id()
            if binding.user_id != user_id and not self._is_company_admin(resolved_company_id):
                raise MailPermissionError(
                    f"no access to mailbox_binding_id={mailbox_binding_id}"
                )
        await self._binding_repository.clear_defaults_for_user(
            resolved_company_id,
            binding.user_id,
            except_binding_id=binding.mailbox_binding_id,
        )
        updated = binding.model_copy(
            update={"is_default": True, "updated_at": _utcnow()}
        )
        return await self._binding_repository.upsert(updated)

    async def patch_binding(
        self,
        mailbox_binding_id: str,
        payload: MailboxBindingPatchPayload,
        *,
        company_id: str | None = None,
    ) -> MailboxBinding:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(mailbox_binding_id, resolved_company_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)

        has_admin_fields = (
            payload.user_id is not None
            or payload.sync_enabled is not None
            or payload.password is not None
        )
        has_color = payload.calendar_color is not None
        if not has_admin_fields and not has_color:
            raise ValueError("MailboxBindingPatchPayload is empty")

        is_admin = self._is_company_admin(resolved_company_id)
        acting_user_id = self._active_user_id()
        is_owner = (
            binding.kind == MailboxBindingKind.USER
            and binding.user_id is not None
            and binding.user_id == acting_user_id
        )
        if has_admin_fields and not is_admin:
            raise MailPermissionError(
                f"admin required to patch mailbox_binding_id={mailbox_binding_id}"
            )
        if has_color and not (is_admin or is_owner):
            raise MailPermissionError(
                f"no access to patch calendar_color for mailbox_binding_id={mailbox_binding_id}"
            )

        user_id = binding.user_id
        if payload.user_id is not None:
            if not payload.user_id.strip():
                raise ValueError("user_id must not be empty")
            user = await self._user_repository.get(payload.user_id)
            if user is None:
                raise ValueError(f"User not found: {payload.user_id}")
            user_id = payload.user_id

        sync_enabled = (
            payload.sync_enabled if payload.sync_enabled is not None else binding.sync_enabled
        )
        password_encrypted = binding.password_encrypted
        if payload.password is not None:
            if not payload.password.strip():
                raise ValueError("password must not be empty")
            password_encrypted = encrypt_secret(payload.password)

        calendar_color = binding.calendar_color
        if payload.calendar_color is not None:
            calendar_color = require_mail_calendar_color(payload.calendar_color)

        updated = binding.model_copy(
            update={
                "user_id": user_id if binding.kind == MailboxBindingKind.USER else None,
                "sync_enabled": sync_enabled,
                "password_encrypted": password_encrypted,
                "calendar_color": calendar_color,
                "updated_at": _utcnow(),
            }
        )
        stored = await self._binding_repository.upsert(updated)
        if (
            payload.user_id is not None
            and stored.kind == MailboxBindingKind.USER
            and stored.user_id is not None
        ):
            existing_for_user = await self._binding_repository.list_by_user(
                resolved_company_id, stored.user_id
            )
            if len(existing_for_user) == 1 and not stored.is_default:
                return await self.set_default_binding(
                    stored.mailbox_binding_id,
                    company_id=resolved_company_id,
                    acting_as_admin=True,
                )
        return stored

    async def bind_mailbox(
        self,
        payload: MailboxBindingCreatePayload,
        *,
        company_id: str | None = None,
    ) -> MailboxBinding:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        connection = await self._connection_repository.get_by_company(resolved_company_id)
        if connection is None:
            raise MailConnectionNotFoundError(resolved_company_id)

        local_part: str
        if payload.local_part is not None and payload.local_part.strip():
            local_part = payload.local_part.strip().lower()
        elif payload.email_address is not None and payload.email_address.strip():
            email_address = payload.email_address.strip().lower()
            if "@" not in email_address:
                raise ValueError(f"Invalid email_address={payload.email_address!r}")
            local_part, domain = email_address.split("@", 1)
            if domain != connection.mail_domain:
                raise ValueError(
                    f"email_address domain {domain!r} != connection mail_domain {connection.mail_domain!r}"
                )
        elif payload.kind == MailboxBindingKind.USER and payload.user_id is not None:
            user = await self._user_repository.get(payload.user_id)
            if user is None:
                raise ValueError(f"User not found: {payload.user_id}")
            local_part = _slug_local_part(user)
        else:
            raise ValueError("local_part or email_address or user_id required")

        if not _LOCAL_PART_RE.match(local_part):
            raise ValueError(f"Invalid local_part={local_part!r}")

        email_address = f"{local_part}@{connection.mail_domain}"
        existing = await self._binding_repository.get_by_email(resolved_company_id, email_address)
        target_user_id = (
            payload.user_id if payload.kind == MailboxBindingKind.USER else None
        )
        if existing is not None and payload.password is None:
            same_owner = (
                payload.kind == MailboxBindingKind.USER
                and target_user_id is not None
                and existing.kind == MailboxBindingKind.USER
                and existing.user_id == target_user_id
            )
            same_role = (
                payload.kind == MailboxBindingKind.ROLE
                and existing.kind == MailboxBindingKind.ROLE
            )
            if same_owner or same_role:
                if payload.provision and connection.supports_provision:
                    port = self._port_for(connection)
                    _ = await port.ensure_mailbox(
                        MailboxEnsureSpec(
                            mail_domain=connection.mail_domain,
                            local_part=local_part,
                            password=secrets.token_urlsafe(24),
                        )
                    )
                return existing

        previous_user_id = existing.user_id if existing is not None else None
        previous_was_default = bool(existing is not None and existing.is_default)

        password = payload.password
        generated_password = False
        if password is None or not password.strip():
            password = secrets.token_urlsafe(24)
            generated_password = True

        mailbox_already_on_server = False
        if payload.provision and connection.supports_provision:
            port = self._port_for(connection)
            before = await port.list_mailboxes(connection.mail_domain)
            mailbox_already_on_server = any(
                item.email_address == email_address for item in before
            )
            _ = await port.ensure_mailbox(
                MailboxEnsureSpec(
                    mail_domain=connection.mail_domain,
                    local_part=local_part,
                    password=password,
                )
            )

        now = _utcnow()
        password_encrypted: str | None
        if existing is not None and payload.password is None:
            password_encrypted = existing.password_encrypted
        elif mailbox_already_on_server and generated_password:
            password_encrypted = (
                existing.password_encrypted if existing is not None else None
            )
        else:
            password_encrypted = encrypt_secret(password)

        is_default = False
        if payload.kind == MailboxBindingKind.USER and target_user_id is not None:
            if payload.is_default is True:
                is_default = True
            elif payload.is_default is False:
                is_default = False
            else:
                siblings = await self._binding_repository.list_by_user(
                    resolved_company_id, target_user_id
                )
                sibling_ids = {item.mailbox_binding_id for item in siblings}
                if existing is not None:
                    sibling_ids.discard(existing.mailbox_binding_id)
                is_default = len(sibling_ids) == 0

        if is_default and target_user_id is not None:
            await self._binding_repository.clear_defaults_for_user(
                resolved_company_id, target_user_id
            )

        if payload.calendar_color is not None:
            calendar_color = require_mail_calendar_color(payload.calendar_color)
        elif existing is not None:
            calendar_color = existing.calendar_color
        else:
            calendar_color = default_calendar_color(email_address)

        binding = MailboxBinding(
            mailbox_binding_id=(
                existing.mailbox_binding_id if existing is not None else f"mailbind_{uuid.uuid4().hex}"
            ),
            company_id=resolved_company_id,
            company_mail_connection_id=connection.company_mail_connection_id,
            user_id=target_user_id,
            kind=payload.kind,
            email_address=email_address,
            local_part=local_part,
            sync_enabled=payload.sync_enabled,
            is_default=is_default,
            calendar_color=calendar_color,
            password_encrypted=password_encrypted,
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        stored = await self._binding_repository.upsert(binding)
        if (
            previous_user_id is not None
            and previous_was_default
            and previous_user_id != target_user_id
        ):
            remaining = await self._binding_repository.list_by_user(
                resolved_company_id, previous_user_id
            )
            if remaining and not any(item.is_default for item in remaining):
                _ = await self.set_default_binding(
                    remaining[0].mailbox_binding_id,
                    company_id=resolved_company_id,
                    acting_as_admin=True,
                )
        return stored

    async def unbind_mailbox(
        self,
        mailbox_binding_id: str,
        *,
        company_id: str | None = None,
    ) -> None:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(mailbox_binding_id, resolved_company_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        deleted = await self._binding_repository.delete(mailbox_binding_id, resolved_company_id)
        if not deleted:
            raise MailBindingNotFoundError(mailbox_binding_id)
        if (
            binding.kind == MailboxBindingKind.USER
            and binding.user_id is not None
            and binding.is_default
        ):
            remaining = await self._binding_repository.list_by_user(
                resolved_company_id, binding.user_id
            )
            if remaining:
                _ = await self.set_default_binding(
                    remaining[0].mailbox_binding_id,
                    company_id=resolved_company_id,
                    acting_as_admin=True,
                )

    async def list_messages(
        self,
        payload: MailMessageListPayload,
        *,
        company_id: str | None = None,
    ) -> MailMessageListResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)

        if self._message_repository is None:
            return MailMessageListResult(items=[], needs_sync=True)
        before_date: datetime | None = None
        before_uid: int | None = None
        if payload.cursor is not None and payload.cursor.strip():
            before_date, before_uid = decode_mail_list_cursor(payload.cursor)
        page = await self._message_repository.list_folder_page(
            payload.mailbox_binding_id,
            folder=payload.folder,
            limit=payload.limit,
            before_date=before_date,
            before_uid=before_uid,
        )
        has_more = len(page) > payload.limit
        rows = page[: payload.limit]
        next_cursor: str | None = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_mail_list_cursor(date_at=last.date_at, uid=last.uid)
        needs_sync = len(rows) == 0 and payload.cursor is None
        return MailMessageListResult(
            items=[stored_to_list_item(item) for item in rows],
            next_cursor=next_cursor,
            has_more=has_more,
            needs_sync=needs_sync,
        )

    async def search_messages(
        self,
        payload: MailMessageSearchPayload,
        *,
        company_id: str | None = None,
    ) -> MailMessageListResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        if self._message_repository is None:
            return MailMessageListResult(items=[], needs_sync=True)
        before_date: datetime | None = None
        before_uid: int | None = None
        if payload.cursor is not None and payload.cursor.strip():
            before_date, before_uid = decode_mail_list_cursor(payload.cursor)
        page = await self._message_repository.search_local(
            payload.mailbox_binding_id,
            q=payload.q,
            folder=payload.folder,
            limit=payload.limit,
            before_date=before_date,
            before_uid=before_uid,
        )
        has_more = len(page) > payload.limit
        rows = page[: payload.limit]
        next_cursor: str | None = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_mail_list_cursor(date_at=last.date_at, uid=last.uid)
        return MailMessageListResult(
            items=[stored_to_list_item(item) for item in rows],
            next_cursor=next_cursor,
            has_more=has_more,
            needs_sync=False,
        )

    def _folder_list_from_stored(
        self,
        stored: list[StoredMailboxFolder],
        *,
        stale: bool,
    ) -> MailFolderListResult:
        if not stored:
            return MailFolderListResult(folders=[], stale=stale)
        first = stored[0]
        folders = [
            MailFolder(
                name=item.folder_name,
                delimiter=item.delimiter,
                flags=list(item.flags),
                role=item.role,
                selectable=item.selectable,
                unseen_count=item.unseen_count,
                message_count=item.message_count,
            )
            for item in stored
        ]
        return MailFolderListResult(
            folders=folders,
            namespace_prefix=first.namespace_prefix,
            delimiter=first.delimiter,
            capabilities=list(first.capabilities),
            missing_standard_roles=[],
            stale=stale,
            needs_sync=stale,
        )

    async def _persist_folder_cache(
        self,
        binding: MailboxBinding,
        folders_result: MailFolderListResult,
    ) -> None:
        if self._folder_repository is None:
            return
        now = _utcnow()
        stored = [
            StoredMailboxFolder(
                mailbox_binding_id=binding.mailbox_binding_id,
                folder_name=folder.name,
                company_id=binding.company_id,
                role=MailFolderRole(str(folder.role)),
                delimiter=folder.delimiter,
                flags=list(folder.flags),
                selectable=folder.selectable,
                message_count=folder.message_count,
                unseen_count=folder.unseen_count,
                namespace_prefix=folders_result.namespace_prefix,
                capabilities=list(folders_result.capabilities),
                updated_at=now,
            )
            for folder in folders_result.folders
        ]
        _ = await self._folder_repository.replace_for_binding(
            binding.mailbox_binding_id,
            company_id=binding.company_id,
            folders=stored,
        )

    async def list_folders(
        self,
        mailbox_binding_id: str,
        *,
        company_id: str | None = None,
    ) -> MailFolderListResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(mailbox_binding_id, resolved_company_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        if self._folder_repository is None:
            return MailFolderListResult(folders=[], stale=True)
        stored = await self._folder_repository.list_for_binding(mailbox_binding_id)
        if not stored:
            return MailFolderListResult(folders=[], stale=True)
        return self._folder_list_from_stored(stored, stale=False)

    async def refresh_folders_from_imap(
        self,
        mailbox_binding_id: str,
        *,
        company_id: str | None = None,
    ) -> MailFolderListResult:
        """IMAP LIST+STATUS → folder cache. Для sync / ensure, не для open UI."""
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(mailbox_binding_id, resolved_company_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        connection = await self._connection_repository.get_by_company(resolved_company_id)
        if connection is None:
            raise MailConnectionNotFoundError(resolved_company_id)
        port = self._port_for(connection)
        folders_result = await port.list_imap_folders(self._binding_secret(binding))
        await self._persist_folder_cache(binding, folders_result)
        return folders_result.model_copy(update={"stale": False})

    async def ensure_standard_folders(
        self,
        mailbox_binding_id: str,
        *,
        company_id: str | None = None,
    ) -> MailFolderListResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(mailbox_binding_id, resolved_company_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        connection = await self._connection_repository.get_by_company(resolved_company_id)
        if connection is None:
            raise MailConnectionNotFoundError(resolved_company_id)
        port = self._port_for(connection)
        folders_result = await port.ensure_standard_imap_folders(self._binding_secret(binding))
        await self._persist_folder_cache(binding, folders_result)
        return folders_result.model_copy(update={"stale": False})

    def _stored_to_public(self, stored: StoredMailMessage) -> InboundMailMessagePublic:
        attachments: list[MailAttachmentPublic] = []
        for ref in stored.attachments:
            attachments.append(
                MailAttachmentPublic(
                    filename=ref.filename,
                    content_type=ref.content_type,
                    size=ref.size,
                    available=ref.available and ref.file_id is not None,
                    parse_error=ref.parse_error,
                    file_id=ref.file_id,
                    content_base64=None,
                )
            )
        return InboundMailMessagePublic(
            uid=str(stored.uid),
            message_id=stored.message_id,
            subject=stored.subject if stored.subject.strip() else None,
            from_address=stored.from_address if stored.from_address.strip() else None,
            to_addresses=list(stored.to_addresses),
            body_text=stored.body_text,
            body_html=stored.body_html,
            unread=stored.unread,
            date=stored.date_at,
            in_reply_to=stored.in_reply_to,
            references=stored.references,
            attachments=attachments,
        )

    async def get_message(
        self,
        *,
        mailbox_binding_id: str,
        uid: str,
        folder: str = "INBOX",
        company_id: str | None = None,
    ) -> InboundMailMessagePublic:
        if not uid.strip():
            raise ValueError("uid is required")
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(mailbox_binding_id, resolved_company_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        if self._message_repository is None:
            raise MailMessageNotFoundError(mailbox_binding_id, uid)
        try:
            uid_int = int(uid)
        except ValueError as exc:
            raise MailMessageNotFoundError(mailbox_binding_id, uid) from exc
        stored = await self._message_repository.get_by_uid(
            mailbox_binding_id,
            folder=folder,
            uid=uid_int,
        )
        if stored is None:
            raise MailMessageNotFoundError(mailbox_binding_id, uid)
        if stored.unread:
            _ = await self._message_repository.set_unread(
                mailbox_binding_id,
                folder=folder,
                uid=int(uid),
                unread=False,
            )
            stored = stored.model_copy(update={"unread": False})
        return self._stored_to_public(stored)

    async def get_thread(
        self,
        payload: MailThreadPayload,
        *,
        company_id: str | None = None,
    ) -> MailThreadResult:
        if not payload.uid.strip():
            raise ValueError("uid is required")
        if not payload.folder.strip():
            raise ValueError("folder is required")
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        if self._message_repository is None:
            raise MailMessageNotFoundError(payload.mailbox_binding_id, payload.uid)
        try:
            uid_int = int(payload.uid)
        except ValueError as exc:
            raise MailMessageNotFoundError(payload.mailbox_binding_id, payload.uid) from exc
        anchor = await self._message_repository.get_by_uid(
            payload.mailbox_binding_id,
            folder=payload.folder,
            uid=uid_int,
        )
        if anchor is None:
            raise MailMessageNotFoundError(payload.mailbox_binding_id, payload.uid)
        thread_rows = await self._message_repository.list_by_thread(
            payload.mailbox_binding_id,
            thread_id=anchor.thread_id,
        )
        if not thread_rows:
            thread_rows = [anchor]
        if anchor.unread:
            _ = await self._message_repository.set_unread(
                payload.mailbox_binding_id,
                folder=payload.folder,
                uid=int(payload.uid),
                unread=False,
            )
        public_items: list[MailThreadMessagePublic] = []
        participants: set[str] = set()
        subject: str | None = anchor.subject if anchor.subject.strip() else None
        for row in thread_rows:
            if row.folder == payload.folder and row.uid == int(payload.uid):
                row = row.model_copy(update={"unread": False})
            public = self._stored_to_public(row)
            public_items.append(to_thread_message_public(public, folder=row.folder))
            from_email = _parse_email_address(row.from_address)
            if from_email is not None:
                participants.add(from_email)
            for address in row.to_addresses:
                to_email = _parse_email_address(address)
                if to_email is not None:
                    participants.add(to_email)
            if subject is None and row.subject.strip():
                subject = row.subject
        return MailThreadResult(
            thread_id=anchor.thread_id,
            subject=subject,
            participant_emails=sorted(participants),
            items=public_items,
        )

    async def mark_message_seen_local(
        self,
        payload: MailMessageFlagPayload,
        *,
        company_id: str | None = None,
    ) -> MailMessageFlagResult:
        if not payload.uid.strip():
            raise ValueError("uid is required")
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        if self._message_repository is not None:
            _ = await self._message_repository.set_unread(
                payload.mailbox_binding_id,
                folder=payload.folder,
                uid=int(payload.uid),
                unread=False,
            )
        return MailMessageFlagResult(uid=payload.uid, unread=False)

    async def mark_message_unseen_local(
        self,
        payload: MailMessageFlagPayload,
        *,
        company_id: str | None = None,
    ) -> MailMessageFlagResult:
        if not payload.uid.strip():
            raise ValueError("uid is required")
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        if self._message_repository is not None:
            _ = await self._message_repository.set_unread(
                payload.mailbox_binding_id,
                folder=payload.folder,
                uid=int(payload.uid),
                unread=True,
            )
        return MailMessageFlagResult(uid=payload.uid, unread=True)

    async def mark_message_seen(
        self,
        payload: MailMessageFlagPayload,
        *,
        company_id: str | None = None,
    ) -> MailMessageFlagResult:
        if not payload.uid.strip():
            raise ValueError("uid is required")
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        connection = await self._connection_repository.get_by_company(resolved_company_id)
        if connection is None:
            raise MailConnectionNotFoundError(resolved_company_id)
        port = self._port_for(connection)
        try:
            await port.mark_message_seen(
                self._binding_secret(binding),
                mailbox=payload.folder,
                uid=payload.uid,
            )
        except MailUidNotFoundError as exc:
            raise MailMessageNotFoundError(payload.mailbox_binding_id, payload.uid) from exc
        if self._message_repository is not None:
            _ = await self._message_repository.set_unread(
                payload.mailbox_binding_id,
                folder=payload.folder,
                uid=int(payload.uid),
                unread=False,
            )
        return MailMessageFlagResult(uid=payload.uid, unread=False)

    async def mark_message_unseen(
        self,
        payload: MailMessageFlagPayload,
        *,
        company_id: str | None = None,
    ) -> MailMessageFlagResult:
        if not payload.uid.strip():
            raise ValueError("uid is required")
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        connection = await self._connection_repository.get_by_company(resolved_company_id)
        if connection is None:
            raise MailConnectionNotFoundError(resolved_company_id)
        port = self._port_for(connection)
        try:
            await port.mark_message_unseen(
                self._binding_secret(binding),
                mailbox=payload.folder,
                uid=payload.uid,
            )
        except MailUidNotFoundError as exc:
            raise MailMessageNotFoundError(payload.mailbox_binding_id, payload.uid) from exc
        if self._message_repository is not None:
            _ = await self._message_repository.set_unread(
                payload.mailbox_binding_id,
                folder=payload.folder,
                uid=int(payload.uid),
                unread=True,
            )
        return MailMessageFlagResult(uid=payload.uid, unread=True)

    async def request_sync_now(
        self,
        payload: MailSyncNowPayload,
        *,
        company_id: str | None = None,
    ) -> MailSyncNowResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        _ = await self.refresh_folders_from_imap(payload.mailbox_binding_id)
        await enqueue_mail_sync_binding(
            company_id=resolved_company_id,
            mailbox_binding_id=payload.mailbox_binding_id,
        )
        return MailSyncNowResult(accepted=True, mailbox_binding_id=payload.mailbox_binding_id)

    async def resolve_folder_name_for_role(
        self,
        mailbox_binding_id: str,
        role: MailFolderRole,
        *,
        company_id: str | None = None,
    ) -> str:
        folders = await self.list_folders(mailbox_binding_id, company_id=company_id)
        for folder in folders.folders:
            if folder.role == role and folder.selectable:
                return folder.name
        ensured = await self.ensure_standard_folders(mailbox_binding_id, company_id=company_id)
        for folder in ensured.folders:
            if folder.role == role and folder.selectable:
                return folder.name
        raise MailConfigError(f"IMAP folder role={role.value} not available")

    async def move_message_local(
        self,
        payload: MailMessageMovePayload,
        *,
        company_id: str | None = None,
    ) -> MailMessageMoveResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        if self._message_repository is None:
            raise MailConfigError("message repository required")
        stored = await self._message_repository.get_by_uid(
            payload.mailbox_binding_id,
            folder=payload.folder,
            uid=int(payload.uid),
        )
        if stored is None:
            raise MailMessageNotFoundError(payload.mailbox_binding_id, payload.uid)
        # Optimistic: remove from source; confirm rewrite on IMAP move result.
        _ = await self._message_repository.delete_by_uids(
            payload.mailbox_binding_id,
            folder=payload.folder,
            uids=[int(payload.uid)],
        )
        return MailMessageMoveResult(
            uid=payload.uid,
            folder=payload.folder,
            destination_folder=payload.destination_folder,
            destination_uid=None,
        )

    async def move_message(
        self,
        payload: MailMessageMovePayload,
        *,
        company_id: str | None = None,
    ) -> MailMessageMoveResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        connection = await self._connection_repository.get_by_company(resolved_company_id)
        if connection is None:
            raise MailConnectionNotFoundError(resolved_company_id)
        port = self._port_for(connection)
        secret = self._binding_secret(binding)
        move_result = await port.uid_move(
            secret,
            mailbox=payload.folder,
            uid=payload.uid,
            destination_folder=payload.destination_folder,
        )
        destination_uid = move_result.destination_uid
        if self._message_repository is not None:
            _ = await self._message_repository.delete_by_uids(
                payload.mailbox_binding_id,
                folder=payload.folder,
                uids=[int(payload.uid)],
            )
        if destination_uid is None:
            # Server did not return COPYUID; sync will pick up destination copy.
            return MailMessageMoveResult(
                uid=payload.uid,
                folder=payload.folder,
                destination_folder=payload.destination_folder,
                destination_uid=None,
            )
        try:
            inbound = await port.fetch_message_by_uid(
                secret,
                mailbox=payload.destination_folder,
                uid=destination_uid,
            )
        except MailUidNotFoundError as exc:
            raise MailMessageNotFoundError(
                payload.mailbox_binding_id, destination_uid
            ) from exc
        await self._persist_synced_messages(
            binding,
            folder=payload.destination_folder,
            messages=[inbound],
            port=port,
            secret=secret,
        )
        return MailMessageMoveResult(
            uid=payload.uid,
            folder=payload.folder,
            destination_folder=payload.destination_folder,
            destination_uid=destination_uid,
        )

    async def trash_message(
        self,
        payload: MailMessageFlagPayload,
        *,
        company_id: str | None = None,
    ) -> MailMessageMoveResult:
        trash = await self.resolve_folder_name_for_role(
            payload.mailbox_binding_id,
            MailFolderRole.TRASH,
            company_id=company_id,
        )
        move_payload = MailMessageMovePayload(
            mailbox_binding_id=payload.mailbox_binding_id,
            folder=payload.folder,
            uid=payload.uid,
            destination_folder=trash,
        )
        return await self.move_message(move_payload, company_id=company_id)

    async def archive_message(
        self,
        payload: MailMessageFlagPayload,
        *,
        company_id: str | None = None,
    ) -> MailMessageMoveResult:
        archive = await self.resolve_folder_name_for_role(
            payload.mailbox_binding_id,
            MailFolderRole.ARCHIVE,
            company_id=company_id,
        )
        move_payload = MailMessageMovePayload(
            mailbox_binding_id=payload.mailbox_binding_id,
            folder=payload.folder,
            uid=payload.uid,
            destination_folder=archive,
        )
        return await self.move_message(move_payload, company_id=company_id)

    async def delete_message_local(
        self,
        payload: MailMessageFlagPayload,
        *,
        company_id: str | None = None,
    ) -> MailMessageFlagResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        if self._message_repository is not None:
            _ = await self._message_repository.delete_by_uids(
                payload.mailbox_binding_id,
                folder=payload.folder,
                uids=[int(payload.uid)],
            )
        return MailMessageFlagResult(uid=payload.uid, unread=False)

    async def delete_message(
        self,
        payload: MailMessageFlagPayload,
        *,
        company_id: str | None = None,
    ) -> MailMessageFlagResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        if self._message_repository is not None:
            _ = await self._message_repository.delete_by_uids(
                payload.mailbox_binding_id,
                folder=payload.folder,
                uids=[int(payload.uid)],
            )
        connection = await self._connection_repository.get_by_company(resolved_company_id)
        if connection is None:
            raise MailConnectionNotFoundError(resolved_company_id)
        port = self._port_for(connection)
        await port.uid_expunge(
            self._binding_secret(binding),
            mailbox=payload.folder,
            uid=payload.uid,
        )
        return MailMessageFlagResult(uid=payload.uid, unread=False)

    async def star_message_local(
        self,
        payload: MailMessageStarPayload,
        *,
        company_id: str | None = None,
    ) -> MailMessageStarResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        if self._message_repository is not None:
            _ = await self._message_repository.set_flags(
                payload.mailbox_binding_id,
                folder=payload.folder,
                uid=int(payload.uid),
                flagged=payload.flagged,
            )
        return MailMessageStarResult(uid=payload.uid, flagged=payload.flagged)

    async def star_message(
        self,
        payload: MailMessageStarPayload,
        *,
        company_id: str | None = None,
    ) -> MailMessageStarResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        connection = await self._connection_repository.get_by_company(resolved_company_id)
        if connection is None:
            raise MailConnectionNotFoundError(resolved_company_id)
        port = self._port_for(connection)
        add_flags = [MailImapSystemFlag.FLAGGED.value] if payload.flagged else []
        remove_flags = [] if payload.flagged else [MailImapSystemFlag.FLAGGED.value]
        await port.uid_store_flags(
            self._binding_secret(binding),
            mailbox=payload.folder,
            uid=payload.uid,
            add_flags=add_flags,
            remove_flags=remove_flags,
        )
        return await self.star_message_local(payload, company_id=resolved_company_id)

    async def save_draft(
        self,
        payload: MailDraftSavePayload,
        *,
        company_id: str | None = None,
    ) -> MailDraftSaveResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        drafts_folder = await self.resolve_folder_name_for_role(
            payload.mailbox_binding_id,
            MailFolderRole.DRAFTS,
            company_id=resolved_company_id,
        )
        if payload.uid is not None and payload.uid.strip():
            _ = await self.delete_message(
                MailMessageFlagPayload(
                    mailbox_binding_id=payload.mailbox_binding_id,
                    folder=drafts_folder,
                    uid=payload.uid,
                ),
                company_id=resolved_company_id,
            )
        to_addresses = list(payload.to_addresses)
        if not to_addresses:
            to_addresses = [binding.email_address]
        outbound = OutboundMailMessage(
            to_addresses=to_addresses,
            subject=payload.subject,
            body_text=payload.body_text,
            body_html=payload.body_html,
            in_reply_to=payload.in_reply_to,
            references=payload.references,
        )
        raw = build_rfc822_bytes(outbound, from_address=binding.email_address)
        connection = await self._connection_repository.get_by_company(resolved_company_id)
        if connection is None:
            raise MailConnectionNotFoundError(resolved_company_id)
        port = self._port_for(connection)
        append_result = await port.append_message(
            self._binding_secret(binding),
            mailbox=drafts_folder,
            raw_message=raw,
            flags=r"(\Draft \Seen)",
        )
        if append_result.uid is None:
            raise MailConfigError("APPEND Drafts did not return uid")
        inbound = await port.fetch_message_by_uid(
            self._binding_secret(binding),
            mailbox=drafts_folder,
            uid=append_result.uid,
        )
        inbound = inbound.model_copy(update={"draft": True, "unread": False})
        await self._persist_synced_messages(
            binding,
            folder=drafts_folder,
            messages=[inbound],
            port=port,
            secret=self._binding_secret(binding),
        )
        return MailDraftSaveResult(
            uid=append_result.uid,
            folder=drafts_folder,
            message_id=append_result.message_id,
        )

    async def list_binding_members(
        self,
        mailbox_binding_id: str,
        *,
        company_id: str | None = None,
    ) -> list[MailboxBindingMember]:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        self.require_company_admin()
        binding = await self._binding_repository.get(mailbox_binding_id, resolved_company_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        if binding.kind != MailboxBindingKind.ROLE:
            raise MailConfigError("members only for kind=role bindings")
        if self._member_repository is None:
            return []
        return await self._member_repository.list_for_binding(mailbox_binding_id)

    async def add_binding_member(
        self,
        mailbox_binding_id: str,
        payload: MailboxBindingMemberPayload,
        *,
        company_id: str | None = None,
    ) -> MailboxBindingMember:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        self.require_company_admin()
        binding = await self._binding_repository.get(mailbox_binding_id, resolved_company_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        if binding.kind != MailboxBindingKind.ROLE:
            raise MailConfigError("members only for kind=role bindings")
        if self._member_repository is None:
            raise MailConfigError("member repository required")
        return await self._member_repository.upsert(
            MailboxBindingMember(
                mailbox_binding_id=mailbox_binding_id,
                user_id=payload.user_id,
                company_id=resolved_company_id,
                role=payload.role,
                created_at=_utcnow(),
            )
        )

    async def remove_binding_member(
        self,
        mailbox_binding_id: str,
        user_id: str,
        *,
        company_id: str | None = None,
    ) -> None:
        self.require_company_admin(company_id)
        if self._member_repository is None:
            raise MailConfigError("member repository required")
        deleted = await self._member_repository.delete(mailbox_binding_id, user_id)
        if not deleted:
            raise MailBindingNotFoundError(mailbox_binding_id)

    async def _materialize_attachments(
        self,
        message: InboundMailMessage,
        *,
        mailbox_binding_id: str,
        mailbox_email: str,
    ) -> dict[int, str]:
        files_service = self._files_service
        if files_service is None:
            return {}
        file_ids: dict[int, str] = {}
        mail_subject = message.subject.strip() if message.subject and message.subject.strip() else None
        for index, attachment in enumerate(message.attachments):
            if not attachment.available or not attachment.content:
                continue
            existing_id = await self._lookup_attachment_file_id(
                mailbox_binding_id=mailbox_binding_id,
                mail_uid=message.uid,
                attachment_index=index,
            )
            source_ref = FileSourceRef(
                mailbox_binding_id=mailbox_binding_id,
                mail_uid=message.uid,
                message_id=message.message_id,
                mailbox_email=mailbox_email,
                mail_subject=mail_subject,
            )
            if existing_id is not None:
                existing = await files_service.get_optional(existing_id)
                if existing is not None:
                    # DocsPlacement уже пытались при первом create; повторный bind к office
                    # не нужен для чтения треда и блокирует UI при недоступном office.
                    file_ids[index] = existing_id
                    continue
            record = await files_service.create(
                FileCreateSpec(
                    source_kind=FileSourceKind.MAIL_MESSAGE,
                    source_ref=source_ref,
                    retention=default_retention_for_source(FileSourceKind.MAIL_MESSAGE),
                    metadata={
                        "mail_filename": attachment.filename,
                        "mail_content_type": attachment.content_type,
                        "mailbox_binding_id": mailbox_binding_id,
                        "mail_uid": message.uid,
                        "attachment_index": str(index),
                    },
                ),
                attachment.content,
                original_name=attachment.filename,
                content_type=attachment.content_type,
            )
            await self._store_attachment_file_id(
                mailbox_binding_id=mailbox_binding_id,
                mail_uid=message.uid,
                attachment_index=index,
                file_id=record.file_id,
            )
            file_ids[index] = record.file_id
        return file_ids

    async def _lookup_attachment_file_id(
        self,
        *,
        mailbox_binding_id: str,
        mail_uid: str,
        attachment_index: int,
    ) -> str | None:
        index = self._attachment_file_index
        if index is None:
            return None
        return await index.get(
            mailbox_binding_id=mailbox_binding_id,
            mail_uid=mail_uid,
            attachment_index=attachment_index,
        )

    async def _store_attachment_file_id(
        self,
        *,
        mailbox_binding_id: str,
        mail_uid: str,
        attachment_index: int,
        file_id: str,
    ) -> None:
        index = self._attachment_file_index
        if index is None:
            return
        await index.set(
            mailbox_binding_id=mailbox_binding_id,
            mail_uid=mail_uid,
            attachment_index=attachment_index,
            file_id=file_id,
        )

    async def prepare_send_local(
        self,
        payload: MailSendPayload,
        *,
        company_id: str | None = None,
    ) -> MailSendResult:
        """Optimistic local Sent upsert before SMTP worker."""
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        for attachment in payload.attachments:
            if not attachment.content:
                raise ValueError(
                    f"outbound attachment content required filename={attachment.filename!r}"
                )
        message_id = payload.message_id
        if message_id is None or not message_id.strip():
            raise ValueError("message_id is required for prepare_send_local")
        if self._message_repository is None:
            raise MailConfigError("message repository required")
        sent_folder = await self.resolve_folder_name_for_role(
            payload.mailbox_binding_id,
            MailFolderRole.SENT,
            company_id=resolved_company_id,
        )
        temp_uid = -(
            int(uuid.uuid5(uuid.NAMESPACE_URL, f"pending-send:{message_id}").int % 1_000_000_000)
            or 1
        )
        now = _utcnow()
        snippet_src = " ".join(payload.body_text.split()) if payload.body_text.strip() else ""
        snippet = snippet_src if len(snippet_src) <= 160 else f"{snippet_src[:157]}..."
        inbound = InboundMailMessage(
            uid=str(temp_uid),
            message_id=message_id,
            subject=payload.subject,
            from_address=binding.email_address,
            to_addresses=list(payload.to_addresses),
            body_text=payload.body_text,
            body_html=payload.body_html,
            unread=False,
            flagged=False,
            answered=False,
            draft=False,
            date=now,
            in_reply_to=payload.in_reply_to,
            references=payload.references,
            attachments=[],
        )
        mail_message_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{binding.mailbox_binding_id}:{sent_folder}:{temp_uid}",
            )
        )
        stored = StoredMailMessage(
            mail_message_id=mail_message_id,
            company_id=binding.company_id,
            mailbox_binding_id=binding.mailbox_binding_id,
            user_id=binding.user_id,
            folder=sent_folder,
            uid=temp_uid,
            message_id=message_id,
            thread_id=thread_id_for_message(inbound),
            subject=payload.subject,
            from_address=binding.email_address,
            to_addresses=list(payload.to_addresses),
            cc_addresses=[],
            date_at=now,
            unread=False,
            flagged=False,
            answered=False,
            draft=False,
            has_attachments=len(payload.attachments) > 0,
            snippet=snippet,
            body_text=payload.body_text,
            body_html=payload.body_html,
            attachments=[],
            in_reply_to=payload.in_reply_to,
            references=payload.references,
            rag_document_id=None,
            rag_namespace=None,
            synced_at=now,
            created_at=now,
            updated_at=now,
        )
        _ = await self._message_repository.upsert(stored)
        return MailSendResult(message_id=message_id, accepted=list(payload.to_addresses))

    async def send_message(
        self,
        payload: MailSendPayload,
        *,
        company_id: str | None = None,
    ) -> MailSendResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(
            payload.mailbox_binding_id, resolved_company_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        for attachment in payload.attachments:
            if not attachment.content:
                raise ValueError(
                    f"outbound attachment content required filename={attachment.filename!r}"
                )
        result = await self.send_from_binding(
            payload.mailbox_binding_id,
            OutboundMailMessage(
                to_addresses=payload.to_addresses,
                subject=payload.subject,
                body_text=payload.body_text,
                body_html=payload.body_html,
                message_id=payload.message_id,
                in_reply_to=payload.in_reply_to,
                references=payload.references,
                attachments=payload.attachments,
            ),
            company_id=resolved_company_id,
        )
        await enqueue_mail_sync_binding(
            company_id=resolved_company_id,
            mailbox_binding_id=payload.mailbox_binding_id,
        )
        return result

    async def healthcheck(self, company_id: str | None = None) -> MailServerHealth:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        connection = await self._connection_repository.get_by_company(resolved_company_id)
        if connection is None:
            raise MailConnectionNotFoundError(resolved_company_id)
        port = self._port_for(connection)
        return await port.healthcheck()

    def _binding_secret(self, binding: MailboxBinding) -> MailboxSecret:
        if binding.password_encrypted is None or not binding.password_encrypted.strip():
            raise MailSecretMissingError(binding.email_address)
        return MailboxSecret(
            email_address=binding.email_address,
            password=decrypt_secret(binding.password_encrypted),
        )

    def binding_secret(self, binding: MailboxBinding) -> MailboxSecret:
        return self._binding_secret(binding)

    async def send_from_binding(
        self,
        mailbox_binding_id: str,
        message: OutboundMailMessage,
        *,
        company_id: str | None = None,
    ) -> MailSendResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(mailbox_binding_id, resolved_company_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        connection = await self._connection_repository.get_by_company(resolved_company_id)
        if connection is None:
            raise MailConnectionNotFoundError(resolved_company_id)
        port = self._port_for(connection)
        return await port.send_message(self._binding_secret(binding), message)

    async def fetch_for_binding(
        self,
        mailbox_binding_id: str,
        query: MailFetchQuery,
        *,
        company_id: str | None = None,
    ) -> list[InboundMailMessage]:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await self._binding_repository.get(mailbox_binding_id, resolved_company_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        connection = await self._connection_repository.get_by_company(resolved_company_id)
        if connection is None:
            raise MailConnectionNotFoundError(resolved_company_id)
        port = self._port_for(connection)
        return await port.fetch_messages(self._binding_secret(binding), query)

    async def list_sync_candidates(
        self,
        *,
        limit: int,
        auth_error_cooldown_seconds: int,
    ) -> list[MailboxBinding]:
        return await self._binding_repository.list_sync_candidates(
            limit=limit,
            auth_error_cooldown_seconds=auth_error_cooldown_seconds,
            folder=INBOX_FOLDER,
        )

    async def sync_lag_stats(
        self,
        *,
        auth_error_cooldown_seconds: int,
    ) -> MailSyncLagStats:
        return await self._binding_repository.sync_lag_stats(
            auth_error_cooldown_seconds=auth_error_cooldown_seconds,
            folder=INBOX_FOLDER,
        )

    async def record_sync_failure(
        self,
        binding: MailboxBinding,
        *,
        error_kind: MailSyncErrorKind,
        error_message: str,
    ) -> None:
        now = _utcnow()
        existing = await self._sync_cursor_repository.get(
            binding.mailbox_binding_id, folder=INBOX_FOLDER
        )
        truncated = error_message.strip()[:1024]
        if not truncated:
            truncated = error_kind.value
        if existing is None:
            cursor = MailboxSyncCursor(
                mailbox_binding_id=binding.mailbox_binding_id,
                folder=INBOX_FOLDER,
                company_id=binding.company_id,
                uidvalidity=0,
                last_uid=0,
                last_synced_at=None,
                last_attempt_at=now,
                last_error_kind=error_kind,
                last_error_at=now,
                last_error_message=truncated,
            )
        else:
            cursor = existing.model_copy(
                update={
                    "last_attempt_at": now,
                    "last_error_kind": error_kind,
                    "last_error_at": now,
                    "last_error_message": truncated,
                }
            )
        _ = await self._sync_cursor_repository.upsert(cursor)

    async def sync_user_inbox(
        self,
        binding: MailboxBinding,
        *,
        max_new_messages: int,
    ) -> MailSyncBindingResult:
        """Alias: sync binding (user или role)."""
        return await self.sync_binding(binding, max_new_messages=max_new_messages)

    async def sync_binding(
        self,
        binding: MailboxBinding,
        *,
        max_new_messages: int,
        backfill_batch_size: int | None = None,
    ) -> MailSyncBindingResult:
        """Синхронизирует selectable IMAP folders: catch-up, backfill, reconcile, flags."""
        if binding.kind == MailboxBindingKind.USER and (
            binding.user_id is None or not binding.user_id.strip()
        ):
            raise ValueError(
                f"sync_binding requires user_id for kind=user mailbox_binding_id={binding.mailbox_binding_id}"
            )
        if max_new_messages < 1:
            raise ValueError("max_new_messages must be >= 1")
        resolved_backfill = (
            backfill_batch_size
            if backfill_batch_size is not None
            else self._backfill_batch_size
        )
        if resolved_backfill < 1:
            raise ValueError("backfill_batch_size must be >= 1")

        connection = await self._connection_repository.get_by_company(binding.company_id)
        if connection is None:
            return MailSyncBindingResult(
                mailbox_binding_id=binding.mailbox_binding_id,
                company_id=binding.company_id,
                user_id=binding.user_id,
                email_address=binding.email_address,
                skipped_reason="connection_missing",
            )
        if connection.status != MailConnectionStatus.ACTIVE:
            return MailSyncBindingResult(
                mailbox_binding_id=binding.mailbox_binding_id,
                company_id=binding.company_id,
                user_id=binding.user_id,
                email_address=binding.email_address,
                skipped_reason=f"connection_status_{connection.status.value}",
            )
        if not binding.sync_enabled:
            return MailSyncBindingResult(
                mailbox_binding_id=binding.mailbox_binding_id,
                company_id=binding.company_id,
                user_id=binding.user_id,
                email_address=binding.email_address,
                skipped_reason="sync_disabled",
            )

        port = self._port_for(connection)
        secret = self._binding_secret(binding)
        folders_result = await port.list_imap_folders(secret)
        await self._persist_folder_cache(binding, folders_result)
        selectable = [folder for folder in folders_result.folders if folder.selectable]
        if not selectable:
            selectable = [
                MailFolder(
                    name=INBOX_FOLDER,
                    delimiter="/",
                    flags=[],
                    role=MailFolderRole.INBOX,
                    selectable=True,
                )
            ]

        now = _utcnow()
        inbox_notify: list[InboundMailMessage] = []
        inbox_bootstrap = False
        backfill_remaining = False
        pass_key = binding.mailbox_binding_id
        pass_count = self._sync_pass_counters.get(pass_key, 0) + 1
        self._sync_pass_counters[pass_key] = pass_count
        do_reconcile = self._reconcile_every_n > 0 and (
            pass_count % self._reconcile_every_n == 0
        )

        for folder in selectable:
            folder_name = folder.name
            is_inbox = (
                folder.role == MailFolderRole.INBOX or folder_name.casefold() == "inbox"
            )
            cursor = await self._sync_cursor_repository.get(
                binding.mailbox_binding_id, folder=folder_name
            )
            since_uid = 0 if cursor is None else cursor.last_uid
            batch = await port.fetch_uids_since(
                secret,
                mailbox=folder_name,
                since_uid=since_uid,
                limit=max_new_messages,
            )
            folder_bootstrap = cursor is None or cursor.uidvalidity != batch.uidvalidity
            if folder_bootstrap:
                if is_inbox:
                    inbox_bootstrap = True
                if self._message_repository is not None:
                    _ = await self._message_repository.delete_folder(
                        binding.mailbox_binding_id, folder=folder_name
                    )
                    recent = await port.fetch_messages(
                        secret,
                        MailFetchQuery(
                            mailbox=folder_name,
                            limit=max_new_messages,
                            include_bodies=True,
                        ),
                    )
                    if recent:
                        await self._persist_synced_messages(
                            binding,
                            folder=folder_name,
                            messages=recent,
                            port=port,
                            secret=secret,
                        )
                    min_uid = min((int(m.uid) for m in recent), default=None)
                    backfill_done = batch.max_uid == 0 or (
                        min_uid is not None and min_uid <= 1
                    )
                    _ = await self._sync_cursor_repository.upsert(
                        MailboxSyncCursor(
                            mailbox_binding_id=binding.mailbox_binding_id,
                            folder=folder_name,
                            company_id=binding.company_id,
                            uidvalidity=batch.uidvalidity,
                            last_uid=batch.max_uid,
                            backfill_completed=backfill_done,
                            oldest_uid=min_uid,
                            last_reconcile_at=now if do_reconcile else None,
                            last_synced_at=now,
                            last_attempt_at=now,
                            last_error_kind=None,
                            last_error_at=None,
                            last_error_message=None,
                        )
                    )
                    if not backfill_done:
                        backfill_remaining = True
                continue

            if cursor is None:
                raise RuntimeError(
                    "mailbox sync cursor missing after bootstrap check: "
                    + f"{binding.mailbox_binding_id}/{folder_name}"
                )

            new_messages = list(batch.messages)
            advanced_uid = cursor.last_uid
            if new_messages:
                advanced_uid = max(int(message.uid) for message in new_messages)
            elif batch.max_uid > cursor.last_uid:
                advanced_uid = batch.max_uid

            if new_messages:
                await self._persist_synced_messages(
                    binding,
                    folder=folder_name,
                    messages=new_messages,
                    port=port,
                    secret=secret,
                )
                if is_inbox:
                    inbox_notify.extend(new_messages)

            if self._message_repository is not None:
                local_rows = await self._message_repository.list_folder(
                    binding.mailbox_binding_id,
                    folder=folder_name,
                    limit=500,
                )
                if local_rows:
                    await self._refresh_flags_for_messages(
                        binding,
                        port,
                        secret,
                        folder=folder_name,
                        messages=[
                            InboundMailMessage(uid=str(row.uid)) for row in local_rows
                        ],
                    )

            oldest_uid = cursor.oldest_uid
            backfill_completed = cursor.backfill_completed
            if not backfill_completed:
                backfilled = await self._backfill_folder(
                    binding,
                    port=port,
                    secret=secret,
                    folder=folder_name,
                    oldest_uid=oldest_uid if oldest_uid is not None else advanced_uid,
                    batch_size=resolved_backfill,
                )
                oldest_uid = backfilled.oldest_uid
                backfill_completed = backfilled.completed
                if not backfill_completed:
                    backfill_remaining = True

            last_reconcile_at = cursor.last_reconcile_at
            if do_reconcile and self._message_repository is not None:
                await self._reconcile_folder_uids(
                    binding,
                    port=port,
                    secret=secret,
                    folder=folder_name,
                )
                last_reconcile_at = now

            _ = await self._sync_cursor_repository.upsert(
                MailboxSyncCursor(
                    mailbox_binding_id=binding.mailbox_binding_id,
                    folder=folder_name,
                    company_id=binding.company_id,
                    uidvalidity=batch.uidvalidity,
                    last_uid=advanced_uid,
                    backfill_completed=backfill_completed,
                    oldest_uid=oldest_uid,
                    last_reconcile_at=last_reconcile_at,
                    last_synced_at=now,
                    last_attempt_at=now,
                    last_error_kind=None,
                    last_error_at=None,
                    last_error_message=None,
                )
            )

        return MailSyncBindingResult(
            mailbox_binding_id=binding.mailbox_binding_id,
            company_id=binding.company_id,
            user_id=binding.user_id,
            email_address=binding.email_address,
            new_messages=inbox_notify,
            bootstrap=inbox_bootstrap,
            backfill_remaining=backfill_remaining,
        )

    async def _backfill_folder(
        self,
        binding: MailboxBinding,
        *,
        port: MailServerPort,
        secret: MailboxSecret,
        folder: str,
        oldest_uid: int,
        batch_size: int,
    ) -> "_BackfillResult":
        if oldest_uid <= 1:
            return _BackfillResult(oldest_uid=oldest_uid, completed=True)
        upper = max(oldest_uid - 1, 1)
        lower = max(upper - batch_size + 1, 1)
        uid_set = f"{lower}:{upper}"
        uids = await port.uid_search(
            secret,
            mailbox=folder,
            criteria=MailUidSearchCriteria(uid_set=uid_set),
        )
        if not uids:
            return _BackfillResult(oldest_uid=lower, completed=lower <= 1)
        messages: list[InboundMailMessage] = []
        for uid in uids:
            try:
                messages.append(
                    await port.fetch_message_by_uid(secret, mailbox=folder, uid=uid)
                )
            except MailUidNotFoundError:
                continue
        if messages:
            await self._persist_synced_messages(
                binding,
                folder=folder,
                messages=messages,
                port=port,
                secret=secret,
            )
        return _BackfillResult(oldest_uid=lower, completed=lower <= 1)

    async def _reconcile_folder_uids(
        self,
        binding: MailboxBinding,
        *,
        port: MailServerPort,
        secret: MailboxSecret,
        folder: str,
    ) -> None:
        if self._message_repository is None:
            return
        remote_uids = {
            int(uid)
            for uid in await port.uid_search(
                secret,
                mailbox=folder,
                criteria=MailUidSearchCriteria(all_messages=True),
            )
        }
        local_uids = await self._message_repository.list_uids(
            binding.mailbox_binding_id, folder=folder
        )
        orphans = [uid for uid in local_uids if uid not in remote_uids and uid > 0]
        if orphans:
            _ = await self._message_repository.delete_by_uids(
                binding.mailbox_binding_id,
                folder=folder,
                uids=orphans,
            )

    async def _refresh_flags_for_messages(
        self,
        binding: MailboxBinding,
        port: MailServerPort,
        secret: MailboxSecret,
        *,
        folder: str,
        messages: list[InboundMailMessage],
    ) -> None:
        if self._message_repository is None or not messages:
            return
        uids = [message.uid for message in messages]
        flags_map = await port.fetch_flags_for_uids(
            secret, mailbox=folder, uids=uids
        )
        for uid, flags in flags_map.items():
            _ = await self._message_repository.set_flags(
                binding.mailbox_binding_id,
                folder=folder,
                uid=int(uid),
                unread=flags.unread,
                flagged=flags.flagged,
                answered=flags.answered,
                draft=flags.draft,
            )

    async def _hydrate_messages_for_persist(
        self,
        port: MailServerPort,
        secret: MailboxSecret,
        *,
        folder: str,
        messages: list[InboundMailMessage],
    ) -> list[InboundMailMessage]:
        """Догружает body для header-only UID batch (RAG ingest)."""
        hydrated: list[InboundMailMessage] = []
        for message in messages:
            needs_body = message.body_text is None or not message.body_text.strip()
            if not needs_body:
                hydrated.append(message)
                continue
            try:
                full = await port.fetch_message_by_uid(
                    secret,
                    mailbox=folder,
                    uid=message.uid,
                )
            except MailUidNotFoundError:
                hydrated.append(message)
                continue
            hydrated.append(
                full.model_copy(
                    update={
                        "unread": message.unread,
                        "flagged": message.flagged,
                        "answered": message.answered,
                        "draft": message.draft,
                    }
                )
            )
        return hydrated

    async def _persist_synced_messages(
        self,
        binding: MailboxBinding,
        *,
        folder: str,
        messages: list[InboundMailMessage],
        port: MailServerPort | None = None,
        secret: MailboxSecret | None = None,
    ) -> None:
        if self._message_repository is None:
            return
        to_store = messages
        if port is not None and secret is not None:
            to_store = await self._hydrate_messages_for_persist(
                port,
                secret,
                folder=folder,
                messages=messages,
            )

        rag_namespace: str | None = None
        if self._namespace_service is not None:
            company = await self._company_repository.get(binding.company_id)
            if company is None:
                raise ValueError(
                    f"company not found for mail sync: {binding.company_id}"
                )
            if binding.kind == MailboxBindingKind.USER:
                if binding.user_id is None or not binding.user_id.strip():
                    raise ValueError("binding.user_id required to persist user mail")
                user = await self._user_repository.get(binding.user_id)
                if user is None:
                    raise ValueError(f"user not found for mail sync: {binding.user_id}")
                await ensure_personal_namespace_for_user(
                    self._namespace_service,
                    user,
                    company=company,
                )
                rag_namespace = personal_namespace_name(user.user_id)
            else:
                technical_name = f"mail-{binding.mailbox_binding_id}"
                _ = await self._namespace_service.get_or_create(
                    technical_name,
                    kind=NamespaceKind.TECHNICAL,
                    description=f"Role mailbox {binding.email_address}",
                )
                rag_namespace = technical_name

        now = _utcnow()
        for message in to_store:
            file_ids = await self._materialize_attachments(
                message,
                mailbox_binding_id=binding.mailbox_binding_id,
                mailbox_email=binding.email_address,
            )
            attachment_refs: list[StoredMailAttachmentRef] = []
            attachment_names: list[str] = []
            for index, attachment in enumerate(message.attachments):
                if attachment.filename.strip():
                    attachment_names.append(attachment.filename)
                file_id = file_ids.get(index)
                attachment_refs.append(
                    StoredMailAttachmentRef(
                        filename=attachment.filename,
                        content_type=attachment.content_type,
                        size=attachment.size if attachment.size > 0 else len(attachment.content),
                        file_id=file_id,
                        available=attachment.available and (
                            file_id is not None or bool(attachment.content)
                        ),
                        parse_error=attachment.parse_error,
                    )
                )
            snippet = ""
            if message.body_text is not None and message.body_text.strip():
                text = " ".join(message.body_text.split())
                snippet = text if len(text) <= 160 else f"{text[:157]}..."
            mail_message_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{binding.mailbox_binding_id}:{folder}:{message.uid}",
                )
            )
            rag_document_id: str | None = None
            rag_text_parts: list[str] = []
            if message.subject is not None and message.subject.strip():
                rag_text_parts.append(f"Subject: {message.subject.strip()}")
            if message.from_address is not None and message.from_address.strip():
                rag_text_parts.append(f"From: {message.from_address.strip()}")
            if message.body_text is not None and message.body_text.strip():
                rag_text_parts.append(message.body_text.strip())
            if attachment_names:
                rag_text_parts.append(
                    "Attachments: " + ", ".join(attachment_names)
                )
            rag_text = "\n\n".join(rag_text_parts)
            file_id_list = [ref.file_id for ref in attachment_refs if ref.file_id is not None]
            if (
                self._rag_client is not None
                and rag_namespace is not None
                and rag_text.strip()
            ):
                rag_metadata: RAGMetadata = {
                    "company_id": binding.company_id,
                    "document_id": mail_message_id,
                    "mailbox_binding_id": binding.mailbox_binding_id,
                    "mail_uid": message.uid,
                    "folder": folder,
                    "thread_id": thread_id_for_message(message),
                    "ttl_seconds": 0,
                    "uploaded_by_user_id": (
                        binding.user_id if binding.user_id is not None else ""
                    ),
                    "has_attachments": len(message.attachments) > 0,
                    "attachment_names": list(attachment_names),
                    "file_ids": file_id_list,
                }
                ingest = await self._rag_client.ingest_text(
                    namespace_id=rag_namespace,
                    text=rag_text,
                    document_name=mail_message_id,
                    metadata=rag_metadata,
                )
                rag_document_id = ingest.document_id
            stored = StoredMailMessage(
                mail_message_id=mail_message_id,
                company_id=binding.company_id,
                mailbox_binding_id=binding.mailbox_binding_id,
                user_id=binding.user_id,
                folder=folder,
                uid=int(message.uid),
                message_id=message.message_id,
                thread_id=thread_id_for_message(message),
                subject=message.subject if message.subject is not None else "",
                from_address=message.from_address if message.from_address is not None else "",
                to_addresses=list(message.to_addresses),
                cc_addresses=[],
                date_at=message.date,
                unread=message.unread,
                flagged=message.flagged,
                answered=message.answered,
                draft=message.draft,
                has_attachments=len(message.attachments) > 0,
                snippet=snippet,
                body_text=message.body_text,
                body_html=message.body_html,
                attachments=attachment_refs,
                in_reply_to=message.in_reply_to,
                references=message.references,
                rag_document_id=rag_document_id,
                rag_namespace=rag_namespace,
                synced_at=now,
                created_at=now,
                updated_at=now,
            )
            _ = await self._message_repository.upsert(stored)

    async def ensure_system_mail_connection(self) -> CompanyMailConnection | None:
        system_cfg = self._mail_config.system
        if not system_cfg.enabled:
            logger.info("mail.system.ensure skipped: mail.system.enabled=false")
            return None
        if system_cfg.imap_host is None or not system_cfg.imap_host.strip():
            raise MailConfigError("mail.system.imap_host is required when enabled")
        if system_cfg.smtp_host is None or not system_cfg.smtp_host.strip():
            raise MailConfigError("mail.system.smtp_host is required when enabled")

        provider = MailProvider(system_cfg.provider)
        existing = await self._connection_repository.get_by_company(SYSTEM_COMPANY_ID)
        now = _utcnow()
        connection_id = (
            existing.company_mail_connection_id
            if existing is not None
            else f"mailconn_{uuid.uuid4().hex}"
        )
        ispmanager: IspmanagerProvisionConfig | None = None
        if provider == MailProvider.ISPMANAGER:
            isp = system_cfg.ispmanager
            if isp.base_url is None or not isp.base_url.strip():
                raise MailConfigError("mail.system.ispmanager.base_url is required")
            if isp.authinfo_user is None or not isp.authinfo_user.strip():
                raise MailConfigError("mail.system.ispmanager.authinfo_user is required")
            password_encrypted: str | None = None
            if isp.authinfo_password is not None and isp.authinfo_password.strip():
                password_encrypted = encrypt_secret(isp.authinfo_password)
            elif (
                existing is not None
                and existing.ispmanager is not None
                and existing.ispmanager.authinfo_password_encrypted is not None
            ):
                password_encrypted = existing.ispmanager.authinfo_password_encrypted
            else:
                raise MailConfigError("mail.system.ispmanager.authinfo_password is required")
            ispmanager = IspmanagerProvisionConfig(
                base_url=isp.base_url.strip(),
                authinfo_user=isp.authinfo_user.strip(),
                authinfo_password_encrypted=password_encrypted,
            )

        connection = CompanyMailConnection(
            company_mail_connection_id=connection_id,
            company_id=SYSTEM_COMPANY_ID,
            mail_domain=system_cfg.mail_domain.strip().lower(),
            provider=provider,
            imap_host=system_cfg.imap_host.strip(),
            imap_port=system_cfg.imap_port,
            smtp_host=system_cfg.smtp_host.strip(),
            smtp_port=system_cfg.smtp_port,
            use_ssl=system_cfg.use_ssl,
            supports_provision=provider == MailProvider.ISPMANAGER,
            status=MailConnectionStatus.ACTIVE,
            ispmanager=ispmanager,
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        stored = await self._connection_repository.upsert(connection)
        logger.info(
            "mail.system.connection_ensured",
            mail_domain=stored.mail_domain,
            provider=str(stored.provider),
        )
        return stored

    async def ensure_system_role_mailboxes(self) -> list[str]:
        connection = await self.ensure_system_mail_connection()
        if connection is None:
            return []
        ensured: list[str] = []
        for local_part_raw in self._mail_config.system.role_mailboxes:
            local_part = local_part_raw.strip().lower()
            if not local_part:
                raise MailConfigError("mail.system.role_mailboxes contains empty local_part")
            binding = await self.bind_mailbox(
                MailboxBindingCreatePayload(
                    kind=MailboxBindingKind.ROLE,
                    local_part=local_part,
                    provision=True,
                    sync_enabled=True,
                ),
                company_id=SYSTEM_COMPANY_ID,
            )
            ensured.append(binding.email_address)
        return ensured

    async def ensure_system_user_bindings(self) -> list[str]:
        connection = await self.ensure_system_mail_connection()
        if connection is None:
            return []
        company = await self._company_repository.get(SYSTEM_COMPANY_ID)
        if company is None:
            raise MailConfigError("system company not found")
        ensured: list[str] = []
        for user_id in company.members:
            existing = await self._binding_repository.get_by_user(SYSTEM_COMPANY_ID, user_id)
            if existing is not None:
                ensured.append(existing.email_address)
                continue
            binding = await self.bind_mailbox(
                MailboxBindingCreatePayload(
                    user_id=user_id,
                    kind=MailboxBindingKind.USER,
                    provision=True,
                    sync_enabled=True,
                ),
                company_id=SYSTEM_COMPANY_ID,
            )
            ensured.append(binding.email_address)
        return ensured

    async def reconcile_system(self) -> MailReconcileResult:
        connection = await self.ensure_system_mail_connection()
        role_mailboxes = await self.ensure_system_role_mailboxes()
        user_bindings = await self.ensure_system_user_bindings()
        return MailReconcileResult(
            connection_ensured=connection is not None,
            role_mailboxes_ensured=role_mailboxes,
            user_bindings_ensured=user_bindings,
        )
