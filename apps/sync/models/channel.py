"""Канал Sync и строка настроек участника."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.sync.models.channel_member import SyncChannelMember
from core.models.platform_model import PlatformModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SyncChannel(PlatformModel):
    """Строка ``sync_channels``, алиас ``sync``, ``__global_model__``.

    Первичный ключ ``channel_id``. Ответ API — ``ChannelRead``: там peer,
    непрочитанные и превью ленты, которых нет в колонках.
    """

    __database_alias__: ClassVar[str | None] = "sync"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "sync_channels"
        indexes: list[Index] = [
            Index(["company_id"]),
            Index(["company_id", "namespace"]),
        ]

    channel_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    namespace: str = DbField(max_length=100)
    type: str = DbField(max_length=32)
    created_by_user_id: str = DbField(max_length=64)
    name: str | None = DbField(default=None, max_length=255)
    is_private: bool = DbField(default=False)
    avatar_url: str | None = DbField(default=None, db_type="TEXT")
    created_at: datetime = DbField(default_factory=_utcnow)
    pinned_message_ids: list[str] = DbField(default_factory=list, db_type="JSONB")
    transcribe_voice_messages: bool = DbField(default=False)
    speech_to_chat_enabled: bool = DbField(default=False)

    @classmethod
    async def by_channel_id(cls, company_id: str, channel_id: str) -> Self | None:
        """Канал компании по channel_id. Нет строки или чужая компания — None. Пустые company_id и channel_id ValueError не дают."""
        return await cls.objects.filter(
            channel_id=channel_id,
            company_id=company_id,
        ).get_or_none()

    @classmethod
    async def list_by_name_in_namespace_asc(
        cls,
        namespace: str,
        *,
        company_id: str,
        limit: int,
        offset: int,
    ) -> list[Self]:
        """Каналы компании в namespace, ORDER BY name ASC, окно limit и offset."""
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
        ).order_by("name").limit(limit).offset(offset).all()

    @classmethod
    async def list_member_channels_by_type_and_name_asc(
        cls,
        user_id: str,
        *,
        company_id: str,
        namespace: str | None,
        limit: int,
        offset: int,
    ) -> list[Self]:
        """Каналы компании, где user_id участник, ORDER BY type, name ASC, окно limit и offset. namespace None не фильтрует. Нет участия — []."""
        member_rows = await SyncChannelMember.objects.filter(
            company_id=company_id,
            user_id=user_id,
        ).all()
        channel_ids = [row.channel_id for row in member_rows]
        if len(channel_ids) == 0:
            return []
        rows = cls.objects.filter(
            company_id=company_id,
            channel_id__in=channel_ids,
        )
        if namespace is not None:
            rows = rows.filter(namespace=namespace)
        return await rows.order_by("type", "name").limit(limit).offset(offset).all()

    @classmethod
    async def list_for_both_members_by_type_and_name_asc(
        cls,
        user_id_a: str,
        user_id_b: str,
        *,
        company_id: str,
        limit: int,
        offset: int,
    ) -> list[Self]:
        """Каналы компании, где оба user_id есть среди участников, ORDER BY type, name ASC. Окно limit и offset. Списки участников без порядка. Нет общего канала — []. limit и offset в теле не проверяются."""
        rows_a = await SyncChannelMember.objects.filter(
            company_id=company_id,
            user_id=user_id_a,
        ).all()
        rows_b = await SyncChannelMember.objects.filter(
            company_id=company_id,
            user_id=user_id_b,
        ).all()
        ids_b = {row.channel_id for row in rows_b}
        shared = [row.channel_id for row in rows_a if row.channel_id in ids_b]
        if len(shared) == 0:
            return []
        return await cls.objects.filter(
            company_id=company_id,
            channel_id__in=shared,
        ).order_by("type", "name").limit(limit).offset(offset).all()

    @classmethod
    async def list_by_name_asc(
        cls,
        company_id: str,
        query: str,
        *,
        limit: int,
    ) -> list[Self]:
        """Каналы компании, ORDER BY name ASC, не больше limit. Пустой query не фильтрует имя."""
        rows = cls.objects.filter(company_id=company_id)
        if query != "":
            rows = rows.filter(name__icontains=query)
        return await rows.order_by("name").limit(limit).all()

    @classmethod
    async def update_name(cls, channel: Self, name: str) -> Self:
        """Пишет name переданной строки и сохраняет её. Повтор с тем же именем пишет его снова."""
        channel.name = name
        _ = await channel.save(using="sync")
        return channel

    @classmethod
    async def update_pinned_message_ids(
        cls,
        channel_id: str,
        message_ids: list[str],
        *,
        company_id: str,
    ) -> None:
        """Пишет pinned_message_ids канала внутри компании. Нет строки — ничего не меняет."""
        _ = await cls.objects.filter(
            channel_id=channel_id,
            company_id=company_id,
        ).update(using="sync", pinned_message_ids=message_ids)

    @classmethod
    async def list_all_by_channel_id_asc(cls, *, limit: int | None) -> list[Self]:
        """Все каналы, ORDER BY channel_id ASC. limit is None не ограничивает."""
        ordered = cls.objects.order_by("channel_id")
        if limit is None:
            return await ordered.all()
        return await ordered.limit(limit).all()
