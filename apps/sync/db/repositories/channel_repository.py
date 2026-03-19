"""Репозиторий для работы с каналами (SQLAlchemy)."""

import logging
from typing import List, Optional, Type

from sqlalchemy import select, exists

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

    async def is_member(self, channel_id: str, user_id: str) -> bool:
        """Проверяет членство пользователя в канале."""
        async with self._db.session() as session:
            stmt = select(
                exists().where(
                    SyncChannelMember.channel_id == channel_id,
                    SyncChannelMember.user_id == user_id,
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
        is_already = await self.is_member(channel_id, user_id)
        if not is_already:
            await self.upsert_member(channel_id, user_id, role, cid)
