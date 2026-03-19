"""Репозиторий для работы с сообщениями (SQLAlchemy)."""

import logging
from datetime import datetime
from typing import List, Optional, Type

from sqlalchemy import select, text

from apps.sync.db.base import BaseSyncRepository, SyncDatabase
from apps.sync.db.models import SyncMessage, SyncMessageContent
from apps.sync.models.messages import MessageContentModel

logger = logging.getLogger(__name__)


class MessageRepository(BaseSyncRepository[SyncMessage]):
    """Репозиторий для сообщений с изоляцией по company_id."""

    def __init__(self, db: SyncDatabase):
        super().__init__(db=db)

    @property
    def model_class(self) -> Type[SyncMessage]:
        return SyncMessage

    @property
    def id_field(self) -> str:
        return "message_id"

    async def list_by_channel(
        self,
        channel_id: str,
        limit: int = 50,
        offset: int = 0,
        company_id: Optional[str] = None,
    ) -> List[SyncMessage]:
        """Корневые сообщения канала (без parent_message_id)."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(SyncMessage)
                .where(
                    SyncMessage.company_id == cid,
                    SyncMessage.channel_id == channel_id,
                    SyncMessage.parent_message_id.is_(None),
                )
                .order_by(SyncMessage.sent_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_by_thread(
        self,
        thread_id: str,
        limit: int = 50,
        offset: int = 0,
        company_id: Optional[str] = None,
    ) -> List[SyncMessage]:
        """Сообщения в треде."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(SyncMessage)
                .where(SyncMessage.company_id == cid, SyncMessage.thread_id == thread_id)
                .order_by(SyncMessage.sent_at.asc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_thread_root(self, message_id: str) -> Optional[SyncMessage]:
        """Находит корневое сообщение треда через рекурсивный CTE."""
        async with self._db.session() as session:
            cte_query = text("""
                WITH RECURSIVE thread_path AS (
                    SELECT message_id, parent_message_id
                    FROM sync_messages
                    WHERE message_id = :msg_id
                    UNION ALL
                    SELECT m.message_id, m.parent_message_id
                    FROM sync_messages m
                    JOIN thread_path tp ON m.message_id = tp.parent_message_id
                )
                SELECT tp.message_id
                FROM thread_path tp
                WHERE tp.parent_message_id IS NULL
                LIMIT 1
            """)
            result = await session.execute(cte_query, {"msg_id": message_id})
            root_id = result.scalar_one_or_none()
            if root_id is None:
                return None
            return await self.get(root_id)

    async def list_contents(self, message_id: str) -> List[SyncMessageContent]:
        """Контент-блоки сообщения."""
        async with self._db.session() as session:
            stmt = (
                select(SyncMessageContent)
                .where(SyncMessageContent.message_id == message_id)
                .order_by(SyncMessageContent.order.asc(), SyncMessageContent.id.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def create_message(
        self,
        *,
        message_id: str,
        company_id: str,
        channel_id: str,
        thread_id: Optional[str],
        parent_message_id: Optional[str],
        sender_user_id: str,
        status: str,
        sent_at: datetime,
        contents: List[MessageContentModel],
    ) -> SyncMessage:
        """Создаёт сообщение с контент-блоками в одной транзакции."""
        async with self._db.session() as session:
            message = SyncMessage(
                message_id=message_id,
                company_id=company_id,
                channel_id=channel_id,
                thread_id=thread_id,
                parent_message_id=parent_message_id,
                sender_user_id=sender_user_id,
                status=status,
                sent_at=sent_at,
            )
            session.add(message)

            for content in contents:
                content_row = SyncMessageContent(
                    message_id=message_id,
                    type=content.type.value,
                    order=content.order,
                    data=content.data.model_dump(),
                )
                session.add(content_row)

            await session.commit()
            await session.refresh(message)
            return message
