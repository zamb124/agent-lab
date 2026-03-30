"""Репозиторий для работы с сообщениями (SQLAlchemy)."""

import json
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Type

from sqlalchemy import and_, func, or_, select, text, tuple_, update
from sqlalchemy import delete as sql_delete

from apps.sync.channel_lane_preview import ChannelLaneSummary, lane_preview_from_content_row
from apps.sync.db.base import BaseSyncRepository, SyncDatabase
from apps.sync.db.models import SyncChannelMember, SyncMessage, SyncMessageContent
from apps.sync.models.messages import MessageContentModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MessageCursorWindow:
    """Окно сообщений для курсорной пагинации."""

    rows: list[SyncMessage]
    has_more_older: bool
    has_more_newer: bool


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
        """Сообщения основной ленты канала: thread_id IS NULL, не удалённые, включая ответы (parent_message_id)."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(SyncMessage)
                .where(
                    SyncMessage.company_id == cid,
                    SyncMessage.channel_id == channel_id,
                    SyncMessage.thread_id.is_(None),
                    SyncMessage.deleted_at.is_(None),
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
                .where(
                    SyncMessage.company_id == cid,
                    SyncMessage.thread_id == thread_id,
                    SyncMessage.deleted_at.is_(None),
                )
                .order_by(SyncMessage.sent_at.asc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_by_channel_cursor(
        self,
        *,
        channel_id: str,
        limit: int,
        before_sent_at: datetime | None,
        before_message_id: str | None,
        after_sent_at: datetime | None,
        after_message_id: str | None,
        company_id: str,
    ) -> MessageCursorWindow:
        """Курсорная выборка сообщений основной ленты канала."""
        if limit < 1:
            raise ValueError("limit должен быть >= 1.")
        if before_sent_at is not None and before_message_id is None:
            raise ValueError("before_message_id обязателен при before_sent_at.")
        if before_sent_at is None and before_message_id is not None:
            raise ValueError("before_sent_at обязателен при before_message_id.")
        if after_sent_at is not None and after_message_id is None:
            raise ValueError("after_message_id обязателен при after_sent_at.")
        if after_sent_at is None and after_message_id is not None:
            raise ValueError("after_sent_at обязателен при after_message_id.")
        if before_sent_at is not None and after_sent_at is not None:
            raise ValueError("Нельзя одновременно передавать before и after.")

        async with self._db.session() as session:
            base_conditions = [
                SyncMessage.company_id == company_id,
                SyncMessage.channel_id == channel_id,
                SyncMessage.thread_id.is_(None),
                SyncMessage.deleted_at.is_(None),
            ]

            fetch_limit = limit + 1

            if before_sent_at is not None:
                stmt = (
                    select(SyncMessage)
                    .where(
                        *base_conditions,
                        tuple_(SyncMessage.sent_at, SyncMessage.message_id)
                        < tuple_(before_sent_at, before_message_id),
                    )
                    .order_by(SyncMessage.sent_at.desc(), SyncMessage.message_id.desc())
                    .limit(fetch_limit)
                )
                result = await session.execute(stmt)
                all_rows = list(result.scalars().all())
                has_more_older = len(all_rows) > limit
                rows = all_rows[:limit]
                return MessageCursorWindow(
                    rows=rows,
                    has_more_older=has_more_older,
                    has_more_newer=True,
                )

            if after_sent_at is not None:
                stmt = (
                    select(SyncMessage)
                    .where(
                        *base_conditions,
                        tuple_(SyncMessage.sent_at, SyncMessage.message_id)
                        > tuple_(after_sent_at, after_message_id),
                    )
                    .order_by(SyncMessage.sent_at.asc(), SyncMessage.message_id.asc())
                    .limit(fetch_limit)
                )
                result = await session.execute(stmt)
                all_rows = list(result.scalars().all())
                has_more_newer = len(all_rows) > limit
                asc_rows = all_rows[:limit]
                rows = list(reversed(asc_rows))
                return MessageCursorWindow(
                    rows=rows,
                    has_more_older=True,
                    has_more_newer=has_more_newer,
                )

            stmt = (
                select(SyncMessage)
                .where(*base_conditions)
                .order_by(SyncMessage.sent_at.desc(), SyncMessage.message_id.desc())
                .limit(fetch_limit)
            )
            result = await session.execute(stmt)
            all_rows = list(result.scalars().all())
            has_more_older = len(all_rows) > limit
            rows = all_rows[:limit]
            return MessageCursorWindow(
                rows=rows,
                has_more_older=has_more_older,
                has_more_newer=False,
            )

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
        forwarded_from_channel_id: Optional[str] = None,
        forwarded_from_channel_name: Optional[str] = None,
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
                reactions=[],
                deleted_at=None,
                forwarded_from_channel_id=forwarded_from_channel_id,
                forwarded_from_channel_name=forwarded_from_channel_name,
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

    async def get_by_id_for_company(
        self,
        message_id: str,
        company_id: str,
    ) -> Optional[SyncMessage]:
        async with self._db.session() as session:
            stmt = select(SyncMessage).where(
                SyncMessage.message_id == message_id,
                SyncMessage.company_id == company_id,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def replace_message_contents(
        self,
        message_id: str,
        contents: List[MessageContentModel],
        edited_at: datetime,
    ) -> None:
        async with self._db.session() as session:
            await session.execute(sql_delete(SyncMessageContent).where(SyncMessageContent.message_id == message_id))
            for content in contents:
                session.add(
                    SyncMessageContent(
                        message_id=message_id,
                        type=content.type.value,
                        order=content.order,
                        data=content.data.model_dump(),
                    )
                )
            await session.execute(
                update(SyncMessage)
                .where(SyncMessage.message_id == message_id)
                .values(edited_at=edited_at)
            )
            await session.commit()

    async def soft_delete_message(self, message_id: str, deleted_at: datetime) -> None:
        async with self._db.session() as session:
            await session.execute(
                update(SyncMessage)
                .where(SyncMessage.message_id == message_id)
                .values(deleted_at=deleted_at)
            )
            await session.commit()

    async def set_message_reactions(self, message_id: str, reactions: list) -> None:
        async with self._db.session() as session:
            await session.execute(
                update(SyncMessage)
                .where(SyncMessage.message_id == message_id)
                .values(reactions=reactions)
            )
            await session.commit()

    async def max_root_lane_sent_at(
        self,
        channel_id: str,
        *,
        company_id: str,
    ) -> Optional[datetime]:
        """Максимальное sent_at среди корневых сообщений канала (основная лента)."""
        async with self._db.session() as session:
            stmt = select(func.max(SyncMessage.sent_at)).where(
                SyncMessage.company_id == company_id,
                SyncMessage.channel_id == channel_id,
                SyncMessage.thread_id.is_(None),
                SyncMessage.deleted_at.is_(None),
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def channel_lane_summaries_batch(
        self,
        *,
        company_id: str,
        channel_ids: list[str],
        viewer_user_id: str,
    ) -> Dict[str, ChannelLaneSummary]:
        """Сводка по основной ленте для списка каналов: непрочитанные и превью последнего сообщения."""
        if not channel_ids:
            return {}
        base: Dict[str, ChannelLaneSummary] = {
            cid: ChannelLaneSummary(
                unread_count=0,
                last_message_preview=None,
                last_message_at=None,
                mention_unread_count=0,
            )
            for cid in channel_ids
        }

        async with self._db.session() as session:
            unread_stmt = (
                select(SyncMessage.channel_id, func.count().label("cnt"))
                .select_from(SyncMessage)
                .join(
                    SyncChannelMember,
                    and_(
                        SyncChannelMember.channel_id == SyncMessage.channel_id,
                        SyncChannelMember.user_id == viewer_user_id,
                        SyncChannelMember.company_id == company_id,
                    ),
                )
                .where(
                    SyncMessage.company_id == company_id,
                    SyncMessage.channel_id.in_(channel_ids),
                    SyncMessage.thread_id.is_(None),
                    SyncMessage.deleted_at.is_(None),
                    SyncMessage.sender_user_id != viewer_user_id,
                    or_(
                        SyncChannelMember.last_read_at.is_(None),
                        SyncMessage.sent_at > SyncChannelMember.last_read_at,
                    ),
                )
                .group_by(SyncMessage.channel_id)
            )
            unread_res = await session.execute(unread_stmt)
            for row in unread_res.all():
                cid = row.channel_id
                cnt = int(row.cnt)
                prev = base[cid]
                base[cid] = ChannelLaneSummary(
                    unread_count=cnt,
                    last_message_preview=prev.last_message_preview,
                    last_message_at=prev.last_message_at,
                    mention_unread_count=prev.mention_unread_count,
                )

            mention_json = json.dumps([viewer_user_id])
            mention_stmt = (
                select(SyncMessage.channel_id, func.count().label("mcnt"))
                .select_from(SyncMessage)
                .join(
                    SyncChannelMember,
                    and_(
                        SyncChannelMember.channel_id == SyncMessage.channel_id,
                        SyncChannelMember.user_id == viewer_user_id,
                        SyncChannelMember.company_id == company_id,
                    ),
                )
                .where(
                    SyncMessage.company_id == company_id,
                    SyncMessage.channel_id.in_(channel_ids),
                    SyncMessage.thread_id.is_(None),
                    SyncMessage.deleted_at.is_(None),
                    SyncMessage.sender_user_id != viewer_user_id,
                    or_(
                        SyncChannelMember.last_read_at.is_(None),
                        SyncMessage.sent_at > SyncChannelMember.last_read_at,
                    ),
                    text(
                        """
                        EXISTS (
                            SELECT 1 FROM sync_message_contents smc
                            WHERE smc.message_id = sync_messages.message_id
                            AND smc.type = 'text/plain'
                            AND smc.data->'mentions' IS NOT NULL
                            AND smc.data->'mentions' @> CAST(:mj AS jsonb)
                        )
                        """
                    ).bindparams(mj=mention_json),
                )
                .group_by(SyncMessage.channel_id)
            )
            mention_res = await session.execute(mention_stmt)
            for row in mention_res.all():
                cid = row.channel_id
                mcnt = int(row.mcnt)
                prev = base[cid]
                base[cid] = ChannelLaneSummary(
                    unread_count=prev.unread_count,
                    last_message_preview=prev.last_message_preview,
                    last_message_at=prev.last_message_at,
                    mention_unread_count=mcnt,
                )

            msg_rn = func.row_number().over(
                partition_by=SyncMessage.channel_id,
                order_by=SyncMessage.sent_at.desc(),
            ).label("msg_rn")

            msg_ranked = (
                select(
                    SyncMessage.channel_id,
                    SyncMessage.message_id,
                    SyncMessage.sent_at,
                    msg_rn,
                )
                .where(
                    SyncMessage.company_id == company_id,
                    SyncMessage.channel_id.in_(channel_ids),
                    SyncMessage.thread_id.is_(None),
                    SyncMessage.deleted_at.is_(None),
                )
                .subquery("msg_ranked")
            )

            last_msgs = (
                select(
                    msg_ranked.c.channel_id,
                    msg_ranked.c.message_id,
                    msg_ranked.c.sent_at,
                )
                .where(msg_ranked.c.msg_rn == 1)
            ).subquery("last_msgs")

            content_rn = func.row_number().over(
                partition_by=SyncMessageContent.message_id,
                order_by=(SyncMessageContent.order.asc(), SyncMessageContent.id.asc()),
            ).label("content_rn")

            content_ranked = (
                select(
                    SyncMessageContent.message_id,
                    SyncMessageContent.type,
                    SyncMessageContent.data,
                    content_rn,
                )
                .select_from(SyncMessageContent)
                .join(last_msgs, last_msgs.c.message_id == SyncMessageContent.message_id)
            ).subquery("content_ranked")

            first_blocks = (
                select(
                    content_ranked.c.message_id,
                    content_ranked.c.type,
                    content_ranked.c.data,
                )
                .where(content_ranked.c.content_rn == 1)
            ).subquery("first_blocks")

            last_stmt = (
                select(
                    last_msgs.c.channel_id,
                    last_msgs.c.sent_at,
                    first_blocks.c.type,
                    first_blocks.c.data,
                )
                .select_from(
                    last_msgs.outerjoin(first_blocks, first_blocks.c.message_id == last_msgs.c.message_id)
                )
            )
            last_res = await session.execute(last_stmt)
            for row in last_res.all():
                cid = row.channel_id
                prev = base[cid]
                preview: str | None = None
                if row.type is not None:
                    if row.data is None:
                        logger.error(
                            "Сводка ленты: тип %s без data (channel_id=%s), превью пропущено.",
                            row.type,
                            cid,
                        )
                    else:
                        preview = lane_preview_from_content_row(row.type, row.data)
                base[cid] = ChannelLaneSummary(
                    unread_count=prev.unread_count,
                    last_message_preview=preview,
                    last_message_at=row.sent_at,
                    mention_unread_count=prev.mention_unread_count,
                )

        return base
