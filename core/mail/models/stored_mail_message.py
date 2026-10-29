"""Таблица почты."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from oxyde import Index, execute_raw
from pydantic import ConfigDict

from core.mail.models.contracts import (
    MESSAGE_COLUMNS,
    MailAttachment,
    MailRagIndexStatus,
    mail_required,
)
from core.models.platform_model import PlatformModel
from core.types import JsonValue, require_json_object


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
            mailbox_binding_id=mail_required(mailbox_binding_id, "mailbox_binding_id"),
            folder=mail_required(folder, "folder"),
            uid=uid,
        ).get_or_none()

    @classmethod
    async def list_for_folder_by_date_at_and_uid_desc(
        cls,
        mailbox_binding_id: str,
        *,
        folder: str,
        limit: int,
    ) -> list[StoredMailMessage]:
        """Письма папки, ORDER BY date_at DESC NULLS LAST, uid DESC, не больше limit."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        rows = await execute_raw(
            f"""
            SELECT {MESSAGE_COLUMNS}
            FROM mail_messages
            WHERE mailbox_binding_id = $1 AND folder = $2
            ORDER BY date_at DESC NULLS LAST, uid DESC
            LIMIT $3
            """,
            [mail_required(mailbox_binding_id, "mailbox_binding_id"), mail_required(folder, "folder"), limit],
            using="shared",
        )
        return _mail_messages(rows)

    @classmethod
    async def list_for_thread_by_date_at_and_uid_asc(
        cls,
        mailbox_binding_id: str,
        *,
        thread_id: str,
        limit: int = 200,
    ) -> list[StoredMailMessage]:
        """Письма треда, ORDER BY date_at ASC NULLS LAST, uid ASC, не больше limit. limit по умолчанию 200. Пустой thread_id и limit < 1 — ValueError."""
        if thread_id.strip() == "":
            raise ValueError("thread_id is required")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        rows = await execute_raw(
            f"""
            SELECT {MESSAGE_COLUMNS}
            FROM mail_messages
            WHERE mailbox_binding_id = $1 AND thread_id = $2
            ORDER BY date_at ASC NULLS LAST, uid ASC
            LIMIT $3
            """,
            [
                mail_required(mailbox_binding_id, "mailbox_binding_id"),
                thread_id.strip(),
                limit,
            ],
            using="shared",
        )
        return _mail_messages(rows)

    @classmethod
    async def update_flags(
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
        """Пишет только переданные флаги. Все None — ValueError. Нет письма — None."""
        if unread is None and flagged is None and answered is None and draft is None:
            raise ValueError("update_flags requires at least one flag field")
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
            mailbox_binding_id=mail_required(mailbox_binding_id, "mailbox_binding_id"),
            folder=mail_required(folder, "folder"),
            uid__in=uids,
        ).delete()

    @classmethod
    async def delete_by_binding_and_folder(cls, mailbox_binding_id: str, *, folder: str) -> int:
        """Письма папки. Возвращает число удалённых строк. Нет писем — 0."""
        return await cls.objects.filter(
            mailbox_binding_id=mail_required(mailbox_binding_id, "mailbox_binding_id"),
            folder=mail_required(folder, "folder"),
        ).delete()

    @classmethod
    async def list_unordered_uids_for_folder(cls, mailbox_binding_id: str, *, folder: str) -> list[int]:
        """Uid папки. Порядка и предела нет."""
        rows = await execute_raw(
            """
            SELECT uid
            FROM mail_messages
            WHERE mailbox_binding_id = $1 AND folder = $2
            """,
            [mail_required(mailbox_binding_id, "mailbox_binding_id"), mail_required(folder, "folder")],
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
    async def list_for_folder_by_date_at_and_uid_desc_over_limit(
        cls,
        mailbox_binding_id: str,
        *,
        folder: str,
        limit: int,
        before_date: datetime | None = None,
        before_uid: int | None = None,
    ) -> list[StoredMailMessage]:
        """Письма папки, ORDER BY date_at DESC NULLS LAST, uid DESC, LIMIT limit + 1."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if (before_date is None) != (before_uid is None):
            raise ValueError("before_date and before_uid must be provided together")
        params: list[str | datetime | int] = [
            mail_required(mailbox_binding_id, "mailbox_binding_id"),
            mail_required(folder, "folder"),
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
            SELECT {MESSAGE_COLUMNS}
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
    async def list_query_matches_by_date_at_and_uid_desc_over_limit(
        cls,
        mailbox_binding_id: str,
        *,
        q: str,
        folder: str | None = None,
        limit: int,
        before_date: datetime | None = None,
        before_uid: int | None = None,
    ) -> list[StoredMailMessage]:
        """Совпадения q в subject, from_address, snippet, body_text или to_addresses. folder is None папку не сужает. ORDER BY date_at DESC NULLS LAST, uid DESC, LIMIT limit + 1."""
        if q.strip() == "":
            raise ValueError("q is required")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if (before_date is None) != (before_uid is None):
            raise ValueError("before_date and before_uid must be provided together")
        params: list[str | datetime | int] = [
            mail_required(mailbox_binding_id, "mailbox_binding_id"),
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
            params.append(mail_required(folder, "folder"))
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
            SELECT {MESSAGE_COLUMNS}
            FROM mail_messages
            WHERE {filters}
            ORDER BY date_at DESC NULLS LAST, uid DESC
            LIMIT ${len(params)}
            """,
            params,
            using="shared",
        )
        return _mail_messages(rows)

def _mail_messages(rows: Sequence[JsonValue]) -> list[StoredMailMessage]:
    return [
        StoredMailMessage.model_validate(require_json_object(row, "mail_messages"))
        for row in rows
    ]
