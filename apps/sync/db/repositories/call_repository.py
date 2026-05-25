"""Репозиторий звонков (sync_calls + sync_call_participants + sync_call_links)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import override

from sqlalchemy import select, update
from sqlalchemy.orm.attributes import InstrumentedAttribute

from apps.sync.db.base import BaseSyncRepository, SyncDatabase
from apps.sync.db.models import (
    SyncCall,
    SyncCallLink,
    SyncCallParticipant,
    SyncChannelMember,
)


class CallNotFoundError(ValueError):
    """Звонок отсутствует или принадлежит другой компании."""

    pass


class CallRepository(BaseSyncRepository[SyncCall]):
    """CRUD для звонков и их участников."""

    def __init__(self, db: SyncDatabase) -> None:
        super().__init__(db)

    @property
    @override
    def model_class(self) -> type[SyncCall]:
        return SyncCall

    @property
    @override
    def id_column(self) -> InstrumentedAttribute[str]:
        return SyncCall.call_id

    @property
    @override
    def company_id_column(self) -> InstrumentedAttribute[str]:
        return SyncCall.company_id

    async def create_call(self, call: SyncCall) -> SyncCall:
        async with self._db.session() as session:
            session.add(call)
            await session.commit()
            await session.refresh(call)
            return call

    async def get_call(self, call_id: str, company_id: str) -> SyncCall:
        async with self._db.session() as session:
            row = await session.get(SyncCall, call_id)
            if row is None or row.company_id != company_id:
                raise CallNotFoundError(f"Звонок {call_id} не найден")
            return row

    async def get_active_call_for_channel(
        self, channel_id: str, company_id: str
    ) -> SyncCall | None:
        """Возвращает активный звонок в канале (status ringing/active) или None."""
        async with self._db.session() as session:
            stmt = (
                select(SyncCall)
                .where(
                    SyncCall.channel_id == channel_id,
                    SyncCall.company_id == company_id,
                    SyncCall.status.in_(["ringing", "active"]),
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update_call_status(
        self,
        call_id: str,
        status: str,
        *,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        values: dict[str, object] = {"status": status}
        if started_at is not None:
            values["started_at"] = started_at
        if ended_at is not None:
            values["ended_at"] = ended_at
        async with self._db.session() as session:
            _ = await session.execute(
                update(SyncCall).where(SyncCall.call_id == call_id).values(**values)
            )
            await session.commit()

    async def set_call_admin(self, call_id: str, admin_user_id: str) -> None:
        async with self._db.session() as session:
            _ = await session.execute(
                update(SyncCall)
                .where(SyncCall.call_id == call_id)
                .values(created_by_user_id=admin_user_id)
            )
            await session.commit()

    async def add_participant(self, participant: SyncCallParticipant) -> SyncCallParticipant:
        async with self._db.session() as session:
            session.add(participant)
            await session.commit()
            await session.refresh(participant)
            return participant

    async def update_participant_status(
        self,
        call_id: str,
        user_id: str,
        status: str,
        *,
        joined_at: datetime | None = None,
        left_at: datetime | None = None,
    ) -> None:
        values: dict[str, object] = {"status": status}
        if joined_at is not None:
            values["joined_at"] = joined_at
        if left_at is not None:
            values["left_at"] = left_at
        async with self._db.session() as session:
            _ = await session.execute(
                update(SyncCallParticipant)
                .where(
                    SyncCallParticipant.call_id == call_id,
                    SyncCallParticipant.user_id == user_id,
                )
                .values(**values)
            )
            await session.commit()

    async def list_participants(self, call_id: str) -> list[SyncCallParticipant]:
        async with self._db.session() as session:
            stmt = select(SyncCallParticipant).where(SyncCallParticipant.call_id == call_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_active_participants(self, call_id: str) -> int:
        """Число участников со статусом joined."""
        participants = await self.list_participants(call_id)
        return sum(1 for p in participants if p.status == "joined")

    # --- Гостевые ссылки ---

    async def create_link(self, link: SyncCallLink) -> SyncCallLink:
        async with self._db.session() as session:
            session.add(link)
            await session.commit()
            await session.refresh(link)
            return link

    async def get_link(self, link_token: str) -> SyncCallLink:
        """Возвращает ссылку. Поднимает ValueError если не найдена или истекла."""
        async with self._db.session() as session:
            row = await session.get(SyncCallLink, link_token)
            if row is None:
                raise ValueError(f"Ссылка {link_token} не найдена.")
            if row.expires_at < datetime.now(UTC):
                raise ValueError("Ссылка истекла.")
            return row

    async def attach_call_to_link(self, link_token: str, call_id: str) -> None:
        """Привязывает созданный звонок к ссылке (при первом входе)."""
        async with self._db.session() as session:
            _ = await session.execute(
                update(SyncCallLink)
                .where(SyncCallLink.link_token == link_token)
                .values(call_id=call_id)
            )
            await session.commit()

    async def get_link_for_company(self, link_token: str, company_id: str) -> SyncCallLink:
        async with self._db.session() as session:
            row = await session.get(SyncCallLink, link_token)
            if row is None or row.company_id != company_id:
                raise ValueError(f"Ссылка {link_token} не найдена.")
            return row

    async def get_link_by_calendar_event(
        self, company_id: str, calendar_event_id: str
    ) -> SyncCallLink | None:
        async with self._db.session() as session:
            stmt = (
                select(SyncCallLink)
                .where(
                    SyncCallLink.company_id == company_id,
                    SyncCallLink.calendar_event_id == calendar_event_id,
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_persistent_channel_link(
        self, company_id: str, channel_id: str
    ) -> SyncCallLink | None:
        async with self._db.session() as session:
            stmt = (
                select(SyncCallLink)
                .where(
                    SyncCallLink.company_id == company_id,
                    SyncCallLink.channel_id == channel_id,
                    SyncCallLink.is_persistent_channel_link.is_(True),
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update_link_expires_at(self, link_token: str, expires_at: datetime) -> None:
        async with self._db.session() as session:
            _ = await session.execute(
                update(SyncCallLink)
                .where(SyncCallLink.link_token == link_token)
                .values(expires_at=expires_at)
            )
            await session.commit()

    async def update_calendar_link(
        self,
        link_token: str,
        company_id: str,
        *,
        title: str | None = None,
        scheduled_start_at: datetime | None = None,
        scheduled_end_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        row = await self.get_link_for_company(link_token, company_id)
        if row.calendar_event_id is None:
            raise ValueError("Ссылка не привязана к событию календаря.")
        values: dict[str, object] = {}
        if title is not None:
            values["title"] = title
        if scheduled_start_at is not None:
            values["scheduled_start_at"] = scheduled_start_at
        if scheduled_end_at is not None:
            values["scheduled_end_at"] = scheduled_end_at
        if expires_at is not None:
            values["expires_at"] = expires_at
        if not values:
            return
        async with self._db.session() as session:
            _ = await session.execute(
                update(SyncCallLink)
                .where(
                    SyncCallLink.link_token == link_token,
                    SyncCallLink.company_id == company_id,
                )
                .values(**values)
            )
            await session.commit()

    async def delete_link(self, link_token: str, company_id: str) -> bool:
        async with self._db.session() as session:
            row = await session.get(SyncCallLink, link_token)
            if row is None or row.company_id != company_id:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def list_scheduled_calendar_links_for_user(
        self,
        company_id: str,
        user_id: str,
        *,
        range_start: datetime,
        range_end: datetime,
        channel_id: str | None = None,
    ) -> list[SyncCallLink]:
        async with self._db.session() as session:
            stmt = (
                select(SyncCallLink)
                .join(
                    SyncChannelMember,
                    SyncChannelMember.channel_id == SyncCallLink.channel_id,
                )
                .where(
                    SyncCallLink.company_id == company_id,
                    SyncChannelMember.company_id == company_id,
                    SyncChannelMember.user_id == user_id,
                    SyncCallLink.calendar_event_id.is_not(None),
                    SyncCallLink.scheduled_start_at.is_not(None),
                    SyncCallLink.scheduled_end_at.is_not(None),
                    SyncCallLink.scheduled_start_at < range_end,
                    SyncCallLink.scheduled_end_at > range_start,
                )
            )
            if channel_id is not None:
                stmt = stmt.where(SyncCallLink.channel_id == channel_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_scheduled_calendar_links_in_range(
        self,
        company_id: str,
        range_start: datetime,
        range_end: datetime,
    ) -> list[SyncCallLink]:
        """Для агрегата календаря platform: все запланированные ссылки компании в окне."""
        async with self._db.session() as session:
            stmt = select(SyncCallLink).where(
                SyncCallLink.company_id == company_id,
                SyncCallLink.calendar_event_id.is_not(None),
                SyncCallLink.scheduled_start_at.is_not(None),
                SyncCallLink.scheduled_end_at.is_not(None),
                SyncCallLink.scheduled_start_at < range_end,
                SyncCallLink.scheduled_end_at > range_start,
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
