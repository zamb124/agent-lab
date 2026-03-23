"""Бизнес-обработка realtime команд (исполняется в sync-worker)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from apps.sync.channel_read_helpers import channel_read_entity_minimal
from apps.sync.db.models import SyncChannel, SyncGitResourceRef, SyncMessage, SyncSpace, SyncThread
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.db.repositories.space_repository import SpaceRepository
from apps.sync.db.repositories.thread_repository import ThreadRepository
from apps.sync.message_read_helpers import message_read_from_entity
from apps.sync.models.channels import ChannelRead, ChannelType, ChannelUpdate
from apps.sync.models.common import UserBrief
from apps.sync.models.git import GitResourceRefRead
from apps.sync.models.messages import MessageContentModel, MessageCreate, MessageRead, MessageStatus
from apps.sync.models.spaces import SpaceRead, SpaceUpdate
from apps.sync.models.threads import ThreadRead
from apps.sync.realtime.commands import (
    ChannelsCreatePayload,
    ChannelsMarkReadPayload,
    ChannelsTypingPayload,
    CommandEnvelope,
    GitResourcesUpsertPayload,
    MessagesDeletePayload,
    MessagesEditPayload,
    MessagesForwardPayload,
    MessagesMarkReadPayload,
    MessagesPinPayload,
    MessagesReactPayload,
    MessagesSendPayload,
    SpacesCreatePayload,
    SpacesUpdatePayload,
    ChannelsUpdatePayload,
    ThreadsCreatePayload,
)
from apps.sync.realtime.events import (
    MessageStatusChangedPayload,
    RealtimeEvent,
    event_channel_created,
    event_channel_pins_changed,
    event_channel_read_updated,
    event_channel_typing,
    event_git_resource_upserted,
    event_message_created,
    event_message_deleted,
    event_message_reaction_changed,
    event_message_status_changed,
    event_message_updated,
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

    if cmd.type == "spaces.update":
        payload = SpacesUpdatePayload.model_validate(cmd.payload)
        space = await _update_space(
            payload.space_id,
            payload.body,
            actor_user_id=cmd.actor_user_id,
            company_id=cmd.company_id,
            spaces=spaces,
        )
        return CommandExecutionResult(ok=True, result=space, events=[])

    if cmd.type == "channels.create":
        payload = ChannelsCreatePayload.model_validate(cmd.payload)
        channel = await _create_channel(payload.body, actor_user_id=cmd.actor_user_id, company_id=cmd.company_id, channels=channels)
        return CommandExecutionResult(ok=True, result=channel, events=[event_channel_created(channel)])

    if cmd.type == "channels.update":
        payload = ChannelsUpdatePayload.model_validate(cmd.payload)
        channel = await _update_channel(
            payload.channel_id,
            payload.body,
            actor_user_id=cmd.actor_user_id,
            company_id=cmd.company_id,
            channels=channels,
        )
        return CommandExecutionResult(ok=True, result=channel, events=[])

    if cmd.type == "channels.mark_read":
        payload = ChannelsMarkReadPayload.model_validate(cmd.payload)
        if await channels.get_member_role(payload.channel_id, cmd.actor_user_id) is None:
            raise PermissionError(
                f"Пользователь не состоит в канале {payload.channel_id}."
            )
        max_at = await messages.max_root_lane_sent_at(
            payload.channel_id,
            company_id=cmd.company_id,
        )
        read_at = max_at if max_at is not None else datetime.now(UTC)
        await channels.set_member_last_read_at(
            payload.channel_id,
            cmd.actor_user_id,
            read_at,
            company_id=cmd.company_id,
        )
        return CommandExecutionResult(
            ok=True,
            result=None,
            events=[
                event_channel_read_updated(
                    payload.channel_id,
                    cmd.actor_user_id,
                    read_at,
                ),
            ],
        )

    if cmd.type == "channels.typing":
        payload = ChannelsTypingPayload.model_validate(cmd.payload)
        if not await channels.is_member(payload.channel_id, cmd.actor_user_id, company_id=cmd.company_id):
            raise PermissionError(
                f"Пользователь не состоит в канале {payload.channel_id}."
            )
        if payload.thread_id is not None and payload.thread_id != "":
            row = await threads.get(payload.thread_id)
            if row is None:
                raise ValueError(f"Тред {payload.thread_id} не найден.")
            if row.company_id != cmd.company_id:
                raise ValueError("Тред не принадлежит компании.")
            if row.channel_id != payload.channel_id:
                raise ValueError("Тред не принадлежит указанному каналу.")
        if user_repository is None:
            raise ValueError("user_repository обязателен для channels.typing.")
        user_brief = await _user_brief(user_repository, cmd.actor_user_id)
        return CommandExecutionResult(
            ok=True,
            result=None,
            events=[
                event_channel_typing(
                    channel_id=payload.channel_id,
                    thread_id=payload.thread_id if payload.thread_id else None,
                    typing=payload.typing,
                    user=user_brief,
                ),
            ],
        )

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

    if cmd.type == "messages.edit":
        payload = MessagesEditPayload.model_validate(cmd.payload)
        out, evs = await _handle_messages_edit(
            payload, cmd.actor_user_id, cmd.company_id, messages, channels, user_repository
        )
        return CommandExecutionResult(ok=True, result=out, events=evs)

    if cmd.type == "messages.delete":
        payload = MessagesDeletePayload.model_validate(cmd.payload)
        evs = await _handle_messages_delete(
            payload, cmd.actor_user_id, cmd.company_id, messages, channels
        )
        return CommandExecutionResult(ok=True, result={"message_id": payload.message_id}, events=evs)

    if cmd.type == "messages.forward":
        payload = MessagesForwardPayload.model_validate(cmd.payload)
        out, evs = await _handle_messages_forward(
            payload, cmd.actor_user_id, cmd.company_id, messages, channels, user_repository
        )
        return CommandExecutionResult(ok=True, result=out, events=evs)

    if cmd.type == "messages.react":
        payload = MessagesReactPayload.model_validate(cmd.payload)
        out, evs = await _handle_messages_react(
            payload, cmd.actor_user_id, cmd.company_id, messages, channels, user_repository
        )
        return CommandExecutionResult(ok=True, result=out, events=evs)

    if cmd.type == "messages.pin":
        payload = MessagesPinPayload.model_validate(cmd.payload)
        out, evs = await _handle_messages_pin(
            payload, cmd.actor_user_id, cmd.company_id, messages, channels
        )
        return CommandExecutionResult(ok=True, result=out, events=evs)

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
    return UserBrief(user_id=user_id, display_name=display_name, avatar_url=avatar_url)


async def _message_read_from_db(
    m: SyncMessage,
    messages: MessageRepository,
    user_repository: Optional[UserRepository],
) -> MessageRead:
    content_rows = await messages.list_contents(m.message_id)
    contents: list[MessageContentModel] = []
    for row in content_rows:
        contents.append(
            MessageContentModel.model_validate(
                {"type": row.type, "data": row.data, "order": row.order}
            )
        )
    sender = await _user_brief(user_repository, m.sender_user_id)
    return message_read_from_entity(m=m, contents=contents, sender=sender)


def _channel_read_entity(entity: SyncChannel) -> ChannelRead:
    return channel_read_entity_minimal(entity)


def _apply_reaction_json(
    reactions_raw: object,
    actor_user_id: str,
    emoji: str | None,
    now: datetime,
) -> list[dict]:
    reactions = reactions_raw if isinstance(reactions_raw, list) else []
    filtered: list[dict] = []
    for r in reactions:
        if isinstance(r, dict) and r.get("user_id") != actor_user_id:
            filtered.append(r)
    if emoji is None:
        return filtered
    filtered.append(
        {
            "user_id": actor_user_id,
            "emoji": emoji,
            "created_at": now.isoformat(),
        }
    )
    return filtered


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
        avatar_url=entity.avatar_url,
        created_at=entity.created_at,
        created_by_user_id=actor_user_id,
    )


async def _update_space(
    space_id: str,
    body: SpaceUpdate,
    *,
    actor_user_id: str,
    company_id: str,
    spaces: SpaceRepository,
) -> SpaceRead:
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise ValueError("Нет полей для обновления пространства.")
    entity = await spaces.get(space_id)
    if entity is None:
        raise ValueError(f"Пространство {space_id} не найдено.")
    if entity.company_id != company_id:
        raise PermissionError("Пространство принадлежит другой компании.")
    if "name" in data:
        entity.name = data["name"]
    if "description" in data:
        entity.description = data["description"]
    if "avatar_url" in data:
        entity.avatar_url = data["avatar_url"]
    await spaces.update(entity)
    return SpaceRead(
        id=entity.space_id,
        name=entity.name,
        description=entity.description,
        avatar_url=entity.avatar_url,
        created_at=entity.created_at,
        created_by_user_id=entity.created_by_user_id,
    )


async def _update_channel(
    channel_id: str,
    body: ChannelUpdate,
    *,
    actor_user_id: str,
    company_id: str,
    channels: ChannelRepository,
) -> ChannelRead:
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise ValueError("Нет полей для обновления канала.")
    role = await channels.get_member_role(channel_id, actor_user_id)
    if role is None:
        raise PermissionError(f"Пользователь не состоит в канале {channel_id}.")
    if role not in ("owner", "admin"):
        raise PermissionError("Изменение настроек канала доступно только ролям owner и admin.")
    entity = await channels.get(channel_id)
    if entity is None:
        raise ValueError(f"Канал {channel_id} не найден.")
    if entity.company_id != company_id:
        raise PermissionError("Канал принадлежит другой компании.")
    if "name" in data:
        entity.name = data["name"]
    if "is_private" in data:
        entity.is_private = data["is_private"]
    if "avatar_url" in data:
        entity.avatar_url = data["avatar_url"]
    await channels.update(entity)
    return _channel_read_entity(entity)


async def _create_channel(body, *, actor_user_id: str, company_id: str, channels: ChannelRepository) -> ChannelRead:
    if body.type == ChannelType.TOPIC:
        if body.space_id is None:
            raise ValueError("Для topic обязателен space_id.")
        if body.name is None:
            raise ValueError("Для topic обязателен name.")

    if body.type == ChannelType.DIRECT:
        if body.space_id is not None:
            raise ValueError("Для direct не задают space_id.")
        mids = body.member_ids
        if mids is None or len(mids) != 1:
            raise ValueError("Для direct в member_ids должен быть ровно один собеседник.")
        if mids[0] == actor_user_id:
            raise ValueError("Нельзя создать личный канал с самим собой.")

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
        pinned_message_ids=[],
    )
    await channels.create(entity)
    await channels.add_member_if_missing(channel_id, actor_user_id, "owner", company_id)

    if body.member_ids is not None:
        for member_id in body.member_ids:
            await channels.add_member_if_missing(channel_id, member_id, "member", company_id)

    return _channel_read_entity(entity)


async def _send_message(
    channel_id: str,
    body,
    *,
    actor_user_id: str,
    company_id: str,
    messages: MessageRepository,
    user_repository: Optional[UserRepository] = None,
    forwarded_from_channel_id: Optional[str] = None,
    forwarded_from_channel_name: Optional[str] = None,
) -> MessageRead:
    message_id = uuid4().hex
    sent_at = datetime.now(tz=UTC)
    row = await messages.create_message(
        message_id=message_id,
        company_id=company_id,
        channel_id=channel_id,
        thread_id=body.thread_id,
        parent_message_id=body.parent_message_id,
        sender_user_id=actor_user_id,
        status=MessageStatus.SENT.value,
        sent_at=sent_at,
        contents=body.contents,
        forwarded_from_channel_id=forwarded_from_channel_id,
        forwarded_from_channel_name=forwarded_from_channel_name,
    )
    return await _message_read_from_db(row, messages, user_repository)


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


async def _handle_messages_edit(
    payload: MessagesEditPayload,
    actor_user_id: str,
    company_id: str,
    messages: MessageRepository,
    channels: ChannelRepository,
    user_repository: Optional[UserRepository],
) -> tuple[MessageRead, list[RealtimeEvent]]:
    if user_repository is None:
        raise ValueError("user_repository обязателен.")
    if not await channels.is_member(payload.channel_id, actor_user_id, company_id=company_id):
        raise ValueError("Нет доступа к каналу.")
    m = await messages.get_by_id_for_company(payload.message_id, company_id)
    if m is None:
        raise ValueError("Сообщение не найдено.")
    if m.channel_id != payload.channel_id:
        raise ValueError("Несовпадение канала.")
    if m.deleted_at is not None:
        raise ValueError("Сообщение удалено.")
    if m.sender_user_id != actor_user_id:
        raise ValueError("Редактировать может только автор.")
    edited_at = datetime.now(tz=UTC)
    await messages.replace_message_contents(payload.message_id, payload.body.contents, edited_at)
    m2 = await messages.get_by_id_for_company(payload.message_id, company_id)
    if m2 is None:
        raise RuntimeError("Сообщение пропало после редактирования.")
    read = await _message_read_from_db(m2, messages, user_repository)
    return read, [event_message_updated(read)]


async def _handle_messages_delete(
    payload: MessagesDeletePayload,
    actor_user_id: str,
    company_id: str,
    messages: MessageRepository,
    channels: ChannelRepository,
) -> list[RealtimeEvent]:
    if not await channels.is_member(payload.channel_id, actor_user_id, company_id=company_id):
        raise ValueError("Нет доступа к каналу.")
    m = await messages.get_by_id_for_company(payload.message_id, company_id)
    if m is None:
        raise ValueError("Сообщение не найдено.")
    if m.channel_id != payload.channel_id:
        raise ValueError("Несовпадение канала.")
    role = await channels.get_member_role(payload.channel_id, actor_user_id)
    if role is None:
        raise ValueError("Нет доступа к каналу.")
    if m.sender_user_id != actor_user_id and role != "owner":
        raise ValueError("Недостаточно прав на удаление.")
    now = datetime.now(tz=UTC)
    await messages.soft_delete_message(payload.message_id, now)
    ch = await channels.get(payload.channel_id)
    evs: list[RealtimeEvent] = [event_message_deleted(payload.channel_id, payload.message_id)]
    if ch is not None:
        pids = list(ch.pinned_message_ids or []) if isinstance(ch.pinned_message_ids, list) else []
        if payload.message_id in pids:
            new_pids = [x for x in pids if x != payload.message_id]
            await channels.set_pinned_message_ids(payload.channel_id, new_pids, company_id=company_id)
            ch2 = await channels.get(payload.channel_id)
            if ch2 is not None:
                evs.append(event_channel_pins_changed(_channel_read_entity(ch2)))
    return evs


async def _handle_messages_forward(
    payload: MessagesForwardPayload,
    actor_user_id: str,
    company_id: str,
    messages: MessageRepository,
    channels: ChannelRepository,
    user_repository: Optional[UserRepository],
) -> tuple[MessageRead, list[RealtimeEvent]]:
    if not await channels.is_member(payload.from_channel_id, actor_user_id, company_id=company_id):
        raise ValueError("Нет доступа к исходному каналу.")
    if not await channels.is_member(payload.to_channel_id, actor_user_id, company_id=company_id):
        raise ValueError("Нет доступа к целевому каналу.")
    m = await messages.get_by_id_for_company(payload.message_id, company_id)
    if m is None:
        raise ValueError("Сообщение не найдено.")
    if m.channel_id != payload.from_channel_id:
        raise ValueError("Несовпадение канала.")
    if m.deleted_at is not None:
        raise ValueError("Нельзя переслать удалённое сообщение.")
    content_rows = await messages.list_contents(m.message_id)
    contents: list[MessageContentModel] = []
    for row in content_rows:
        contents.append(
            MessageContentModel.model_validate(
                {"type": row.type, "data": row.data, "order": row.order}
            )
        )
    body = MessageCreate(
        thread_id=payload.thread_id,
        parent_message_id=None,
        contents=contents,
    )
    src_ch = await channels.get(payload.from_channel_id)
    if src_ch is None:
        raise ValueError("Исходный канал не найден.")
    raw_name = src_ch.name
    fwd_label = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() != "" else None
    new_read = await _send_message(
        payload.to_channel_id,
        body,
        actor_user_id=actor_user_id,
        company_id=company_id,
        messages=messages,
        user_repository=user_repository,
        forwarded_from_channel_id=payload.from_channel_id,
        forwarded_from_channel_name=fwd_label,
    )
    return new_read, [event_message_created(new_read)]


async def _handle_messages_react(
    payload: MessagesReactPayload,
    actor_user_id: str,
    company_id: str,
    messages: MessageRepository,
    channels: ChannelRepository,
    user_repository: Optional[UserRepository],
) -> tuple[MessageRead, list[RealtimeEvent]]:
    if user_repository is None:
        raise ValueError("user_repository обязателен.")
    if not await channels.is_member(payload.channel_id, actor_user_id, company_id=company_id):
        raise ValueError("Нет доступа к каналу.")
    m = await messages.get_by_id_for_company(payload.message_id, company_id)
    if m is None:
        raise ValueError("Сообщение не найдено.")
    if m.channel_id != payload.channel_id:
        raise ValueError("Несовпадение канала.")
    if m.deleted_at is not None:
        raise ValueError("Сообщение удалено.")
    now = datetime.now(tz=UTC)
    new_reactions = _apply_reaction_json(m.reactions, actor_user_id, payload.emoji, now)
    await messages.set_message_reactions(payload.message_id, new_reactions)
    m2 = await messages.get_by_id_for_company(payload.message_id, company_id)
    if m2 is None:
        raise RuntimeError("Сообщение пропало после реакции.")
    read = await _message_read_from_db(m2, messages, user_repository)
    return read, [
        event_message_reaction_changed(payload.channel_id, payload.message_id, new_reactions),
        event_message_updated(read),
    ]


async def _handle_messages_pin(
    payload: MessagesPinPayload,
    actor_user_id: str,
    company_id: str,
    messages: MessageRepository,
    channels: ChannelRepository,
) -> tuple[ChannelRead, list[RealtimeEvent]]:
    if not await channels.is_member(payload.channel_id, actor_user_id, company_id=company_id):
        raise ValueError("Нет доступа к каналу.")
    role = await channels.get_member_role(payload.channel_id, actor_user_id)
    if role != "owner":
        raise ValueError("Закреплять может только владелец канала.")
    m = await messages.get_by_id_for_company(payload.message_id, company_id)
    if m is None:
        raise ValueError("Сообщение не найдено.")
    if m.channel_id != payload.channel_id:
        raise ValueError("Несовпадение канала.")
    if m.deleted_at is not None:
        raise ValueError("Нельзя закрепить удалённое сообщение.")
    ch = await channels.get(payload.channel_id)
    if ch is None:
        raise ValueError("Канал не найден.")
    pids = list(ch.pinned_message_ids or []) if isinstance(ch.pinned_message_ids, list) else []
    if payload.action == "add":
        if payload.message_id not in pids:
            pids.insert(0, payload.message_id)
    else:
        pids = [x for x in pids if x != payload.message_id]
    await channels.set_pinned_message_ids(payload.channel_id, pids, company_id=company_id)
    ch2 = await channels.get(payload.channel_id)
    if ch2 is None:
        raise RuntimeError("Канал пропал после обновления.")
    cr = _channel_read_entity(ch2)
    return cr, [event_channel_pins_changed(cr)]
