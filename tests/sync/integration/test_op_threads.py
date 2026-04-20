"""op_threads_* — create/list/item, изоляция по company.

Реальная БД, без моков.
"""

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
from apps.sync.models.threads import ThreadCreate
from apps.sync.realtime.operations import (
    ChannelsCreatePayload,
    MessagesSendPayload,
    ThreadsCreatePayload,
    ThreadsItemPayload,
    ThreadsListPayload,
    op_channels_create,
    op_messages_send,
    op_threads_create,
    op_threads_item,
    op_threads_list,
)
from core.models.identity_models import User
from core.websocket import WsCommandError
from tests.sync.integration._helpers import seed_test_namespace


async def _create_namespace_and_channel(
    op_user: User,
    op_container: SyncContainer,
    unique_id: str,
) -> str:
    namespace = await seed_test_namespace(op_user, op_container, unique_id, suffix="th")
    channel = await op_channels_create(
        ChannelsCreatePayload(
            body=ChannelCreate(
                type=ChannelType.TOPIC,
                name=f"ThCh {unique_id}",
                namespace=namespace,
                is_private=False,
            )
        ),
        user=op_user,
        container=op_container,
    )
    return channel.id


async def _send_root_message(
    op_user: User,
    op_container: SyncContainer,
    channel_id: str,
    text: str,
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
async def test_op_threads_create_and_item(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    channel_id = await _create_namespace_and_channel(op_user, op_container, unique_id)
    root_id = await _send_root_message(op_user, op_container, channel_id, "root")

    thread = await op_threads_create(
        ThreadsCreatePayload(
            body=ThreadCreate(root_message_id=root_id, title=f"T {unique_id}")
        ),
        user=op_user,
        container=op_container,
    )
    assert thread.title == f"T {unique_id}"
    assert thread.channel_id == channel_id

    item = await op_threads_item(
        ThreadsItemPayload(thread_id=thread.id),
        user=op_user,
        container=op_container,
    )
    assert item.id == thread.id
    assert item.title == f"T {unique_id}"


@pytest.mark.asyncio
async def test_op_threads_list_in_channel(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    channel_id = await _create_namespace_and_channel(op_user, op_container, unique_id)
    root1 = await _send_root_message(op_user, op_container, channel_id, "r1")
    root2 = await _send_root_message(op_user, op_container, channel_id, "r2")
    await op_threads_create(
        ThreadsCreatePayload(body=ThreadCreate(root_message_id=root1, title="t1")),
        user=op_user,
        container=op_container,
    )
    await op_threads_create(
        ThreadsCreatePayload(body=ThreadCreate(root_message_id=root2, title="t2")),
        user=op_user,
        container=op_container,
    )

    result = await op_threads_list(
        ThreadsListPayload(channel_id=channel_id, limit=10, offset=0),
        user=op_user,
        container=op_container,
    )
    titles = sorted(t.title for t in result.items)
    assert titles == ["t1", "t2"]


@pytest.mark.asyncio
async def test_op_threads_item_not_found_raises(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
) -> None:
    with pytest.raises(WsCommandError) as exc_info:
        await op_threads_item(
            ThreadsItemPayload(thread_id="missing_thread_id"),
            user=op_user,
            container=op_container,
        )
    assert exc_info.value.code == "not_found"
