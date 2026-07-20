"""SQL-репозитории почты (shared БД)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Final, final

from sqlalchemy import String, and_, cast, delete, nulls_first, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from core.db.database import get_session_factory
from core.db.models.platform import (
    CompanyMailConnectionRecord,
    MailboxBindingMemberRecord,
    MailboxBindingRecord,
    MailboxFolderRecord,
    MailboxSyncCursorRecord,
    MailMessageRecord,
)
from core.db.utils import get_rowcount
from core.mail.models import (
    CompanyMailConnection,
    IspmanagerProvisionConfig,
    MailboxBinding,
    MailboxBindingKind,
    MailboxBindingMember,
    MailboxBindingMemberRole,
    MailboxSyncCursor,
    MailConnectionStatus,
    MailFolderRole,
    MailProvider,
    MailSyncErrorKind,
    MailSyncLagStats,
    StoredMailAttachmentRef,
    StoredMailboxFolder,
    StoredMailMessage,
)
from core.types import JsonObject

INBOX_FOLDER: Final[str] = "INBOX"


def _connection_from_record(record: CompanyMailConnectionRecord) -> CompanyMailConnection:
    ispmanager: IspmanagerProvisionConfig | None = None
    if record.ispmanager_base_url is not None and record.ispmanager_authinfo_user is not None:
        ispmanager = IspmanagerProvisionConfig(
            base_url=record.ispmanager_base_url,
            authinfo_user=record.ispmanager_authinfo_user,
            authinfo_password_encrypted=record.ispmanager_authinfo_password_encrypted,
        )
    return CompanyMailConnection(
        company_mail_connection_id=record.company_mail_connection_id,
        company_id=record.company_id,
        mail_domain=record.mail_domain,
        provider=MailProvider(record.provider),
        imap_host=record.imap_host,
        imap_port=record.imap_port,
        smtp_host=record.smtp_host,
        smtp_port=record.smtp_port,
        use_ssl=record.use_ssl,
        supports_provision=record.supports_provision,
        status=MailConnectionStatus(record.status),
        ispmanager=ispmanager,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _binding_from_record(record: MailboxBindingRecord) -> MailboxBinding:
    return MailboxBinding(
        mailbox_binding_id=record.mailbox_binding_id,
        company_id=record.company_id,
        company_mail_connection_id=record.company_mail_connection_id,
        user_id=record.user_id,
        kind=MailboxBindingKind(record.kind),
        email_address=record.email_address,
        local_part=record.local_part,
        sync_enabled=record.sync_enabled,
        is_default=record.is_default,
        calendar_color=record.calendar_color,
        password_encrypted=record.password_encrypted,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _cursor_from_record(record: MailboxSyncCursorRecord) -> MailboxSyncCursor:
    error_kind: MailSyncErrorKind | None = None
    if record.last_error_kind is not None:
        error_kind = MailSyncErrorKind(record.last_error_kind)
    return MailboxSyncCursor(
        mailbox_binding_id=record.mailbox_binding_id,
        folder=record.folder,
        company_id=record.company_id,
        uidvalidity=int(record.uidvalidity),
        last_uid=int(record.last_uid),
        backfill_completed=bool(record.backfill_completed),
        oldest_uid=int(record.oldest_uid) if record.oldest_uid is not None else None,
        last_reconcile_at=record.last_reconcile_at,
        last_synced_at=record.last_synced_at,
        last_attempt_at=record.last_attempt_at,
        last_error_kind=error_kind,
        last_error_at=record.last_error_at,
        last_error_message=record.last_error_message,
    )


@final
class CompanyMailConnectionRepository:
    def __init__(self, db_url: str) -> None:
        self._db_url: Final[str] = db_url

    async def get_by_company(self, company_id: str) -> CompanyMailConnection | None:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(CompanyMailConnectionRecord).where(
                    CompanyMailConnectionRecord.company_id == company_id
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _connection_from_record(row)

    async def upsert(self, connection: CompanyMailConnection) -> CompanyMailConnection:
        session_factory = await get_session_factory(self._db_url)
        ispmanager_base_url: str | None = None
        ispmanager_authinfo_user: str | None = None
        ispmanager_authinfo_password_encrypted: str | None = None
        if connection.ispmanager is not None:
            ispmanager_base_url = connection.ispmanager.base_url
            ispmanager_authinfo_user = connection.ispmanager.authinfo_user
            ispmanager_authinfo_password_encrypted = (
                connection.ispmanager.authinfo_password_encrypted
            )
        values = {
            "company_mail_connection_id": connection.company_mail_connection_id,
            "company_id": connection.company_id,
            "mail_domain": connection.mail_domain,
            "provider": str(connection.provider),
            "imap_host": connection.imap_host,
            "imap_port": connection.imap_port,
            "smtp_host": connection.smtp_host,
            "smtp_port": connection.smtp_port,
            "use_ssl": connection.use_ssl,
            "supports_provision": connection.supports_provision,
            "status": str(connection.status),
            "ispmanager_base_url": ispmanager_base_url,
            "ispmanager_authinfo_user": ispmanager_authinfo_user,
            "ispmanager_authinfo_password_encrypted": ispmanager_authinfo_password_encrypted,
            "created_at": connection.created_at,
            "updated_at": connection.updated_at,
        }
        stmt = insert(CompanyMailConnectionRecord).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["company_id"],
            set_={
                "company_mail_connection_id": stmt.excluded.company_mail_connection_id,
                "mail_domain": stmt.excluded.mail_domain,
                "provider": stmt.excluded.provider,
                "imap_host": stmt.excluded.imap_host,
                "imap_port": stmt.excluded.imap_port,
                "smtp_host": stmt.excluded.smtp_host,
                "smtp_port": stmt.excluded.smtp_port,
                "use_ssl": stmt.excluded.use_ssl,
                "supports_provision": stmt.excluded.supports_provision,
                "status": stmt.excluded.status,
                "ispmanager_base_url": stmt.excluded.ispmanager_base_url,
                "ispmanager_authinfo_user": stmt.excluded.ispmanager_authinfo_user,
                "ispmanager_authinfo_password_encrypted": (
                    stmt.excluded.ispmanager_authinfo_password_encrypted
                ),
                "updated_at": stmt.excluded.updated_at,
            },
        )
        async with session_factory() as session:
            _ = await session.execute(stmt)
            await session.commit()
        stored = await self.get_by_company(connection.company_id)
        if stored is None:
            raise RuntimeError(
                f"CompanyMailConnection upsert failed for company_id={connection.company_id}"
            )
        return stored


@final
class MailboxBindingRepository:
    def __init__(self, db_url: str) -> None:
        self._db_url: Final[str] = db_url

    async def get(
        self, mailbox_binding_id: str, company_id: str
    ) -> MailboxBinding | None:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailboxBindingRecord).where(
                    MailboxBindingRecord.mailbox_binding_id == mailbox_binding_id,
                    MailboxBindingRecord.company_id == company_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _binding_from_record(row)

    async def get_by_email(
        self, company_id: str, email_address: str
    ) -> MailboxBinding | None:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailboxBindingRecord).where(
                    MailboxBindingRecord.company_id == company_id,
                    MailboxBindingRecord.email_address == email_address,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _binding_from_record(row)

    async def list_by_user(
        self, company_id: str, user_id: str
    ) -> list[MailboxBinding]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailboxBindingRecord)
                .where(
                    MailboxBindingRecord.company_id == company_id,
                    MailboxBindingRecord.user_id == user_id,
                    MailboxBindingRecord.kind == str(MailboxBindingKind.USER),
                )
                .order_by(
                    MailboxBindingRecord.is_default.desc(),
                    MailboxBindingRecord.email_address,
                )
            )
            rows = result.scalars().all()
            return [_binding_from_record(row) for row in rows]

    async def get_by_user(
        self, company_id: str, user_id: str
    ) -> MailboxBinding | None:
        """Default или первый user-binding (совместимость с lazy/reconcile)."""
        bindings = await self.list_by_user(company_id, user_id)
        if not bindings:
            return None
        for binding in bindings:
            if binding.is_default:
                return binding
        return bindings[0]

    async def list_by_company(self, company_id: str) -> list[MailboxBinding]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailboxBindingRecord)
                .where(MailboxBindingRecord.company_id == company_id)
                .order_by(MailboxBindingRecord.email_address)
            )
            rows = result.scalars().all()
            return [_binding_from_record(row) for row in rows]

    async def list_sync_candidates(
        self,
        *,
        limit: int,
        auth_error_cooldown_seconds: int,
        folder: str = INBOX_FOLDER,
    ) -> list[MailboxBinding]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if auth_error_cooldown_seconds < 0:
            raise ValueError("auth_error_cooldown_seconds must be >= 0")
        cooldown_cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=auth_error_cooldown_seconds
        )
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailboxBindingRecord)
                .join(
                    CompanyMailConnectionRecord,
                    CompanyMailConnectionRecord.company_mail_connection_id
                    == MailboxBindingRecord.company_mail_connection_id,
                )
                .outerjoin(
                    MailboxSyncCursorRecord,
                    and_(
                        MailboxSyncCursorRecord.mailbox_binding_id
                        == MailboxBindingRecord.mailbox_binding_id,
                        MailboxSyncCursorRecord.folder == folder,
                    ),
                )
                .where(
                    MailboxBindingRecord.sync_enabled.is_(True),
                    CompanyMailConnectionRecord.status
                    == str(MailConnectionStatus.ACTIVE),
                    or_(
                        and_(
                            MailboxBindingRecord.kind == str(MailboxBindingKind.USER),
                            MailboxBindingRecord.user_id.is_not(None),
                        ),
                        MailboxBindingRecord.kind == str(MailboxBindingKind.ROLE),
                    ),
                    or_(
                        MailboxSyncCursorRecord.last_error_kind.is_(None),
                        MailboxSyncCursorRecord.last_error_kind
                        != str(MailSyncErrorKind.AUTH),
                        MailboxSyncCursorRecord.last_error_at.is_(None),
                        MailboxSyncCursorRecord.last_error_at <= cooldown_cutoff,
                    ),
                )
                .order_by(nulls_first(MailboxSyncCursorRecord.last_synced_at.asc()))
                .limit(limit)
            )
            rows = result.scalars().all()
            return [_binding_from_record(row) for row in rows]

    async def count_sync_candidates(
        self,
        *,
        auth_error_cooldown_seconds: int,
        folder: str = INBOX_FOLDER,
    ) -> int:
        if auth_error_cooldown_seconds < 0:
            raise ValueError("auth_error_cooldown_seconds must be >= 0")
        cooldown_cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=auth_error_cooldown_seconds
        )
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailboxBindingRecord.mailbox_binding_id)
                .join(
                    CompanyMailConnectionRecord,
                    CompanyMailConnectionRecord.company_mail_connection_id
                    == MailboxBindingRecord.company_mail_connection_id,
                )
                .outerjoin(
                    MailboxSyncCursorRecord,
                    and_(
                        MailboxSyncCursorRecord.mailbox_binding_id
                        == MailboxBindingRecord.mailbox_binding_id,
                        MailboxSyncCursorRecord.folder == folder,
                    ),
                )
                .where(
                    MailboxBindingRecord.sync_enabled.is_(True),
                    CompanyMailConnectionRecord.status
                    == str(MailConnectionStatus.ACTIVE),
                    or_(
                        and_(
                            MailboxBindingRecord.kind == str(MailboxBindingKind.USER),
                            MailboxBindingRecord.user_id.is_not(None),
                        ),
                        MailboxBindingRecord.kind == str(MailboxBindingKind.ROLE),
                    ),
                    or_(
                        MailboxSyncCursorRecord.last_error_kind.is_(None),
                        MailboxSyncCursorRecord.last_error_kind
                        != str(MailSyncErrorKind.AUTH),
                        MailboxSyncCursorRecord.last_error_at.is_(None),
                        MailboxSyncCursorRecord.last_error_at <= cooldown_cutoff,
                    ),
                )
            )
            return len(list(result.scalars().all()))

    async def list_accessible_bindings(
        self,
        company_id: str,
        user_id: str,
    ) -> list[MailboxBinding]:
        if not user_id.strip():
            raise ValueError("user_id is required")
        own = await self.list_by_user(company_id, user_id)
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailboxBindingRecord)
                .join(
                    MailboxBindingMemberRecord,
                    and_(
                        MailboxBindingMemberRecord.mailbox_binding_id
                        == MailboxBindingRecord.mailbox_binding_id,
                        MailboxBindingMemberRecord.user_id == user_id,
                    ),
                )
                .where(
                    MailboxBindingRecord.company_id == company_id,
                    MailboxBindingRecord.kind == str(MailboxBindingKind.ROLE),
                )
                .order_by(MailboxBindingRecord.email_address)
            )
            role_rows = list(result.scalars().all())
        by_id = {binding.mailbox_binding_id: binding for binding in own}
        for row in role_rows:
            binding = _binding_from_record(row)
            by_id[binding.mailbox_binding_id] = binding
        return sorted(by_id.values(), key=lambda item: item.email_address)

    async def sync_lag_stats(
        self,
        *,
        auth_error_cooldown_seconds: int,
        folder: str = INBOX_FOLDER,
    ) -> MailSyncLagStats:
        candidates = await self.list_sync_candidates(
            limit=10_000,
            auth_error_cooldown_seconds=auth_error_cooldown_seconds,
            folder=folder,
        )
        now = datetime.now(timezone.utc)
        max_lag_seconds = 0
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            for binding in candidates:
                result = await session.execute(
                    select(MailboxSyncCursorRecord.last_synced_at).where(
                        MailboxSyncCursorRecord.mailbox_binding_id
                        == binding.mailbox_binding_id,
                        MailboxSyncCursorRecord.folder == folder,
                    )
                )
                last_synced_at = result.scalar_one_or_none()
                if last_synced_at is None:
                    max_lag_seconds = max(max_lag_seconds, 10**9)
                    continue
                lag = int((now - last_synced_at).total_seconds())
                if lag > max_lag_seconds:
                    max_lag_seconds = lag
        return MailSyncLagStats(
            bindings_pending=len(candidates),
            max_lag_seconds=max_lag_seconds if max_lag_seconds < 10**9 else max_lag_seconds,
            candidates_total=len(candidates),
        )

    async def clear_defaults_for_user(
        self, company_id: str, user_id: str, *, except_binding_id: str | None = None
    ) -> None:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            stmt = (
                update(MailboxBindingRecord)
                .where(
                    MailboxBindingRecord.company_id == company_id,
                    MailboxBindingRecord.user_id == user_id,
                    MailboxBindingRecord.kind == str(MailboxBindingKind.USER),
                    MailboxBindingRecord.is_default.is_(True),
                )
                .values(is_default=False)
            )
            if except_binding_id is not None:
                stmt = stmt.where(
                    MailboxBindingRecord.mailbox_binding_id != except_binding_id
                )
            _ = await session.execute(stmt)
            await session.commit()

    async def upsert(self, binding: MailboxBinding) -> MailboxBinding:
        session_factory = await get_session_factory(self._db_url)
        values = {
            "mailbox_binding_id": binding.mailbox_binding_id,
            "company_id": binding.company_id,
            "company_mail_connection_id": binding.company_mail_connection_id,
            "user_id": binding.user_id,
            "kind": str(binding.kind),
            "email_address": binding.email_address,
            "local_part": binding.local_part,
            "sync_enabled": binding.sync_enabled,
            "is_default": binding.is_default,
            "calendar_color": binding.calendar_color,
            "password_encrypted": binding.password_encrypted,
            "created_at": binding.created_at,
            "updated_at": binding.updated_at,
        }
        stmt = insert(MailboxBindingRecord).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["company_id", "email_address"],
            set_={
                "mailbox_binding_id": stmt.excluded.mailbox_binding_id,
                "company_mail_connection_id": stmt.excluded.company_mail_connection_id,
                "user_id": stmt.excluded.user_id,
                "kind": stmt.excluded.kind,
                "local_part": stmt.excluded.local_part,
                "sync_enabled": stmt.excluded.sync_enabled,
                "is_default": stmt.excluded.is_default,
                "calendar_color": stmt.excluded.calendar_color,
                "password_encrypted": stmt.excluded.password_encrypted,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        async with session_factory() as session:
            _ = await session.execute(stmt)
            await session.commit()
        stored = await self.get_by_email(binding.company_id, binding.email_address)
        if stored is None:
            raise RuntimeError(
                f"MailboxBinding upsert failed for email_address={binding.email_address}"
            )
        return stored

    async def delete(self, mailbox_binding_id: str, company_id: str) -> bool:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                delete(MailboxBindingRecord).where(
                    MailboxBindingRecord.mailbox_binding_id == mailbox_binding_id,
                    MailboxBindingRecord.company_id == company_id,
                )
            )
            await session.commit()
            return get_rowcount(result) > 0


@final
class MailboxSyncCursorRepository:
    def __init__(self, db_url: str) -> None:
        self._db_url: Final[str] = db_url

    async def get(
        self, mailbox_binding_id: str, *, folder: str = INBOX_FOLDER
    ) -> MailboxSyncCursor | None:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailboxSyncCursorRecord).where(
                    MailboxSyncCursorRecord.mailbox_binding_id == mailbox_binding_id,
                    MailboxSyncCursorRecord.folder == folder,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _cursor_from_record(row)

    async def upsert(self, cursor: MailboxSyncCursor) -> MailboxSyncCursor:
        session_factory = await get_session_factory(self._db_url)
        values = {
            "mailbox_binding_id": cursor.mailbox_binding_id,
            "folder": cursor.folder,
            "company_id": cursor.company_id,
            "uidvalidity": cursor.uidvalidity,
            "last_uid": cursor.last_uid,
            "backfill_completed": cursor.backfill_completed,
            "oldest_uid": cursor.oldest_uid,
            "last_reconcile_at": cursor.last_reconcile_at,
            "last_synced_at": cursor.last_synced_at,
            "last_attempt_at": cursor.last_attempt_at,
            "last_error_kind": (
                str(cursor.last_error_kind) if cursor.last_error_kind is not None else None
            ),
            "last_error_at": cursor.last_error_at,
            "last_error_message": cursor.last_error_message,
        }
        stmt = insert(MailboxSyncCursorRecord).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["mailbox_binding_id", "folder"],
            set_={
                "company_id": stmt.excluded.company_id,
                "uidvalidity": stmt.excluded.uidvalidity,
                "last_uid": stmt.excluded.last_uid,
                "backfill_completed": stmt.excluded.backfill_completed,
                "oldest_uid": stmt.excluded.oldest_uid,
                "last_reconcile_at": stmt.excluded.last_reconcile_at,
                "last_synced_at": stmt.excluded.last_synced_at,
                "last_attempt_at": stmt.excluded.last_attempt_at,
                "last_error_kind": stmt.excluded.last_error_kind,
                "last_error_at": stmt.excluded.last_error_at,
                "last_error_message": stmt.excluded.last_error_message,
            },
        )
        async with session_factory() as session:
            _ = await session.execute(stmt)
            await session.commit()
        stored = await self.get(cursor.mailbox_binding_id, folder=cursor.folder)
        if stored is None:
            raise RuntimeError(
                f"MailboxSyncCursor upsert failed for mailbox_binding_id={cursor.mailbox_binding_id}"
            )
        return stored

    async def delete(self, mailbox_binding_id: str, *, folder: str) -> bool:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                delete(MailboxSyncCursorRecord).where(
                    MailboxSyncCursorRecord.mailbox_binding_id == mailbox_binding_id,
                    MailboxSyncCursorRecord.folder == folder,
                )
            )
            await session.commit()
            return get_rowcount(result) > 0


def _attachment_refs_from_json(
    raw: list[JsonObject] | None,
) -> list[StoredMailAttachmentRef]:
    if raw is None:
        return []
    refs: list[StoredMailAttachmentRef] = []
    for item in raw:
        refs.append(StoredMailAttachmentRef.model_validate(item))
    return refs


def _stored_from_record(record: MailMessageRecord) -> StoredMailMessage:
    return StoredMailMessage(
        mail_message_id=record.mail_message_id,
        company_id=record.company_id,
        mailbox_binding_id=record.mailbox_binding_id,
        user_id=record.user_id,
        folder=record.folder,
        uid=int(record.uid),
        message_id=record.message_id,
        thread_id=record.thread_id,
        subject=record.subject,
        from_address=record.from_address,
        to_addresses=list(record.to_addresses),
        cc_addresses=list(record.cc_addresses),
        date_at=record.date_at,
        unread=bool(record.unread),
        flagged=bool(record.flagged),
        answered=bool(record.answered),
        draft=bool(record.draft),
        has_attachments=bool(record.has_attachments),
        snippet=record.snippet,
        body_text=record.body_text,
        body_html=record.body_html,
        attachments=_attachment_refs_from_json(list(record.attachments_json)),
        in_reply_to=record.in_reply_to,
        references=record.references_header,
        rag_document_id=record.rag_document_id,
        rag_namespace=record.rag_namespace,
        synced_at=record.synced_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@final
class MailMessageRepository:
    """Локальные метаданные писем."""

    def __init__(self, db_url: str) -> None:
        self._db_url: Final[str] = db_url

    async def upsert(self, message: StoredMailMessage) -> StoredMailMessage:
        session_factory = await get_session_factory(self._db_url)
        attachments_json: list[JsonObject] = [
            attachment.model_dump(mode="json") for attachment in message.attachments
        ]
        values = {
            "mail_message_id": message.mail_message_id,
            "company_id": message.company_id,
            "mailbox_binding_id": message.mailbox_binding_id,
            "user_id": message.user_id,
            "folder": message.folder,
            "uid": message.uid,
            "message_id": message.message_id,
            "thread_id": message.thread_id,
            "subject": message.subject,
            "from_address": message.from_address,
            "to_addresses": message.to_addresses,
            "cc_addresses": message.cc_addresses,
            "date_at": message.date_at,
            "unread": message.unread,
            "flagged": message.flagged,
            "answered": message.answered,
            "draft": message.draft,
            "has_attachments": message.has_attachments,
            "snippet": message.snippet,
            "body_text": message.body_text,
            "body_html": message.body_html,
            "attachments_json": attachments_json,
            "in_reply_to": message.in_reply_to,
            "references_header": message.references,
            "rag_document_id": message.rag_document_id,
            "rag_namespace": message.rag_namespace,
            "synced_at": message.synced_at,
            "created_at": message.created_at,
            "updated_at": message.updated_at,
        }
        stmt = insert(MailMessageRecord).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_mail_messages_binding_folder_uid",
            set_={
                "message_id": stmt.excluded.message_id,
                "thread_id": stmt.excluded.thread_id,
                "subject": stmt.excluded.subject,
                "from_address": stmt.excluded.from_address,
                "to_addresses": stmt.excluded.to_addresses,
                "cc_addresses": stmt.excluded.cc_addresses,
                "date_at": stmt.excluded.date_at,
                "unread": stmt.excluded.unread,
                "flagged": stmt.excluded.flagged,
                "answered": stmt.excluded.answered,
                "draft": stmt.excluded.draft,
                "has_attachments": stmt.excluded.has_attachments,
                "snippet": stmt.excluded.snippet,
                "body_text": stmt.excluded.body_text,
                "body_html": stmt.excluded.body_html,
                "attachments_json": stmt.excluded.attachments_json,
                "in_reply_to": stmt.excluded.in_reply_to,
                "references_header": stmt.excluded.references_header,
                "rag_document_id": stmt.excluded.rag_document_id,
                "rag_namespace": stmt.excluded.rag_namespace,
                "synced_at": stmt.excluded.synced_at,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        async with session_factory() as session:
            _ = await session.execute(stmt)
            await session.commit()
        stored = await self.get_by_uid(
            message.mailbox_binding_id,
            folder=message.folder,
            uid=message.uid,
        )
        if stored is None:
            raise RuntimeError(
                f"MailMessage upsert failed for {message.mailbox_binding_id}/{message.folder}/{message.uid}"
            )
        return stored

    async def get_by_uid(
        self,
        mailbox_binding_id: str,
        *,
        folder: str,
        uid: int,
    ) -> StoredMailMessage | None:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailMessageRecord).where(
                    MailMessageRecord.mailbox_binding_id == mailbox_binding_id,
                    MailMessageRecord.folder == folder,
                    MailMessageRecord.uid == uid,
                )
            )
            record = result.scalar_one_or_none()
        if record is None:
            return None
        return _stored_from_record(record)

    async def list_folder(
        self,
        mailbox_binding_id: str,
        *,
        folder: str,
        limit: int,
    ) -> list[StoredMailMessage]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailMessageRecord)
                .where(
                    MailMessageRecord.mailbox_binding_id == mailbox_binding_id,
                    MailMessageRecord.folder == folder,
                )
                .order_by(
                    MailMessageRecord.date_at.desc().nulls_last(),
                    MailMessageRecord.uid.desc(),
                )
                .limit(limit)
            )
            records = list(result.scalars().all())
        return [_stored_from_record(record) for record in records]

    async def list_by_thread(
        self,
        mailbox_binding_id: str,
        *,
        thread_id: str,
        limit: int = 200,
    ) -> list[StoredMailMessage]:
        if not thread_id.strip():
            raise ValueError("thread_id is required")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailMessageRecord)
                .where(
                    MailMessageRecord.mailbox_binding_id == mailbox_binding_id,
                    MailMessageRecord.thread_id == thread_id,
                )
                .order_by(
                    MailMessageRecord.date_at.asc().nulls_last(),
                    MailMessageRecord.uid.asc(),
                )
                .limit(limit)
            )
            records = list(result.scalars().all())
        return [_stored_from_record(record) for record in records]

    async def set_unread(
        self,
        mailbox_binding_id: str,
        *,
        folder: str,
        uid: int,
        unread: bool,
    ) -> StoredMailMessage | None:
        return await self.set_flags(
            mailbox_binding_id,
            folder=folder,
            uid=uid,
            unread=unread,
        )

    async def set_flags(
        self,
        mailbox_binding_id: str,
        *,
        folder: str,
        uid: int,
        unread: bool | None = None,
        flagged: bool | None = None,
        answered: bool | None = None,
        draft: bool | None = None,
    ) -> StoredMailMessage | None:
        values: dict[str, object] = {"updated_at": datetime.now(timezone.utc)}
        if unread is not None:
            values["unread"] = unread
        if flagged is not None:
            values["flagged"] = flagged
        if answered is not None:
            values["answered"] = answered
        if draft is not None:
            values["draft"] = draft
        if len(values) == 1:
            raise ValueError("set_flags requires at least one flag field")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                update(MailMessageRecord)
                .where(
                    MailMessageRecord.mailbox_binding_id == mailbox_binding_id,
                    MailMessageRecord.folder == folder,
                    MailMessageRecord.uid == uid,
                )
                .values(**values)
                .returning(MailMessageRecord)
            )
            record = result.scalar_one_or_none()
            await session.commit()
        if record is None:
            return None
        return _stored_from_record(record)

    async def delete_by_uids(
        self,
        mailbox_binding_id: str,
        *,
        folder: str,
        uids: list[int],
    ) -> int:
        if not uids:
            return 0
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                delete(MailMessageRecord).where(
                    MailMessageRecord.mailbox_binding_id == mailbox_binding_id,
                    MailMessageRecord.folder == folder,
                    MailMessageRecord.uid.in_(uids),
                )
            )
            await session.commit()
            return get_rowcount(result)

    async def delete_folder(self, mailbox_binding_id: str, *, folder: str) -> int:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                delete(MailMessageRecord).where(
                    MailMessageRecord.mailbox_binding_id == mailbox_binding_id,
                    MailMessageRecord.folder == folder,
                )
            )
            await session.commit()
            return get_rowcount(result)

    async def list_uids(self, mailbox_binding_id: str, *, folder: str) -> list[int]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailMessageRecord.uid).where(
                    MailMessageRecord.mailbox_binding_id == mailbox_binding_id,
                    MailMessageRecord.folder == folder,
                )
            )
            return [int(uid) for uid in result.scalars().all()]

    async def list_folder_page(
        self,
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
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            stmt = select(MailMessageRecord).where(
                MailMessageRecord.mailbox_binding_id == mailbox_binding_id,
                MailMessageRecord.folder == folder,
            )
            if before_date is not None and before_uid is not None:
                stmt = stmt.where(
                    or_(
                        MailMessageRecord.date_at < before_date,
                        and_(
                            MailMessageRecord.date_at == before_date,
                            MailMessageRecord.uid < before_uid,
                        ),
                        and_(
                            MailMessageRecord.date_at.is_(None),
                            MailMessageRecord.uid < before_uid,
                        ),
                    )
                )
            stmt = (
                stmt.order_by(
                    MailMessageRecord.date_at.desc().nulls_last(),
                    MailMessageRecord.uid.desc(),
                ).limit(limit + 1)
            )
            result = await session.execute(stmt)
            records = list(result.scalars().all())
        return [_stored_from_record(record) for record in records]

    async def search_local(
        self,
        mailbox_binding_id: str,
        *,
        q: str,
        folder: str | None = None,
        limit: int,
        before_date: datetime | None = None,
        before_uid: int | None = None,
    ) -> list[StoredMailMessage]:
        if not q.strip():
            raise ValueError("q is required")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if (before_date is None) != (before_uid is None):
            raise ValueError("before_date and before_uid must be provided together")
        pattern = f"%{q.strip()}%"
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            stmt = select(MailMessageRecord).where(
                MailMessageRecord.mailbox_binding_id == mailbox_binding_id,
                or_(
                    MailMessageRecord.subject.ilike(pattern),
                    MailMessageRecord.from_address.ilike(pattern),
                    MailMessageRecord.snippet.ilike(pattern),
                    MailMessageRecord.body_text.ilike(pattern),
                    cast(MailMessageRecord.to_addresses, String).ilike(pattern),
                ),
            )
            if folder is not None:
                stmt = stmt.where(MailMessageRecord.folder == folder)
            if before_date is not None and before_uid is not None:
                stmt = stmt.where(
                    or_(
                        MailMessageRecord.date_at < before_date,
                        and_(
                            MailMessageRecord.date_at == before_date,
                            MailMessageRecord.uid < before_uid,
                        ),
                    )
                )
            stmt = (
                stmt.order_by(
                    MailMessageRecord.date_at.desc().nulls_last(),
                    MailMessageRecord.uid.desc(),
                ).limit(limit + 1)
            )
            result = await session.execute(stmt)
            records = list(result.scalars().all())
        return [_stored_from_record(record) for record in records]


def _member_from_record(record: MailboxBindingMemberRecord) -> MailboxBindingMember:
    return MailboxBindingMember(
        mailbox_binding_id=record.mailbox_binding_id,
        user_id=record.user_id,
        company_id=record.company_id,
        role=MailboxBindingMemberRole(record.role),
        created_at=record.created_at,
    )


@final
class MailboxBindingMemberRepository:
    def __init__(self, db_url: str) -> None:
        self._db_url: Final[str] = db_url

    async def list_for_binding(self, mailbox_binding_id: str) -> list[MailboxBindingMember]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailboxBindingMemberRecord)
                .where(MailboxBindingMemberRecord.mailbox_binding_id == mailbox_binding_id)
                .order_by(MailboxBindingMemberRecord.user_id.asc())
            )
            return [_member_from_record(row) for row in result.scalars().all()]

    async def list_binding_ids_for_user(
        self, company_id: str, user_id: str
    ) -> list[str]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailboxBindingMemberRecord.mailbox_binding_id).where(
                    MailboxBindingMemberRecord.company_id == company_id,
                    MailboxBindingMemberRecord.user_id == user_id,
                )
            )
            return list(result.scalars().all())

    async def is_member(self, mailbox_binding_id: str, user_id: str) -> bool:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailboxBindingMemberRecord.user_id).where(
                    MailboxBindingMemberRecord.mailbox_binding_id == mailbox_binding_id,
                    MailboxBindingMemberRecord.user_id == user_id,
                )
            )
            return result.scalar_one_or_none() is not None

    async def upsert(self, member: MailboxBindingMember) -> MailboxBindingMember:
        session_factory = await get_session_factory(self._db_url)
        values = {
            "mailbox_binding_id": member.mailbox_binding_id,
            "user_id": member.user_id,
            "company_id": member.company_id,
            "role": str(member.role),
            "created_at": member.created_at,
        }
        stmt = insert(MailboxBindingMemberRecord).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["mailbox_binding_id", "user_id"],
            set_={
                "company_id": stmt.excluded.company_id,
                "role": stmt.excluded.role,
            },
        )
        async with session_factory() as session:
            _ = await session.execute(stmt)
            await session.commit()
        members = await self.list_for_binding(member.mailbox_binding_id)
        for item in members:
            if item.user_id == member.user_id:
                return item
        raise RuntimeError(
            f"MailboxBindingMember upsert failed for {member.mailbox_binding_id}/{member.user_id}"
        )

    async def delete(self, mailbox_binding_id: str, user_id: str) -> bool:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                delete(MailboxBindingMemberRecord).where(
                    MailboxBindingMemberRecord.mailbox_binding_id == mailbox_binding_id,
                    MailboxBindingMemberRecord.user_id == user_id,
                )
            )
            await session.commit()
            return get_rowcount(result) > 0

    async def delete_all_for_binding(self, mailbox_binding_id: str) -> int:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                delete(MailboxBindingMemberRecord).where(
                    MailboxBindingMemberRecord.mailbox_binding_id == mailbox_binding_id
                )
            )
            await session.commit()
            return get_rowcount(result)


def _folder_from_record(record: MailboxFolderRecord) -> StoredMailboxFolder:
    return StoredMailboxFolder(
        mailbox_binding_id=record.mailbox_binding_id,
        folder_name=record.folder_name,
        company_id=record.company_id,
        role=MailFolderRole(record.role),
        delimiter=record.delimiter,
        flags=list(record.flags),
        selectable=bool(record.selectable),
        message_count=int(record.message_count),
        unseen_count=int(record.unseen_count),
        namespace_prefix=record.namespace_prefix,
        capabilities=list(record.capabilities),
        updated_at=record.updated_at,
    )


@final
class MailboxFolderRepository:
    """Кэш IMAP folders для local-first UI."""

    def __init__(self, db_url: str) -> None:
        self._db_url: Final[str] = db_url

    async def list_for_binding(
        self, mailbox_binding_id: str
    ) -> list[StoredMailboxFolder]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(MailboxFolderRecord)
                .where(MailboxFolderRecord.mailbox_binding_id == mailbox_binding_id)
                .order_by(MailboxFolderRecord.folder_name.asc())
            )
            records = list(result.scalars().all())
        return [_folder_from_record(record) for record in records]

    async def replace_for_binding(
        self,
        mailbox_binding_id: str,
        *,
        company_id: str,
        folders: list[StoredMailboxFolder],
    ) -> list[StoredMailboxFolder]:
        if not mailbox_binding_id.strip():
            raise ValueError("mailbox_binding_id is required")
        if not company_id.strip():
            raise ValueError("company_id is required")
        now = datetime.now(timezone.utc)
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            _ = await session.execute(
                delete(MailboxFolderRecord).where(
                    MailboxFolderRecord.mailbox_binding_id == mailbox_binding_id
                )
            )
            for folder in folders:
                session.add(
                    MailboxFolderRecord(
                        mailbox_binding_id=mailbox_binding_id,
                        folder_name=folder.folder_name,
                        company_id=company_id,
                        role=str(folder.role),
                        delimiter=folder.delimiter,
                        flags=list(folder.flags),
                        selectable=folder.selectable,
                        message_count=folder.message_count,
                        unseen_count=folder.unseen_count,
                        namespace_prefix=folder.namespace_prefix,
                        capabilities=list(folder.capabilities),
                        updated_at=now,
                    )
                )
            await session.commit()
        return await self.list_for_binding(mailbox_binding_id)
