"""Сообщение Sync, блоки контента и связь с файлом."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from json import dumps
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, atomic, execute_raw
from oxyde.queries.select import Query

from apps.sync.models.lane_preview import ChannelLaneSummary, lane_preview_from_content
from apps.sync.models.messages import MessageContentModel, ReactionEntry
from core.models.platform_model import PlatformModel
from core.types import JsonObject, parse_json_object, require_json_object


class SyncMessage(PlatformModel):
    """Строка ``sync_messages``, алиас ``sync``, ``__global_model__``.

    Первичный ключ ``message_id``. Ответ API — ``MessageRead``: там отправитель,
    блоки контента и упоминания. ``reactions`` — JSON этой строки.
    В ``0001`` внешние ключи ``channel_id`` и ``thread_id`` и ``parent_message_id``
    и ``call_id`` остаются.
    """

    __database_alias__: ClassVar[str | None] = "sync"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "sync_messages"
        indexes: list[Index] = [
            Index(["company_id"]),
            Index(["channel_id"]),
            Index(["thread_id"]),
            Index(["sent_at"]),
            Index(["call_id"]),
            Index(["channel_id", "call_id"]),
        ]

    message_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    channel_id: str = DbField(max_length=64)
    sender_user_id: str = DbField(max_length=200)
    status: str = DbField(max_length=32)
    sent_at: datetime
    thread_id: str | None = DbField(default=None, max_length=64)
    parent_message_id: str | None = DbField(default=None, max_length=64)
    call_id: str | None = DbField(default=None, max_length=64)
    edited_at: datetime | None = DbField(default=None)
    reactions: list[JsonObject] = DbField(default_factory=list, db_type="JSONB")
    deleted_at: datetime | None = DbField(default=None)
    forwarded_from_channel_id: str | None = DbField(default=None, max_length=64)
    forwarded_from_channel_name: str | None = DbField(default=None, max_length=255)

    @classmethod
    async def find_in_company(
        cls, company_id: str, message_id: str
    ) -> SyncMessage | None:
        if company_id == "":
            raise ValueError("company_id cannot be empty.")
        if message_id == "":
            raise ValueError("message_id cannot be empty.")
        return await cls.objects.filter(
            message_id=message_id, company_id=company_id
        ).get_or_none()

    @classmethod
    async def list_root_lane(
        cls,
        channel_id: str,
        *,
        company_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id,
            channel_id=channel_id,
            thread_id=None,
            deleted_at=None,
        ).order_by("-sent_at").limit(limit).offset(offset).all()

    @classmethod
    async def list_root_lane_by_call(
        cls,
        *,
        channel_id: str,
        call_id: str,
        company_id: str,
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id,
            channel_id=channel_id,
            call_id=call_id,
            thread_id=None,
            deleted_at=None,
        ).order_by("sent_at", "message_id").all()

    @classmethod
    async def list_by_thread(
        cls,
        thread_id: str,
        *,
        company_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id,
            thread_id=thread_id,
            deleted_at=None,
        ).order_by("sent_at").limit(limit).offset(offset).all()

    @classmethod
    async def list_root_lane_cursor(
        cls,
        *,
        channel_id: str,
        limit: int,
        before_sent_at: datetime | None,
        before_message_id: str | None,
        after_sent_at: datetime | None,
        after_message_id: str | None,
        company_id: str,
    ) -> MessageCursorWindow[Self]:
        if limit < 1:
            raise ValueError("limit must be >= 1.")
        if before_sent_at is not None and before_message_id is None:
            raise ValueError("before_message_id is required when before_sent_at is set.")
        if before_sent_at is None and before_message_id is not None:
            raise ValueError("before_sent_at is required when before_message_id is set.")
        if after_sent_at is not None and after_message_id is None:
            raise ValueError("after_message_id is required when after_sent_at is set.")
        if after_sent_at is None and after_message_id is not None:
            raise ValueError("after_sent_at is required when after_message_id is set.")
        if before_sent_at is not None and after_sent_at is not None:
            raise ValueError("Cannot pass before and after at the same time.")
        query = cls.objects.filter(
            company_id=company_id,
            channel_id=channel_id,
            thread_id=None,
            deleted_at=None,
        )
        fetch_limit = limit + 1
        if before_sent_at is not None:
            if before_message_id is None:
                raise ValueError("before_message_id is required when before_sent_at is set.")
            older = await _root_lane_before(
                query,
                before_sent_at=before_sent_at,
                before_message_id=before_message_id,
                fetch_limit=fetch_limit,
            )
            has_more_older = len(older) > limit
            return MessageCursorWindow(
                rows=older[:limit],
                has_more_older=has_more_older,
                has_more_newer=True,
            )
        if after_sent_at is not None:
            if after_message_id is None:
                raise ValueError("after_message_id is required when after_sent_at is set.")
            newer = await _root_lane_after(
                query,
                after_sent_at=after_sent_at,
                after_message_id=after_message_id,
                fetch_limit=fetch_limit,
            )
            has_more_newer = len(newer) > limit
            page = newer[:limit]
            page.reverse()
            return MessageCursorWindow(
                rows=page,
                has_more_older=True,
                has_more_newer=has_more_newer,
            )
        latest = await query.order_by("-sent_at", "-message_id").limit(fetch_limit).all()
        has_more_older = len(latest) > limit
        return MessageCursorWindow(
            rows=latest[:limit],
            has_more_older=has_more_older,
            has_more_newer=False,
        )

    @classmethod
    async def thread_root(cls, message_id: str) -> SyncMessage | None:
        fetched = await execute_raw(
            """WITH RECURSIVE thread_path AS (
                SELECT message_id, parent_message_id FROM sync_messages WHERE message_id = $1
                UNION ALL
                SELECT m.message_id, m.parent_message_id FROM sync_messages m
                JOIN thread_path tp ON m.message_id = tp.parent_message_id
            ) SELECT message_id FROM thread_path WHERE parent_message_id IS NULL LIMIT 1""",
            [message_id],
            using="sync",
        )
        if len(fetched) == 0:
            return None
        parsed = require_json_object(fetched[0], "sync message thread root")
        root_id = parsed.get("message_id")
        if not isinstance(root_id, str) or root_id == "":
            raise ValueError("thread root query returned non-string message_id.")
        return await cls.objects.filter(message_id=root_id).get_or_none()

    @classmethod
    async def create_with_contents(
        cls,
        *,
        message_id: str,
        company_id: str,
        channel_id: str,
        thread_id: str | None,
        parent_message_id: str | None,
        call_id: str | None = None,
        sender_user_id: str,
        status: str,
        sent_at: datetime,
        contents: list[MessageContentModel],
        forwarded_from_channel_id: str | None = None,
        forwarded_from_channel_name: str | None = None,
    ) -> SyncMessage:
        message = cls(
            message_id=message_id,
            company_id=company_id,
            channel_id=channel_id,
            thread_id=thread_id,
            parent_message_id=parent_message_id,
            call_id=call_id,
            sender_user_id=sender_user_id,
            status=status,
            sent_at=sent_at,
            forwarded_from_channel_id=forwarded_from_channel_id,
            forwarded_from_channel_name=forwarded_from_channel_name,
        )
        async with atomic(using="sync"):
            created = await cls.objects.create(instance=message)
            for block in contents:
                _ = await SyncMessageContent.objects.create(
                    instance=SyncMessageContent(
                        message_id=message_id,
                        type=block.type.value,
                        order_index=block.order,
                        data=_content_data(block),
                    )
                )
        return created

    @classmethod
    async def replace_contents(
        cls,
        message_id: str,
        contents: list[MessageContentModel],
        edited_at: datetime,
    ) -> None:
        async with atomic(using="sync"):
            _ = await SyncMessageContent.objects.filter(message_id=message_id).delete()
            for block in contents:
                _ = await SyncMessageContent.objects.create(
                    instance=SyncMessageContent(
                        message_id=message_id,
                        type=block.type.value,
                        order_index=block.order,
                        data=_content_data(block),
                    )
                )
            _ = await cls.objects.filter(message_id=message_id).update(
                using="sync", edited_at=edited_at
            )

    @classmethod
    async def soft_delete(cls, message_id: str, deleted_at: datetime) -> None:
        _ = await cls.objects.filter(message_id=message_id).update(
            using="sync", deleted_at=deleted_at
        )

    @classmethod
    async def set_reactions(cls, message_id: str, reactions: list[ReactionEntry]) -> None:
        payload = [
            parse_json_object(reaction.model_dump_json(), "ReactionEntry")
            for reaction in reactions
        ]
        _ = await cls.objects.filter(message_id=message_id).update(
            using="sync", reactions=payload
        )

    @classmethod
    async def max_root_lane_sent_at(
        cls, channel_id: str, *, company_id: str
    ) -> datetime | None:
        fetched = await execute_raw(
            """SELECT max(sent_at) AS sent_at FROM sync_messages
            WHERE company_id = $1 AND channel_id = $2
            AND thread_id IS NULL AND deleted_at IS NULL""",
            [company_id, channel_id],
            using="sync",
        )
        if len(fetched) != 1:
            raise ValueError("sync message max sent_at returned an unexpected row count")
        parsed = require_json_object(fetched[0], "sync message max sent_at")
        raw_sent_at = parsed.get("sent_at")
        if raw_sent_at is None:
            return None
        return _datetime_cell(raw_sent_at, "sync message max sent_at")

    @classmethod
    async def channel_lane_summaries(
        cls,
        *,
        company_id: str,
        channel_ids: list[str],
        viewer_user_id: str,
    ) -> dict[str, ChannelLaneSummary]:
        if len(channel_ids) == 0:
            return {}
        id_sql = ", ".join(
            f"${index}" for index in range(3, 3 + len(channel_ids))
        )
        mention_param = 3 + len(channel_ids)
        last_id_sql = ", ".join(
            f"${index}" for index in range(2, 2 + len(channel_ids))
        )
        base = {
            channel_id: ChannelLaneSummary(
                unread_count=0,
                last_message_preview=None,
                last_message_at=None,
                mention_unread_count=0,
            )
            for channel_id in channel_ids
        }
        unread_rows = await execute_raw(
            """SELECT m.channel_id, count(*)::int AS unread_count
            FROM sync_messages m
            JOIN sync_channel_members mem
            ON mem.channel_id = m.channel_id AND mem.user_id = $2 AND mem.company_id = $1
            WHERE m.company_id = $1 AND m.channel_id IN ("""
            + id_sql
            + """)
            AND m.thread_id IS NULL AND m.deleted_at IS NULL
            AND m.sender_user_id <> $2
            AND (mem.last_read_at IS NULL OR m.sent_at > mem.last_read_at)
            GROUP BY m.channel_id""",
            [company_id, viewer_user_id, *channel_ids],
            using="sync",
        )
        for row in unread_rows:
            parsed = require_json_object(row, "sync unread count")
            channel_id = _str_cell(parsed.get("channel_id"), "sync unread channel_id")
            count = _int_cell(parsed.get("unread_count"), "sync unread count")
            prev = base[channel_id]
            base[channel_id] = ChannelLaneSummary(
                unread_count=count,
                last_message_preview=prev.last_message_preview,
                last_message_at=prev.last_message_at,
                mention_unread_count=prev.mention_unread_count,
            )
        mention_rows = await execute_raw(
            """SELECT m.channel_id, count(*)::int AS mention_unread_count
            FROM sync_messages m
            JOIN sync_channel_members mem
            ON mem.channel_id = m.channel_id AND mem.user_id = $2 AND mem.company_id = $1
            WHERE m.company_id = $1 AND m.channel_id IN ("""
            + id_sql
            + """)
            AND m.thread_id IS NULL AND m.deleted_at IS NULL
            AND m.sender_user_id <> $2
            AND (mem.last_read_at IS NULL OR m.sent_at > mem.last_read_at)
            AND EXISTS (
            SELECT 1 FROM sync_message_contents smc
            WHERE smc.message_id = m.message_id AND smc.type = 'text/plain'
            AND smc.data->'mentions' IS NOT NULL
            AND smc.data->'mentions' @> $"""
            + str(mention_param)
            + """::jsonb
            ) GROUP BY m.channel_id""",
            [company_id, viewer_user_id, *channel_ids, dumps([viewer_user_id])],
            using="sync",
        )
        for row in mention_rows:
            parsed = require_json_object(row, "sync mention unread")
            channel_id = _str_cell(parsed.get("channel_id"), "sync mention channel_id")
            count = _int_cell(parsed.get("mention_unread_count"), "sync mention unread")
            prev = base[channel_id]
            base[channel_id] = ChannelLaneSummary(
                unread_count=prev.unread_count,
                last_message_preview=prev.last_message_preview,
                last_message_at=prev.last_message_at,
                mention_unread_count=count,
            )
        last_rows = await execute_raw(
            """SELECT DISTINCT ON (m.channel_id) m.channel_id, m.message_id, m.sent_at
            FROM sync_messages m
            WHERE m.company_id = $1 AND m.channel_id IN ("""
            + last_id_sql
            + """)
            AND m.thread_id IS NULL AND m.deleted_at IS NULL
            ORDER BY m.channel_id, m.sent_at DESC""",
            [company_id, *channel_ids],
            using="sync",
        )
        for row in last_rows:
            parsed = require_json_object(row, "sync last message")
            channel_id = _str_cell(parsed.get("channel_id"), "sync last channel_id")
            message_id = _str_cell(parsed.get("message_id"), "sync last message_id")
            sent_at = _datetime_cell(parsed.get("sent_at"), "sync last sent_at")
            blocks = await SyncMessageContent.list_for_message(message_id)
            preview = lane_preview_from_content(blocks[0]) if len(blocks) > 0 else None
            prev = base[channel_id]
            base[channel_id] = ChannelLaneSummary(
                unread_count=prev.unread_count,
                last_message_preview=preview,
                last_message_at=sent_at,
                mention_unread_count=prev.mention_unread_count,
            )
        return base


class SyncMessageContent(PlatformModel):
    """Строка ``sync_message_contents``, алиас ``sync``, ``__global_model__``.

    Первичный ключ в базе — ``id`` (BIGSERIAL). Поле модели — ``content_id``.
    Колонка порядка — ``order``, поле модели — ``order_index``.
    Ответ API — ``MessageContentModel``, не эта строка.
    """

    __database_alias__: ClassVar[str | None] = "sync"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "sync_message_contents"
        indexes: list[Index] = [
            Index(["message_id"]),
        ]

    message_id: str = DbField(max_length=64)
    type: str = DbField(max_length=64)
    order_index: int = DbField(db_column="order", db_type="INTEGER")
    data: JsonObject = DbField(db_type="JSONB")
    content_id: int | None = DbField(default=None, db_pk=True, db_column="id")

    @classmethod
    async def list_for_message(cls, message_id: str) -> list[MessageContentModel]:
        rows = await cls.objects.filter(message_id=message_id).order_by(
            "order_index", "content_id"
        ).all()
        return [_content_model(row) for row in rows]


class SyncMessageFile(PlatformModel):
    """Строка ``sync_message_files``, алиас ``sync``, ``__global_model__``.

    В базе ключ — пара ``(message_id, file_id)``. Oxyde помечает ``db_pk`` только
    ``message_id``. ``save`` и PK-CRUD ``get``/``set``/``delete_by_id`` для неё не вызываются.
    В ``0001`` ключ остаётся составным, оба внешних ключа ON DELETE CASCADE.
    """

    __database_alias__: ClassVar[str | None] = "sync"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "sync_message_files"
        unique_together: list[tuple[str, str]] = [("message_id", "file_id")]

    message_id: str = DbField(db_pk=True, max_length=64)
    file_id: str = DbField(max_length=64)
    role: str = DbField(max_length=32)


@dataclass(frozen=True)
class MessageCursorWindow[T]:
    """Окно сообщений основной ленты."""

    rows: list[T]
    has_more_older: bool
    has_more_newer: bool


def _content_data(block: MessageContentModel) -> JsonObject:
    return require_json_object(block.data.model_dump(mode="json"), "message content")


def _content_model(row: SyncMessageContent) -> MessageContentModel:
    raw_data = row.data
    if isinstance(raw_data, str):
        data = parse_json_object(raw_data, "message content")
    else:
        data = require_json_object(raw_data, "message content")
    return MessageContentModel.model_validate(
        {"type": row.type, "data": data, "order": row.order_index}
    )


def _str_cell(value: object, label: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ValueError(label)
    return value


async def _root_lane_before[TMessage: SyncMessage](
    query: Query[TMessage],
    *,
    before_sent_at: datetime,
    before_message_id: str,
    fetch_limit: int,
) -> list[TMessage]:
    same_sent_at = await query.filter(sent_at=before_sent_at).order_by("-message_id").all()
    tied = [row for row in same_sent_at if row.message_id < before_message_id]
    if len(tied) >= fetch_limit:
        return tied[:fetch_limit]
    older_sent_at = await query.filter(sent_at__lt=before_sent_at).order_by(
        "-sent_at", "-message_id"
    ).limit(fetch_limit - len(tied)).all()
    return [*tied, *older_sent_at]


async def _root_lane_after[TMessage: SyncMessage](
    query: Query[TMessage],
    *,
    after_sent_at: datetime,
    after_message_id: str,
    fetch_limit: int,
) -> list[TMessage]:
    same_sent_at = await query.filter(sent_at=after_sent_at).order_by("message_id").all()
    tied = [row for row in same_sent_at if row.message_id > after_message_id]
    if len(tied) >= fetch_limit:
        return tied[:fetch_limit]
    newer_sent_at = await query.filter(sent_at__gt=after_sent_at).order_by(
        "sent_at", "message_id"
    ).limit(fetch_limit - len(tied)).all()
    return [*tied, *newer_sent_at]


def _int_cell(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(label)
    return value


def _datetime_cell(value: object, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value)
    else:
        raise ValueError(label)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
