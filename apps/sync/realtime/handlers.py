"""Бизнес-обработка realtime команд (исполняется в sync-worker)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from apps.sync.db.models import SyncSpace, SyncChannel, SyncThread, SyncGitResourceRef
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.db.repositories.space_repository import SpaceRepository
from apps.sync.db.repositories.thread_repository import ThreadRepository
from apps.sync.models.channels import ChannelRead, ChannelType
from apps.sync.models.common import UserBrief
from apps.sync.models.git import GitResourceRefRead
from apps.sync.models.messages import MessageRead, MessageStatus
from apps.sync.models.spaces import SpaceRead
from apps.sync.models.threads import ThreadRead
from apps.sync.realtime.commands import (
    ChannelsCreatePayload,
    CommandEnvelope,
    GitResourcesUpsertPayload,
    MessagesMarkReadPayload,
    MessagesSendPayload,
    SpacesCreatePayload,
    ThreadsCreatePayload,
)
from apps.sync.realtime.events import (
    MessageStatusChangedPayload,
    RealtimeEvent,
    event_channel_created,
    event_git_resource_upserted,
    event_message_created,
    event_message_status_changed,
    event_space_created,
    event_thread_created,
)
from core.db.repositories.user_repository import UserRepository


class CommandExecutionResult:
    def __init__(self, *, ok: bool, result: object | None, events: list[RealtimeEvent]) -> None:
        self.ok = ok
        self.result = result
        self.events = events


async def execute_command(
    cmd: CommandEnvelope,
    *,
    spaces: SpaceRepository,
    channels: ChannelRepository,
    threads: ThreadRepository,
    messages: MessageRepository,
    git_refs: GitResourceRefRepository,
    user_repository: Optional[UserRepository] = None,
) -> CommandExecutionResult:
    if cmd.type == "spaces.create":
        payload = SpacesCreatePayload.model_validate(cmd.payload)
        space = await _create_space(payload.body, actor_user_id=cmd.actor_user_id, company_id=cmd.company_id, spaces=spaces)
        return CommandExecutionResult(ok=True, result=space, events=[event_space_created(space)])

    if cmd.type == "channels.create":
        payload = ChannelsCreatePayload.model_validate(cmd.payload)
        channel = await _create_channel(payload.body, actor_user_id=cmd.actor_user_id, company_id=cmd.company_id, channels=channels)
        return CommandExecutionResult(ok=True, result=channel, events=[event_channel_created(channel)])

    if cmd.type == "threads.create":
        payload = ThreadsCreatePayload.model_validate(cmd.payload)
        thread = await _create_thread(
            payload.body,
            actor_user_id=cmd.actor_user_id,
            company_id=cmd.company_id,
            threads=threads,
            messages=messages,
            user_repository=user_repository,
        )
        return CommandExecutionResult(ok=True, result=thread, events=[event_thread_created(thread)])

    if cmd.type == "messages.send":
        payload = MessagesSendPayload.model_validate(cmd.payload)
        message = await _send_message(
            payload.channel_id,
            payload.body,
            actor_user_id=cmd.actor_user_id,
            company_id=cmd.company_id,
            messages=messages,
            user_repository=user_repository,
        )
        return CommandExecutionResult(ok=True, result=message, events=[event_message_created(message)])

    if cmd.type == "messages.mark_read":
        payload = MessagesMarkReadPayload.model_validate(cmd.payload)
        event = event_message_status_changed(
            payload.channel_id,
            MessageStatusChangedPayload(message_id=payload.message_id, status=MessageStatus.READ),
        )
        return CommandExecutionResult(ok=True, result=None, events=[event])

    if cmd.type == "git.resources.upsert":
        payload = GitResourcesUpsertPayload.model_validate(cmd.payload)
        ref = await _upsert_git_resource(payload.body, company_id=cmd.company_id, git_refs=git_refs)
        return CommandExecutionResult(ok=True, result=ref, events=[event_git_resource_upserted(ref)])

    raise RuntimeError(f"Неизвестный тип команды: {cmd.type!r}.")


async def _user_brief(user_repository: Optional[UserRepository], user_id: str) -> UserBrief:
    display_name = user_id
    avatar_url = None
    if user_repository is not None:
        u = await user_repository.get(user_id)
        if u is not None:
            display_name = u.name
            avatar_url = u.avatar_url
    return UserBrief(id=user_id, display_name=display_name, avatar_url=avatar_url)


async def _create_space(body, *, actor_user_id: str, company_id: str, spaces: SpaceRepository) -> SpaceRead:
    space_id = uuid4().hex
    entity = SyncSpace(
        space_id=space_id,
        company_id=company_id,
        name=body.name,
        description=body.description,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
    )
    await spaces.create(entity)
    return SpaceRead(
        id=space_id,
        name=entity.name,
        description=entity.description,
        created_at=entity.created_at,
        created_by_user_id=actor_user_id,
    )


async def _create_channel(body, *, actor_user_id: str, company_id: str, channels: ChannelRepository) -> ChannelRead:
    if body.type == ChannelType.TOPIC:
        if body.space_id is None:
            raise ValueError("Для topic обязателен space_id.")
        if body.name is None:
            raise ValueError("Для topic обязателен name.")

    channel_id = uuid4().hex
    entity = SyncChannel(
        channel_id=channel_id,
        company_id=company_id,
        space_id=body.space_id,
        type=body.type.value,
        name=body.name,
        is_private=body.is_private,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
    )
    await channels.create(entity)
    await channels.add_member_if_missing(channel_id, actor_user_id, "owner", company_id)

    if body.member_ids is not None:
        for member_id in body.member_ids:
            await channels.add_member_if_missing(channel_id, member_id, "member", company_id)

    return ChannelRead(
        id=channel_id,
        space_id=body.space_id,
        type=body.type,
        name=body.name,
        is_private=body.is_private,
        created_at=entity.created_at,
        created_by_user_id=actor_user_id,
    )


async def _send_message(
    channel_id: str,
    body,
    *,
    actor_user_id: str,
    company_id: str,
    messages: MessageRepository,
    user_repository: Optional[UserRepository] = None,
) -> MessageRead:
    message_id = uuid4().hex
    sent_at = datetime.now(tz=UTC)
    await messages.create_message(
        message_id=message_id,
        company_id=company_id,
        channel_id=channel_id,
        thread_id=body.thread_id,
        parent_message_id=body.parent_message_id,
        sender_user_id=actor_user_id,
        status=MessageStatus.SENT.value,
        sent_at=sent_at,
        contents=body.contents,
    )
    sender = await _user_brief(user_repository, actor_user_id)
    return MessageRead(
        id=message_id,
        channel_id=channel_id,
        thread_id=body.thread_id,
        parent_message_id=body.parent_message_id,
        sender=sender,
        status=MessageStatus.SENT,
        sent_at=sent_at,
        edited_at=None,
        contents=body.contents,
    )


async def _create_thread(
    body,
    *,
    actor_user_id: str,
    company_id: str,
    threads: ThreadRepository,
    messages: MessageRepository,
    user_repository: Optional[UserRepository] = None,
) -> ThreadRead:
    root = await messages.get(body.root_message_id)
    if root is None:
        raise ValueError("root_message_id не найден.")

    thread_id = uuid4().hex
    entity = SyncThread(
        thread_id=thread_id,
        company_id=company_id,
        channel_id=root.channel_id,
        root_message_id=body.root_message_id,
        title=body.title,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
    )
    await threads.create(entity)
    created_by = await _user_brief(user_repository, actor_user_id)
    return ThreadRead(
        id=thread_id,
        channel_id=root.channel_id,
        root_message_id=body.root_message_id,
        title=body.title,
        created_at=entity.created_at,
        created_by=created_by,
    )


async def _upsert_git_resource(body, *, company_id: str, git_refs: GitResourceRefRepository) -> GitResourceRefRead:
    ref_id = f"{body.provider.value}:{body.kind.value}:{body.project_key}:{body.external_id}"
    entity = SyncGitResourceRef(
        git_ref_id=ref_id,
        company_id=company_id,
        provider=body.provider.value,
        kind=body.kind.value,
        project_key=body.project_key,
        external_id=body.external_id,
        url=body.url,
        extra=body.extra or {},
    )
    await git_refs.update(entity)
    return GitResourceRefRead(
        id=ref_id,
        provider=body.provider,
        kind=body.kind,
        project_key=body.project_key,
        external_id=body.external_id,
        url=body.url,
        extra=body.extra or {},
    )
