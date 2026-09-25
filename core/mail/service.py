"""MailService: connection, bindings, system ensure/reconcile."""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final, final

from core.ai.company_settings import decrypt_secret, encrypt_secret
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzCheckItem, AuthzObject, AuthzSubject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation, AuthzSubjectKind
from core.clients.rag_client import RagClient
from core.config import get_settings
from core.config.models import MailConfig, MailLocalDevConfig
from core.context import get_context
from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.reader.service import read_stored_file_by_id
from core.files.registry import default_retention_for_source
from core.files.service import FilesService
from core.logging import get_logger
from core.mail.attachment_index import MailAttachmentFileIndex
from core.mail.authz.tuples import (
    mailbox_binding_company_link,
    mailbox_binding_member_tuple,
    mailbox_binding_owner_tuple,
)
from core.mail.calendar_colors import default_calendar_color, require_mail_calendar_color
from core.mail.enqueue import enqueue_mail_rag_index, enqueue_mail_sync_binding
from core.mail.exceptions import (
    MailBindingNotFoundError,
    MailConfigError,
    MailConnectionNotFoundError,
    MailMessageNotFoundError,
    MailPermissionError,
    MailSecretMissingError,
    MailSystemConnectionReadOnlyError,
    MailTransportError,
    MailUidNotFoundError,
)
from core.mail.factory import build_mail_server_port
from core.mail.html_text import looks_like_html, mail_snippet, mail_visible_text
from core.mail.imip import calendar_upsert_payload_from_imip, extract_imip_ics
from core.mail.models import (
    INBOX_FOLDER,
    CompanyMailConnection,
    CompanyMailConnectionUpsertPayload,
    InboundMailMessage,
    IspmanagerProvisionConfig,
    MailAttachment,
    MailboxBinding,
    MailboxBindingCreatePayload,
    MailboxBindingHealthcheckPayload,
    MailboxBindingKind,
    MailboxBindingMember,
    MailboxBindingMemberPayload,
    MailboxBindingMemberRole,
    MailboxBindingPatchPayload,
    MailboxEnsureSpec,
    MailboxSecret,
    MailboxSyncCursor,
    MailConnectionScope,
    MailConnectionStatus,
    MailDraftSavePayload,
    MailDraftSaveResult,
    MailFetchQuery,
    MailFolder,
    MailFolderListResult,
    MailFolderRole,
    MailFoldersReorderPayload,
    MailImapSystemFlag,
    MailMessageFlagPayload,
    MailMessageFlagResult,
    MailMessageListItem,
    MailMessageListPayload,
    MailMessageListResult,
    MailMessageMovePayload,
    MailMessageMoveResult,
    MailMessageRagIndexPayload,
    MailMessageRagIndexResult,
    MailMessageSearchPayload,
    MailMessageStarPayload,
    MailMessageStarResult,
    MailProvider,
    MailRagIndexStatus,
    MailReconcileResult,
    MailSendPayload,
    MailSendResult,
    MailServerHealth,
    MailSyncBindingResult,
    MailSyncErrorKind,
    MailSyncLagStats,
    MailSyncNowPayload,
    MailSyncNowResult,
    MailSystemEnsureResult,
    MailThreadMessage,
    MailThreadPayload,
    MailThreadResult,
    MailUidSearchCriteria,
    OutboundMailMessage,
    PersonalMailboxConnectPayload,
    PersonalMailboxHealthcheckPayload,
    StoredMailboxFolder,
    StoredMailMessage,
)
from core.mail.mutations import build_rfc822_bytes
from core.mail.ports import MailCalendarBridge, MailServerPort
from core.mail.threads import thread_id_for_message
from core.models.calendar_models import CalendarAutolinkStatus
from core.models.identity_models import SYSTEM_COMPANY_ID, Company, NamespaceKind, User
from core.namespace import (
    NamespaceService,
    ensure_personal_namespace_for_user,
    personal_namespace_name,
)
from core.pagination import decode_cursor, encode_cursor
from core.rag.models import RAGMetadata
from core.utils.time import utcnow

logger = get_logger(__name__)

_LOCAL_PART_RE = re.compile(r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")


@dataclass(frozen=True, slots=True)
class _BackfillResult:
    oldest_uid: int
    completed: bool


_FOLDER_ROLE_SORT_ORDER: Final[dict[MailFolderRole, int]] = {
    MailFolderRole.INBOX: 0,
    MailFolderRole.SENT: 1,
    MailFolderRole.DRAFTS: 2,
    MailFolderRole.TRASH: 3,
    MailFolderRole.ARCHIVE: 4,
    MailFolderRole.JUNK: 5,
    MailFolderRole.OTHER: 6,
}


def _default_folder_sort_key(folder: MailFolder) -> tuple[int, str]:
    return (_FOLDER_ROLE_SORT_ORDER.get(folder.role, 6), folder.name.lower())




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


def to_message_list_item(message: InboundMailMessage) -> MailMessageListItem:
    clipped = mail_snippet(body_text=message.body_text, body_html=message.body_html)
    snippet: str | None = clipped if clipped else None
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
        rag_index_status=MailRagIndexStatus.SKIPPED,
    )


def stored_to_list_item(stored: StoredMailMessage) -> MailMessageListItem:
    snippet_raw = stored.snippet
    if snippet_raw.strip() and looks_like_html(snippet_raw):
        snippet_raw = mail_snippet(body_text=None, body_html=snippet_raw)
    return MailMessageListItem(
        uid=str(stored.uid),
        message_id=stored.message_id,
        subject=stored.subject if stored.subject.strip() else None,
        from_address=stored.from_address if stored.from_address.strip() else None,
        to_addresses=list(stored.to_addresses),
        snippet=snippet_raw if snippet_raw.strip() else None,
        attachment_count=len(stored.attachments) if stored.attachments else (
            1 if stored.has_attachments else 0
        ),
        unread=stored.unread,
        flagged=stored.flagged,
        date=stored.date_at,
        in_reply_to=stored.in_reply_to,
        references=stored.references,
        rag_index_status=stored.rag_index_status,
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
        authz: AuthzService,
        namespace_service: NamespaceService | None = None,
        rag_client: RagClient | None = None,
        mail_config: MailConfig,
        port_override: MailServerPort | None = None,
        files_service: FilesService | None = None,
        attachment_file_index: MailAttachmentFileIndex | None = None,
        mail_sync_backfill_batch_size: int = 50,
        mail_sync_reconcile_every_n: int = 1,
        calendar_bridge: MailCalendarBridge | None = None,
    ) -> None:
        self._authz: Final[AuthzService] = authz
        self._namespace_service: Final[NamespaceService | None] = namespace_service
        self._rag_client: Final[RagClient | None] = rag_client
        self._mail_config: Final[MailConfig] = mail_config
        self._port_override: Final[MailServerPort | None] = port_override
        self._files_service: Final[FilesService | None] = files_service
        self._attachment_file_index: Final[MailAttachmentFileIndex | None] = attachment_file_index
        self._backfill_batch_size: Final[int] = mail_sync_backfill_batch_size
        self._reconcile_every_n: Final[int] = mail_sync_reconcile_every_n
        self._calendar_bridge: Final[MailCalendarBridge | None] = calendar_bridge
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

    async def _connection_for_binding(
        self, binding: MailboxBinding
    ) -> CompanyMailConnection | None:
        return await CompanyMailConnection.get(binding.company_mail_connection_id)

    async def _require_connection_for_binding(
        self, binding: MailboxBinding
    ) -> CompanyMailConnection:
        connection = await self._connection_for_binding(binding)
        if connection is None:
            raise MailConnectionNotFoundError(
                company_mail_connection_id=binding.company_mail_connection_id,
            )
        return connection

    async def require_connection_for_binding(
        self, binding: MailboxBinding
    ) -> CompanyMailConnection:
        """Connection for binding FK (company or personal). Not get_by_company."""
        return await self._require_connection_for_binding(binding)

    async def public_binding(self, binding: MailboxBinding) -> MailboxBinding:
        connection = await self._connection_for_binding(binding)
        if connection is None:
            return binding
        return binding.model_copy(
            update={
                "connection_scope": connection.scope,
                "imap_host": connection.imap_host,
                "imap_port": connection.imap_port,
                "smtp_host": connection.smtp_host,
                "smtp_port": connection.smtp_port,
                "use_ssl": connection.use_ssl,
            }
        )

    async def get_connection(self, company_id: str | None = None) -> CompanyMailConnection | None:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        return await CompanyMailConnection.for_company(resolved_company_id)

    async def upsert_connection(
        self,
        payload: CompanyMailConnectionUpsertPayload,
        *,
        company_id: str | None = None,
    ) -> CompanyMailConnection:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        if resolved_company_id == SYSTEM_COMPANY_ID:
            raise MailSystemConnectionReadOnlyError()

        existing = await CompanyMailConnection.for_company(resolved_company_id)
        now = utcnow()
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
            scope=MailConnectionScope.COMPANY,
            owner_user_id=None,
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
        return await CompanyMailConnection.upsert_by_company_mail_connection_id(connection)

    def _active_user_id(self) -> str:
        ctx = get_context()
        if ctx is None:
            raise MailConfigError("authenticated user is required for mail operations")
        return ctx.user.user_id

    async def _is_company_admin(self, company_id: str) -> bool:
        return await self._authz.check_company_admin(company_id=company_id)

    async def require_company_admin(self, company_id: str | None = None) -> None:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        try:
            await self._authz.require_company_admin(company_id=resolved_company_id)
        except AuthzDenied as exc:
            raise MailPermissionError(
                f"admin role required for company_id={resolved_company_id}"
            ) from exc

    async def check_company_admin(self, company_id: str | None = None) -> bool:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        return await self._is_company_admin(resolved_company_id)

    async def _require_binding_access(
        self,
        binding: MailboxBinding,
        *,
        company_id: str,
        level: str = "viewer",
    ) -> None:
        _ = company_id
        user_id = self._active_user_id()
        obj = AuthzObject.mailbox_binding(binding.mailbox_binding_id)
        try:
            if level == "viewer":
                await self._authz.require_can_view(obj, user_id=user_id)
            elif level == "editor":
                await self._authz.require_can_edit(obj, user_id=user_id)
            elif level == "admin":
                await self._authz.require_can_admin(obj, user_id=user_id)
            else:
                raise ValueError(f"unsupported mailbox binding access level: {level}")
        except AuthzDenied as exc:
            raise MailPermissionError(
                f"no access to mailbox_binding_id={binding.mailbox_binding_id}"
            ) from exc

    async def _write_binding_owner(
        self,
        mailbox_binding_id: str,
        owner_user_id: str,
        *,
        company_id: str,
    ) -> None:
        await self._authz.write(
            [
                mailbox_binding_company_link(mailbox_binding_id, company_id),
                mailbox_binding_owner_tuple(mailbox_binding_id, owner_user_id),
            ]
        )

    async def _clear_binding_tuples(self, mailbox_binding_id: str) -> None:
        deletes = await self._authz.list_tuples(AuthzObject.mailbox_binding(mailbox_binding_id))
        if deletes:
            await self._authz.delete(deletes)

    async def list_my_bindings(self, company_id: str | None = None) -> list[MailboxBinding]:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        user_id = self._active_user_id()
        candidates = await MailboxBinding.list_by_company(resolved_company_id)
        if not candidates:
            return []
        checks = [
            AuthzCheckItem(
                subject=AuthzSubject.user(user_id),
                relation=AuthzRelation.CAN_VIEW,
                obj=AuthzObject.mailbox_binding(binding.mailbox_binding_id),
                correlation_id=binding.mailbox_binding_id,
            )
            for binding in candidates
        ]
        allowed = await self._authz.batch_check(checks)
        return [
            binding
            for binding, ok in zip(candidates, allowed, strict=True)
            if ok
        ]

    async def list_bindings(self, company_id: str | None = None) -> list[MailboxBinding]:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        return await MailboxBinding.list_by_company(resolved_company_id)

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
        existing_list = await MailboxBinding.list_by_user(
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
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        if binding.kind != MailboxBindingKind.USER or binding.user_id is None:
            raise ValueError("only user bindings can be default")
        if not acting_as_admin:
            user_id = self._active_user_id()
            if binding.user_id != user_id and not await self._is_company_admin(resolved_company_id):
                raise MailPermissionError(
                    f"no access to mailbox_binding_id={mailbox_binding_id}"
                )
        await MailboxBinding.clear_defaults_for_user(
            resolved_company_id,
            binding.user_id,
            except_binding_id=binding.mailbox_binding_id,
        )
        updated = binding.model_copy(
            update={"is_default": True, "updated_at": utcnow()}
        )
        return await MailboxBinding.upsert_by_email(updated)

    async def patch_binding(
        self,
        mailbox_binding_id: str,
        payload: MailboxBindingPatchPayload,
        *,
        company_id: str | None = None,
    ) -> MailboxBinding:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)

        connection = await self._require_connection_for_binding(binding)
        is_personal = connection.scope == MailConnectionScope.PERSONAL

        has_host_fields = (
            payload.imap_host is not None
            or payload.imap_port is not None
            or payload.smtp_host is not None
            or payload.smtp_port is not None
            or payload.use_ssl is not None
        )
        has_admin_fields = (
            payload.user_id is not None
            or payload.sync_enabled is not None
            or payload.password is not None
        )
        has_color = payload.calendar_color is not None
        if not has_admin_fields and not has_color and not has_host_fields:
            raise ValueError("MailboxBindingPatchPayload is empty")

        is_admin = await self._is_company_admin(resolved_company_id)
        acting_user_id = self._active_user_id()
        is_owner = (
            binding.kind == MailboxBindingKind.USER
            and binding.user_id is not None
            and binding.user_id == acting_user_id
        )
        if payload.user_id is not None and not is_admin:
            raise MailPermissionError(
                f"admin required to reassign mailbox_binding_id={mailbox_binding_id}"
            )
        if has_host_fields and not is_personal:
            raise MailPermissionError(
                "imap/smtp hosts can only be patched on personal mailboxes"
            )
        if is_personal:
            if not (is_admin or is_owner):
                raise MailPermissionError(
                    f"no access to patch mailbox_binding_id={mailbox_binding_id}"
                )
        else:
            if (payload.sync_enabled is not None or payload.password is not None) and not is_admin:
                raise MailPermissionError(
                    f"admin required to patch mailbox_binding_id={mailbox_binding_id}"
                )
            if has_color and not (is_admin or is_owner):
                raise MailPermissionError(
                    f"no access to patch calendar_color for mailbox_binding_id={mailbox_binding_id}"
                )

        previous_owner_user_id = binding.user_id
        user_id = binding.user_id
        if payload.user_id is not None:
            if not payload.user_id.strip():
                raise ValueError("user_id must not be empty")
            user = await User.get(payload.user_id)
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

        if has_host_fields:
            updated_connection = connection.model_copy(
                update={
                    "imap_host": (
                        payload.imap_host.strip()
                        if payload.imap_host is not None
                        else connection.imap_host
                    ),
                    "imap_port": (
                        payload.imap_port
                        if payload.imap_port is not None
                        else connection.imap_port
                    ),
                    "smtp_host": (
                        payload.smtp_host.strip()
                        if payload.smtp_host is not None
                        else connection.smtp_host
                    ),
                    "smtp_port": (
                        payload.smtp_port
                        if payload.smtp_port is not None
                        else connection.smtp_port
                    ),
                    "use_ssl": (
                        payload.use_ssl if payload.use_ssl is not None else connection.use_ssl
                    ),
                    "updated_at": utcnow(),
                }
            )
            if not updated_connection.imap_host.strip():
                raise ValueError("imap_host must not be empty")
            if not updated_connection.smtp_host.strip():
                raise ValueError("smtp_host must not be empty")
            _ = await CompanyMailConnection.upsert_by_company_mail_connection_id(updated_connection)

        updated = binding.model_copy(
            update={
                "user_id": user_id if binding.kind == MailboxBindingKind.USER else None,
                "sync_enabled": sync_enabled,
                "password_encrypted": password_encrypted,
                "calendar_color": calendar_color,
                "updated_at": utcnow(),
            }
        )
        stored = await MailboxBinding.upsert_by_email(updated)
        if (
            payload.user_id is not None
            and stored.kind == MailboxBindingKind.USER
            and stored.user_id is not None
            and stored.user_id != previous_owner_user_id
        ):
            try:
                await self._clear_binding_tuples(stored.mailbox_binding_id)
                await self._write_binding_owner(
                    stored.mailbox_binding_id,
                    stored.user_id,
                    company_id=resolved_company_id,
                )
            except Exception:
                _ = await MailboxBinding.upsert_by_email(binding)
                if previous_owner_user_id is not None:
                    await self._clear_binding_tuples(stored.mailbox_binding_id)
                    await self._write_binding_owner(
                        stored.mailbox_binding_id,
                        previous_owner_user_id,
                        company_id=resolved_company_id,
                    )
                raise
        if (
            payload.user_id is not None
            and stored.kind == MailboxBindingKind.USER
            and stored.user_id is not None
        ):
            existing_for_user = await MailboxBinding.list_by_user(
                resolved_company_id, stored.user_id
            )
            if len(existing_for_user) == 1 and not stored.is_default:
                return await self.set_default_binding(
                    stored.mailbox_binding_id,
                    company_id=resolved_company_id,
                    acting_as_admin=True,
                )
        return stored

    async def connect_personal_mailbox(
        self,
        payload: PersonalMailboxConnectPayload,
        *,
        company_id: str | None = None,
    ) -> MailboxBinding:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        acting_user_id = self._active_user_id()
        email_address = payload.email_address.strip().lower()
        if "@" not in email_address:
            raise ValueError(f"Invalid email_address={payload.email_address!r}")
        local_part, mail_domain = email_address.split("@", 1)
        if not local_part.strip() or not mail_domain.strip():
            raise ValueError(f"Invalid email_address={payload.email_address!r}")
        if not payload.password.strip():
            raise ValueError("password must not be empty")
        imap_host = payload.imap_host.strip()
        smtp_host = payload.smtp_host.strip()
        if not imap_host or not smtp_host:
            raise ValueError("imap_host and smtp_host are required")

        health = await self.healthcheck_personal_credentials(payload)
        if not health.imap_ok or not health.smtp_ok:
            detail = health.detail if health.detail is not None else "imap/smtp login failed"
            raise MailConfigError(f"personal mailbox healthcheck failed: {detail}")

        existing = await MailboxBinding.by_email(
            resolved_company_id, email_address
        )
        now = utcnow()
        if existing is not None:
            existing_connection = await self._require_connection_for_binding(existing)
            if existing_connection.scope != MailConnectionScope.PERSONAL:
                raise MailPermissionError(
                    f"email_address={email_address} is already bound as company mailbox"
                )
            if existing.user_id != acting_user_id:
                raise MailPermissionError(
                    f"email_address={email_address} belongs to another user"
                )
            connection = existing_connection.model_copy(
                update={
                    "mail_domain": mail_domain,
                    "imap_host": imap_host,
                    "imap_port": payload.imap_port,
                    "smtp_host": smtp_host,
                    "smtp_port": payload.smtp_port,
                    "use_ssl": payload.use_ssl,
                    "status": MailConnectionStatus.ACTIVE,
                    "updated_at": now,
                }
            )
            _ = await CompanyMailConnection.upsert_by_company_mail_connection_id(connection)
            calendar_color = (
                require_mail_calendar_color(payload.calendar_color)
                if payload.calendar_color is not None
                else existing.calendar_color
            )
            updated = existing.model_copy(
                update={
                    "password_encrypted": encrypt_secret(payload.password),
                    "sync_enabled": payload.sync_enabled,
                    "calendar_color": calendar_color,
                    "updated_at": now,
                }
            )
            stored = await MailboxBinding.upsert_by_email(updated)
            _ = await self.refresh_folders_from_imap(
                stored.mailbox_binding_id,
                company_id=resolved_company_id,
            )
            await enqueue_mail_sync_binding(
                company_id=resolved_company_id,
                mailbox_binding_id=stored.mailbox_binding_id,
            )
            return await self._autolink_mailbox_calendar(
                binding=stored,
                company_id=resolved_company_id,
                imap_host=imap_host,
                mail_domain=mail_domain,
                password=payload.password,
            )

        connection_id = f"mailconn_{uuid.uuid4().hex}"
        connection = CompanyMailConnection(
            company_mail_connection_id=connection_id,
            company_id=resolved_company_id,
            scope=MailConnectionScope.PERSONAL,
            owner_user_id=acting_user_id,
            mail_domain=mail_domain,
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host=imap_host,
            imap_port=payload.imap_port,
            smtp_host=smtp_host,
            smtp_port=payload.smtp_port,
            use_ssl=payload.use_ssl,
            supports_provision=False,
            status=MailConnectionStatus.ACTIVE,
            ispmanager=None,
            created_at=now,
            updated_at=now,
        )
        _ = await CompanyMailConnection.upsert_by_company_mail_connection_id(connection)

        existing_for_user = await MailboxBinding.list_by_user(
            resolved_company_id, acting_user_id
        )
        is_default = len(existing_for_user) == 0
        calendar_color = (
            require_mail_calendar_color(payload.calendar_color)
            if payload.calendar_color is not None
            else default_calendar_color(email_address)
        )
        binding = MailboxBinding(
            mailbox_binding_id=f"mailbind_{uuid.uuid4().hex}",
            company_id=resolved_company_id,
            company_mail_connection_id=connection_id,
            user_id=acting_user_id,
            kind=MailboxBindingKind.USER,
            email_address=email_address,
            local_part=local_part,
            sync_enabled=payload.sync_enabled,
            is_default=is_default,
            calendar_color=calendar_color,
            password_encrypted=encrypt_secret(payload.password),
            created_at=now,
            updated_at=now,
        )
        if is_default:
            await MailboxBinding.clear_defaults_for_user(
                resolved_company_id,
                acting_user_id,
                except_binding_id=binding.mailbox_binding_id,
            )
        stored = await MailboxBinding.upsert_by_email(binding)
        try:
            await self._write_binding_owner(
                stored.mailbox_binding_id,
                acting_user_id,
                company_id=resolved_company_id,
            )
        except Exception:
            _ = await MailboxBinding.delete_in_company(
                resolved_company_id, stored.mailbox_binding_id
            )
            raise
        _ = await self.refresh_folders_from_imap(
            stored.mailbox_binding_id,
            company_id=resolved_company_id,
        )
        await enqueue_mail_sync_binding(
            company_id=resolved_company_id,
            mailbox_binding_id=stored.mailbox_binding_id,
        )
        return await self._autolink_mailbox_calendar(
            binding=stored,
            company_id=resolved_company_id,
            imap_host=imap_host,
            mail_domain=mail_domain,
            password=payload.password,
        )

    async def relink_mailbox_calendar(
        self,
        mailbox_binding_id: str,
        *,
        company_id: str | None = None,
    ) -> MailboxBinding:
        """
        Повторная попытка авто-привязки календаря по сохранённому паролю ящика:
        пользователю не нужно вводить app password заново.
        """
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        await self._require_binding_calendar_access(
            binding, company_id=resolved_company_id
        )
        connection = await self._require_connection_for_binding(binding)
        secret = self._binding_secret(binding)
        return await self._autolink_mailbox_calendar(
            binding=binding,
            company_id=resolved_company_id,
            imap_host=connection.imap_host,
            mail_domain=connection.mail_domain,
            password=secret.password,
        )

    async def unlink_mailbox_calendar(
        self,
        mailbox_binding_id: str,
        *,
        company_id: str | None = None,
    ) -> MailboxBinding:
        """Отключить календарь ящика, оставив саму почту подключённой."""
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        await self._require_binding_calendar_access(
            binding, company_id=resolved_company_id
        )
        await self._unlink_mailbox_calendar(binding)
        return await self._store_calendar_autolink_status(
            binding=binding,
            status=CalendarAutolinkStatus.DISABLED,
            detail="disconnected by user",
        )

    async def _require_binding_calendar_access(
        self,
        binding: MailboxBinding,
        *,
        company_id: str,
    ) -> None:
        if await self._is_company_admin(company_id):
            return
        acting_user_id = self._active_user_id()
        is_owner = (
            binding.kind == MailboxBindingKind.USER
            and binding.user_id is not None
            and binding.user_id == acting_user_id
        )
        if not is_owner:
            raise MailPermissionError(
                f"no access to manage calendar for mailbox_binding_id={binding.mailbox_binding_id}"
            )

    async def _autolink_mailbox_calendar(
        self,
        *,
        binding: MailboxBinding,
        company_id: str,
        imap_host: str,
        mail_domain: str,
        password: str,
    ) -> MailboxBinding:
        """
        Поднять CalDAV календарь ящика и записать итог в binding. Сбой календаря
        (HTTP/discovery) не откатывает bind почты, но виден как статус привязки.
        """
        if not self._calendar_autolink_enabled():
            return await self._store_calendar_autolink_status(
                binding=binding,
                status=CalendarAutolinkStatus.DISABLED,
                detail="calendar_sync.autolink_enabled is false",
            )
        if self._calendar_bridge is None or binding.user_id is None:
            return await self._store_calendar_autolink_status(
                binding=binding,
                status=CalendarAutolinkStatus.DISABLED,
                detail="calendar autolink needs a user-owned mailbox and calendar bridge",
            )
        try:
            outcome = await self._calendar_bridge.ensure_caldav_integration_from_mailbox(
                user_id=binding.user_id,
                company_id=company_id,
                mailbox_binding_id=binding.mailbox_binding_id,
                email_address=binding.email_address,
                password=password,
                imap_host=imap_host,
                mail_domain=mail_domain,
            )
        except Exception as exc:
            logger.warning(
                "mail.calendar_autolink_failed",
                mailbox_binding_id=binding.mailbox_binding_id,
                imap_host=imap_host,
                mail_domain=mail_domain,
                error=str(exc),
            )
            return await self._store_calendar_autolink_status(
                binding=binding,
                status=CalendarAutolinkStatus.FAILED,
                detail=str(exc),
            )
        return await self._store_calendar_autolink_status(
            binding=binding,
            status=outcome.status,
            detail=outcome.detail,
        )

    def _calendar_autolink_enabled(self) -> bool:
        return get_settings().calendar_sync.autolink_enabled

    async def _store_calendar_autolink_status(
        self,
        *,
        binding: MailboxBinding,
        status: CalendarAutolinkStatus,
        detail: str | None,
    ) -> MailboxBinding:
        if (
            binding.calendar_autolink_status == status
            and binding.calendar_autolink_detail == detail
        ):
            return binding
        updated = binding.model_copy(
            update={
                "calendar_autolink_status": status,
                "calendar_autolink_detail": detail,
                "updated_at": utcnow(),
            }
        )
        return await MailboxBinding.upsert_by_email(updated)

    async def _autolink_company_mailbox_calendar(
        self,
        *,
        binding: MailboxBinding,
        connection: CompanyMailConnection,
    ) -> MailboxBinding:
        """
        Авто-подъём календаря для корпоративного ящика. Пробуем один раз: после
        первой попытки статус зафиксирован, повтор — из настроек пользователем.
        """
        if binding.calendar_autolink_status != CalendarAutolinkStatus.DISABLED:
            return binding
        if binding.user_id is None:
            return binding
        secret = self._binding_secret(binding)
        return await self._autolink_mailbox_calendar(
            binding=binding,
            company_id=binding.company_id,
            imap_host=connection.imap_host,
            mail_domain=connection.mail_domain,
            password=secret.password,
        )

    async def _unlink_mailbox_calendar(self, binding: MailboxBinding) -> None:
        """
        Снять календарные интеграции отвязанного ящика: per-mailbox credential
        без ящика — висячая строка.
        """
        if self._calendar_bridge is None:
            return
        try:
            _ = await self._calendar_bridge.delete_calendar_integrations_for_mailbox(
                company_id=binding.company_id,
                mailbox_binding_id=binding.mailbox_binding_id,
            )
        except Exception as exc:
            logger.warning(
                "mail.calendar_unlink_failed",
                mailbox_binding_id=binding.mailbox_binding_id,
                error=str(exc),
            )

    async def _ingest_imip_invites(
        self,
        binding: MailboxBinding,
        messages: list[InboundMailMessage],
    ) -> None:
        """
        iMIP: входящий text/calendar -> upsert события календаря (дедуп по
        source_id). Best-effort: bad ICS / сбой календаря логируется, не ломает
        сохранение письма. Только для user-binding (есть owner).
        """
        if self._calendar_bridge is None or binding.user_id is None:
            return
        for message in messages:
            ics_text = extract_imip_ics(message)
            if ics_text is None:
                continue
            try:
                payload = calendar_upsert_payload_from_imip(
                    ics_text,
                    attendee_email=binding.email_address,
                    mailbox_binding_id=binding.mailbox_binding_id,
                )
                _ = await self._calendar_bridge.upsert_imip_event(
                    payload=payload,
                    user_id=binding.user_id,
                    company_id=binding.company_id,
                )
            except Exception as exc:
                logger.warning(
                    "mail.imip_ingest_failed",
                    mailbox_binding_id=binding.mailbox_binding_id,
                    message_uid=message.uid,
                    error=str(exc),
                )

    async def healthcheck_personal_credentials(
        self,
        payload: PersonalMailboxHealthcheckPayload | PersonalMailboxConnectPayload,
    ) -> MailServerHealth:
        email_address = payload.email_address.strip().lower()
        if "@" not in email_address:
            raise ValueError(f"Invalid email_address={payload.email_address!r}")
        if not payload.password.strip():
            raise ValueError("password must not be empty")
        imap_host = payload.imap_host.strip()
        smtp_host = payload.smtp_host.strip()
        if not imap_host or not smtp_host:
            raise ValueError("imap_host and smtp_host are required")
        _, mail_domain = email_address.split("@", 1)
        now = utcnow()
        ephemeral = CompanyMailConnection(
            company_mail_connection_id=f"mailconn_health_{uuid.uuid4().hex}",
            company_id=self._active_company_id(),
            scope=MailConnectionScope.PERSONAL,
            owner_user_id=self._active_user_id(),
            mail_domain=mail_domain,
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host=imap_host,
            imap_port=payload.imap_port,
            smtp_host=smtp_host,
            smtp_port=payload.smtp_port,
            use_ssl=payload.use_ssl,
            supports_provision=False,
            status=MailConnectionStatus.ACTIVE,
            ispmanager=None,
            created_at=now,
            updated_at=now,
        )
        port = self._port_for(ephemeral)
        secret = MailboxSecret(email_address=email_address, password=payload.password)
        return await port.healthcheck_with_credentials(secret)

    async def healthcheck_binding(
        self,
        mailbox_binding_id: str,
        payload: MailboxBindingHealthcheckPayload,
        *,
        company_id: str | None = None,
    ) -> MailServerHealth:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        connection = await self._require_connection_for_binding(binding)
        if connection.scope != MailConnectionScope.PERSONAL:
            raise MailPermissionError(
                "binding healthcheck is only for personal mailboxes"
            )
        is_admin = await self._is_company_admin(resolved_company_id)
        acting_user_id = self._active_user_id()
        is_owner = (
            binding.kind == MailboxBindingKind.USER
            and binding.user_id is not None
            and binding.user_id == acting_user_id
        )
        if not (is_admin or is_owner):
            raise MailPermissionError(
                f"no access to healthcheck mailbox_binding_id={mailbox_binding_id}"
            )

        imap_host = (
            payload.imap_host.strip()
            if payload.imap_host is not None
            else connection.imap_host
        )
        smtp_host = (
            payload.smtp_host.strip()
            if payload.smtp_host is not None
            else connection.smtp_host
        )
        if not imap_host or not smtp_host:
            raise ValueError("imap_host and smtp_host are required")
        probe_connection = connection.model_copy(
            update={
                "imap_host": imap_host,
                "imap_port": (
                    payload.imap_port
                    if payload.imap_port is not None
                    else connection.imap_port
                ),
                "smtp_host": smtp_host,
                "smtp_port": (
                    payload.smtp_port
                    if payload.smtp_port is not None
                    else connection.smtp_port
                ),
                "use_ssl": (
                    payload.use_ssl if payload.use_ssl is not None else connection.use_ssl
                ),
            }
        )
        if payload.password is not None:
            if not payload.password.strip():
                raise ValueError("password must not be empty")
            secret = MailboxSecret(
                email_address=binding.email_address,
                password=payload.password,
            )
        else:
            secret = self._binding_secret(binding)
        port = self._port_for(probe_connection)
        return await port.healthcheck_with_credentials(secret)

    async def bind_mailbox(
        self,
        payload: MailboxBindingCreatePayload,
        *,
        company_id: str | None = None,
    ) -> MailboxBinding:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        connection = await CompanyMailConnection.for_company(resolved_company_id)
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
            user = await User.get(payload.user_id)
            if user is None:
                raise ValueError(f"User not found: {payload.user_id}")
            local_part = _slug_local_part(user)
        else:
            raise ValueError("local_part or email_address or user_id required")

        if not _LOCAL_PART_RE.match(local_part):
            raise ValueError(f"Invalid local_part={local_part!r}")

        email_address = f"{local_part}@{connection.mail_domain}"
        existing = await MailboxBinding.by_email(resolved_company_id, email_address)
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
                has_secret = bool(
                    existing.password_encrypted and existing.password_encrypted.strip()
                )
                local_override = self._local_dev_mailbox_password(email_address)
                if has_secret and local_override is None:
                    if payload.provision and connection.supports_provision:
                        port = self._port_for(connection)
                        spec = MailboxEnsureSpec(
                            mail_domain=connection.mail_domain,
                            local_part=local_part,
                            password=secrets.token_urlsafe(24),
                        )
                        _ = await port.ensure_mailbox(spec)
                    return await self._autolink_company_mailbox_calendar(
                        binding=existing,
                        connection=connection,
                    )
                password = local_override if local_override is not None else secrets.token_urlsafe(24)
                if payload.provision and connection.supports_provision:
                    port = self._port_for(connection)
                    spec = MailboxEnsureSpec(
                        mail_domain=connection.mail_domain,
                        local_part=local_part,
                        password=password,
                    )
                    _ = await port.ensure_mailbox(spec)
                    if self._local_dev_allows_remote_password_mutation():
                        await port.set_mailbox_password(spec)
                    elif local_override is None and not has_secret:
                        raise MailConfigError(
                            "mail.local_dev: remote password mutation disabled; "
                            + f"add mailbox_passwords[{email_address!r}] in conf.local.json"
                        )
                repaired = existing.model_copy(
                    update={
                        "password_encrypted": encrypt_secret(password),
                        "updated_at": utcnow(),
                    }
                )
                stored_repaired = await MailboxBinding.upsert_by_email(repaired)
                return await self._autolink_company_mailbox_calendar(
                    binding=stored_repaired,
                    connection=connection,
                )

        previous_user_id = existing.user_id if existing is not None else None
        previous_was_default = bool(existing is not None and existing.is_default)

        local_override = self._local_dev_mailbox_password(email_address)
        password = payload.password
        if password is None or not password.strip():
            if local_override is not None:
                password = local_override
            else:
                password = secrets.token_urlsafe(24)

        mailbox_already_on_server = False
        if payload.provision and connection.supports_provision:
            port = self._port_for(connection)
            before = await port.list_mailboxes(connection.mail_domain)
            mailbox_already_on_server = any(
                item.email_address == email_address for item in before
            )
            spec = MailboxEnsureSpec(
                mail_domain=connection.mail_domain,
                local_part=local_part,
                password=password,
            )
            _ = await port.ensure_mailbox(spec)
            if mailbox_already_on_server:
                if self._local_dev_allows_remote_password_mutation():
                    await port.set_mailbox_password(spec)
                elif local_override is None and (
                    existing is None
                    or not existing.password_encrypted
                    or not existing.password_encrypted.strip()
                ):
                    raise MailConfigError(
                        "mail.local_dev: remote password mutation disabled; "
                        + f"add mailbox_passwords[{email_address!r}] in conf.local.json"
                    )

        now = utcnow()
        password_encrypted: str | None
        if payload.password is not None and payload.password.strip():
            password_encrypted = encrypt_secret(password)
        elif payload.provision and connection.supports_provision:
            password_encrypted = encrypt_secret(password)
        elif existing is not None and existing.password_encrypted is not None:
            password_encrypted = existing.password_encrypted
        else:
            password_encrypted = encrypt_secret(password)

        is_default = False
        if payload.kind == MailboxBindingKind.USER and target_user_id is not None:
            if payload.is_default is True:
                is_default = True
            elif payload.is_default is False:
                is_default = False
            else:
                siblings = await MailboxBinding.list_by_user(
                    resolved_company_id, target_user_id
                )
                sibling_ids = {item.mailbox_binding_id for item in siblings}
                if existing is not None:
                    sibling_ids.discard(existing.mailbox_binding_id)
                is_default = len(sibling_ids) == 0

        if is_default and target_user_id is not None:
            await MailboxBinding.clear_defaults_for_user(
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
        stored = await MailboxBinding.upsert_by_email(binding)
        owner_user_id = (
            stored.user_id if stored.user_id is not None else self._active_user_id()
        )
        try:
            await self._write_binding_owner(
                stored.mailbox_binding_id,
                owner_user_id,
                company_id=resolved_company_id,
            )
        except Exception:
            if existing is None:
                _ = await MailboxBinding.delete_in_company(
                    resolved_company_id, stored.mailbox_binding_id
                )
            raise
        if (
            previous_user_id is not None
            and previous_was_default
            and previous_user_id != target_user_id
        ):
            remaining = await MailboxBinding.list_by_user(
                resolved_company_id, previous_user_id
            )
            if remaining and not any(item.is_default for item in remaining):
                _ = await self.set_default_binding(
                    remaining[0].mailbox_binding_id,
                    company_id=resolved_company_id,
                    acting_as_admin=True,
                )
        return await self._autolink_company_mailbox_calendar(
            binding=stored,
            connection=connection,
        )

    async def unbind_mailbox(
        self,
        mailbox_binding_id: str,
        *,
        company_id: str | None = None,
        acting_as_admin: bool = False,
    ) -> None:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        connection = await self._connection_for_binding(binding)
        is_personal = (
            connection is not None and connection.scope == MailConnectionScope.PERSONAL
        )
        if not acting_as_admin:
            is_admin = await self._is_company_admin(resolved_company_id)
            acting_user_id = self._active_user_id()
            is_owner = (
                binding.kind == MailboxBindingKind.USER
                and binding.user_id is not None
                and binding.user_id == acting_user_id
            )
            if is_personal:
                if not (is_admin or is_owner):
                    raise MailPermissionError(
                        f"no access to unbind mailbox_binding_id={mailbox_binding_id}"
                    )
            elif not is_admin:
                raise MailPermissionError(
                    f"admin required to unbind mailbox_binding_id={mailbox_binding_id}"
                )
        deleted = await MailboxBinding.delete_in_company(resolved_company_id, mailbox_binding_id)
        if not deleted:
            raise MailBindingNotFoundError(mailbox_binding_id)
        await self._clear_binding_tuples(mailbox_binding_id)
        await self._unlink_mailbox_calendar(binding)
        if is_personal and connection is not None:
            _ = await CompanyMailConnection.delete_by_id(
                connection.company_mail_connection_id
            )
        if (
            binding.kind == MailboxBindingKind.USER
            and binding.user_id is not None
            and binding.is_default
        ):
            remaining = await MailboxBinding.list_by_user(
                resolved_company_id, binding.user_id
            )
            if remaining:
                _ = await self.set_default_binding(
                    remaining[0].mailbox_binding_id,
                    company_id=resolved_company_id,
                    acting_as_admin=True,
                )

    async def unbind_company_user_mailboxes(
        self,
        user_id: str,
        *,
        company_id: str | None = None,
    ) -> None:
        if not user_id.strip():
            raise ValueError("user_id is required")
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        bindings = await MailboxBinding.list_by_user(resolved_company_id, user_id)
        for binding in bindings:
            connection = await self._connection_for_binding(binding)
            if connection is not None and connection.scope == MailConnectionScope.PERSONAL:
                continue
            await self.unbind_mailbox(
                binding.mailbox_binding_id,
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
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)

        before_date: datetime | None = None
        before_uid: int | None = None
        if payload.cursor is not None and payload.cursor.strip():
            before_date, before_uid = decode_mail_list_cursor(payload.cursor)
        page = await StoredMailMessage.list_folder_page(
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
        needs_sync = False
        if payload.cursor is None and len(rows) == 0:
            folder_cursor = await MailboxSyncCursor.by_binding_folder(
                payload.mailbox_binding_id, folder=payload.folder
            )
            needs_sync = folder_cursor is None or folder_cursor.last_synced_at is None
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
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        before_date: datetime | None = None
        before_uid: int | None = None
        if payload.cursor is not None and payload.cursor.strip():
            before_date, before_uid = decode_mail_list_cursor(payload.cursor)
        page = await StoredMailMessage.search_local(
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
                sort_index=item.sort_index,
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
        now = utcnow()
        existing = await StoredMailboxFolder.list_for_binding(binding.mailbox_binding_id)
        existing_index = {item.folder_name: item.sort_index for item in existing}
        is_bootstrap = len(existing) == 0
        if is_bootstrap:
            ordered_folders = sorted(folders_result.folders, key=_default_folder_sort_key)
            assigned: dict[str, int] = {
                folder.name: index for index, folder in enumerate(ordered_folders)
            }
        else:
            assigned = dict(existing_index)
            next_index = (max(existing_index.values()) + 1) if existing_index else 0
            for folder in folders_result.folders:
                if folder.name not in assigned:
                    assigned[folder.name] = next_index
                    next_index += 1
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
                sort_index=assigned[folder.name],
                updated_at=now,
            )
            for folder in folders_result.folders
        ]
        _ = await StoredMailboxFolder.replace_for_binding(
            binding.mailbox_binding_id,
            company_id=binding.company_id,
            folders=stored,
        )

    async def reorder_folders(
        self,
        payload: MailFoldersReorderPayload,
        *,
        company_id: str | None = None,
    ) -> MailFolderListResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        names = [name.strip() for name in payload.folder_names]
        if any(not name for name in names):
            raise ValueError("folder_names must not contain empty entries")
        if len(names) != len(set(names)):
            raise ValueError("folder_names must not contain duplicates")
        folder_name_to_index = {name: index for index, name in enumerate(names)}
        stored = await StoredMailboxFolder.set_sort_indices(
            payload.mailbox_binding_id,
            folder_name_to_index=folder_name_to_index,
        )
        return self._folder_list_from_stored(stored, stale=False)

    async def list_folders(
        self,
        mailbox_binding_id: str,
        *,
        company_id: str | None = None,
    ) -> MailFolderListResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        stored = await StoredMailboxFolder.list_for_binding(mailbox_binding_id)
        if not stored:
            return MailFolderListResult(folders=[], stale=True, needs_sync=True)
        return self._folder_list_from_stored(stored, stale=False)

    async def refresh_folders_from_imap(
        self,
        mailbox_binding_id: str,
        *,
        company_id: str | None = None,
    ) -> MailFolderListResult:
        """IMAP LIST+STATUS → folder cache. Для sync / ensure, не для open UI."""
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        connection = await self._require_connection_for_binding(binding)
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
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        connection = await self._require_connection_for_binding(binding)
        port = self._port_for(connection)
        folders_result = await port.ensure_standard_imap_folders(self._binding_secret(binding))
        await self._persist_folder_cache(binding, folders_result)
        return folders_result.model_copy(update={"stale": False})

    def _inbound_message(self, stored: StoredMailMessage) -> InboundMailMessage:
        attachments: list[MailAttachment] = []
        for ref in stored.attachments:
            attachments.append(
                ref.model_copy(
                    update={"available": ref.available and ref.file_id is not None}
                )
            )
        return InboundMailMessage(
            uid=str(stored.uid),
            message_id=stored.message_id,
            subject=stored.subject if stored.subject.strip() else None,
            from_address=stored.from_address if stored.from_address.strip() else None,
            to_addresses=list(stored.to_addresses),
            body_text=stored.body_text,
            body_html=stored.body_html,
            unread=stored.unread,
            flagged=stored.flagged,
            answered=stored.answered,
            draft=stored.draft,
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
    ) -> InboundMailMessage:
        if not uid.strip():
            raise ValueError("uid is required")
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        try:
            uid_int = int(uid)
        except ValueError as exc:
            raise MailMessageNotFoundError(mailbox_binding_id, uid) from exc
        stored = await StoredMailMessage.by_binding_folder_uid(
            mailbox_binding_id,
            folder=folder,
            uid=uid_int,
        )
        if stored is None:
            raise MailMessageNotFoundError(mailbox_binding_id, uid)
        if stored.unread:
            _ = await StoredMailMessage.set_unread(
                mailbox_binding_id,
                folder=folder,
                uid=int(uid),
                unread=False,
            )
            stored = stored.model_copy(update={"unread": False})
        return self._inbound_message(stored)

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
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        try:
            uid_int = int(payload.uid)
        except ValueError as exc:
            raise MailMessageNotFoundError(payload.mailbox_binding_id, payload.uid) from exc
        anchor = await StoredMailMessage.by_binding_folder_uid(
            payload.mailbox_binding_id,
            folder=payload.folder,
            uid=uid_int,
        )
        if anchor is None:
            raise MailMessageNotFoundError(payload.mailbox_binding_id, payload.uid)
        thread_rows = await StoredMailMessage.list_by_thread(
            payload.mailbox_binding_id,
            thread_id=anchor.thread_id,
        )
        if not thread_rows:
            thread_rows = [anchor]
        # Открытие треда = прочитаны все непрочитанные письма текущей папки в этом треде
        # (не только якорь uid из UI).
        marked_seen_uids: list[str] = []
        public_items: list[MailThreadMessage] = []
        participants: set[str] = set()
        subject: str | None = anchor.subject if anchor.subject.strip() else None
        for row in thread_rows:
            if row.folder == payload.folder and row.unread:
                _ = await StoredMailMessage.set_unread(
                    payload.mailbox_binding_id,
                    folder=payload.folder,
                    uid=row.uid,
                    unread=False,
                )
                marked_seen_uids.append(str(row.uid))
                row = row.model_copy(update={"unread": False})
            message = self._inbound_message(row)
            public_items.append(
                MailThreadMessage.model_validate(
                    {**message.model_dump(mode="json"), "folder": row.folder}
                )
            )
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
            marked_seen_uids=marked_seen_uids,
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
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        _ = await StoredMailMessage.set_unread(
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
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        _ = await StoredMailMessage.set_unread(
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
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        connection = await self._require_connection_for_binding(binding)
        port = self._port_for(connection)
        try:
            await port.mark_message_seen(
                self._binding_secret(binding),
                mailbox=payload.folder,
                uid=payload.uid,
            )
        except MailUidNotFoundError as exc:
            raise MailMessageNotFoundError(payload.mailbox_binding_id, payload.uid) from exc
        _ = await StoredMailMessage.set_unread(
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
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        connection = await self._require_connection_for_binding(binding)
        port = self._port_for(connection)
        try:
            await port.mark_message_unseen(
                self._binding_secret(binding),
                mailbox=payload.folder,
                uid=payload.uid,
            )
        except MailUidNotFoundError as exc:
            raise MailMessageNotFoundError(payload.mailbox_binding_id, payload.uid) from exc
        _ = await StoredMailMessage.set_unread(
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
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
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
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        stored = await StoredMailMessage.by_binding_folder_uid(
            payload.mailbox_binding_id,
            folder=payload.folder,
            uid=int(payload.uid),
        )
        if stored is None:
            raise MailMessageNotFoundError(payload.mailbox_binding_id, payload.uid)
        # Optimistic: remove from source; confirm rewrite on IMAP move result.
        _ = await StoredMailMessage.delete_by_uids(
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
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        connection = await self._require_connection_for_binding(binding)
        port = self._port_for(connection)
        secret = self._binding_secret(binding)
        move_result = await port.uid_move(
            secret,
            mailbox=payload.folder,
            uid=payload.uid,
            destination_folder=payload.destination_folder,
        )
        destination_uid = move_result.destination_uid
        _ = await StoredMailMessage.delete_by_uids(
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
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        _ = await StoredMailMessage.delete_by_uids(
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
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        _ = await StoredMailMessage.delete_by_uids(
            payload.mailbox_binding_id,
            folder=payload.folder,
            uids=[int(payload.uid)],
        )
        connection = await self._require_connection_for_binding(binding)
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
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        _ = await StoredMailMessage.set_flags(
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
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        connection = await self._require_connection_for_binding(binding)
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
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
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
        connection = await self._require_connection_for_binding(binding)
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
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        if binding.kind != MailboxBindingKind.ROLE:
            raise MailConfigError("members only for kind=role bindings")
        await self._require_binding_access(binding, company_id=resolved_company_id, level="admin")
        items: list[MailboxBindingMember] = []
        now = utcnow()
        for relation, role in (
            (AuthzRelation.MEMBER, MailboxBindingMemberRole.MEMBER),
            (AuthzRelation.MANAGER, MailboxBindingMemberRole.MANAGER),
        ):
            tuples = await self._authz.list_tuples(
                AuthzObject.mailbox_binding(mailbox_binding_id),
                relation=relation,
            )
            for item in tuples:
                if item.subject.kind is not AuthzSubjectKind.USER:
                    continue
                items.append(
                    MailboxBindingMember(
                        mailbox_binding_id=mailbox_binding_id,
                        user_id=item.subject.value,
                        company_id=resolved_company_id,
                        role=role,
                        created_at=now,
                    )
                )
        items.sort(key=lambda row: row.user_id)
        return items

    async def add_binding_member(
        self,
        mailbox_binding_id: str,
        payload: MailboxBindingMemberPayload,
        *,
        company_id: str | None = None,
    ) -> MailboxBindingMember:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        if binding.kind != MailboxBindingKind.ROLE:
            raise MailConfigError("members only for kind=role bindings")
        await self._require_binding_access(binding, company_id=resolved_company_id, level="admin")
        relation = (
            AuthzRelation.MANAGER
            if payload.role is MailboxBindingMemberRole.MANAGER
            else AuthzRelation.MEMBER
        )
        deletes = [
            mailbox_binding_member_tuple(mailbox_binding_id, payload.user_id, item)
            for item in (AuthzRelation.MEMBER, AuthzRelation.MANAGER)
            if item is not relation
        ]
        write = mailbox_binding_member_tuple(mailbox_binding_id, payload.user_id, relation)
        await self._authz.write_and_delete([write], deletes)
        return MailboxBindingMember(
            mailbox_binding_id=mailbox_binding_id,
            user_id=payload.user_id,
            company_id=resolved_company_id,
            role=payload.role,
            created_at=utcnow(),
        )

    async def remove_binding_member(
        self,
        mailbox_binding_id: str,
        user_id: str,
        *,
        company_id: str | None = None,
    ) -> None:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id, level="admin")
        deletes = [
            mailbox_binding_member_tuple(mailbox_binding_id, user_id, item)
            for item in (AuthzRelation.MEMBER, AuthzRelation.MANAGER)
        ]
        existing = await self._authz.list_tuples(AuthzObject.mailbox_binding(mailbox_binding_id))
        subject_ids = {
            item.subject.value
            for item in existing
            if item.subject.kind is AuthzSubjectKind.USER
            and item.relation in (AuthzRelation.MEMBER, AuthzRelation.MANAGER)
        }
        if user_id not in subject_ids:
            raise MailBindingNotFoundError(mailbox_binding_id)
        await self._authz.delete(deletes)

    async def _resolve_outbound_attachments(
        self,
        attachments: list[MailAttachment],
    ) -> list[MailAttachment]:
        """file_id (chunked upload) → content bytes for SMTP / local Sent."""
        resolved: list[MailAttachment] = []
        for attachment in attachments:
            file_id = attachment.file_id
            if file_id is None or file_id.strip() == "":
                raise ValueError(
                    "outbound attachment file_id required "
                    + f"filename={attachment.filename!r}"
                )
            if len(attachment.content) > 0:
                raise ValueError(
                    "outbound attachment content forbidden; use file_id "
                    + f"filename={attachment.filename!r}"
                )
            data, _original_name = await read_stored_file_by_id(file_id.strip())
            if len(data) == 0:
                raise ValueError(
                    "outbound attachment empty after file_id resolve "
                    + f"filename={attachment.filename!r} file_id={file_id!r}"
                )
            resolved.append(
                attachment.model_copy(
                    update={
                        "content": data,
                        "size": len(data),
                        "file_id": None,
                    }
                )
            )
        return resolved

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

    async def allocate_outbound_message_id(
        self,
        mailbox_binding_id: str,
        *,
        company_id: str | None = None,
    ) -> str:
        """Message-Id domain from binding connection (company or personal)."""
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        connection = await self._require_connection_for_binding(binding)
        domain = connection.mail_domain.strip()
        if not domain:
            raise MailConfigError("mail_domain is required for outbound Message-ID")
        return f"<{uuid.uuid4().hex}@{domain}>"

    async def prepare_send_local(
        self,
        payload: MailSendPayload,
        *,
        company_id: str | None = None,
    ) -> MailSendResult:
        """Optimistic local Sent upsert before SMTP worker."""
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        message_id = payload.message_id
        if message_id is None or not message_id.strip():
            message_id = await self.allocate_outbound_message_id(
                payload.mailbox_binding_id,
                company_id=resolved_company_id,
            )
        sent_folder = await self.resolve_folder_name_for_role(
            payload.mailbox_binding_id,
            MailFolderRole.SENT,
            company_id=resolved_company_id,
        )
        temp_uid = -(
            int(uuid.uuid5(uuid.NAMESPACE_URL, f"pending-send:{message_id}").int % 1_000_000_000)
            or 1
        )
        now = utcnow()
        snippet = mail_snippet(body_text=payload.body_text, body_html=payload.body_html)
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
            rag_index_status=MailRagIndexStatus.SKIPPED,
            synced_at=now,
            created_at=now,
            updated_at=now,
        )
        _ = await StoredMailMessage.upsert_by_binding_folder_uid(stored)
        return MailSendResult(message_id=message_id, accepted=list(payload.to_addresses))

    async def send_message(
        self,
        payload: MailSendPayload,
        *,
        company_id: str | None = None,
    ) -> MailSendResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        resolved_attachments = await self._resolve_outbound_attachments(payload.attachments)
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
                attachments=resolved_attachments,
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
        connection = await CompanyMailConnection.for_company(resolved_company_id)
        if connection is None:
            raise MailConnectionNotFoundError(resolved_company_id)
        port = self._port_for(connection)
        return await port.healthcheck()

    def _mail_local_dev(self) -> MailLocalDevConfig | None:
        fields = type(self._mail_config).model_fields
        if "local_dev" not in fields:
            return None
        return self._mail_config.local_dev

    def _local_dev_allows_remote_password_mutation(self) -> bool:
        local_dev = self._mail_local_dev()
        if local_dev is None or not local_dev.enabled:
            return True
        return local_dev.mutate_remote_passwords

    def _local_dev_requires_known_password(self) -> bool:
        local_dev = self._mail_local_dev()
        if local_dev is None or not local_dev.enabled:
            return False
        return not local_dev.mutate_remote_passwords

    def _local_dev_mailbox_password(self, email_address: str) -> str | None:
        local_dev = self._mail_local_dev()
        if local_dev is None or not local_dev.enabled:
            return None
        key = email_address.strip().lower()
        if not key:
            return None
        password = local_dev.mailbox_passwords.get(key)
        if password is None:
            return None
        if not password.strip():
            raise MailConfigError(
                f"mail.local_dev.mailbox_passwords[{key!r}] must be non-empty"
            )
        return password

    def _binding_secret(self, binding: MailboxBinding) -> MailboxSecret:
        override = self._local_dev_mailbox_password(binding.email_address)
        if override is not None:
            return MailboxSecret(
                email_address=binding.email_address,
                password=override,
            )
        if binding.password_encrypted is None or not binding.password_encrypted.strip():
            raise MailSecretMissingError(binding.email_address)
        return MailboxSecret(
            email_address=binding.email_address,
            password=decrypt_secret(binding.password_encrypted),
        )

    async def apply_local_dev_mailbox_passwords(self) -> int:
        """Записать mail.local_dev.mailbox_passwords в локальные bindings (без ISP)."""
        local_dev = self._mail_local_dev()
        if local_dev is None or not local_dev.enabled:
            return 0
        applied = 0
        for email_raw, password in local_dev.mailbox_passwords.items():
            email = email_raw.strip().lower()
            if not email:
                raise MailConfigError("mail.local_dev.mailbox_passwords has empty email key")
            if not password.strip():
                raise MailConfigError(
                    f"mail.local_dev.mailbox_passwords[{email!r}] must be non-empty"
                )
            binding = await MailboxBinding.by_email(SYSTEM_COMPANY_ID, email)
            if binding is None:
                continue
            updated = binding.model_copy(
                update={
                    "password_encrypted": encrypt_secret(password),
                    "updated_at": utcnow(),
                }
            )
            _ = await MailboxBinding.upsert_by_email(updated)
            applied += 1
        if applied > 0:
            logger.info(
                "mail.local_dev.passwords_applied",
                applied=applied,
                configured=len(local_dev.mailbox_passwords),
            )
        return applied

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
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        connection = await self._require_connection_for_binding(binding)
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
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        connection = await self._require_connection_for_binding(binding)
        port = self._port_for(connection)
        return await port.fetch_messages(self._binding_secret(binding), query)

    async def list_sync_candidates(
        self,
        *,
        limit: int,
        auth_error_cooldown_seconds: int,
    ) -> list[MailboxBinding]:
        return await MailboxBinding.list_sync_candidates(
            limit=limit,
            auth_error_cooldown_seconds=auth_error_cooldown_seconds,
            folder=INBOX_FOLDER,
        )

    async def sync_lag_stats(
        self,
        *,
        auth_error_cooldown_seconds: int,
    ) -> MailSyncLagStats:
        return await MailboxBinding.sync_lag_stats(
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
        now = utcnow()
        existing = await MailboxSyncCursor.by_binding_folder(
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
        _ = await MailboxSyncCursor.upsert_by_binding_folder(cursor)

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

        connection = await self._connection_for_binding(binding)
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

        now = utcnow()
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
            cursor = await MailboxSyncCursor.by_binding_folder(
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
                _ = await StoredMailMessage.delete_folder(
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
                _ = await MailboxSyncCursor.upsert_by_binding_folder(
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

            local_rows = await StoredMailMessage.list_folder(
                binding.mailbox_binding_id,
                folder=folder_name,
                limit=500,
            )
            if local_rows:
                try:
                    await self._refresh_flags_for_messages(
                        binding,
                        port,
                        secret,
                        folder=folder_name,
                        messages=[
                            InboundMailMessage(uid=str(row.uid))
                            for row in local_rows
                            if row.uid > 0
                        ],
                    )
                except MailTransportError as exc:
                    logger.warning(
                        "mail.sync.flag_refresh_failed",
                        mailbox_binding_id=binding.mailbox_binding_id,
                        folder=folder_name,
                        error=str(exc),
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
            if do_reconcile:
                await self._reconcile_folder_uids(
                    binding,
                    port=port,
                    secret=secret,
                    folder=folder_name,
                )
                last_reconcile_at = now

            _ = await MailboxSyncCursor.upsert_by_binding_folder(
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
        remote_uids = {
            int(uid)
            for uid in await port.uid_search(
                secret,
                mailbox=folder,
                criteria=MailUidSearchCriteria(all_messages=True),
            )
        }
        local_uids = await StoredMailMessage.list_uids(
            binding.mailbox_binding_id, folder=folder
        )
        orphans = [uid for uid in local_uids if uid not in remote_uids and uid > 0]
        if orphans:
            _ = await StoredMailMessage.delete_by_uids(
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
        if not messages:
            return
        uids: list[str] = []
        for message in messages:
            uid_raw = message.uid.strip()
            if not uid_raw.isdigit() or int(uid_raw) < 1:
                continue
            uids.append(uid_raw)
        if not uids:
            return
        flags_map = await port.fetch_flags_for_uids(
            secret, mailbox=folder, uids=uids
        )
        for uid, flags in flags_map.items():
            _ = await StoredMailMessage.set_flags(
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
            has_text = message.body_text is not None and bool(message.body_text.strip())
            has_html = message.body_html is not None and bool(message.body_html.strip())
            needs_body = not has_text and not has_html
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
        to_store = messages
        if port is not None and secret is not None:
            to_store = await self._hydrate_messages_for_persist(
                port,
                secret,
                folder=folder,
                messages=messages,
            )

        await self._ingest_imip_invites(binding, to_store)

        rag_namespace: str | None = None
        if self._namespace_service is not None:
            company = await Company.get(binding.company_id)
            if company is None:
                raise ValueError(
                    f"company not found for mail sync: {binding.company_id}"
                )
            if binding.kind == MailboxBindingKind.USER:
                if binding.user_id is None or not binding.user_id.strip():
                    raise ValueError("binding.user_id required to persist user mail")
                user = await User.get(binding.user_id)
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

        now = utcnow()
        for message in to_store:
            file_ids = await self._materialize_attachments(
                message,
                mailbox_binding_id=binding.mailbox_binding_id,
                mailbox_email=binding.email_address,
            )
            attachment_refs: list[MailAttachment] = []
            attachment_names: list[str] = []
            for index, attachment in enumerate(message.attachments):
                if attachment.filename.strip():
                    attachment_names.append(attachment.filename)
                file_id = file_ids.get(index)
                attachment_refs.append(
                    MailAttachment(
                        filename=attachment.filename,
                        content_type=attachment.content_type,
                        size=attachment.size if attachment.size > 0 else len(attachment.content),
                        file_id=file_id,
                        available=attachment.available and file_id is not None,
                        parse_error=attachment.parse_error,
                        content_id=attachment.content_id,
                    )
                )
            snippet = mail_snippet(body_text=message.body_text, body_html=message.body_html)
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
            visible_body = mail_visible_text(
                body_text=message.body_text,
                body_html=message.body_html,
            )
            if visible_body:
                rag_text_parts.append(visible_body)
            if attachment_names:
                rag_text_parts.append(
                    "Attachments: " + ", ".join(attachment_names)
                )
            rag_text = "\n\n".join(rag_text_parts)
            should_index = (
                self._rag_client is not None
                and rag_namespace is not None
                and bool(rag_text.strip())
            )
            rag_index_status = (
                MailRagIndexStatus.PENDING if should_index else MailRagIndexStatus.SKIPPED
            )
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
                rag_index_status=rag_index_status,
                synced_at=now,
                created_at=now,
                updated_at=now,
            )
            _ = await StoredMailMessage.upsert_by_binding_folder_uid(stored)
            if should_index:
                await enqueue_mail_rag_index(
                    company_id=binding.company_id,
                    mailbox_binding_id=binding.mailbox_binding_id,
                    folder=folder,
                    uid=str(message.uid),
                )

    async def _resolve_mail_rag_namespace(self, binding: MailboxBinding) -> str | None:
        if self._namespace_service is None:
            return None
        company = await Company.get(binding.company_id)
        if company is None:
            raise ValueError(f"company not found for mail rag: {binding.company_id}")
        if binding.kind == MailboxBindingKind.USER:
            if binding.user_id is None or not binding.user_id.strip():
                raise ValueError("binding.user_id required for user mail RAG")
            user = await User.get(binding.user_id)
            if user is None:
                raise ValueError(f"user not found for mail rag: {binding.user_id}")
            await ensure_personal_namespace_for_user(
                self._namespace_service,
                user,
                company=company,
            )
            return personal_namespace_name(user.user_id)
        technical_name = f"mail-{binding.mailbox_binding_id}"
        _ = await self._namespace_service.get_or_create(
            technical_name,
            kind=NamespaceKind.TECHNICAL,
            description=f"Role mailbox {binding.email_address}",
        )
        return technical_name

    def _build_mail_rag_text(self, stored: StoredMailMessage) -> str:
        parts: list[str] = []
        if stored.subject.strip():
            parts.append(f"Subject: {stored.subject.strip()}")
        if stored.from_address.strip():
            parts.append(f"From: {stored.from_address.strip()}")
        visible_body = mail_visible_text(
            body_text=stored.body_text,
            body_html=stored.body_html,
        )
        if visible_body:
            parts.append(visible_body)
        attachment_names = [
            ref.filename for ref in stored.attachments if ref.filename.strip()
        ]
        if attachment_names:
            parts.append("Attachments: " + ", ".join(attachment_names))
        return "\n\n".join(parts)

    async def index_mail_message(
        self,
        *,
        mailbox_binding_id: str,
        folder: str,
        uid: str,
        company_id: str | None = None,
    ) -> StoredMailMessage:
        """
        Фоновая RAG-индексация одного письма. Persist уже выполнен;
        при ошибке ingest ставит failed и пробрасывает исключение.
        """
        if self._rag_client is None:
            raise MailConfigError("rag client required for mail indexing")
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(resolved_company_id, mailbox_binding_id)
        if binding is None:
            raise MailBindingNotFoundError(mailbox_binding_id)
        stored = await StoredMailMessage.by_binding_folder_uid(
            mailbox_binding_id,
            folder=folder,
            uid=int(uid),
        )
        if stored is None:
            raise MailMessageNotFoundError(mailbox_binding_id, uid)
        rag_text = self._build_mail_rag_text(stored)
        if not rag_text.strip():
            updated = stored.model_copy(
                update={
                    "rag_index_status": MailRagIndexStatus.SKIPPED,
                    "updated_at": utcnow(),
                }
            )
            return await StoredMailMessage.upsert_by_binding_folder_uid(updated)
        rag_namespace = await self._resolve_mail_rag_namespace(binding)
        if rag_namespace is None:
            raise MailConfigError("namespace service required for mail indexing")
        file_id_list = [ref.file_id for ref in stored.attachments if ref.file_id is not None]
        attachment_names = [
            ref.filename for ref in stored.attachments if ref.filename.strip()
        ]
        rag_metadata: RAGMetadata = {
            "company_id": binding.company_id,
            "document_id": stored.mail_message_id,
            "mailbox_binding_id": binding.mailbox_binding_id,
            "mail_uid": str(stored.uid),
            "folder": folder,
            "thread_id": stored.thread_id,
            "ttl_seconds": 0,
            "uploaded_by_user_id": (
                binding.user_id if binding.user_id is not None else ""
            ),
            "has_attachments": stored.has_attachments,
            "attachment_names": list(attachment_names),
            "file_ids": file_id_list,
        }
        try:
            ingest = await self._rag_client.ingest_text(
                namespace_id=rag_namespace,
                text=rag_text,
                document_name=stored.mail_message_id,
                metadata=rag_metadata,
            )
        except Exception as exc:
            failed = stored.model_copy(
                update={
                    "rag_namespace": rag_namespace,
                    "rag_index_status": MailRagIndexStatus.FAILED,
                    "updated_at": utcnow(),
                }
            )
            _ = await StoredMailMessage.upsert_by_binding_folder_uid(failed)
            logger.warning(
                "mail.rag_index_failed",
                mailbox_binding_id=mailbox_binding_id,
                message_uid=uid,
                error=str(exc),
            )
            raise
        ready = stored.model_copy(
            update={
                "rag_document_id": ingest.document_id,
                "rag_namespace": rag_namespace,
                "rag_index_status": MailRagIndexStatus.READY,
                "updated_at": utcnow(),
            }
        )
        return await StoredMailMessage.upsert_by_binding_folder_uid(ready)

    async def request_rag_index(
        self,
        payload: MailMessageRagIndexPayload,
        *,
        company_id: str | None = None,
    ) -> MailMessageRagIndexResult:
        resolved_company_id = company_id if company_id is not None else self._active_company_id()
        binding = await MailboxBinding.find_in_company(
            resolved_company_id, payload.mailbox_binding_id
        )
        if binding is None:
            raise MailBindingNotFoundError(payload.mailbox_binding_id)
        await self._require_binding_access(binding, company_id=resolved_company_id)
        stored = await StoredMailMessage.by_binding_folder_uid(
            payload.mailbox_binding_id,
            folder=payload.folder,
            uid=int(payload.uid),
        )
        if stored is None:
            raise MailMessageNotFoundError(payload.mailbox_binding_id, payload.uid)
        if stored.rag_index_status == MailRagIndexStatus.READY and stored.rag_document_id:
            return MailMessageRagIndexResult(
                accepted=True,
                mailbox_binding_id=payload.mailbox_binding_id,
                folder=payload.folder,
                uid=payload.uid,
                rag_index_status=MailRagIndexStatus.READY,
            )
        rag_text = self._build_mail_rag_text(stored)
        if not rag_text.strip() or self._rag_client is None:
            skipped = stored.model_copy(
                update={
                    "rag_index_status": MailRagIndexStatus.SKIPPED,
                    "updated_at": utcnow(),
                }
            )
            _ = await StoredMailMessage.upsert_by_binding_folder_uid(skipped)
            return MailMessageRagIndexResult(
                accepted=True,
                mailbox_binding_id=payload.mailbox_binding_id,
                folder=payload.folder,
                uid=payload.uid,
                rag_index_status=MailRagIndexStatus.SKIPPED,
            )
        pending = stored.model_copy(
            update={
                "rag_index_status": MailRagIndexStatus.PENDING,
                "updated_at": utcnow(),
            }
        )
        _ = await StoredMailMessage.upsert_by_binding_folder_uid(pending)
        await enqueue_mail_rag_index(
            company_id=resolved_company_id,
            mailbox_binding_id=payload.mailbox_binding_id,
            folder=payload.folder,
            uid=payload.uid,
        )
        return MailMessageRagIndexResult(
            accepted=True,
            mailbox_binding_id=payload.mailbox_binding_id,
            folder=payload.folder,
            uid=payload.uid,
            rag_index_status=MailRagIndexStatus.PENDING,
        )

    async def ensure_system_mail_connection(self) -> CompanyMailConnection | None:
        system_cfg = self._mail_config.system
        if not system_cfg.enabled:
            logger.info("mail.system.ensure")
            return None
        if system_cfg.imap_host is None or not system_cfg.imap_host.strip():
            raise MailConfigError("mail.system.imap_host is required when enabled")
        if system_cfg.smtp_host is None or not system_cfg.smtp_host.strip():
            raise MailConfigError("mail.system.smtp_host is required when enabled")

        provider = MailProvider(system_cfg.provider)
        existing = await CompanyMailConnection.for_company(SYSTEM_COMPANY_ID)
        now = utcnow()
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
            scope=MailConnectionScope.COMPANY,
            owner_user_id=None,
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
        stored = await CompanyMailConnection.upsert_by_company_mail_connection_id(connection)
        logger.info(
            "mail.system.connection_ensured",
            mail_domain=stored.mail_domain,
            provider=str(stored.provider),
        )
        return stored

    async def ensure_system_role_mailboxes(self) -> MailSystemEnsureResult:
        connection = await self.ensure_system_mail_connection()
        if connection is None:
            return MailSystemEnsureResult(ensured=[], missing_password=[])
        ensured: list[str] = []
        missing_password: list[str] = []
        inventory = self._local_dev_requires_known_password()
        for local_part_raw in self._mail_config.system.role_mailboxes:
            local_part = local_part_raw.strip().lower()
            if not local_part:
                raise MailConfigError("mail.system.role_mailboxes contains empty local_part")
            email_address = f"{local_part}@{connection.mail_domain}"
            if inventory:
                existing = await MailboxBinding.by_email(
                    SYSTEM_COMPANY_ID, email_address
                )
                if existing is not None:
                    ensured.append(existing.email_address)
                    continue
                if self._local_dev_mailbox_password(email_address) is None:
                    missing_password.append(email_address)
                    continue
            binding = await self.bind_mailbox(
                MailboxBindingCreatePayload(
                    kind=MailboxBindingKind.ROLE,
                    local_part=local_part,
                    provision=not inventory,
                    sync_enabled=True,
                ),
                company_id=SYSTEM_COMPANY_ID,
            )
            ensured.append(binding.email_address)
        return MailSystemEnsureResult(ensured=ensured, missing_password=missing_password)

    async def ensure_system_user_bindings(self) -> MailSystemEnsureResult:
        connection = await self.ensure_system_mail_connection()
        if connection is None:
            return MailSystemEnsureResult(ensured=[], missing_password=[])
        company = await Company.get(SYSTEM_COMPANY_ID)
        if company is None:
            raise MailConfigError("system company not found")
        member_ids = set(company.members)
        ensured: list[str] = []
        missing_password: list[str] = []
        inventory = self._local_dev_requires_known_password()
        for user_id in company.members:
            existing = await MailboxBinding.preferred_for_user(SYSTEM_COMPANY_ID, user_id)
            if existing is not None:
                ensured.append(existing.email_address)
                continue
            if inventory:
                user = await User.get(user_id)
                if user is None:
                    raise ValueError(f"User not found: {user_id}")
                email_address = f"{_slug_local_part(user)}@{connection.mail_domain}"
                if self._local_dev_mailbox_password(email_address) is None:
                    missing_password.append(email_address)
                    continue
            binding = await self.bind_mailbox(
                MailboxBindingCreatePayload(
                    user_id=user_id,
                    kind=MailboxBindingKind.USER,
                    provision=not inventory,
                    sync_enabled=True,
                ),
                company_id=SYSTEM_COMPANY_ID,
            )
            ensured.append(binding.email_address)
        listed = await MailboxBinding.list_by_company(SYSTEM_COMPANY_ID)
        for binding in listed:
            if binding.kind != MailboxBindingKind.USER:
                continue
            if binding.user_id is None or binding.user_id in member_ids:
                continue
            leftover_connection = await self._connection_for_binding(binding)
            if (
                leftover_connection is not None
                and leftover_connection.scope == MailConnectionScope.PERSONAL
            ):
                continue
            await self.unbind_mailbox(
                binding.mailbox_binding_id,
                company_id=SYSTEM_COMPANY_ID,
                acting_as_admin=True,
            )
        return MailSystemEnsureResult(ensured=ensured, missing_password=missing_password)

    async def reconcile_system(self) -> MailReconcileResult:
        connection = await self.ensure_system_mail_connection()
        role_result = await self.ensure_system_role_mailboxes()
        user_result = await self.ensure_system_user_bindings()
        _ = await self.apply_local_dev_mailbox_passwords()
        if role_result.missing_password or user_result.missing_password:
            logger.warning(
                "mail.local_dev.bindings_missing_password",
                role_mailboxes=role_result.missing_password,
                user_bindings=user_result.missing_password,
            )
        return MailReconcileResult(
            connection_ensured=connection is not None,
            role_mailboxes_ensured=role_result.ensured,
            user_bindings_ensured=user_result.ensured,
            role_mailboxes_missing_password=role_result.missing_password,
            user_bindings_missing_password=user_result.missing_password,
        )
