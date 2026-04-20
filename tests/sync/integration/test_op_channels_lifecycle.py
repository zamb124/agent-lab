"""op_channels_* lifecycle: create/update/list/mark_read/typing/add_member/list_members.

Реальная БД, без моков.
"""

from __future__ import annotations

import pytest

from apps.sync.container import SyncContainer
from apps.sync.models.channels import ChannelCreate, ChannelType, ChannelUpdate
from apps.sync.models.spaces import SpaceCreate
from apps.sync.realtime.operations import (
    ChannelsAddMemberPayload,
    ChannelsCreatePayload,
    ChannelsListMembersPayload,
    ChannelsListPayload,
    ChannelsMarkReadPayload,
    ChannelsTypingPayload,
    ChannelsUpdatePayload,
    SpacesCreatePayload,
    op_channels_add_member,
    op_channels_create,
    op_channels_list,
    op_channels_list_members,
    op_channels_mark_read,
    op_channels_typing,
    op_channels_update,
    op_spaces_create,
)
from core.models.identity_models import User
from core.websocket import WsCommandError


@pytest.mark.asyncio
async def test_op_channels_create_topic_and_list(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    space = await op_spaces_create(
        SpacesCreatePayload(
            body=SpaceCreate(
                name=f"ChLifeSp {unique_id}", description=None, namespace=f"chl_{unique_id}"
            )
        ),
        user=op_user,
        container=op_container,
    )
    channel = await op_channels_create(
        ChannelsCreatePayload(
            body=ChannelCreate(
                type=ChannelType.TOPIC,
                name=f"Topic {unique_id}",
                space_id=space.id,
                is_private=False,
            )
        ),
        user=op_user,
        container=op_container,
    )
    assert channel.type == ChannelType.TOPIC
    assert channel.name == f"Topic {unique_id}"

    listing = await op_channels_list(
        ChannelsListPayload(space_id=space.id, limit=10, offset=0),
        user=op_user,
        container=op_container,
    )
    assert any(c.id == channel.id for c in listing.items)


@pytest.mark.asyncio
async def test_op_channels_create_direct_with_peer(
    op_user: User,
    op_user2: User,
    op_container: SyncContainer,
    op_context: None,
    sync_auth_token_user2: str,
    unique_id: str,
) -> None:
    _ = sync_auth_token_user2  # обеспечивает создание user2 в shared
    direct = await op_channels_create(
        ChannelsCreatePayload(
            body=ChannelCreate(
                type=ChannelType.DIRECT,
                space_id=None,
                member_ids=[op_user2.user_id],
                is_private=True,
            )
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
    space = await op_spaces_create(
        SpacesCreatePayload(
            body=SpaceCreate(
                name=f"UpdChSp {unique_id}", description=None, namespace=f"upch_{unique_id}"
            )
        ),
        user=op_user,
        container=op_container,
    )
    channel = await op_channels_create(
        ChannelsCreatePayload(
            body=ChannelCreate(
                type=ChannelType.TOPIC,
                name=f"OldName {unique_id}",
                space_id=space.id,
                is_private=False,
            )
        ),
        user=op_user,
        container=op_container,
    )
    updated = await op_channels_update(
        ChannelsUpdatePayload(
            channel_id=channel.id,
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
    space = await op_spaces_create(
        SpacesCreatePayload(
            body=SpaceCreate(
                name=f"MRSp {unique_id}", description=None, namespace=f"mr_{unique_id}"
            )
        ),
        user=op_user,
        container=op_container,
    )
    channel = await op_channels_create(
        ChannelsCreatePayload(
            body=ChannelCreate(
                type=ChannelType.TOPIC,
                name=f"MRCh {unique_id}",
                space_id=space.id,
                is_private=False,
            )
        ),
        user=op_user,
        container=op_container,
    )
    # Не должно бросать — пустой канал, mark_read ставит read_at = now.
    result = await op_channels_mark_read(
        ChannelsMarkReadPayload(channel_id=channel.id),
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
    # user2 не в канале → forbidden.
    space = await op_spaces_create(
        SpacesCreatePayload(
            body=SpaceCreate(
                name=f"TypSp {unique_id}", description=None, namespace=f"typ_{unique_id}"
            )
        ),
        user=op_user,
        container=op_container,
    )
    channel = await op_channels_create(
        ChannelsCreatePayload(
            body=ChannelCreate(
                type=ChannelType.TOPIC,
                name=f"Typ {unique_id}",
                space_id=space.id,
                is_private=False,
            )
        ),
        user=op_user,
        container=op_container,
    )
    with pytest.raises(WsCommandError) as exc_info:
        await op_channels_typing(
            ChannelsTypingPayload(channel_id=channel.id, typing=True, thread_id=None),
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
    space = await op_spaces_create(
        SpacesCreatePayload(
            body=SpaceCreate(
                name=f"AMSp {unique_id}", description=None, namespace=f"am_{unique_id}"
            )
        ),
        user=op_user,
        container=op_container,
    )
    channel = await op_channels_create(
        ChannelsCreatePayload(
            body=ChannelCreate(
                type=ChannelType.TOPIC,
                name=f"AMCh {unique_id}",
                space_id=space.id,
                is_private=False,
            )
        ),
        user=op_user,
        container=op_container,
    )
    member = await op_channels_add_member(
        ChannelsAddMemberPayload(
            channel_id=channel.id, user_id=op_user2.user_id, role="member"
        ),
        user=op_user,
        container=op_container,
    )
    assert member.user_id == op_user2.user_id

    listing = await op_channels_list_members(
        ChannelsListMembersPayload(channel_id=channel.id),
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
