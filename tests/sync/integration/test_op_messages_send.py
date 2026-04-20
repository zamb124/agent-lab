"""op_messages_send — happy path + zero-fallback errors."""

from __future__ import annotations

import pytest

from apps.sync.container import SyncContainer
from apps.sync.models.channels import ChannelCreate, ChannelType
from apps.sync.models.messages import (
    MessageContentModel,
    MessageContentType,
    MessageCreate,
    TextPlainContent,
)
from apps.sync.models.spaces import SpaceCreate
from apps.sync.realtime.operations import (
    ChannelsCreatePayload,
    MessagesSendPayload,
    SpacesCreatePayload,
    op_channels_create,
    op_messages_send,
    op_spaces_create,
)
from core.models.identity_models import User


async def _setup_channel(
    op_user: User, op_container: SyncContainer, unique_id: str
) -> str:
    space = await op_spaces_create(
        SpacesCreatePayload(
            body=SpaceCreate(
                name=f"MsgSp {unique_id}", description=None, namespace=f"msg_{unique_id}"
            )
        ),
        user=op_user,
        container=op_container,
    )
    ch = await op_channels_create(
        ChannelsCreatePayload(
            body=ChannelCreate(
                type=ChannelType.TOPIC,
                name=f"MsgCh {unique_id}",
                space_id=space.id,
                is_private=False,
            )
        ),
        user=op_user,
        container=op_container,
    )
    return ch.id


@pytest.mark.asyncio
async def test_op_messages_send_happy_path(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    channel_id = await _setup_channel(op_user, op_container, unique_id)
    body = MessageCreate(
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body=f"Hello {unique_id}", mentions=None),
                order=0,
            )
        ]
    )
    msg = await op_messages_send(
        MessagesSendPayload(channel_id=channel_id, body=body),
        user=op_user,
        container=op_container,
    )
    assert msg.contents[0].data.body == f"Hello {unique_id}"
    assert msg.sender.user_id == op_user.user_id


@pytest.mark.asyncio
async def test_op_messages_send_forbidden_for_non_member(
    op_user: User,
    op_user2: User,
    op_container: SyncContainer,
    op_context: None,
    sync_auth_token_user2: str,
    unique_id: str,
) -> None:
    _ = sync_auth_token_user2
    channel_id = await _setup_channel(op_user, op_container, unique_id)
    body = MessageCreate(
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body=f"x {unique_id}", mentions=None),
                order=0,
            )
        ]
    )
    with pytest.raises(PermissionError):
        await op_messages_send(
            MessagesSendPayload(channel_id=channel_id, body=body),
            user=op_user2,
            container=op_container,
        )
