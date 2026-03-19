"""Репозиторий для работы с тредами (SQLAlchemy)."""

import logging
from typing import List, Optional, Type

from sqlalchemy import select

from apps.sync.db.base import BaseSyncRepository, SyncDatabase
from apps.sync.db.models import SyncThread

logger = logging.getLogger(__name__)


class ThreadRepository(BaseSyncRepository[SyncThread]):
    """Репозиторий для тредов с изоляцией по company_id."""

    def __init__(self, db: SyncDatabase):
        super().__init__(db=db)

    @property
    def model_class(self) -> Type[SyncThread]:
        return SyncThread

    @property
    def id_field(self) -> str:
        return "thread_id"

    async def list_by_channel(
        self,
        channel_id: str,
        limit: int = 100,
        offset: int = 0,
        company_id: Optional[str] = None,
    ) -> List[SyncThread]:
        """Треды в канале."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(SyncThread)
                .where(SyncThread.company_id == cid, SyncThread.channel_id == channel_id)
                .order_by(SyncThread.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
