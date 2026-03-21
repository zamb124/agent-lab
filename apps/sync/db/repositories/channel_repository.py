"""Репозиторий для работы с каналами (SQLAlchemy)."""

import logging
from datetime import datetime
from typing import List, Optional, Type

from sqlalchemy import exists, nullslast, select, update

from apps.sync.db.base import BaseSyncRepository, SyncDatabase
from apps.sync.db.models import SyncChannel, SyncChannelMember

logger = logging.getLogger(__name__)


class ChannelRepository(BaseSyncRepository[SyncChannel]):
    """Репозиторий для каналов с изоляцией по company_id."""

    def __init__(self, db: SyncDatabase):
        super().__init__(db=db)

    @property
    def model_class(self) -> Type[SyncChannel]:
        return SyncChannel

    @property
    def id_field(self) -> str:
        return "channel_id"

    async def list_by_space(
        self,
        space_id: str,
        limit: int = 100,
        offset: int = 0,
        company_id: Optional[str] = None,
    ) -> List[SyncChannel]:
        """Каналы в пространстве."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(SyncChannel)
                .where(SyncChannel.company_id == cid, SyncChannel.space_id == space_id)
                .order_by(SyncChannel.name.asc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_for_user(
        self,
        user_id: str,
        *,
        space_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        company_id: Optional[str] = None,
    ) -> List[SyncChannel]:
        """Каналы, в которых состоит пользователь."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(SyncChannel)
                .join(
                    SyncChannelMember,
                    SyncChannelMember.channel_id == SyncChannel.channel_id,
                )
                .where(
                    SyncChannel.company_id == cid,
                    SyncChannelMember.company_id == cid,
                    SyncChannelMember.user_id == user_id,
                )
            )
            if space_id is not None:
                stmt = stmt.where(SyncChannel.space_id == space_id)
            stmt = (
                stmt.order_by(
                    SyncChannel.type.asc(),
                    nullslast(SyncChannel.name.asc()),
                )
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_member_user_ids(
        self,
        channel_id: str,
        company_id: Optional[str] = None,
    ) -> List[str]:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(SyncChannelMember.user_id).where(
                SyncChannelMember.channel_id == channel_id,
                SyncChannelMember.company_id == cid,
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def is_member(
        self,
        channel_id: str,
        user_id: str,
        company_id: Optional[str] = None,
    ) -> bool:
        """Проверяет членство пользователя в канале (в рамках компании)."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(
                exists().where(
                    SyncChannelMember.channel_id == channel_id,
                    SyncChannelMember.user_id == user_id,
                    SyncChannelMember.company_id == cid,
                )
            )
            result = await session.execute(stmt)
            return result.scalar() or False

    async def upsert_member(self, channel_id: str, user_id: str, role: str, company_id: Optional[str] = None) -> None:
        """Добавляет или обновляет роль участника канала."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            existing = await session.get(SyncChannelMember, (channel_id, user_id))
            if existing:
                existing.role = role
            else:
                member = SyncChannelMember(
                    channel_id=channel_id,
                    user_id=user_id,
                    company_id=cid,
                    role=role,
                )
                session.add(member)
            await session.commit()

    async def add_member_if_missing(self, channel_id: str, user_id: str, role: str, company_id: Optional[str] = None) -> None:
        """Добавляет участника, если его ещё нет."""
        cid = company_id or self._get_company_id()
        is_already = await self.is_member(channel_id, user_id, company_id=cid)
        if not is_already:
            await self.upsert_member(channel_id, user_id, role, company_id=cid)

    async def get_member_role(self, channel_id: str, user_id: str) -> Optional[str]:
        async with self._db.session() as session:
            row = await session.get(SyncChannelMember, (channel_id, user_id))
            if row is None:
                return None
            return row.role

    async def list_member_rows(
        self,
        channel_id: str,
        *,
        company_id: Optional[str] = None,
    ) -> List[tuple[str, str]]:
        """Список (user_id, role) участников канала в компании."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(SyncChannelMember.user_id, SyncChannelMember.role)
                .where(
                    SyncChannelMember.channel_id == channel_id,
                    SyncChannelMember.company_id == cid,
                )
                .order_by(SyncChannelMember.user_id.asc())
            )
            result = await session.execute(stmt)
            return [(r[0], r[1]) for r in result.all()]

    async def set_member_last_read_at(
        self,
        channel_id: str,
        user_id: str,
        at: datetime,
        company_id: Optional[str] = None,
    ) -> None:
        """Курсор прочитанного в основной ленте для участника канала."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            row = await session.get(SyncChannelMember, (channel_id, user_id))
            if row is None:
                raise ValueError(
                    f"Участник канала не найден: channel_id={channel_id}, user_id={user_id}."
                )
            if row.company_id != cid:
                raise ValueError(
                    f"Запись участника принадлежит другой компании: channel_id={channel_id}."
                )
            row.last_read_at = at
            await session.commit()

    async def set_pinned_message_ids(
        self,
        channel_id: str,
        message_ids: list[str],
        company_id: Optional[str] = None,
    ) -> None:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            await session.execute(
                update(SyncChannel)
                .where(
                    SyncChannel.channel_id == channel_id,
                    SyncChannel.company_id == cid,
                )
                .values(pinned_message_ids=message_ids)
            )
            await session.commit()
