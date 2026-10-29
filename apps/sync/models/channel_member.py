"""Участник канала Sync."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


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
    async def list_unordered_user_ids(
        cls,
        channel_id: str,
        *,
        company_id: str,
    ) -> list[str]:
        """user_id участников канала в компании. Порядка нет. Чужой канал — []."""
        rows = await cls.objects.filter(
            channel_id=channel_id,
            company_id=company_id,
        ).all()
        return [row.user_id for row in rows]

    @classmethod
    async def ensure_member(
        cls,
        channel_id: str,
        user_id: str,
        *,
        company_id: str,
    ) -> None:
        """Создаёт строку участника, если её нет. Существующую не меняет. Та же пара в другой компании — ValueError."""
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
    async def delete_by_user(
        cls,
        channel_id: str,
        user_id: str,
        *,
        company_id: str,
    ) -> bool:
        """Удаляет участника канала в компании. Нет строки — False. Удалена одна строка — True."""
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
    async def update_last_read_at(
        cls,
        channel_id: str,
        user_id: str,
        at: datetime,
        *,
        company_id: str,
    ) -> None:
        """Пишет last_read_at участника в компании. Нет строки или чужая компания — ValueError."""
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
    async def is_notifications_muted(
        cls,
        channel_id: str,
        user_id: str,
        *,
        company_id: str,
    ) -> bool:
        """Флаг notifications_muted участника в компании. Нет строки — ValueError."""
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
    async def update_notifications_muted(
        cls,
        channel_id: str,
        user_id: str,
        muted: bool,
        *,
        company_id: str,
    ) -> None:
        """Пишет notifications_muted участника в компании. Нет строки — ValueError. Обновление не одной строки — ValueError."""
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
    async def peer_last_read_at(
        cls,
        channel_id: str,
        viewer_user_id: str,
        *,
        company_id: str,
    ) -> datetime | None:
        """last_read_at одного другого участника канала. Нет другого участника — None. Какой именно, если их несколько, не задано."""
        rows = await cls.objects.filter(
            channel_id=channel_id,
            company_id=company_id,
        ).exclude(user_id=viewer_user_id).limit(1).all()
        if len(rows) == 0:
            return None
        return rows[0].last_read_at

    @classmethod
    async def list_all_by_channel_id_and_user_id_asc(cls, *, limit: int | None) -> list[Self]:
        """Все строки участников, ORDER BY channel_id, user_id ASC. limit is None не ограничивает."""
        ordered = cls.objects.order_by("channel_id", "user_id")
        if limit is None:
            return await ordered.all()
        return await ordered.limit(limit).all()
