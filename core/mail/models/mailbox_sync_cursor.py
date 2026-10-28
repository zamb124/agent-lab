"""Таблица почты."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from oxyde import Index
from pydantic import model_validator

from core.mail.models.contracts import (
    INBOX_FOLDER,
    MailSyncErrorKind,
    mail_required,
)
from core.models.platform_model import PlatformModel


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
            mailbox_binding_id=mail_required(mailbox_binding_id, "mailbox_binding_id"),
            folder=mail_required(folder, "folder"),
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
    async def delete_by_mailbox_binding_and_folder(cls, mailbox_binding_id: str, *, folder: str) -> bool:
        """Удаляет курсор ящика в папке. Нет строки — False. Пустые mailbox_binding_id и folder — ValueError."""
        deleted = await cls.objects.filter(
            mailbox_binding_id=mail_required(mailbox_binding_id, "mailbox_binding_id"),
            folder=mail_required(folder, "folder"),
        ).delete()
        return deleted > 0
