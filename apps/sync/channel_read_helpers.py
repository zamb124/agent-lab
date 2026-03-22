"""Сборка ChannelRead из сущностей БД (API и handlers)."""

from __future__ import annotations

from apps.sync.channel_lane_preview import ChannelLaneSummary
from apps.sync.db.models import SyncChannel
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.models.channels import ChannelRead, ChannelType
from apps.sync.models.common import UserBrief
from core.db.repositories.user_repository import UserRepository


async def _user_brief(user_repository: UserRepository | None, user_id: str) -> UserBrief:
    display_name = user_id
    avatar_url = None
    if user_repository is not None:
        u = await user_repository.get(user_id)
        if u is not None:
            display_name = u.name
            avatar_url = u.avatar_url
    return UserBrief(id=user_id, display_name=display_name, avatar_url=avatar_url)


async def channel_read_from_entity(
    entity: SyncChannel,
    *,
    viewer_user_id: str,
    channel_repository: ChannelRepository,
    user_repository: UserRepository | None,
    company_id: str,
    lane_summary: ChannelLaneSummary | None = None,
) -> ChannelRead:
    """Строит ChannelRead; для direct подставляет peer (любой участник кроме viewer)."""
    summ = lane_summary or ChannelLaneSummary(
        unread_count=0,
        last_message_preview=None,
        last_message_at=None,
    )
    pids = entity.pinned_message_ids if isinstance(entity.pinned_message_ids, list) else []
    peer: UserBrief | None = None
    if entity.type == ChannelType.DIRECT.value:
        member_ids = await channel_repository.list_member_user_ids(
            entity.channel_id,
            company_id=company_id,
        )
        others = [uid for uid in member_ids if uid != viewer_user_id]
        if len(others) >= 1:
            peer = await _user_brief(user_repository, others[0])
    return ChannelRead(
        id=entity.channel_id,
        space_id=entity.space_id,
        type=ChannelType(entity.type),
        name=entity.name,
        is_private=entity.is_private,
        created_at=entity.created_at,
        created_by_user_id=entity.created_by_user_id,
        pinned_message_ids=pids,
        peer=peer,
        avatar_url=entity.avatar_url,
        unread_count=summ.unread_count,
        last_message_preview=summ.last_message_preview,
        last_message_at=summ.last_message_at,
    )


def channel_read_entity_minimal(entity: SyncChannel) -> ChannelRead:
    """ChannelRead без peer (ответ команд создания до полной выборки)."""
    pids = entity.pinned_message_ids if isinstance(entity.pinned_message_ids, list) else []
    return ChannelRead(
        id=entity.channel_id,
        space_id=entity.space_id,
        type=ChannelType(entity.type),
        name=entity.name,
        is_private=entity.is_private,
        created_at=entity.created_at,
        created_by_user_id=entity.created_by_user_id,
        pinned_message_ids=pids,
        peer=None,
        avatar_url=entity.avatar_url,
        unread_count=0,
        last_message_preview=None,
        last_message_at=None,
    )
