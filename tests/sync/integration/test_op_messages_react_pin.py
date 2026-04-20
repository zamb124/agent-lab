"""op_messages_react / op_messages_pin."""

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
from apps.sync.realtime.operations import (
    ChannelsCreatePayload,
    MessagesPinPayload,
    MessagesReactPayload,
    MessagesSendPayload,
    op_channels_create,
    op_messages_pin,
    op_messages_react,
    op_messages_send,
)
from core.models.identity_models import User
from tests.sync.integration._helpers import seed_test_namespace


async def _setup_message(
    op_user: User, op_container: SyncContainer, unique_id: str
) -> tuple[str, str]:
    namespace = await seed_test_namespace(op_user, op_container, unique_id, suffix="rp")
    ch = await op_channels_create(
        ChannelsCreatePayload(
            body=ChannelCreate(
                type=ChannelType.TOPIC,
                name=f"RPCh {unique_id}",
                namespace=namespace,
                is_private=False,
            )
        ),
        user=op_user,
        container=op_container,
    )
    msg = await op_messages_send(
        MessagesSendPayload(
            channel_id=ch.id,
            body=MessageCreate(
                contents=[
                    MessageContentModel(
                        type=MessageContentType.TEXT_PLAIN,
                        data=TextPlainContent(body=f"hi {unique_id}", mentions=None),
                        order=0,
                    )
                ]
            ),
        ),
        user=op_user,
        container=op_container,
    )
    return ch.id, msg.id


@pytest.mark.asyncio
async def test_op_messages_react_toggle(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    channel_id, message_id = await _setup_message(op_user, op_container, unique_id)
    # Set reaction
    after_set = await op_messages_react(
        MessagesReactPayload(
            channel_id=channel_id, message_id=message_id, emoji=":fire:"
        ),
        user=op_user,
        container=op_container,
    )
    assert any(r.emoji == ":fire:" for r in after_set.reactions)
    # Remove (emoji=None)
    after_remove = await op_messages_react(
        MessagesReactPayload(channel_id=channel_id, message_id=message_id, emoji=None),
        user=op_user,
        container=op_container,
    )
    user_reactions = [
        r for r in after_remove.reactions if r.user_id == op_user.user_id
    ]
    assert user_reactions == []


@pytest.mark.asyncio
async def test_op_messages_pin_owner_only(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    channel_id, message_id = await _setup_message(op_user, op_container, unique_id)
    pinned_channel = await op_messages_pin(
        MessagesPinPayload(channel_id=channel_id, message_id=message_id, action="add"),
        user=op_user,
        container=op_container,
    )
    assert message_id in pinned_channel.pinned_message_ids

    unpinned = await op_messages_pin(
        MessagesPinPayload(
            channel_id=channel_id, message_id=message_id, action="remove"
        ),
        user=op_user,
        container=op_container,
    )
    assert message_id not in unpinned.pinned_message_ids
