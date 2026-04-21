"""op_channels_* lifecycle: create/update/list/mark_read/typing/add_member/list_members.

Реальная БД, без моков.
"""

from __future__ import annotations

import pytest

from apps.sync.container import SyncContainer
from apps.sync.models.channels import ChannelCreate, ChannelType, ChannelUpdate
from apps.sync.realtime.operations import (
    ChannelsAddMemberPayload,
    ChannelsListMembersPayload,
    ChannelsListPayload,
    ChannelsMarkReadPayload,
    ChannelsTypingPayload,
    ChannelsUpdatePayload,
    op_channels_add_member,
    op_channels_create,
    op_channels_list,
    op_channels_list_members,
    op_channels_mark_read,
    op_channels_typing,
    op_channels_update,
)
from core.models.identity_models import User
from core.websocket import WsCommandError
from tests.sync.integration._helpers import seed_test_namespace


async def _create_topic(
    op_user: User,
    op_container: SyncContainer,
    unique_id: str,
    *,
    suffix: str,
    name: str,
) -> tuple[str, str]:
    namespace = await seed_test_namespace(op_user, op_container, unique_id, suffix=suffix)
    channel = await op_channels_create(
        ChannelCreate(
            type=ChannelType.TOPIC,
            name=name,
            namespace=namespace,
            is_private=False,
        ),
        user=op_user,
        container=op_container,
    )
    return channel.id, namespace


@pytest.mark.asyncio
async def test_op_channels_create_topic_and_list(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    channel_id, namespace = await _create_topic(
        op_user, op_container, unique_id, suffix="chl", name=f"Topic {unique_id}"
    )
    listing = await op_channels_list(
        ChannelsListPayload(namespace=namespace, limit=10, offset=0),
        user=op_user,
        container=op_container,
    )
    assert any(c.id == channel_id for c in listing.items)


@pytest.mark.asyncio
async def test_op_channels_create_direct_with_peer(
    op_user: User,
    op_user2: User,
    op_container: SyncContainer,
    op_context: None,
    sync_auth_token_user2: str,
    unique_id: str,
) -> None:
    _ = sync_auth_token_user2
    direct = await op_channels_create(
        ChannelCreate(
            type=ChannelType.DIRECT,
            member_ids=[op_user2.user_id],
            is_private=True,
        ),
        user=op_user,
        container=op_container,
    )
    assert direct.type == ChannelType.DIRECT


@pytest.mark.asyncio
async def test_op_channels_update_renames_channel(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    channel_id, _ = await _create_topic(
        op_user, op_container, unique_id, suffix="upch", name=f"OldName {unique_id}"
    )
    updated = await op_channels_update(
        ChannelsUpdatePayload(
            channel_id=channel_id,
            body=ChannelUpdate(name=f"NewName {unique_id}"),
        ),
        user=op_user,
        container=op_container,
    )
    assert updated.name == f"NewName {unique_id}"


@pytest.mark.asyncio
async def test_op_channels_mark_read_no_op_when_no_messages(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    channel_id, _ = await _create_topic(
        op_user, op_container, unique_id, suffix="mr", name=f"MRCh {unique_id}"
    )
    result = await op_channels_mark_read(
        ChannelsMarkReadPayload(channel_id=channel_id),
        user=op_user,
        container=op_container,
    )
    assert result is None


@pytest.mark.asyncio
async def test_op_channels_typing_requires_membership(
    op_user: User,
    op_user2: User,
    op_container: SyncContainer,
    op_context: None,
    sync_auth_token_user2: str,
    unique_id: str,
) -> None:
    _ = sync_auth_token_user2
    channel_id, _ = await _create_topic(
        op_user, op_container, unique_id, suffix="typ", name=f"Typ {unique_id}"
    )
    with pytest.raises(WsCommandError) as exc_info:
        await op_channels_typing(
            ChannelsTypingPayload(channel_id=channel_id, typing=True, thread_id=None),
            user=op_user2,
            container=op_container,
        )
    assert exc_info.value.code == "forbidden"


@pytest.mark.asyncio
async def test_op_channels_add_member_then_list_members(
    op_user: User,
    op_user2: User,
    op_container: SyncContainer,
    op_context: None,
    sync_auth_token_user2: str,
    unique_id: str,
) -> None:
    _ = sync_auth_token_user2
    channel_id, _ = await _create_topic(
        op_user, op_container, unique_id, suffix="am", name=f"AMCh {unique_id}"
    )
    member = await op_channels_add_member(
        ChannelsAddMemberPayload(
            channel_id=channel_id, user_id=op_user2.user_id, role="member"
        ),
        user=op_user,
        container=op_container,
    )
    assert member.user_id == op_user2.user_id

    listing = await op_channels_list_members(
        ChannelsListMembersPayload(channel_id=channel_id),
        user=op_user,
        container=op_container,
    )
    user_ids = {m.user_id for m in listing.items}
    assert op_user.user_id in user_ids
    assert op_user2.user_id in user_ids


@pytest.mark.asyncio
async def test_op_channels_update_not_found_raises(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
) -> None:
    with pytest.raises((WsCommandError, ValueError, PermissionError)):
        await op_channels_update(
            ChannelsUpdatePayload(
                channel_id="missing_channel_id",
                body=ChannelUpdate(name="X"),
            ),
            user=op_user,
            container=op_container,
        )
