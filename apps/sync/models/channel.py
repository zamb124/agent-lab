"""Канал Sync и строка настроек участника."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

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
    async def channel_for_company(
        cls,
        channel_id: str,
        company_id: str,
    ) -> Self | None:
        return await cls.objects.filter(
            channel_id=channel_id,
            company_id=company_id,
        ).get_or_none()

    @classmethod
    async def list_channels_in_namespace(
        cls,
        namespace: str,
        *,
        company_id: str,
        limit: int,
        offset: int,
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
        ).order_by("name").limit(limit).offset(offset).all()

    @classmethod
    async def list_channels_for_user(
        cls,
        user_id: str,
        *,
        company_id: str,
        namespace: str | None,
        limit: int,
        offset: int,
    ) -> list[Self]:
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
    async def list_channels_where_both_members(
        cls,
        user_id_a: str,
        user_id_b: str,
        *,
        company_id: str,
        limit: int,
        offset: int,
    ) -> list[Self]:
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
    async def search_channels_by_name(
        cls,
        company_id: str,
        query: str,
        *,
        limit: int,
    ) -> list[Self]:
        rows = cls.objects.filter(company_id=company_id)
        if query != "":
            rows = rows.filter(name__icontains=query)
        return await rows.order_by("name").limit(limit).all()

    @classmethod
    async def rename_channel(cls, channel: Self, name: str) -> Self:
        channel.name = name
        _ = await channel.save(using="sync")
        return channel

    @classmethod
    async def set_channel_pinned_message_ids(
        cls,
        channel_id: str,
        message_ids: list[str],
        *,
        company_id: str,
    ) -> None:
        _ = await cls.objects.filter(
            channel_id=channel_id,
            company_id=company_id,
        ).update(using="sync", pinned_message_ids=message_ids)

    @classmethod
    async def list_for_authz(cls, *, limit: int | None) -> list[Self]:
        ordered = cls.objects.order_by("channel_id")
        if limit is None:
            return await ordered.all()
        return await ordered.limit(limit).all()


class SyncChannelMember(PlatformModel):
    """Строка ``sync_channel_members``, алиас ``sync``, ``__global_model__``.

    В базе ключ — пара ``(channel_id, user_id)``. Oxyde хранит один ``db_pk`` —
    ``channel_id``. Строку читают и пишут фильтром ``channel_id`` и ``user_id``:
    ``save`` и PK-CRUD ``get``/``set``/``delete_by_id`` задели бы остальных участников канала.
    ``channel_id`` ссылается на ``sync_channels.channel_id`` ON DELETE CASCADE.
    В ``0001`` первичный ключ остаётся составным.
    """

    __database_alias__: ClassVar[str | None] = "sync"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "sync_channel_members"
        unique_together: list[tuple[str, str]] = [("channel_id", "user_id")]
        indexes: list[Index] = [
            Index(["company_id"]),
        ]

    channel_id: str = DbField(db_pk=True, max_length=64)
    user_id: str = DbField(max_length=64)
    company_id: str = DbField(max_length=100)
    last_read_at: datetime | None = DbField(default=None)
    notifications_muted: bool = DbField(default=False)

    @classmethod
    async def list_channel_member_user_ids(
        cls,
        channel_id: str,
        *,
        company_id: str,
    ) -> list[str]:
        rows = await cls.objects.filter(
            channel_id=channel_id,
            company_id=company_id,
        ).all()
        return [row.user_id for row in rows]

    @classmethod
    async def ensure_channel_member_row(
        cls,
        channel_id: str,
        user_id: str,
        *,
        company_id: str,
    ) -> None:
        existing = await cls.objects.filter(
            channel_id=channel_id,
            user_id=user_id,
        ).get_or_none()
        if existing is not None:
            if existing.company_id != company_id:
                raise ValueError(
                    f"Member row belongs to another company: channel_id={channel_id}."
                )
            return
        row = cls(
            channel_id=channel_id,
            user_id=user_id,
            company_id=company_id,
            notifications_muted=False,
        )
        _ = await cls.objects.create(instance=row)

    @classmethod
    async def delete_channel_member(
        cls,
        channel_id: str,
        user_id: str,
        *,
        company_id: str,
    ) -> bool:
        existing = await cls.objects.filter(
            channel_id=channel_id,
            user_id=user_id,
            company_id=company_id,
        ).get_or_none()
        if existing is None:
            return False
        deleted = await cls.objects.filter(
            channel_id=channel_id,
            user_id=user_id,
            company_id=company_id,
        ).delete()
        return deleted == 1

    @classmethod
    async def set_channel_member_last_read_at(
        cls,
        channel_id: str,
        user_id: str,
        at: datetime,
        *,
        company_id: str,
    ) -> None:
        existing = await cls.objects.filter(
            channel_id=channel_id,
            user_id=user_id,
        ).get_or_none()
        if existing is None:
            raise ValueError(
                f"Channel member not found: channel_id={channel_id}, user_id={user_id}."
            )
        if existing.company_id != company_id:
            raise ValueError(
                f"Member row belongs to another company: channel_id={channel_id}."
            )
        updated = await cls.objects.filter(
            channel_id=channel_id,
            user_id=user_id,
            company_id=company_id,
        ).update(using="sync", last_read_at=at)
        if updated != 1:
            raise ValueError(
                f"Channel member not found: channel_id={channel_id}, user_id={user_id}."
            )

    @classmethod
    async def channel_member_notifications_muted(
        cls,
        channel_id: str,
        user_id: str,
        *,
        company_id: str,
    ) -> bool:
        row = await cls.objects.filter(
            channel_id=channel_id,
            user_id=user_id,
            company_id=company_id,
        ).get_or_none()
        if row is None:
            raise ValueError(
                f"Channel member not found: channel_id={channel_id}, user_id={user_id}."
            )
        return row.notifications_muted

    @classmethod
    async def set_channel_member_notifications_muted(
        cls,
        channel_id: str,
        user_id: str,
        muted: bool,
        *,
        company_id: str,
    ) -> None:
        existing = await cls.objects.filter(
            channel_id=channel_id,
            user_id=user_id,
            company_id=company_id,
        ).get_or_none()
        if existing is None:
            raise ValueError(
                f"Channel member not found: channel_id={channel_id}, user_id={user_id}."
            )
        updated = await cls.objects.filter(
            channel_id=channel_id,
            user_id=user_id,
            company_id=company_id,
        ).update(using="sync", notifications_muted=muted)
        if updated != 1:
            raise ValueError(
                f"Channel member not found: channel_id={channel_id}, user_id={user_id}."
            )

    @classmethod
    async def peer_channel_member_last_read_at(
        cls,
        channel_id: str,
        viewer_user_id: str,
        *,
        company_id: str,
    ) -> datetime | None:
        rows = await cls.objects.filter(
            channel_id=channel_id,
            company_id=company_id,
        ).exclude(user_id=viewer_user_id).limit(1).all()
        if len(rows) == 0:
            return None
        return rows[0].last_read_at

    @classmethod
    async def list_for_authz(cls, *, limit: int | None) -> list[Self]:
        ordered = cls.objects.order_by("channel_id", "user_id")
        if limit is None:
            return await ordered.all()
        return await ordered.limit(limit).all()
