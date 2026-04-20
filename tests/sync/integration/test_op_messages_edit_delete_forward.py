"""op_messages_edit / delete / forward / list."""

from __future__ import annotations

import pytest

from apps.sync.container import SyncContainer
from apps.sync.models.channels import ChannelCreate, ChannelType
from apps.sync.models.messages import (
    MessageContentModel,
    MessageContentType,
    MessageCreate,
    MessageEdit,
    TextPlainContent,
)
from apps.sync.models.spaces import SpaceCreate
from apps.sync.realtime.operations import (
    ChannelsCreatePayload,
    MessagesDeletePayload,
    MessagesEditPayload,
    MessagesForwardPayload,
    MessagesListPayload,
    MessagesSendPayload,
    SpacesCreatePayload,
    op_channels_create,
    op_messages_delete,
    op_messages_edit,
    op_messages_forward,
    op_messages_list,
    op_messages_send,
    op_spaces_create,
)
from core.models.identity_models import User
from core.websocket import WsCommandError


async def _setup_two_channels(
    op_user: User, op_container: SyncContainer, unique_id: str
) -> tuple[str, str]:
    space = await op_spaces_create(
        SpacesCreatePayload(
            body=SpaceCreate(
                name=f"EDFSp {unique_id}", description=None, namespace=f"edf_{unique_id}"
            )
        ),
        user=op_user,
        container=op_container,
    )
    ch1 = await op_channels_create(
        ChannelsCreatePayload(
            body=ChannelCreate(
                type=ChannelType.TOPIC,
                name=f"From {unique_id}",
                space_id=space.id,
                is_private=False,
            )
        ),
        user=op_user,
        container=op_container,
    )
    ch2 = await op_channels_create(
        ChannelsCreatePayload(
            body=ChannelCreate(
                type=ChannelType.TOPIC,
                name=f"To {unique_id}",
                space_id=space.id,
                is_private=False,
            )
        ),
        user=op_user,
        container=op_container,
    )
    return ch1.id, ch2.id


async def _send_text(
    op_user: User, op_container: SyncContainer, channel_id: str, text: str
) -> str:
    msg = await op_messages_send(
        MessagesSendPayload(
            channel_id=channel_id,
            body=MessageCreate(
                contents=[
                    MessageContentModel(
                        type=MessageContentType.TEXT_PLAIN,
                        data=TextPlainContent(body=text, mentions=None),
                        order=0,
                    )
                ]
            ),
        ),
        user=op_user,
        container=op_container,
    )
    return msg.id


@pytest.mark.asyncio
async def test_op_messages_edit_by_author(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    ch_id, _ = await _setup_two_channels(op_user, op_container, unique_id)
    msg_id = await _send_text(op_user, op_container, ch_id, "before")
    edited = await op_messages_edit(
        MessagesEditPayload(
            channel_id=ch_id,
            message_id=msg_id,
            body=MessageEdit(
                contents=[
                    MessageContentModel(
                        type=MessageContentType.TEXT_PLAIN,
                        data=TextPlainContent(body="after", mentions=None),
                        order=0,
                    )
                ]
            ),
        ),
        user=op_user,
        container=op_container,
    )
    assert edited.contents[0].data.body == "after"


@pytest.mark.asyncio
async def test_op_messages_delete_by_owner(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    ch_id, _ = await _setup_two_channels(op_user, op_container, unique_id)
    msg_id = await _send_text(op_user, op_container, ch_id, "to_delete")
    result = await op_messages_delete(
        MessagesDeletePayload(channel_id=ch_id, message_id=msg_id),
        user=op_user,
        container=op_container,
    )
    assert result == {"message_id": msg_id}


@pytest.mark.asyncio
async def test_op_messages_forward_to_other_channel(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    ch_from, ch_to = await _setup_two_channels(op_user, op_container, unique_id)
    msg_id = await _send_text(op_user, op_container, ch_from, f"forwarded {unique_id}")
    fwd = await op_messages_forward(
        MessagesForwardPayload(
            from_channel_id=ch_from,
            message_id=msg_id,
            to_channel_id=ch_to,
            thread_id=None,
        ),
        user=op_user,
        container=op_container,
    )
    assert fwd.contents[0].data.body == f"forwarded {unique_id}"
    assert fwd.forwarded_from is not None
    assert fwd.forwarded_from.channel_id == ch_from


@pytest.mark.asyncio
async def test_op_messages_list_returns_chronological(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    ch_id, _ = await _setup_two_channels(op_user, op_container, unique_id)
    await _send_text(op_user, op_container, ch_id, "m1")
    await _send_text(op_user, op_container, ch_id, "m2")
    result = await op_messages_list(
        MessagesListPayload(channel_id=ch_id, limit=10),
        user=op_user,
        container=op_container,
    )
    bodies = [m.contents[0].data.body for m in result.items]
    assert bodies == ["m1", "m2"]


@pytest.mark.asyncio
async def test_op_messages_edit_not_found_raises(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    ch_id, _ = await _setup_two_channels(op_user, op_container, unique_id)
    with pytest.raises(WsCommandError) as exc_info:
        await op_messages_edit(
            MessagesEditPayload(
                channel_id=ch_id,
                message_id="missing_msg_id",
                body=MessageEdit(
                    contents=[
                        MessageContentModel(
                            type=MessageContentType.TEXT_PLAIN,
                            data=TextPlainContent(body="x", mentions=None),
                            order=0,
                        )
                    ]
                ),
            ),
            user=op_user,
            container=op_container,
        )
    assert exc_info.value.code in ("not_found", "forbidden")
