"""Таблица почты."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from oxyde import Index, execute_raw
from pydantic import ConfigDict, SerializerFunctionWrapHandler, model_serializer

from core.mail.models.contracts import (
    INBOX_FOLDER,
    MailboxBindingKind,
    MailConnectionScope,
    MailConnectionStatus,
    MailSyncErrorKind,
    MailSyncLagStats,
    mail_json_str,
    mail_required,
)
from core.mail.models.mailbox_sync_cursor import MailboxSyncCursor
from core.models.base import StrictBaseModel
from core.models.calendar_models import CalendarAutolinkStatus
from core.models.platform_model import PlatformModel
from core.types import JsonObject, require_json_object, require_serializer_json_object


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
    async def list_by_mailbox_binding_id_asc(cls, *, limit: int | None) -> list[Self]:
        """Все привязки, ORDER BY mailbox_binding_id ASC. limit is None не ограничивает."""
        ordered = cls.objects.order_by("mailbox_binding_id")
        if limit is None:
            return await ordered.all()
        return await ordered.limit(limit).all()

    @classmethod
    async def list_with_user_by_mailbox_binding_id_asc(cls, *, limit: int | None) -> list[Self]:
        """Привязки с user_id, ORDER BY mailbox_binding_id ASC. limit is None не ограничивает."""
        ordered = cls.objects.filter(user_id__isnull=False).order_by("mailbox_binding_id")
        if limit is None:
            return await ordered.all()
        return await ordered.limit(limit).all()


    @classmethod
    async def by_mailbox_binding_id(cls, company_id: str, mailbox_binding_id: str) -> Self | None:
        """Строка компании по mailbox_binding_id. Нет строки — None. Пустые company_id и mailbox_binding_id — ValueError."""
        return await cls.objects.filter(
            mailbox_binding_id=mail_required(mailbox_binding_id, "mailbox_binding_id"),
            company_id=mail_required(company_id, "company_id"),
        ).get_or_none()

    @classmethod
    async def by_company_and_email(cls, company_id: str, email_address: str) -> Self | None:
        """Уникальный ключ company_id, email_address. Нет строки — None."""
        return await cls.objects.filter(
            company_id=mail_required(company_id, "company_id"),
            email_address=mail_required(email_address, "email_address"),
        ).get_or_none()

    @classmethod
    async def list_user_kind_by_default_desc_and_email_asc(cls, company_id: str, user_id: str) -> list[Self]:
        """Привязки kind user, ORDER BY is_default DESC, email_address ASC. Предела нет. Пустые company_id и user_id — ValueError."""
        return await cls.objects.filter(
            company_id=mail_required(company_id, "company_id"),
            user_id=mail_required(user_id, "user_id"),
            kind=MailboxBindingKind.USER,
        ).order_by("-is_default", "email_address").all()

    @classmethod
    async def find_default_or_first_by_email_for_user(cls, company_id: str, user_id: str) -> Self | None:
        """Первая привязка kind=user с is_default в порядке is_default DESC, email_address ASC. Иначе первая строка этого порядка. Нет строк — None."""
        bindings = await cls.list_user_kind_by_default_desc_and_email_asc(company_id, user_id)
        if len(bindings) == 0:
            return None
        for binding in bindings:
            if binding.is_default:
                return binding
        return bindings[0]

    @classmethod
    async def list_for_company_by_email_address_asc(cls, company_id: str) -> list[Self]:
        """Все привязки компании, ORDER BY email_address ASC. Предела нет. Пустой company_id — ValueError."""
        return await cls.objects.filter(
            company_id=mail_required(company_id, "company_id"),
        ).order_by("email_address").all()

    @classmethod
    async def list_sync_ready_by_last_synced_at_asc(
        cls,
        *,
        limit: int,
        auth_error_cooldown_seconds: int,
        folder: str = INBOX_FOLDER,
    ) -> list[Self]:
        """Готовые к синхронизации: sync_enabled, активное подключение, user с user_id или role; ошибка auth отсутствует либо старше cooldown. ORDER BY last_synced_at ASC NULLS FIRST, не больше limit. folder по умолчанию inbox."""
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
            binding = await cls.by_mailbox_binding_id(
                mail_json_str(payload, "company_id"),
                mail_json_str(payload, "mailbox_binding_id"),
            )
            if binding is None:
                raise RuntimeError("sync candidate binding disappeared")
            bindings.append(binding)
        return bindings

    @classmethod
    async def count_sync_ready(
        cls,
        *,
        auth_error_cooldown_seconds: int,
        folder: str = INBOX_FOLDER,
    ) -> int:
        """Число готовых к синхронизации привязок. Тот же отбор, что у list_sync_ready_by_last_synced_at_asc. Порядка нет."""
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
        candidates = await cls.list_sync_ready_by_last_synced_at_asc(
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
            company_id=mail_required(company_id, "company_id"),
            user_id=mail_required(user_id, "user_id"),
            kind=MailboxBindingKind.USER,
            is_default=True,
        )
        if except_binding_id is not None:
            query = query.exclude(
                mailbox_binding_id=mail_required(except_binding_id, "except_binding_id")
            )
        _ = await query.update(is_default=False)

    @classmethod
    async def upsert_by_company_and_email(cls, binding: Self) -> Self:
        """Слияние по company_id и email_address. Нет строки — вставка. Тот же mailbox_binding_id — обновление полей. Другой id — перенос строки."""
        by_email = await cls.by_company_and_email(binding.company_id, binding.email_address)
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
        stored = await cls.by_mailbox_binding_id(binding.company_id, binding.mailbox_binding_id)
        if stored is None:
            raise RuntimeError(
                f"MailboxBinding upsert failed for email_address={binding.email_address}"
            )
        return stored

    @classmethod
    async def delete_by_company_and_binding(cls, company_id: str, mailbox_binding_id: str) -> bool:
        """Удаление привязки компании. Нет строки — False."""
        deleted = await cls.objects.filter(
            mailbox_binding_id=mail_required(mailbox_binding_id, "mailbox_binding_id"),
            company_id=mail_required(company_id, "company_id"),
        ).delete()
        return deleted > 0

class MailboxBindingsMeResponse(StrictBaseModel):
    """Мои mailbox bindings + server-driven company admin capability."""

    items: list[MailboxBinding]
    can_admin: bool
