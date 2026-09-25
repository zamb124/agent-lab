"""Тред Sync: таблица и ответы API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index
from pydantic import BaseModel, Field

from apps.sync.models.common import UserBrief
from core.models.platform_model import PlatformModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SyncThread(PlatformModel):
    """Строка ``sync_threads``, алиас ``sync``, ``__global_model__``.

    ``channel_id`` ссылается на ``sync_channels.channel_id`` (ON DELETE CASCADE).
    Канал ещё SQLAlchemy, поэтому внешний ключ в модели не объявлен.
    Ответ списка — ``ThreadRow`` без ``company_id``. Карточка — ``ThreadRead``.
    """

    __database_alias__: ClassVar[str | None] = "sync"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "sync_threads"
        indexes: list[Index] = [
            Index(["company_id"]),
            Index(["channel_id"]),
        ]

    thread_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    channel_id: str = DbField(max_length=64)
    root_message_id: str = DbField(max_length=64)
    created_by_user_id: str = DbField(max_length=64)
    created_at: datetime = DbField(default_factory=_utcnow)
    title: str | None = DbField(default=None, max_length=255)

    @classmethod
    async def list_threads_in_channel(
        cls,
        company_id: str,
        channel_id: str,
        *,
        limit: int,
        offset: int,
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id,
            channel_id=channel_id,
        ).order_by("-created_at").limit(limit).offset(offset).all()

    @classmethod
    async def create_thread(cls, thread: Self) -> Self:
        return await cls.objects.create(instance=thread)


class ThreadRow(BaseModel):
    """Тред в списке и карточке без автора."""

    thread_id: str = Field(description="Идентификатор треда.")
    channel_id: str = Field(description="Канал, в котором находится тред.")
    root_message_id: str = Field(description="Корневое сообщение треда.")
    title: str | None = Field(default=None, description="Опциональный заголовок треда.")
    created_at: datetime = Field(description="Время создания треда.")
    created_by_user_id: str = Field(description="Создатель треда.")


class ThreadRead(BaseModel):
    """Полная информация о треде."""

    thread_id: str = Field(description="Идентификатор треда.")
    channel_id: str = Field(description="Канал, в котором находится тред.")
    root_message_id: str = Field(description="Корневое сообщение треда.")
    title: str | None = Field(
        default=None,
        description="Опциональный заголовок треда.",
    )
    created_at: datetime = Field(description="Время создания треда.")
    created_by: UserBrief = Field(description="Пользователь, создавший тред.")


class ThreadCreate(BaseModel):
    """Создание треда от корневого сообщения."""

    root_message_id: str = Field(description="Корневое сообщение для треда.")
    title: str | None = Field(
        default=None,
        description="Опциональный заголовок треда.",
    )


class ThreadSummary(BaseModel):
    """Краткое представление треда для списков."""

    thread_id: str = Field(description="Идентификатор треда.")
    channel_id: str = Field(description="Канал треда.")
    root_message_preview: str = Field(
        description="Краткий текстовый превью корневого сообщения.",
    )
    replies_count: int = Field(description="Количество ответов в треде.")
    last_reply_at: datetime | None = Field(
        default=None,
        description="Время последнего ответа.",
    )
