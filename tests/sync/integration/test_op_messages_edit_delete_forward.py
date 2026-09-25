"""op_messages_edit / delete / forward / list."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apps.sync.models.channels import ChannelCreate, ChannelType
from apps.sync.models.message import SyncMessage
from apps.sync.models.messages import (
    MessageContentModel,
    MessageContentType,
    MessageCreate,
    MessageEdit,
    TextPlainContent,
)
from apps.sync.models.threads import ThreadCreate
from apps.sync.realtime.operations import (
    MessagesDeletePayload,
    MessagesEditPayload,
    MessagesForwardPayload,
    MessagesListPayload,
    MessagesListThreadPayload,
    MessagesSendPayload,
    ThreadsCreatePayload,
    op_channels_create,
    op_messages_delete,
    op_messages_edit,
    op_messages_forward,
    op_messages_list,
    op_messages_list_thread,
    op_messages_send,
    op_threads_create,
)
from core.models.identity_models import User
from core.websocket import WsCommandError
from tests.sync.integration._helpers import seed_test_namespace


async def _setup_two_channels(
    op_user: User, sync_di, unique_id: str
) -> tuple[str, str]:
    namespace = await seed_test_namespace(op_user, sync_di, unique_id, suffix="edf")
    ch1 = await op_channels_create(
        ChannelCreate(
            type=ChannelType.TOPIC,
            name=f"From {unique_id}",
            namespace=namespace,
            is_private=False,
        ),
        user=op_user,
        di=sync_di,
    )
    ch2 = await op_channels_create(
        ChannelCreate(
            type=ChannelType.TOPIC,
            name=f"To {unique_id}",
            namespace=namespace,
            is_private=False,
        ),
        user=op_user,
        di=sync_di,
    )
    return ch1.channel_id, ch2.channel_id


async def _send_text(
    op_user: User, sync_di, channel_id: str, text: str
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
        di=sync_di,
    )
    return msg.message_id


async def _insert_guest_text(
    sync_di,
    *,
    company_id: str,
    channel_id: str,
    text: str,
    guest_sender_id: str,
    thread_id: str | None = None,
) -> None:
    _ = await SyncMessage.create_with_contents(
        message_id=uuid4().hex,
        company_id=company_id,
        channel_id=channel_id,
        thread_id=thread_id,
        parent_message_id=None,
        sender_user_id=guest_sender_id,
        status="sent",
        sent_at=datetime.now(tz=UTC),
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body=text, mentions=None),
                order=0,
            )
        ],
    )


@pytest.mark.asyncio
async def test_op_messages_edit_by_author(
    op_user: User,
    sync_di,
    op_context: None,
    unique_id: str,
) -> None:
    ch_id, _ = await _setup_two_channels(op_user, sync_di, unique_id)
    msg_id = await _send_text(op_user, sync_di, ch_id, "before")
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
        di=sync_di,
    )
    assert edited.contents[0].data.body == "after"


@pytest.mark.asyncio
async def test_op_messages_delete_by_owner(
    op_user: User,
    sync_di,
    op_context: None,
    unique_id: str,
) -> None:
    ch_id, _ = await _setup_two_channels(op_user, sync_di, unique_id)
    msg_id = await _send_text(op_user, sync_di, ch_id, "to_delete")
    result = await op_messages_delete(
        MessagesDeletePayload(channel_id=ch_id, message_id=msg_id),
        user=op_user,
        di=sync_di,
    )
    assert result.message_id == msg_id
    assert result.channel_id == ch_id


@pytest.mark.asyncio
async def test_op_messages_forward_to_other_channel(
    op_user: User,
    sync_di,
    op_context: None,
    unique_id: str,
) -> None:
    ch_from, ch_to = await _setup_two_channels(op_user, sync_di, unique_id)
    msg_id = await _send_text(op_user, sync_di, ch_from, f"forwarded {unique_id}")
    fwd = await op_messages_forward(
        MessagesForwardPayload(
            from_channel_id=ch_from,
            message_id=msg_id,
            to_channel_id=ch_to,
            thread_id=None,
        ),
        user=op_user,
        di=sync_di,
    )
    assert fwd.contents[0].data.body == f"forwarded {unique_id}"
    assert fwd.forwarded_from is not None
    assert fwd.forwarded_from.channel_id == ch_from


@pytest.mark.asyncio
async def test_op_messages_list_returns_chronological(
    op_user: User,
    sync_di,
    op_context: None,
    unique_id: str,
) -> None:
    ch_id, _ = await _setup_two_channels(op_user, sync_di, unique_id)
    await _send_text(op_user, sync_di, ch_id, "m1")
    await _send_text(op_user, sync_di, ch_id, "m2")
    result = await op_messages_list(
        MessagesListPayload(channel_id=ch_id, limit=10),
        user=op_user,
        di=sync_di,
    )
    bodies = [m.contents[0].data.body for m in result.items]
    assert bodies == ["m1", "m2"]


@pytest.mark.asyncio
async def test_op_messages_list_guest_sender_uses_name_from_id(
    op_user: User,
    sync_di,
    op_context: None,
    unique_id: str,
) -> None:
    company_id = op_user.active_company_id
    ch_id, _ = await _setup_two_channels(op_user, sync_di, unique_id)
    guest_sender_id = f"guest:aabbccdd:{unique_id}"
    await _insert_guest_text(
        sync_di,
        company_id=company_id,
        channel_id=ch_id,
        text="from guest",
        guest_sender_id=guest_sender_id,
    )
    result = await op_messages_list(
        MessagesListPayload(channel_id=ch_id, limit=10),
        user=op_user,
        di=sync_di,
    )
    guest_items = [m for m in result.items if m.sender.user_id == guest_sender_id]
    assert len(guest_items) == 1
    assert guest_items[0].sender.display_name == unique_id
    assert guest_items[0].sender.display_name != guest_sender_id


@pytest.mark.asyncio
async def test_op_messages_list_thread_guest_sender_uses_name_from_id(
    op_user: User,
    sync_di,
    op_context: None,
    unique_id: str,
) -> None:
    company_id = op_user.active_company_id
    ch_id, _ = await _setup_two_channels(op_user, sync_di, unique_id)
    root_id = await _send_text(op_user, sync_di, ch_id, "root")
    thread = await op_threads_create(
        ThreadsCreatePayload(body=ThreadCreate(root_message_id=root_id)),
        user=op_user,
        di=sync_di,
    )
    guest_sender_id = f"guest:deadbeef:{unique_id}"
    await _insert_guest_text(
        sync_di,
        company_id=company_id,
        channel_id=ch_id,
        text="thread guest",
        guest_sender_id=guest_sender_id,
        thread_id=thread.thread_id,
    )
    result = await op_messages_list_thread(
        MessagesListThreadPayload(
            channel_id=ch_id, thread_id=thread.thread_id, limit=20, offset=0
        ),
        user=op_user,
        di=sync_di,
    )
    guest_items = [m for m in result.items if m.sender.user_id == guest_sender_id]
    assert len(guest_items) == 1
    assert guest_items[0].sender.display_name == unique_id
    assert guest_items[0].sender.display_name != guest_sender_id


@pytest.mark.asyncio
async def test_op_messages_edit_not_found_raises(
    op_user: User,
    sync_di,
    op_context: None,
    unique_id: str,
) -> None:
    ch_id, _ = await _setup_two_channels(op_user, sync_di, unique_id)
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
            di=sync_di,
        )
    assert exc_info.value.code in ("not_found", "forbidden")
