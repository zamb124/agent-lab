"""Доменные модели платформенной почты."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import ClassVar, Final, Self, override

from oxyde import Field as DbField
from oxyde import Index, atomic, execute_raw
from oxyde.exceptions import IntegrityError
from pydantic import (
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from core.models.base import StrictBaseModel
from core.models.calendar_models import CalendarAutolinkStatus
from core.models.platform_model import PlatformModel
from core.types import JsonObject, require_json_object, require_serializer_json_object

INBOX_FOLDER: Final[str] = "INBOX"
_CONNECTION_UPSERT_MAX_ATTEMPTS: Final[int] = 5
_MESSAGE_COLUMNS: Final[str] = """
    mail_message_id, company_id, mailbox_binding_id, user_id, folder, uid,
    message_id, thread_id, subject, from_address, to_addresses, cc_addresses,
    date_at, unread, flagged, answered, draft, has_attachments, snippet,
    body_text, body_html, attachments, in_reply_to, "references",
    rag_document_id, rag_namespace, rag_index_status, synced_at, created_at, updated_at
"""


def _mail_required(value: str, field_name: str) -> str:
    if value == "":
        raise ValueError(f"{field_name} cannot be empty.")
    return value


def _mail_json_str(payload: JsonObject, key: str) -> str:
    value = payload[key]
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _mail_messages(rows: Sequence[object]) -> list[StoredMailMessage]:
    return [
        StoredMailMessage.model_validate(require_json_object(row, "mail_messages"))
        for row in rows
    ]

class MailProvider(StrEnum):
    ISPMANAGER = "ispmanager"
    GENERIC_IMAP_SMTP = "generic_imap_smtp"


class MailConnectionStatus(StrEnum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    DISABLED = "disabled"


class MailConnectionScope(StrEnum):
    COMPANY = "company"
    PERSONAL = "personal"


class MailboxBindingKind(StrEnum):
    USER = "user"
    ROLE = "role"


class MailUserLocalPartStrategy(StrEnum):
    SLUG_UNIQUE = "slug_unique"


class MailFolderRole(StrEnum):
    INBOX = "inbox"
    SENT = "sent"
    DRAFTS = "drafts"
    TRASH = "trash"
    JUNK = "junk"
    ARCHIVE = "archive"
    OTHER = "other"


class MailRagIndexStatus(StrEnum):
    """Статус фоновой RAG-индексации письма (не блокирует local-first persist)."""

    READY = "ready"
    PENDING = "pending"
    FAILED = "failed"
    SKIPPED = "skipped"


class MailFolder(StrictBaseModel):
    name: str
    delimiter: str | None = None
    flags: list[str] = Field(default_factory=list)
    role: MailFolderRole = MailFolderRole.OTHER
    selectable: bool = True
    unseen_count: int = Field(default=0, ge=0)
    message_count: int = Field(default=0, ge=0)
    sort_index: int = Field(default=0)


class MailFolderListResult(StrictBaseModel):
    folders: list[MailFolder] = Field(default_factory=list)
    namespace_prefix: str = ""
    delimiter: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    missing_standard_roles: list[MailFolderRole] = Field(default_factory=list)
    stale: bool = False
    needs_sync: bool = False


class MailFoldersEnsurePayload(StrictBaseModel):
    mailbox_binding_id: str


class MailFoldersReorderPayload(StrictBaseModel):
    mailbox_binding_id: str
    folder_names: list[str] = Field(min_length=1)

class IspmanagerProvisionConfig(StrictBaseModel):
    base_url: str
    authinfo_user: str
    authinfo_password_encrypted: str | None = None


class CompanyMailConnection(PlatformModel):
    """Подключение почтового сервера. Таблица ``company_mail_connections`` в ``platform_shared``.

    ``__global_model__``: синхронизация читает подключения всех компаний.
    Пароль ISPmanager в JSON не отдаётся.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    company_mail_connection_id: str = DbField(db_pk=True, max_length=255)

    class Meta:
        is_table: bool = True
        table_name: str = "company_mail_connections"
        indexes: list[Index] = [
            Index(("company_id",), unique=True, where="scope = 'company'"),
            Index(("mail_domain",)),
        ]

    company_id: str = DbField(db_index=True, max_length=255)
    scope: MailConnectionScope = DbField(
        default=MailConnectionScope.COMPANY,
        max_length=32,
        db_type="TEXT",
    )
    owner_user_id: str | None = DbField(default=None, db_index=True, max_length=255)
    mail_domain: str = DbField(max_length=255)
    provider: MailProvider = DbField(max_length=64, db_type="TEXT")
    imap_host: str = DbField(max_length=255)
    imap_port: int = DbField(ge=1, le=65535)
    smtp_host: str = DbField(max_length=255)
    smtp_port: int = DbField(ge=1, le=65535)
    use_ssl: bool = DbField(default=True)
    supports_provision: bool = DbField()
    status: MailConnectionStatus = DbField(
        default=MailConnectionStatus.ACTIVE,
        max_length=32,
        db_type="TEXT",
    )
    ispmanager: IspmanagerProvisionConfig | None = DbField(default=None, db_type="JSONB")
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @model_serializer(mode="wrap", when_used="json")
    def _json_without_isp_password(self, handler: SerializerFunctionWrapHandler) -> JsonObject:
        payload = require_serializer_json_object(handler, self, "CompanyMailConnection")
        ispmanager = payload.get("ispmanager")
        if isinstance(ispmanager, dict) and "authinfo_password_encrypted" in ispmanager:
            del ispmanager["authinfo_password_encrypted"]
        payload["has_ispmanager_auth"] = self.has_ispmanager_auth
        return payload

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if self.company_mail_connection_id == "" or self.company_id == "" or self.mail_domain == "":
            raise ValueError("company_mail_connection_id, company_id and mail_domain are required")
        if self.scope == MailConnectionScope.COMPANY and self.owner_user_id is not None:
            raise ValueError("company mail connection cannot have owner_user_id")
        if self.scope == MailConnectionScope.PERSONAL and (
            self.owner_user_id is None or self.owner_user_id == ""
        ):
            raise ValueError("personal mail connection requires owner_user_id")
        self.updated_at = datetime.now(timezone.utc)

    @property
    def has_ispmanager_auth(self) -> bool:
        secret = None if self.ispmanager is None else self.ispmanager.authinfo_password_encrypted
        return secret is not None and secret.strip() != ""


    @classmethod
    async def for_company(cls, company_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=_mail_required(company_id, "company_id"),
            scope=MailConnectionScope.COMPANY,
        ).get_or_none()

    @classmethod
    async def upsert_by_company_mail_connection_id(cls, connection: Self) -> Self:
        last_error: IntegrityError | None = None
        for _attempt in range(_CONNECTION_UPSERT_MAX_ATTEMPTS):
            resolved = connection
            if connection.scope == MailConnectionScope.COMPANY:
                existing_company = await cls.for_company(connection.company_id)
                if (
                    existing_company is not None
                    and existing_company.company_mail_connection_id
                    != connection.company_mail_connection_id
                ):
                    resolved = connection.model_copy(
                        update={
                            "company_mail_connection_id": existing_company.company_mail_connection_id,
                            "created_at": existing_company.created_at,
                        }
                    )
            try:
                existing = await cls.get(resolved.company_mail_connection_id)
                if existing is None:
                    return await cls.objects.create(instance=resolved)
                existing.company_id = resolved.company_id
                existing.scope = resolved.scope
                existing.owner_user_id = resolved.owner_user_id
                existing.mail_domain = resolved.mail_domain
                existing.provider = resolved.provider
                existing.imap_host = resolved.imap_host
                existing.imap_port = resolved.imap_port
                existing.smtp_host = resolved.smtp_host
                existing.smtp_port = resolved.smtp_port
                existing.use_ssl = resolved.use_ssl
                existing.supports_provision = resolved.supports_provision
                existing.status = resolved.status
                existing.ispmanager = resolved.ispmanager
                existing.updated_at = resolved.updated_at
                _ = await existing.save()
                return existing
            except IntegrityError as exc:
                last_error = exc
                continue
        if last_error is None:
            raise RuntimeError("CompanyMailConnection upsert failed without IntegrityError")
        raise RuntimeError(
            "CompanyMailConnection upsert exhausted retries for "
            + f"company_id={connection.company_id}"
        ) from last_error



class CompanyMailConnectionUpsertPayload(StrictBaseModel):
    mail_domain: str
    provider: MailProvider
    imap_host: str
    imap_port: int = Field(ge=1, le=65535)
    smtp_host: str
    smtp_port: int = Field(ge=1, le=65535)
    use_ssl: bool = True
    ispmanager_base_url: str | None = None
    ispmanager_authinfo_user: str | None = None
    ispmanager_authinfo_password: str | None = None
    status: MailConnectionStatus = MailConnectionStatus.ACTIVE


class MailboxBinding(PlatformModel):
    """Ящик на почтовом сервере. Таблица ``mailbox_bindings`` в ``platform_shared``.

    ``__global_model__``: синхронизация читает ящики всех компаний.
    ``password_encrypted`` в JSON не отдаётся.
    Поля подключения (``connection_scope``, IMAP/SMTP) заполняет ``public_binding`` и в таблицу не пишутся.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    mailbox_binding_id: str = DbField(db_pk=True, max_length=255)

    class Meta:
        is_table: bool = True
        table_name: str = "mailbox_bindings"
        indexes: list[Index] = [
            Index(("company_id", "email_address"), unique=True),
            Index(("company_id", "local_part")),
            Index(("company_id", "user_id", "is_default")),
        ]

    company_id: str = DbField(db_index=True, max_length=255)
    company_mail_connection_id: str = DbField(db_index=True, max_length=255)
    user_id: str | None = DbField(default=None, db_index=True, max_length=255)
    kind: MailboxBindingKind = DbField(max_length=32, db_type="TEXT")
    email_address: str = DbField(max_length=320)
    local_part: str = DbField(max_length=255)
    sync_enabled: bool = DbField(default=True)
    is_default: bool = DbField(default=False)
    calendar_color: str = DbField(default="default", max_length=32)
    calendar_autolink_status: CalendarAutolinkStatus = DbField(
        default=CalendarAutolinkStatus.DISABLED,
        max_length=32,
    )
    calendar_autolink_detail: str | None = DbField(default=None, db_type="TEXT")
    password_encrypted: str | None = DbField(default=None, db_type="TEXT")
    connection_scope: MailConnectionScope = DbField(
        default=MailConnectionScope.COMPANY,
        exclude=True,
        db_reverse_fk="company_mail_connection_id",
    )
    imap_host: str | None = DbField(
        default=None,
        exclude=True,
        db_reverse_fk="company_mail_connection_id",
    )
    imap_port: int | None = DbField(
        default=None,
        exclude=True,
        db_reverse_fk="company_mail_connection_id",
    )
    smtp_host: str | None = DbField(
        default=None,
        exclude=True,
        db_reverse_fk="company_mail_connection_id",
    )
    smtp_port: int | None = DbField(
        default=None,
        exclude=True,
        db_reverse_fk="company_mail_connection_id",
    )
    use_ssl: bool | None = DbField(
        default=None,
        exclude=True,
        db_reverse_fk="company_mail_connection_id",
    )
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @model_serializer(mode="wrap", when_used="json")
    def _json_without_password(self, handler: SerializerFunctionWrapHandler) -> JsonObject:
        payload = require_serializer_json_object(handler, self, "MailboxBinding")
        if "password_encrypted" in payload:
            del payload["password_encrypted"]
        payload["has_password"] = self.has_password
        payload["connection_scope"] = self.connection_scope.value
        payload["imap_host"] = self.imap_host
        payload["imap_port"] = self.imap_port
        payload["smtp_host"] = self.smtp_host
        payload["smtp_port"] = self.smtp_port
        payload["use_ssl"] = self.use_ssl
        return payload

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if (
            self.mailbox_binding_id == ""
            or self.company_id == ""
            or self.company_mail_connection_id == ""
            or self.email_address == ""
            or self.local_part == ""
        ):
            raise ValueError(
                "mailbox_binding_id, company_id, company_mail_connection_id, email_address and local_part are required"
            )
        if self.kind == MailboxBindingKind.USER and (self.user_id is None or self.user_id == ""):
            raise ValueError("user mailbox binding requires user_id")
        self.updated_at = datetime.now(timezone.utc)

    @property
    def has_password(self) -> bool:
        secret = self.password_encrypted
        return secret is not None and secret.strip() != ""

    @classmethod
    async def list_for_authz(cls, *, limit: int | None) -> list[Self]:
        ordered = cls.objects.order_by("mailbox_binding_id")
        if limit is None:
            return await ordered.all()
        return await ordered.limit(limit).all()

    @classmethod
    async def list_with_user_for_authz(cls, *, limit: int | None) -> list[Self]:
        ordered = cls.objects.filter(user_id__isnull=False).order_by("mailbox_binding_id")
        if limit is None:
            return await ordered.all()
        return await ordered.limit(limit).all()


    @classmethod
    async def find_in_company(cls, company_id: str, mailbox_binding_id: str) -> Self | None:
        return await cls.objects.filter(
            mailbox_binding_id=_mail_required(mailbox_binding_id, "mailbox_binding_id"),
            company_id=_mail_required(company_id, "company_id"),
        ).get_or_none()

    @classmethod
    async def by_email(cls, company_id: str, email_address: str) -> Self | None:
        return await cls.objects.filter(
            company_id=_mail_required(company_id, "company_id"),
            email_address=_mail_required(email_address, "email_address"),
        ).get_or_none()

    @classmethod
    async def list_by_user(cls, company_id: str, user_id: str) -> list[Self]:
        return await cls.objects.filter(
            company_id=_mail_required(company_id, "company_id"),
            user_id=_mail_required(user_id, "user_id"),
            kind=MailboxBindingKind.USER,
        ).order_by("-is_default", "email_address").all()

    @classmethod
    async def preferred_for_user(cls, company_id: str, user_id: str) -> Self | None:
        bindings = await cls.list_by_user(company_id, user_id)
        if len(bindings) == 0:
            return None
        for binding in bindings:
            if binding.is_default:
                return binding
        return bindings[0]

    @classmethod
    async def list_by_company(cls, company_id: str) -> list[Self]:
        return await cls.objects.filter(
            company_id=_mail_required(company_id, "company_id"),
        ).order_by("email_address").all()

    @classmethod
    async def list_sync_candidates(
        cls,
        *,
        limit: int,
        auth_error_cooldown_seconds: int,
        folder: str = INBOX_FOLDER,
    ) -> list[Self]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if auth_error_cooldown_seconds < 0:
            raise ValueError("auth_error_cooldown_seconds must be >= 0")
        cooldown_cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=auth_error_cooldown_seconds
        )
        rows = await execute_raw(
            """
            SELECT b.mailbox_binding_id, b.company_id
            FROM mailbox_bindings b
            JOIN company_mail_connections c
              ON c.company_mail_connection_id = b.company_mail_connection_id
            LEFT JOIN mailbox_sync_cursors cur
              ON cur.mailbox_binding_id = b.mailbox_binding_id AND cur.folder = $1
            WHERE b.sync_enabled = true
              AND c.status = $2
              AND (
                (b.kind = $3 AND b.user_id IS NOT NULL)
                OR b.kind = $4
              )
              AND (
                cur.last_error_kind IS NULL
                OR cur.last_error_kind <> $5
                OR cur.last_error_at IS NULL
                OR cur.last_error_at <= $6
              )
            ORDER BY cur.last_synced_at ASC NULLS FIRST
            LIMIT $7
            """,
            [
                folder,
                MailConnectionStatus.ACTIVE.value,
                MailboxBindingKind.USER.value,
                MailboxBindingKind.ROLE.value,
                MailSyncErrorKind.AUTH.value,
                cooldown_cutoff,
                limit,
            ],
            using="shared",
        )
        bindings: list[Self] = []
        for row in rows:
            payload = require_json_object(row, "mailbox_sync_candidate")
            binding = await cls.find_in_company(
                _mail_json_str(payload, "company_id"),
                _mail_json_str(payload, "mailbox_binding_id"),
            )
            if binding is None:
                raise RuntimeError("sync candidate binding disappeared")
            bindings.append(binding)
        return bindings

    @classmethod
    async def count_sync_candidates(
        cls,
        *,
        auth_error_cooldown_seconds: int,
        folder: str = INBOX_FOLDER,
    ) -> int:
        if auth_error_cooldown_seconds < 0:
            raise ValueError("auth_error_cooldown_seconds must be >= 0")
        cooldown_cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=auth_error_cooldown_seconds
        )
        rows = await execute_raw(
            """
            SELECT count(*)::int AS candidate_count
            FROM mailbox_bindings b
            JOIN company_mail_connections c
              ON c.company_mail_connection_id = b.company_mail_connection_id
            LEFT JOIN mailbox_sync_cursors cur
              ON cur.mailbox_binding_id = b.mailbox_binding_id AND cur.folder = $1
            WHERE b.sync_enabled = true
              AND c.status = $2
              AND (
                (b.kind = $3 AND b.user_id IS NOT NULL)
                OR b.kind = $4
              )
              AND (
                cur.last_error_kind IS NULL
                OR cur.last_error_kind <> $5
                OR cur.last_error_at IS NULL
                OR cur.last_error_at <= $6
              )
            """,
            [
                folder,
                MailConnectionStatus.ACTIVE.value,
                MailboxBindingKind.USER.value,
                MailboxBindingKind.ROLE.value,
                MailSyncErrorKind.AUTH.value,
                cooldown_cutoff,
            ],
            using="shared",
        )
        if len(rows) != 1:
            raise RuntimeError("sync candidate count returned no row")
        payload = require_json_object(rows[0], "mailbox_sync_candidate_count")
        candidate_count = payload["candidate_count"]
        if not isinstance(candidate_count, int):
            raise ValueError("candidate_count must be an int")
        return candidate_count

    @classmethod
    async def sync_lag_stats(
        cls,
        *,
        auth_error_cooldown_seconds: int,
        folder: str = INBOX_FOLDER,
    ) -> MailSyncLagStats:
        candidates = await cls.list_sync_candidates(
            limit=10_000,
            auth_error_cooldown_seconds=auth_error_cooldown_seconds,
            folder=folder,
        )
        now = datetime.now(timezone.utc)
        max_lag_seconds = 0
        for binding in candidates:
            cursor = await MailboxSyncCursor.objects.filter(
                mailbox_binding_id=binding.mailbox_binding_id,
                folder=folder,
            ).get_or_none()
            last_synced_at = None if cursor is None else cursor.last_synced_at
            if last_synced_at is None:
                if 10**9 > max_lag_seconds:
                    max_lag_seconds = 10**9
                continue
            lag = int((now - last_synced_at).total_seconds())
            if lag > max_lag_seconds:
                max_lag_seconds = lag
        return MailSyncLagStats(
            bindings_pending=len(candidates),
            max_lag_seconds=max_lag_seconds if max_lag_seconds < 10**9 else max_lag_seconds,
            candidates_total=len(candidates),
        )

    @classmethod
    async def clear_defaults_for_user(
        cls, company_id: str, user_id: str, *, except_binding_id: str | None = None
    ) -> None:
        query = cls.objects.filter(
            company_id=_mail_required(company_id, "company_id"),
            user_id=_mail_required(user_id, "user_id"),
            kind=MailboxBindingKind.USER,
            is_default=True,
        )
        if except_binding_id is not None:
            query = query.exclude(
                mailbox_binding_id=_mail_required(except_binding_id, "except_binding_id")
            )
        _ = await query.update(is_default=False)

    @classmethod
    async def upsert_by_email(cls, binding: Self) -> Self:
        by_email = await cls.by_email(binding.company_id, binding.email_address)
        if by_email is None:
            return await cls.objects.create(instance=binding)
        if by_email.mailbox_binding_id == binding.mailbox_binding_id:
            by_email.company_mail_connection_id = binding.company_mail_connection_id
            by_email.user_id = binding.user_id
            by_email.kind = binding.kind
            by_email.local_part = binding.local_part
            by_email.sync_enabled = binding.sync_enabled
            by_email.is_default = binding.is_default
            by_email.calendar_color = binding.calendar_color
            by_email.calendar_autolink_status = binding.calendar_autolink_status
            by_email.calendar_autolink_detail = binding.calendar_autolink_detail
            by_email.password_encrypted = binding.password_encrypted
            _ = await by_email.save()
            return by_email
        _ = await cls.objects.filter(
            company_id=binding.company_id,
            email_address=binding.email_address,
        ).update(
            mailbox_binding_id=binding.mailbox_binding_id,
            company_mail_connection_id=binding.company_mail_connection_id,
            user_id=binding.user_id,
            kind=binding.kind,
            local_part=binding.local_part,
            sync_enabled=binding.sync_enabled,
            is_default=binding.is_default,
            calendar_color=binding.calendar_color,
            calendar_autolink_status=binding.calendar_autolink_status,
            calendar_autolink_detail=binding.calendar_autolink_detail,
            password_encrypted=binding.password_encrypted,
            updated_at=datetime.now(timezone.utc),
        )
        stored = await cls.find_in_company(binding.company_id, binding.mailbox_binding_id)
        if stored is None:
            raise RuntimeError(
                f"MailboxBinding upsert failed for email_address={binding.email_address}"
            )
        return stored

    @classmethod
    async def delete_in_company(cls, company_id: str, mailbox_binding_id: str) -> bool:
        deleted = await cls.objects.filter(
            mailbox_binding_id=_mail_required(mailbox_binding_id, "mailbox_binding_id"),
            company_id=_mail_required(company_id, "company_id"),
        ).delete()
        return deleted > 0



class MailboxBindingCreatePayload(StrictBaseModel):
    user_id: str | None = None
    kind: MailboxBindingKind = MailboxBindingKind.USER
    local_part: str | None = None
    email_address: str | None = None
    password: str | None = None
    sync_enabled: bool = True
    provision: bool = True
    is_default: bool | None = None
    calendar_color: str | None = None


class PersonalMailboxConnectPayload(StrictBaseModel):
    email_address: str = Field(min_length=3)
    password: str = Field(min_length=1)
    imap_host: str = Field(min_length=1)
    imap_port: int = Field(ge=1, le=65535, default=993)
    smtp_host: str = Field(min_length=1)
    smtp_port: int = Field(ge=1, le=65535, default=465)
    use_ssl: bool = True
    sync_enabled: bool = True
    calendar_color: str | None = None


class PersonalMailboxHealthcheckPayload(StrictBaseModel):
    email_address: str = Field(min_length=3)
    password: str = Field(min_length=1)
    imap_host: str = Field(min_length=1)
    imap_port: int = Field(ge=1, le=65535, default=993)
    smtp_host: str = Field(min_length=1)
    smtp_port: int = Field(ge=1, le=65535, default=465)
    use_ssl: bool = True


class MailboxBindingHealthcheckPayload(StrictBaseModel):
    """Проверка login существующего binding; password/hosts опциональны (иначе stored)."""

    password: str | None = None
    imap_host: str | None = None
    imap_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_host: str | None = None
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    use_ssl: bool | None = None


class MailboxBindingPatchPayload(StrictBaseModel):
    user_id: str | None = None
    sync_enabled: bool | None = None
    password: str | None = None
    calendar_color: str | None = None
    imap_host: str | None = None
    imap_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_host: str | None = None
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    use_ssl: bool | None = None


class MailboxBindingsMeResponse(StrictBaseModel):
    """Мои mailbox bindings + server-driven company admin capability."""

    items: list[MailboxBinding]
    can_admin: bool


class MailMessageListPayload(StrictBaseModel):
    mailbox_binding_id: str
    folder: str = "INBOX"
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class MailMessageListItem(StrictBaseModel):
    uid: str
    message_id: str | None = None
    subject: str | None = None
    from_address: str | None = None
    to_addresses: list[str] = Field(default_factory=list)
    snippet: str | None = None
    attachment_count: int = 0
    unread: bool = True
    flagged: bool = False
    date: datetime | None = None
    in_reply_to: str | None = None
    references: str | None = None
    rag_index_status: MailRagIndexStatus = MailRagIndexStatus.SKIPPED


class MailMessageRagIndexPayload(StrictBaseModel):
    mailbox_binding_id: str
    folder: str = "INBOX"
    uid: str


class MailMessageRagIndexResult(StrictBaseModel):
    accepted: bool
    mailbox_binding_id: str
    folder: str
    uid: str
    rag_index_status: MailRagIndexStatus


class MailMessageListResult(StrictBaseModel):
    """List + sync meta (до CursorPage wrapper в API)."""

    items: list[MailMessageListItem] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False
    needs_sync: bool = False


class MailMessageFlagPayload(StrictBaseModel):
    mailbox_binding_id: str
    folder: str = "INBOX"
    uid: str


class MailMessageFlagResult(StrictBaseModel):
    uid: str
    unread: bool


class MailSyncNowPayload(StrictBaseModel):
    mailbox_binding_id: str


class MailSyncNowResult(StrictBaseModel):
    accepted: bool
    mailbox_binding_id: str


class MailMessageMovePayload(StrictBaseModel):
    mailbox_binding_id: str
    folder: str
    uid: str
    destination_folder: str


class MailMessageMoveResult(StrictBaseModel):
    uid: str
    folder: str
    destination_folder: str
    destination_uid: str | None = None


class MailMessageStarPayload(StrictBaseModel):
    mailbox_binding_id: str
    folder: str = "INBOX"
    uid: str
    flagged: bool


class MailMessageStarResult(StrictBaseModel):
    uid: str
    flagged: bool


class MailDraftSavePayload(StrictBaseModel):
    mailbox_binding_id: str
    subject: str = ""
    body_text: str = ""
    body_html: str | None = None
    to_addresses: list[str] = Field(default_factory=list)
    uid: str | None = None
    in_reply_to: str | None = None
    references: str | None = None


class MailDraftSaveResult(StrictBaseModel):
    uid: str
    folder: str
    message_id: str | None = None


class MailMessageSearchPayload(StrictBaseModel):
    mailbox_binding_id: str
    q: str = Field(min_length=1)
    folder: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class MailboxBindingMemberRole(StrEnum):
    MEMBER = "member"
    MANAGER = "manager"


class MailboxBindingMember(StrictBaseModel):
    mailbox_binding_id: str
    user_id: str
    company_id: str
    role: MailboxBindingMemberRole
    created_at: datetime


class MailboxBindingMemberPayload(StrictBaseModel):
    user_id: str
    role: MailboxBindingMemberRole = MailboxBindingMemberRole.MEMBER


class MailThreadPayload(StrictBaseModel):
    mailbox_binding_id: str
    folder: str = "INBOX"
    uid: str


class MailThreadResult(StrictBaseModel):
    thread_id: str
    subject: str | None = None
    participant_emails: list[str] = Field(default_factory=list)
    items: list["MailThreadMessage"] = Field(default_factory=list)
    # UID в payload.folder, которые локально помечены seen при открытии треда (для IMAP enqueue).
    marked_seen_uids: list[str] = Field(default_factory=list)


class MailboxSecret(StrictBaseModel):
    email_address: str
    password: str


class MailboxEnsureSpec(StrictBaseModel):
    mail_domain: str
    local_part: str
    password: str


class MailboxInfo(StrictBaseModel):
    email_address: str
    local_part: str
    mail_domain: str


class MailServerHealth(StrictBaseModel):
    provider: MailProvider
    provision_ok: bool
    imap_ok: bool
    smtp_ok: bool
    detail: str | None = None


class MailAttachment(StrictBaseModel):
    """Вложение письма (MIME part). content может быть пустым при list/ошибке разбора.

    Outbound MailSendPayload: только ``file_id`` (байты уже в Files через chunked upload).
    Inbound MIME / SMTP после resolve: ``content`` in-process.
    """

    filename: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    content: bytes = Field(default=b"", exclude=True)
    size: int = Field(default=0, ge=0)
    available: bool = True
    parse_error: str | None = None
    file_id: str | None = None
    content_id: str | None = None

    @model_validator(mode="after")
    def _content_xor_file_id(self) -> MailAttachment:
        has_file_id = self.file_id is not None and self.file_id.strip() != ""
        has_content = len(self.content) > 0
        if has_file_id and has_content:
            raise ValueError(
                "MailAttachment: content and file_id are mutually exclusive "
                + f"filename={self.filename!r}"
            )
        return self


class MailSendPayload(StrictBaseModel):
    mailbox_binding_id: str
    to_addresses: list[str] = Field(min_length=1)
    subject: str
    body_text: str
    body_html: str | None = None
    message_id: str | None = None
    in_reply_to: str | None = None
    references: str | None = None
    attachments: list[MailAttachment] = Field(default_factory=list)

    @model_validator(mode="after")
    def _attachments_require_file_id(self) -> MailSendPayload:
        for attachment in self.attachments:
            has_file_id = (
                attachment.file_id is not None and attachment.file_id.strip() != ""
            )
            if not has_file_id:
                raise ValueError(
                    "MailSendPayload: attachment.file_id required "
                    + f"filename={attachment.filename!r}"
                )
            if len(attachment.content) > 0:
                raise ValueError(
                    "MailSendPayload: attachment.content forbidden; use file_id "
                    + f"filename={attachment.filename!r}"
                )
        return self


class OutboundMailMessage(StrictBaseModel):
    to_addresses: list[str] = Field(min_length=1)
    subject: str
    body_text: str
    body_html: str | None = None
    message_id: str | None = None
    from_address: str | None = None
    in_reply_to: str | None = None
    references: str | None = None
    attachments: list[MailAttachment] = Field(default_factory=list)


class MailSendResult(StrictBaseModel):
    message_id: str
    accepted: list[str]


class MailFetchQuery(StrictBaseModel):
    mailbox: str = "INBOX"
    subject_contains: str | None = None
    message_id: str | None = None
    limit: int = Field(default=20, ge=1, le=200)
    include_bodies: bool = True


class InboundMailMessage(StrictBaseModel):
    uid: str
    message_id: str | None = None
    subject: str | None = None
    from_address: str | None = None
    to_addresses: list[str] = Field(default_factory=list)
    body_text: str | None = None
    body_html: str | None = None
    unread: bool = True
    flagged: bool = False
    answered: bool = False
    draft: bool = False
    date: datetime | None = None
    in_reply_to: str | None = None
    references: str | None = None
    attachments: list[MailAttachment] = Field(default_factory=list)


class MailThreadMessage(InboundMailMessage):
    folder: str


class MailImapSystemFlag(StrEnum):
    SEEN = "\\Seen"
    FLAGGED = "\\Flagged"
    DELETED = "\\Deleted"
    ANSWERED = "\\Answered"
    DRAFT = "\\Draft"


class MailMessageFlags(StrictBaseModel):
    unread: bool = True
    flagged: bool = False
    answered: bool = False
    draft: bool = False
    deleted: bool = False


class MailUidSearchCriteria(StrictBaseModel):
    all_messages: bool = False
    uid_set: str | None = None
    text: str | None = None
    from_address: str | None = None
    subject: str | None = None
    header_name: str | None = None
    header_value: str | None = None


class MailUidMoveResult(StrictBaseModel):
    source_uid: str
    destination_folder: str
    destination_uid: str | None = None


class MailAppendResult(StrictBaseModel):
    folder: str
    uid: str | None = None
    message_id: str | None = None


class MailIdleWakeKind(StrEnum):
    EXISTS = "exists"
    RECENT = "recent"
    EXPUNGE = "expunge"
    TIMEOUT = "timeout"
    BYE = "bye"
    OTHER = "other"


class MailIdleWake(StrictBaseModel):
    kind: MailIdleWakeKind
    raw: str = ""


class MailSystemEnsureResult(StrictBaseModel):
    ensured: list[str]
    missing_password: list[str]


class MailReconcileResult(StrictBaseModel):
    connection_ensured: bool
    role_mailboxes_ensured: list[str]
    user_bindings_ensured: list[str]
    role_mailboxes_missing_password: list[str]
    user_bindings_missing_password: list[str]


class MailSyncErrorKind(StrEnum):
    AUTH = "auth"
    NETWORK = "network"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


class MailboxSyncCursor(PlatformModel):
    """IMAP-курсор ящика. Таблица ``mailbox_sync_cursors`` в ``platform_shared``.

    ``__global_model__``: синхронизация читает курсоры всех компаний.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    mailbox_binding_id: str = DbField(db_index=True, max_length=255)
    folder: str = DbField(max_length=255)
    company_id: str = DbField(db_index=True, max_length=255)
    uidvalidity: int = DbField()
    last_uid: int = DbField()
    backfill_completed: bool = DbField(default=False)
    oldest_uid: int | None = DbField(default=None)
    last_reconcile_at: datetime | None = DbField(default=None)
    last_synced_at: datetime | None = DbField(default=None, db_index=True)
    last_attempt_at: datetime | None = DbField(default=None)
    last_error_kind: MailSyncErrorKind | None = DbField(
        default=None,
        max_length=32,
        db_type="TEXT",
    )
    last_error_at: datetime | None = DbField(default=None)
    last_error_message: str | None = DbField(default=None, max_length=1024)
    mailbox_sync_cursor_id: str = DbField(default="", db_pk=True, max_length=512)

    class Meta:
        is_table: bool = True
        table_name: str = "mailbox_sync_cursors"
        indexes: list[Index] = [Index(("mailbox_binding_id", "folder"), unique=True)]

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if self.mailbox_binding_id == "" or self.folder == "" or self.company_id == "":
            raise ValueError("mailbox_binding_id, folder and company_id are required")
        self.mailbox_sync_cursor_id = f"{self.mailbox_binding_id}:{self.folder}"

    @model_validator(mode="after")
    def bind_utc_timestamps(self) -> Self:
        if self.last_reconcile_at is not None and self.last_reconcile_at.tzinfo is None:
            self.last_reconcile_at = self.last_reconcile_at.replace(tzinfo=timezone.utc)
        if self.last_synced_at is not None and self.last_synced_at.tzinfo is None:
            self.last_synced_at = self.last_synced_at.replace(tzinfo=timezone.utc)
        if self.last_attempt_at is not None and self.last_attempt_at.tzinfo is None:
            self.last_attempt_at = self.last_attempt_at.replace(tzinfo=timezone.utc)
        if self.last_error_at is not None and self.last_error_at.tzinfo is None:
            self.last_error_at = self.last_error_at.replace(tzinfo=timezone.utc)
        return self


    @classmethod
    async def by_binding_folder(
        cls, mailbox_binding_id: str, *, folder: str = INBOX_FOLDER
    ) -> Self | None:
        return await cls.objects.filter(
            mailbox_binding_id=_mail_required(mailbox_binding_id, "mailbox_binding_id"),
            folder=_mail_required(folder, "folder"),
        ).get_or_none()

    @classmethod
    async def upsert_by_binding_folder(cls, cursor: Self) -> Self:
        existing = await cls.by_binding_folder(cursor.mailbox_binding_id, folder=cursor.folder)
        if existing is None:
            return await cls.objects.create(instance=cursor)
        existing.company_id = cursor.company_id
        existing.uidvalidity = cursor.uidvalidity
        existing.last_uid = cursor.last_uid
        existing.backfill_completed = cursor.backfill_completed
        existing.oldest_uid = cursor.oldest_uid
        existing.last_reconcile_at = cursor.last_reconcile_at
        existing.last_synced_at = cursor.last_synced_at
        existing.last_attempt_at = cursor.last_attempt_at
        existing.last_error_kind = cursor.last_error_kind
        existing.last_error_at = cursor.last_error_at
        existing.last_error_message = cursor.last_error_message
        _ = await existing.save()
        return existing

    @classmethod
    async def delete_by_mailbox_binding(cls, mailbox_binding_id: str, *, folder: str) -> bool:
        deleted = await cls.objects.filter(
            mailbox_binding_id=_mail_required(mailbox_binding_id, "mailbox_binding_id"),
            folder=_mail_required(folder, "folder"),
        ).delete()
        return deleted > 0



class StoredMailMessage(PlatformModel):
    """Локальное письмо. Таблица ``mail_messages`` в ``platform_shared``.

    ``__global_model__``: чтение идёт по ящику, не по активной компании запроса.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    class Meta:
        is_table: bool = True
        table_name: str = "mail_messages"
        indexes: list[Index] = [
            Index(("mailbox_binding_id", "folder", "uid"), unique=True),
            Index(("mailbox_binding_id", "folder", "date_at")),
        ]

    mail_message_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(db_index=True, max_length=255)
    mailbox_binding_id: str = DbField(db_index=True, max_length=255)
    folder: str = DbField(max_length=255)
    uid: int = DbField()
    thread_id: str = DbField(db_index=True, max_length=255)
    synced_at: datetime = DbField()
    created_at: datetime = DbField()
    user_id: str | None = DbField(default=None, db_index=True, max_length=255)
    message_id: str | None = DbField(default=None, max_length=998)
    subject: str = DbField(default="", db_type="TEXT")
    from_address: str = DbField(default="", max_length=998)
    to_addresses: list[str] = DbField(default_factory=list, db_type="JSONB")
    cc_addresses: list[str] = DbField(default_factory=list, db_type="JSONB")
    date_at: datetime | None = DbField(default=None)
    unread: bool = DbField(default=True)
    flagged: bool = DbField(default=False)
    answered: bool = DbField(default=False)
    draft: bool = DbField(default=False)
    has_attachments: bool = DbField(default=False)
    snippet: str = DbField(default="", db_type="TEXT")
    body_text: str | None = DbField(default=None, db_type="TEXT")
    body_html: str | None = DbField(default=None, db_type="TEXT")
    attachments: list[MailAttachment] = DbField(default_factory=list, db_type="JSONB")
    in_reply_to: str | None = DbField(default=None, max_length=998)
    references: str | None = DbField(default=None, db_type="TEXT")
    rag_document_id: str | None = DbField(default=None, max_length=255)
    rag_namespace: str | None = DbField(default=None, max_length=255)
    rag_index_status: MailRagIndexStatus = DbField(
        default=MailRagIndexStatus.SKIPPED,
        max_length=32,
        db_type="TEXT",
    )
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if (
            self.mail_message_id == ""
            or self.company_id == ""
            or self.mailbox_binding_id == ""
            or self.folder == ""
            or self.thread_id == ""
        ):
            raise ValueError(
                "mail_message_id, company_id, mailbox_binding_id, folder and thread_id are required"
            )
        self.updated_at = datetime.now(timezone.utc)


    @classmethod
    async def upsert_by_binding_folder_uid(cls, message: Self) -> Self:
        existing = await cls.by_binding_folder_uid(
            message.mailbox_binding_id,
            folder=message.folder,
            uid=message.uid,
        )
        if existing is None:
            return await cls.objects.create(instance=message)
        existing.message_id = message.message_id
        existing.thread_id = message.thread_id
        existing.subject = message.subject
        existing.from_address = message.from_address
        existing.to_addresses = message.to_addresses
        existing.cc_addresses = message.cc_addresses
        existing.date_at = message.date_at
        existing.unread = message.unread
        existing.flagged = message.flagged
        existing.answered = message.answered
        existing.draft = message.draft
        existing.has_attachments = message.has_attachments
        existing.snippet = message.snippet
        existing.body_text = message.body_text
        existing.body_html = message.body_html
        existing.attachments = message.attachments
        existing.in_reply_to = message.in_reply_to
        existing.references = message.references
        existing.rag_document_id = message.rag_document_id
        existing.rag_namespace = message.rag_namespace
        existing.rag_index_status = message.rag_index_status
        existing.synced_at = message.synced_at
        existing.user_id = message.user_id
        _ = await existing.save()
        return existing

    @classmethod
    async def by_binding_folder_uid(
        cls,
        mailbox_binding_id: str,
        *,
        folder: str,
        uid: int,
    ) -> Self | None:
        return await cls.objects.filter(
            mailbox_binding_id=_mail_required(mailbox_binding_id, "mailbox_binding_id"),
            folder=_mail_required(folder, "folder"),
            uid=uid,
        ).get_or_none()

    @classmethod
    async def list_folder(
        cls,
        mailbox_binding_id: str,
        *,
        folder: str,
        limit: int,
    ) -> list[StoredMailMessage]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        rows = await execute_raw(
            f"""
            SELECT {_MESSAGE_COLUMNS}
            FROM mail_messages
            WHERE mailbox_binding_id = $1 AND folder = $2
            ORDER BY date_at DESC NULLS LAST, uid DESC
            LIMIT $3
            """,
            [_mail_required(mailbox_binding_id, "mailbox_binding_id"), _mail_required(folder, "folder"), limit],
            using="shared",
        )
        return _mail_messages(rows)

    @classmethod
    async def list_by_thread(
        cls,
        mailbox_binding_id: str,
        *,
        thread_id: str,
        limit: int = 200,
    ) -> list[StoredMailMessage]:
        if thread_id.strip() == "":
            raise ValueError("thread_id is required")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        rows = await execute_raw(
            f"""
            SELECT {_MESSAGE_COLUMNS}
            FROM mail_messages
            WHERE mailbox_binding_id = $1 AND thread_id = $2
            ORDER BY date_at ASC NULLS LAST, uid ASC
            LIMIT $3
            """,
            [
                _mail_required(mailbox_binding_id, "mailbox_binding_id"),
                thread_id.strip(),
                limit,
            ],
            using="shared",
        )
        return _mail_messages(rows)

    @classmethod
    async def set_unread(
        cls,
        mailbox_binding_id: str,
        *,
        folder: str,
        uid: int,
        unread: bool,
    ) -> Self | None:
        return await cls.set_flags(
            mailbox_binding_id,
            folder=folder,
            uid=uid,
            unread=unread,
        )

    @classmethod
    async def set_flags(
        cls,
        mailbox_binding_id: str,
        *,
        folder: str,
        uid: int,
        unread: bool | None = None,
        flagged: bool | None = None,
        answered: bool | None = None,
        draft: bool | None = None,
    ) -> Self | None:
        if unread is None and flagged is None and answered is None and draft is None:
            raise ValueError("set_flags requires at least one flag field")
        message = await cls.by_binding_folder_uid(mailbox_binding_id, folder=folder, uid=uid)
        if message is None:
            return None
        if unread is not None:
            message.unread = unread
        if flagged is not None:
            message.flagged = flagged
        if answered is not None:
            message.answered = answered
        if draft is not None:
            message.draft = draft
        _ = await message.save()
        return message

    @classmethod
    async def delete_by_uids(
        cls,
        mailbox_binding_id: str,
        *,
        folder: str,
        uids: list[int],
    ) -> int:
        if len(uids) == 0:
            return 0
        return await cls.objects.filter(
            mailbox_binding_id=_mail_required(mailbox_binding_id, "mailbox_binding_id"),
            folder=_mail_required(folder, "folder"),
            uid__in=uids,
        ).delete()

    @classmethod
    async def delete_folder(cls, mailbox_binding_id: str, *, folder: str) -> int:
        return await cls.objects.filter(
            mailbox_binding_id=_mail_required(mailbox_binding_id, "mailbox_binding_id"),
            folder=_mail_required(folder, "folder"),
        ).delete()

    @classmethod
    async def list_uids(cls, mailbox_binding_id: str, *, folder: str) -> list[int]:
        rows = await execute_raw(
            """
            SELECT uid
            FROM mail_messages
            WHERE mailbox_binding_id = $1 AND folder = $2
            """,
            [_mail_required(mailbox_binding_id, "mailbox_binding_id"), _mail_required(folder, "folder")],
            using="shared",
        )
        uids: list[int] = []
        for row in rows:
            payload = require_json_object(row, "mail_message_uid")
            uid = payload["uid"]
            if not isinstance(uid, int):
                raise ValueError("uid must be an int")
            uids.append(uid)
        return uids

    @classmethod
    async def list_folder_page(
        cls,
        mailbox_binding_id: str,
        *,
        folder: str,
        limit: int,
        before_date: datetime | None = None,
        before_uid: int | None = None,
    ) -> list[StoredMailMessage]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if (before_date is None) != (before_uid is None):
            raise ValueError("before_date and before_uid must be provided together")
        params: list[str | datetime | int] = [
            _mail_required(mailbox_binding_id, "mailbox_binding_id"),
            _mail_required(folder, "folder"),
        ]
        cursor_sql = ""
        if before_date is not None and before_uid is not None:
            cursor_sql = """
              AND (
                date_at < $3::timestamptz
                OR (date_at = $3::timestamptz AND uid < $4)
                OR (date_at IS NULL AND uid < $4)
              )
            """
            params.extend([before_date, before_uid])
        params.append(limit + 1)
        limit_param = f"${len(params)}"
        rows = await execute_raw(
            f"""
            SELECT {_MESSAGE_COLUMNS}
            FROM mail_messages
            WHERE mailbox_binding_id = $1 AND folder = $2
            {cursor_sql}
            ORDER BY date_at DESC NULLS LAST, uid DESC
            LIMIT {limit_param}
            """,
            params,
            using="shared",
        )
        return _mail_messages(rows)

    @classmethod
    async def search_local(
        cls,
        mailbox_binding_id: str,
        *,
        q: str,
        folder: str | None = None,
        limit: int,
        before_date: datetime | None = None,
        before_uid: int | None = None,
    ) -> list[StoredMailMessage]:
        if q.strip() == "":
            raise ValueError("q is required")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if (before_date is None) != (before_uid is None):
            raise ValueError("before_date and before_uid must be provided together")
        params: list[str | datetime | int] = [
            _mail_required(mailbox_binding_id, "mailbox_binding_id"),
            f"%{q.strip()}%",
        ]
        filters = """
            mailbox_binding_id = $1
            AND (
                subject ILIKE $2
                OR from_address ILIKE $2
                OR snippet ILIKE $2
                OR body_text ILIKE $2
                OR to_addresses::text ILIKE $2
            )
        """
        if folder is not None:
            params.append(_mail_required(folder, "folder"))
            filters += f" AND folder = ${len(params)}"
        if before_date is not None and before_uid is not None:
            params.append(before_date)
            date_param = len(params)
            params.append(before_uid)
            uid_param = len(params)
            filters += (
                f" AND (date_at < ${date_param}::timestamptz"
                f" OR (date_at = ${date_param}::timestamptz AND uid < ${uid_param}))"
            )
        params.append(limit + 1)
        rows = await execute_raw(
            f"""
            SELECT {_MESSAGE_COLUMNS}
            FROM mail_messages
            WHERE {filters}
            ORDER BY date_at DESC NULLS LAST, uid DESC
            LIMIT ${len(params)}
            """,
            params,
            using="shared",
        )
        return _mail_messages(rows)



class MailUidBatch(StrictBaseModel):
    """Результат инкрементального IMAP peek (заголовки, не полные тела)."""

    uidvalidity: int
    max_uid: int
    messages: list[InboundMailMessage] = Field(default_factory=list)


class MailSyncBindingResult(StrictBaseModel):
    mailbox_binding_id: str
    company_id: str
    user_id: str | None
    email_address: str
    new_messages: list[InboundMailMessage] = Field(default_factory=list)
    bootstrap: bool = False
    skipped_reason: str | None = None
    backfill_remaining: bool = False


class MailSyncLagStats(StrictBaseModel):
    """Метрики fairness drain для mail_sync_tick."""

    bindings_pending: int = 0
    max_lag_seconds: int = 0
    candidates_total: int = 0


class StoredMailboxFolder(PlatformModel):
    """Кэш IMAP-папки. Таблица ``mailbox_folders`` в ``platform_shared``.

    ``__global_model__``: список читается по ящику, не по активной компании запроса.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    mailbox_binding_id: str = DbField(db_index=True, max_length=255)
    folder_name: str = DbField(max_length=255)
    company_id: str = DbField(db_index=True, max_length=255)
    role: MailFolderRole = DbField(default=MailFolderRole.OTHER, max_length=32, db_type="TEXT")
    delimiter: str | None = DbField(default=None, max_length=16)
    flags: list[str] = DbField(default_factory=list, db_type="JSONB")
    selectable: bool = DbField(default=True)
    message_count: int = DbField(default=0, ge=0)
    unseen_count: int = DbField(default=0, ge=0)
    namespace_prefix: str = DbField(default="", max_length=255)
    capabilities: list[str] = DbField(default_factory=list, db_type="JSONB")
    sort_index: int = DbField(default=0)
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    mailbox_folder_id: str = DbField(default="", db_pk=True, max_length=512)

    class Meta:
        is_table: bool = True
        table_name: str = "mailbox_folders"
        indexes: list[Index] = [Index(("mailbox_binding_id", "folder_name"), unique=True)]

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if self.mailbox_binding_id == "" or self.folder_name == "" or self.company_id == "":
            raise ValueError("mailbox_binding_id, folder_name and company_id are required")
        self.mailbox_folder_id = f"{self.mailbox_binding_id}:{self.folder_name}"
        self.updated_at = datetime.now(timezone.utc)


    @classmethod
    async def list_for_binding(cls, mailbox_binding_id: str) -> list[Self]:
        return await cls.objects.filter(
            mailbox_binding_id=_mail_required(mailbox_binding_id, "mailbox_binding_id"),
        ).order_by("sort_index", "folder_name").all()

    @classmethod
    async def replace_for_binding(
        cls,
        mailbox_binding_id: str,
        *,
        company_id: str,
        folders: list[Self],
    ) -> list[Self]:
        binding_id = _mail_required(mailbox_binding_id, "mailbox_binding_id")
        scoped_company_id = _mail_required(company_id, "company_id")
        rows = [
            folder.model_copy(
                update={
                    "mailbox_binding_id": binding_id,
                    "company_id": scoped_company_id,
                }
            )
            for folder in folders
        ]
        async with atomic(using="shared"):
            _ = await cls.objects.filter(mailbox_binding_id=binding_id).delete()
            for row in rows:
                _ = await cls.objects.create(instance=row)
        return await cls.list_for_binding(binding_id)

    @classmethod
    async def set_sort_indices(
        cls,
        mailbox_binding_id: str,
        *,
        folder_name_to_index: dict[str, int],
    ) -> list[Self]:
        binding_id = _mail_required(mailbox_binding_id, "mailbox_binding_id")
        if len(folder_name_to_index) == 0:
            raise ValueError("folder_name_to_index is required")
        existing = await cls.list_for_binding(binding_id)
        known = {folder.folder_name for folder in existing}
        payload_names = set(folder_name_to_index.keys())
        if known != payload_names:
            missing = sorted(known - payload_names)
            extra = sorted(payload_names - known)
            raise ValueError(
                f"folder_names must match cached folders exactly; missing={missing!r} extra={extra!r}"
            )
        async with atomic(using="shared"):
            for folder in existing:
                folder.sort_index = folder_name_to_index[folder.folder_name]
                _ = await folder.save()
        return await cls.list_for_binding(binding_id)



_ = MailThreadResult.model_rebuild()
