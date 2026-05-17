"""REST-зеркала команд channels. Тонкие обвязки над `op_channels_*`."""

from fastapi import APIRouter, Query
from pydantic import BaseModel

from apps.sync.dependencies import ContainerDep
from apps.sync.models.channels import (
    ChannelCreate,
    ChannelMemberAdd,
    ChannelMemberRead,
    ChannelNotificationSettingsUpdate,
    ChannelRead,
    ChannelUpdate,
)
from apps.sync.realtime.context import require_current_user
from apps.sync.realtime.operations import (
    ChannelsAddMemberPayload,
    ChannelsListMembersPayload,
    ChannelsListPayload,
    ChannelsMarkReadPayload,
    ChannelsNotificationSettingsUpdatePayload,
    ChannelsTypingPayload,
    ChannelsUpdatePayload,
    op_channels_add_member,
    op_channels_create,
    op_channels_list,
    op_channels_list_members,
    op_channels_mark_read,
    op_channels_notification_settings_update,
    op_channels_typing,
    op_channels_update,
)
from core.pagination import ListResponse, OffsetPage

router = APIRouter()


class _TypingBody(BaseModel):
    typing: bool
    thread_id: str | None = None


@router.get("/", response_model=OffsetPage[ChannelRead])
async def list_channels(
    container: ContainerDep,
    namespace: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OffsetPage[ChannelRead]:
    user = require_current_user()
    result = await op_channels_list(
        ChannelsListPayload(namespace=namespace, limit=limit, offset=offset),
        user=user,
        container=container,
    )
    return OffsetPage[ChannelRead](
        items=result.items, total=result.total, limit=result.limit, offset=result.offset
    )


@router.post("/", status_code=201, response_model=ChannelRead)
async def create_channel(container: ContainerDep, body: ChannelCreate) -> ChannelRead:
    user = require_current_user()
    return await op_channels_create(body, user=user, container=container)


@router.patch("/{channel_id}", response_model=ChannelRead)
async def update_channel(
    container: ContainerDep, channel_id: str, body: ChannelUpdate
) -> ChannelRead:
    user = require_current_user()
    return await op_channels_update(
        ChannelsUpdatePayload(channel_id=channel_id, body=body),
        user=user,
        container=container,
    )


@router.patch("/{channel_id}/notification-settings", response_model=ChannelRead)
async def patch_channel_notification_settings(
    channel_id: str,
    body: ChannelNotificationSettingsUpdate,
    container: ContainerDep,
) -> ChannelRead:
    user = require_current_user()
    return await op_channels_notification_settings_update(
        ChannelsNotificationSettingsUpdatePayload(
            channel_id=channel_id, notifications_muted=body.notifications_muted
        ),
        user=user,
        container=container,
    )


@router.post("/{channel_id}/read", status_code=204)
async def mark_channel_read(container: ContainerDep, channel_id: str) -> None:
    user = require_current_user()
    await op_channels_mark_read(
        ChannelsMarkReadPayload(channel_id=channel_id),
        user=user,
        container=container,
    )


@router.post("/{channel_id}/typing", status_code=204)
async def typing_channel(
    container: ContainerDep, channel_id: str, body: _TypingBody
) -> None:
    user = require_current_user()
    await op_channels_typing(
        ChannelsTypingPayload(
            channel_id=channel_id, typing=body.typing, thread_id=body.thread_id
        ),
        user=user,
        container=container,
    )


@router.get("/{channel_id}/members", response_model=ListResponse[ChannelMemberRead])
async def list_channel_members(
    channel_id: str, container: ContainerDep
) -> ListResponse[ChannelMemberRead]:
    user = require_current_user()
    result = await op_channels_list_members(
        ChannelsListMembersPayload(channel_id=channel_id),
        user=user,
        container=container,
    )
    return ListResponse[ChannelMemberRead](items=result.items)


@router.post("/{channel_id}/members", status_code=201, response_model=ChannelMemberRead)
async def add_member(
    channel_id: str, body: ChannelMemberAdd, container: ContainerDep
) -> ChannelMemberRead:
    user = require_current_user()
    return await op_channels_add_member(
        ChannelsAddMemberPayload(
            channel_id=channel_id, user_id=body.user_id, role=body.role
        ),
        user=user,
        container=container,
    )
