"""Репозиторий звонков (sync_calls + sync_call_participants + sync_call_links)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import select, update

from apps.sync.db.base import BaseSyncRepository, SyncDatabase
from apps.sync.db.models import SyncCall, SyncCallLink, SyncCallParticipant


class CallRepository(BaseSyncRepository[SyncCall]):
    """CRUD для звонков и их участников."""

    def __init__(self, db: SyncDatabase) -> None:
        super().__init__(db)

    @property
    def model_class(self) -> type[SyncCall]:
        return SyncCall

    @property
    def id_field(self) -> str:
        return "call_id"

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
                raise ValueError(f"Звонок {call_id} не найден")
            return row

    async def get_active_call_for_channel(
        self, channel_id: str, company_id: str
    ) -> Optional[SyncCall]:
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
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
    ) -> None:
        values: dict = {"status": status}
        if started_at is not None:
            values["started_at"] = started_at
        if ended_at is not None:
            values["ended_at"] = ended_at
        async with self._db.session() as session:
            await session.execute(
                update(SyncCall).where(SyncCall.call_id == call_id).values(**values)
            )
            await session.commit()

    async def set_call_admin(self, call_id: str, admin_user_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(
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
        joined_at: Optional[datetime] = None,
        left_at: Optional[datetime] = None,
    ) -> None:
        values: dict = {"status": status}
        if joined_at is not None:
            values["joined_at"] = joined_at
        if left_at is not None:
            values["left_at"] = left_at
        async with self._db.session() as session:
            await session.execute(
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
            await session.execute(
                update(SyncCallLink)
                .where(SyncCallLink.link_token == link_token)
                .values(call_id=call_id)
            )
            await session.commit()
