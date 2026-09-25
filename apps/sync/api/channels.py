"""REST-зеркала команд channels. Тонкие обвязки над `op_channels_*`."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.sync.di import Di
from apps.sync.models.channels import (
    ChannelCreate,
    ChannelMemberAdd,
    ChannelMemberRead,
    ChannelNotificationSettingsUpdate,
    ChannelRead,
    ChannelUpdate,
)
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
from core.context import require_context
from core.pagination import ListResponse, OffsetPage
from core.websocket import WsCommandError

router = APIRouter()


@router.get("/", response_model=OffsetPage[ChannelRead])
async def list_channels(
    di: Di,
    namespace: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[ChannelRead]:
    user = require_context().user
    return await op_channels_list(
        ChannelsListPayload(namespace=namespace, limit=limit, offset=offset),
        user=user,
        di=di,
    )


@router.post("/", status_code=201, response_model=ChannelRead)
async def create_channel(di: Di, body: ChannelCreate) -> ChannelRead:
    user = require_context().user
    return await op_channels_create(body, user=user, di=di)


@router.patch("/{channel_id}", response_model=ChannelRead)
async def update_channel(
    di: Di, channel_id: str, body: ChannelUpdate
) -> ChannelRead:
    user = require_context().user
    return await op_channels_update(
        ChannelsUpdatePayload(channel_id=channel_id, body=body),
        user=user,
        di=di,
    )


@router.patch("/{channel_id}/notification-settings", response_model=ChannelRead)
async def patch_channel_notification_settings(
    channel_id: str,
    body: ChannelNotificationSettingsUpdate,
    di: Di,
) -> ChannelRead:
    user = require_context().user
    return await op_channels_notification_settings_update(
        ChannelsNotificationSettingsUpdatePayload(
            channel_id=channel_id, notifications_muted=body.notifications_muted
        ),
        user=user,
        di=di,
    )


@router.post("/{channel_id}/read", status_code=204)
async def mark_channel_read(di: Di, channel_id: str) -> None:
    user = require_context().user
    await op_channels_mark_read(
        ChannelsMarkReadPayload(channel_id=channel_id),
        user=user,
        di=di,
    )


@router.post("/{channel_id}/typing", status_code=204)
async def typing_channel(
    di: Di, channel_id: str, body: ChannelsTypingPayload
) -> None:
    if body.channel_id != channel_id:
        raise WsCommandError("ws_invalid_payload", "channel_id mismatch", error_code='ws_invalid_payload')
    user = require_context().user
    await op_channels_typing(body, user=user, di=di)


@router.get("/{channel_id}/members", response_model=ListResponse[ChannelMemberRead])
async def list_channel_members(
    channel_id: str, di: Di
) -> ListResponse[ChannelMemberRead]:
    user = require_context().user
    return await op_channels_list_members(
        ChannelsListMembersPayload(channel_id=channel_id),
        user=user,
        di=di,
    )


@router.post("/{channel_id}/members", status_code=201, response_model=ChannelMemberRead)
async def add_member(
    channel_id: str, body: ChannelMemberAdd, di: Di
) -> ChannelMemberRead:
    user = require_context().user
    return await op_channels_add_member(
        ChannelsAddMemberPayload(
            channel_id=channel_id, user_id=body.user_id, role=body.role
        ),
        user=user,
        di=di,
    )
