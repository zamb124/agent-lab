"""Push-события: каждая op публикует ожидаемый realtime-фрейм в `platform:ui_events`.

Real Redis Pub/Sub подписчик из `redis_pubsub_listener` фикстуры. Без моков.
"""

from __future__ import annotations

import pytest

from apps.sync.container import SyncContainer
from apps.sync.models.channels import ChannelCreate, ChannelType
from apps.sync.models.git import GitProvider, GitResourceKind, GitResourceRefCreate
from apps.sync.models.messages import (
    MessageContentModel,
    MessageContentType,
    MessageCreate,
    TextPlainContent,
)
from apps.sync.realtime.operations import (
    ChannelsTypingPayload,
    GitResourcesUpsertPayload,
    MessagesSendPayload,
    op_channels_create,
    op_channels_typing,
    op_git_resources_upsert,
    op_messages_send,
)
from core.models.identity_models import User
from tests.sync.integration._helpers import seed_test_namespace


async def _create_topic_channel(
    op_user: User,
    op_container: SyncContainer,
    unique_id: str,
    *,
    suffix: str,
    name: str,
) -> str:
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
    return channel.id


@pytest.mark.asyncio
async def test_op_channels_create_publishes_channel_created(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    redis_pubsub_listener,
    unique_id: str,
) -> None:
    channel_id = await _create_topic_channel(
        op_user, op_container, unique_id, suffix="pubch", name=f"PubCh {unique_id}"
    )
    events = await redis_pubsub_listener("sync/channel/created", timeout=2.0)
    assert any(e.get("payload", {}).get("id") == channel_id for e in events)


@pytest.mark.asyncio
async def test_op_messages_send_publishes_message_created(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    redis_pubsub_listener,
    unique_id: str,
) -> None:
    channel_id = await _create_topic_channel(
        op_user, op_container, unique_id, suffix="pubm", name=f"PubMsgCh {unique_id}"
    )
    msg = await op_messages_send(
        MessagesSendPayload(
            channel_id=channel_id,
            body=MessageCreate(
                contents=[
                    MessageContentModel(
                        type=MessageContentType.TEXT_PLAIN,
                        data=TextPlainContent(body="push test", mentions=None),
                        order=0,
                    )
                ]
            ),
        ),
        user=op_user,
        container=op_container,
    )
    events = await redis_pubsub_listener("sync/message/created", timeout=2.0)
    assert any(e.get("payload", {}).get("id") == msg.id for e in events)


@pytest.mark.asyncio
async def test_op_channels_typing_publishes_channel_typing(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    redis_pubsub_listener,
    unique_id: str,
) -> None:
    channel_id = await _create_topic_channel(
        op_user, op_container, unique_id, suffix="pubt", name=f"PubTypCh {unique_id}"
    )
    await op_channels_typing(
        ChannelsTypingPayload(channel_id=channel_id, typing=True, thread_id=None),
        user=op_user,
        container=op_container,
    )
    events = await redis_pubsub_listener("sync/channel/typing", timeout=2.0)
    assert any(
        e.get("payload", {}).get("channel_id") == channel_id and e.get("payload", {}).get("typing") is True
        for e in events
    )


@pytest.mark.asyncio
async def test_op_git_resources_upsert_publishes_git_resource_upserted(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    redis_pubsub_listener,
    unique_id: str,
) -> None:
    payload = GitResourcesUpsertPayload(
        body=GitResourceRefCreate(
            provider=GitProvider.GITLAB,
            kind=GitResourceKind.MERGE_REQUEST,
            project_key=f"pub/proj_{unique_id}",
            external_id="111",
            url=f"https://git.example/pub/proj_{unique_id}/-/merge_requests/111",
        )
    )
    ref = await op_git_resources_upsert(payload, user=op_user, container=op_container)
    events = await redis_pubsub_listener("sync/git_resource/upserted", timeout=2.0)
    assert any(e.get("payload", {}).get("id") == ref.id for e in events)
