"""SQL-репозитории почты (shared БД)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Final, final

from sqlalchemy import and_, delete, nulls_first, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from core.db.database import get_session_factory
from core.db.models.platform import (
    CompanyMailConnectionRecord,
    MailboxBindingRecord,
    MailboxSyncCursorRecord,
)
from core.db.utils import get_rowcount
from core.mail.models import (
    CompanyMailConnection,
    IspmanagerProvisionConfig,
    MailboxBinding,
    MailboxBindingKind,
    MailboxSyncCursor,
    MailConnectionStatus,
    MailProvider,
    MailSyncErrorKind,
)

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
                    MailboxBindingRecord.kind == str(MailboxBindingKind.USER),
                    MailboxBindingRecord.sync_enabled.is_(True),
                    MailboxBindingRecord.user_id.is_not(None),
                    CompanyMailConnectionRecord.status
                    == str(MailConnectionStatus.ACTIVE),
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
