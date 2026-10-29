"""Сценарии команд каналов Sync."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from apps.sync.channel_read_helpers import (
    channel_read_entity_minimal,
    channel_read_from_entity,
)
from apps.sync.events import (
    event_channel_created,
    event_channel_member_added,
    event_channel_read_updated,
    event_channel_typing,
)
from apps.sync.models.channel import SyncChannel
from apps.sync.models.channel_member import SyncChannelMember
from apps.sync.models.channels import (
    ChannelCreate,
    ChannelMemberRead,
    ChannelMemberRole,
    ChannelRead,
    ChannelType,
    ChannelUpdate,
)
from apps.sync.models.common import UserBrief
from apps.sync.models.company_members import CompanyMemberRead
from apps.sync.models.message import SyncMessage
from apps.sync.models.threads import SyncThread
from apps.sync.services.sync_channel_access_service import SyncChannelAccessService
from apps.sync.ws_presence import batch_peer_presence
from core.authz.models import AuthzCheckItem, AuthzObject, AuthzSubject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation
from core.config import get_settings
from core.events import publish_events
from core.models.identity_models import Company, User
from core.namespace import NamespaceService
from core.pagination import ListResponse, OffsetPage
from core.websocket import WsCommandError


async def _channel_read_for_viewer(
    entity: SyncChannel,
    *,
    viewer_user_id: str,
    company_id: str,
    channel_access: SyncChannelAccessService,
) -> ChannelRead:
    """ChannelRead для ответа create/list: direct с заполненным peer."""
    return await channel_read_from_entity(
        entity,
        viewer_user_id=viewer_user_id,
        channel_access=channel_access,
        resolve_user=True,
        company_id=company_id,
        lane_summary=None,
    )


async def _update_channel_row(
    channel_id: str,
    body: ChannelUpdate,
    *,
    actor_user_id: str,
    company_id: str,
    authz: AuthzService,
) -> ChannelRead:
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise WsCommandError("ws_invalid_payload", "No fields to update on the channel.", error_code='ws_invalid_payload')
    if not await authz.can_view(
        AuthzObject.sync_channel(channel_id), user_id=actor_user_id
    ):
        raise WsCommandError("forbidden", f"User is not a member of channel {channel_id}.", error_code='forbidden')
    if not await authz.can_admin(
        AuthzObject.sync_channel(channel_id), user_id=actor_user_id
    ):
        raise WsCommandError(
            "forbidden",
            "Channel settings can be changed only by owner and admin roles.",
                  error_code='forbidden',
              )
    entity = await SyncChannel.get(channel_id)
    if entity is None:
        raise WsCommandError("not_found", f"Channel {channel_id} not found.", error_code='not_found')
    if entity.company_id != company_id:
        raise WsCommandError("forbidden", "Channel belongs to another company.", error_code='forbidden')
    if "name" in data:
        entity.name = data["name"]
    if "is_private" in data:
        entity.is_private = data["is_private"]
    if "avatar_url" in data:
        entity.avatar_url = data["avatar_url"]
    if "transcribe_voice_messages" in data:
        entity.transcribe_voice_messages = data["transcribe_voice_messages"]
    if "speech_to_chat_enabled" in data:
        entity.speech_to_chat_enabled = data["speech_to_chat_enabled"]
    _ = await entity.save(using="sync")
    return channel_read_entity_minimal(entity)


async def _find_existing_direct_for_pair(
    *,
    user_a: str,
    user_b: str,
    namespace: str,
    company_id: str,
    channel_access: SyncChannelAccessService,
) -> SyncChannel | None:
    """Один личный чат с собеседником в рамках namespace (без дублей create)."""
    candidates = await SyncChannel.list_for_both_members_by_type_and_name_asc(
        user_a,
        user_b,
        company_id=company_id,
        limit=200,
        offset=0,
    )
    for ch in candidates:
        if ch.type != ChannelType.DIRECT.value:
            continue
        if ch.namespace != namespace:
            continue
        member_ids = await channel_access.list_member_user_ids(ch.channel_id)
        if len(member_ids) == 2:
            return ch
    return None


async def _create_channel_row(
    body: ChannelCreate,
    *,
    actor_user_id: str,
    company_id: str,
    channel_access: SyncChannelAccessService,
    namespaces: NamespaceService,
) -> tuple[ChannelRead, bool]:
    """Создаёт канал, привязанный к платформенному `namespace`.

    Дефолты STT (`transcribe_voice_messages`, `speech_to_chat_enabled`)
    берутся из `Namespace.sync_settings`; на канале можно перекрыть точечно
    через `body.transcribe_voice_messages` / `body.speech_to_chat_enabled`.

    Возвращает (ChannelRead, created_new). Для direct с тем же собеседником
    и namespace возвращается существующий канал с created_new=False (без дублей).
    """
    if body.type == ChannelType.TOPIC:
        if body.namespace is None or body.namespace == "":
            raise ValueError("topic requires namespace.")
        if body.name is None:
            raise ValueError("topic requires name.")

    if body.type == ChannelType.DIRECT:
        mids = body.member_ids
        if mids is None or len(mids) != 1:
            raise ValueError("direct requires exactly one peer in member_ids.")
        if mids[0] == actor_user_id:
            raise ValueError("Cannot create a direct channel with yourself.")

    if body.type == ChannelType.CALENDAR_MEETING:
        if body.name is None or body.name.strip() == "":
            raise ValueError("calendar_meeting requires name (meeting title).")

    namespace = body.namespace if body.namespace else "default"
    ns_entity = await namespaces.ensure_exists(namespace)
    if ns_entity.company_id != company_id:
        raise PermissionError(f"Namespace '{namespace}' belongs to another company.")
    sync_defaults = ns_entity.sync_settings
    transcribe_voice = bool(sync_defaults.transcribe_voice_messages) if sync_defaults else False
    speech_to_chat = bool(sync_defaults.speech_to_chat_enabled) if sync_defaults else False
    if body.transcribe_voice_messages is not None:
        transcribe_voice = body.transcribe_voice_messages
    if body.speech_to_chat_enabled is not None:
        speech_to_chat = body.speech_to_chat_enabled

    if body.type == ChannelType.DIRECT:
        direct_member_ids = body.member_ids
        if direct_member_ids is None:
            raise ValueError("direct requires exactly one peer in member_ids.")
        peer_id = direct_member_ids[0]
        existing = await _find_existing_direct_for_pair(
            user_a=actor_user_id,
            user_b=peer_id,
            namespace=namespace,
            company_id=company_id,
            channel_access=channel_access,
        )
        if existing is not None:
            read = await _channel_read_for_viewer(
                existing,
                viewer_user_id=actor_user_id,
                company_id=company_id,
                channel_access=channel_access,
            )
            return read, False

    channel_id = uuid4().hex
    entity = SyncChannel(
        channel_id=channel_id,
        company_id=company_id,
        namespace=namespace,
        type=body.type.value,
        name=body.name,
        is_private=body.is_private,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
        pinned_message_ids=[],
        transcribe_voice_messages=transcribe_voice,
        speech_to_chat_enabled=speech_to_chat,
    )
    _ = await SyncChannel.set(entity)
    member_ids = list(body.member_ids) if body.member_ids is not None else []
    await SyncChannelMember.ensure_member(
        channel_id, actor_user_id, company_id=company_id
    )
    for member_id in member_ids:
        await SyncChannelMember.ensure_member(
            channel_id, member_id, company_id=company_id
        )
    try:
        await channel_access.sync_channel_created(
            channel_id,
            company_id=company_id,
            owner_user_id=actor_user_id,
            member_user_ids=member_ids,
        )
    except Exception:
        _ = await SyncChannel.delete_by_id(channel_id)
        raise

    read = await _channel_read_for_viewer(
        entity,
        viewer_user_id=actor_user_id,
        company_id=company_id,
        channel_access=channel_access,
    )
    return read, True


class SyncChannelService:
    """Команды каналов: список, создание, участники, прочтение, typing."""

    def __init__(
        self,
        authz: AuthzService,
        channel_access: SyncChannelAccessService,
        namespaces: NamespaceService,
    ) -> None:
        self._authz: AuthzService = authz
        self._channel_access: SyncChannelAccessService = channel_access
        self._namespaces: NamespaceService = namespaces

    async def filter_visible(
        self,
        channels: list[SyncChannel],
        *,
        user_id: str,
        peer_user_id: str | None = None,
    ) -> list[SyncChannel]:
        """SQL-кандидаты пересекаются с FGA can_view."""
        if not channels:
            return []
        checks: list[AuthzCheckItem] = [
            AuthzCheckItem(
                subject=AuthzSubject.user(user_id),
                relation=AuthzRelation.CAN_VIEW,
                obj=AuthzObject.sync_channel(channel.channel_id),
                correlation_id=channel.channel_id,
            )
            for channel in channels
        ]
        if peer_user_id is not None:
            checks.extend(
                AuthzCheckItem(
                    subject=AuthzSubject.user(peer_user_id),
                    relation=AuthzRelation.CAN_VIEW,
                    obj=AuthzObject.sync_channel(channel.channel_id),
                    correlation_id=f"peer:{channel.channel_id}",
                )
                for channel in channels
            )
        allowed = await self._authz.batch_check(checks)
        if peer_user_id is None:
            return [
                channel
                for channel, ok in zip(channels, allowed, strict=True)
                if ok
            ]
        viewer_flags = allowed[: len(channels)]
        peer_flags = allowed[len(channels) :]
        return [
            channel
            for channel, viewer_ok, peer_ok in zip(
                channels, viewer_flags, peer_flags, strict=True
            )
            if viewer_ok and peer_ok
        ]

    async def list_channels(
        self,
        *,
        user_id: str,
        company_id: str,
        namespace: str | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[ChannelRead]:
        candidates = await SyncChannel.list_member_channels_by_type_and_name_asc(
            user_id,
            namespace=namespace,
            limit=limit,
            offset=offset,
            company_id=company_id,
        )
        channels = await self.filter_visible(candidates, user_id=user_id)
        channel_ids = [channel.channel_id for channel in channels]
        summaries = await SyncMessage.channel_lane_summaries_by_channel_id_asc_and_sent_at_desc(
            company_id=company_id,
            channel_ids=channel_ids,
            viewer_user_id=user_id,
        )
        items: list[ChannelRead] = []
        for channel in channels:
            items.append(
                await channel_read_from_entity(
                    channel,
                    viewer_user_id=user_id,
                    channel_access=self._channel_access,
                    resolve_user=True,
                    company_id=company_id,
                    lane_summary=summaries[channel.channel_id],
                )
            )
        return OffsetPage[ChannelRead](
            items=items, total=len(items), limit=limit, offset=offset
        )

    async def create_channel(
        self,
        body: ChannelCreate,
        *,
        actor_user_id: str,
        company_id: str,
    ) -> ChannelRead:
        channel, created_new = await _create_channel_row(
            body,
            actor_user_id=actor_user_id,
            company_id=company_id,
            channel_access=self._channel_access,
            namespaces=self._namespaces,
        )
        if created_new:
            recipients = await self._channel_access.list_member_user_ids(channel.channel_id)
            await publish_events(
                [
                    event_channel_created(
                        channel, company_id=company_id, recipient_user_ids=recipients
                    ),
                ]
            )
        return channel

    async def update_channel(
        self,
        channel_id: str,
        body: ChannelUpdate,
        *,
        actor_user_id: str,
        company_id: str,
    ) -> ChannelRead:
        return await _update_channel_row(
            channel_id,
            body,
            actor_user_id=actor_user_id,
            company_id=company_id,
            authz=self._authz,
        )

    async def mark_read(
        self, *, channel_id: str, user_id: str, company_id: str
    ) -> None:
        if not await self._authz.can_view(
            AuthzObject.sync_channel(channel_id), user_id=user_id
        ):
            raise WsCommandError(
                "forbidden",
                f"User is not a member of channel {channel_id}.",
                error_code="forbidden",
            )
        max_at = await SyncMessage.max_root_lane_sent_at(channel_id, company_id=company_id)
        read_at = max_at if max_at is not None else datetime.now(UTC)
        await SyncChannelMember.update_last_read_at(
            channel_id, user_id, read_at, company_id=company_id
        )
        recipients = await self._channel_access.list_member_user_ids(channel_id)
        await publish_events(
            [
                event_channel_read_updated(
                    channel_id,
                    user_id,
                    read_at,
                    company_id=company_id,
                    recipient_user_ids=recipients,
                ),
            ]
        )

    async def set_typing(
        self,
        *,
        channel_id: str,
        thread_id: str | None,
        typing: bool,
        user_id: str,
        company_id: str,
    ) -> None:
        if not await self._authz.can_view(
            AuthzObject.sync_channel(channel_id), user_id=user_id
        ):
            raise WsCommandError(
                "forbidden",
                f"User is not a member of channel {channel_id}.",
                error_code="forbidden",
            )
        if thread_id is not None and thread_id != "":
            thread = await SyncThread.get(thread_id)
            if thread is None:
                raise WsCommandError(
                    "not_found", f"Thread {thread_id} not found.", error_code="not_found"
                )
            if thread.company_id != company_id:
                raise WsCommandError(
                    "forbidden", "Thread does not belong to the company.", error_code="forbidden"
                )
            if thread.channel_id != channel_id:
                raise WsCommandError(
                    "forbidden",
                    "Thread does not belong to the given channel.",
                    error_code="forbidden",
                )
        user_obj = await User.get(user_id)
        if user_obj is None:
            raise WsCommandError(
                "not_found", f"User {user_id} not found.", error_code="not_found"
            )
        user_brief = UserBrief(
            user_id=user_id, display_name=user_obj.name, avatar_url=user_obj.avatar_url
        )
        recipients = await self._channel_access.list_member_user_ids(channel_id)
        await publish_events(
            [
                event_channel_typing(
                    channel_id=channel_id,
                    thread_id=thread_id if thread_id else None,
                    typing=typing,
                    user=user_brief,
                    company_id=company_id,
                    recipient_user_ids=recipients,
                ),
            ]
        )

    async def update_notification_settings(
        self,
        *,
        channel_id: str,
        notifications_muted: bool,
        user_id: str,
        company_id: str,
    ) -> ChannelRead:
        channel = await SyncChannel.get(channel_id)
        if channel is None or channel.company_id != company_id:
            raise WsCommandError("not_found", "Channel not found.", error_code="not_found")
        if not await self._authz.can_view(
            AuthzObject.sync_channel(channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "No access to channel.", error_code="forbidden")
        await SyncChannelMember.update_notifications_muted(
            channel_id, user_id, notifications_muted, company_id=company_id
        )
        summaries = await SyncMessage.channel_lane_summaries_by_channel_id_asc_and_sent_at_desc(
            company_id=company_id,
            channel_ids=[channel.channel_id],
            viewer_user_id=user_id,
        )
        return await channel_read_from_entity(
            channel,
            viewer_user_id=user_id,
            channel_access=self._channel_access,
            resolve_user=True,
            company_id=company_id,
            lane_summary=summaries[channel.channel_id],
        )

    async def add_member(
        self,
        *,
        channel_id: str,
        member_user_id: str,
        role: ChannelMemberRole,
        actor_user_id: str,
        company_id: str,
    ) -> ChannelMemberRead:
        channel = await SyncChannel.get(channel_id)
        if channel is None or channel.company_id != company_id:
            raise WsCommandError("not_found", "Channel not found.", error_code="not_found")
        if not await self._authz.can_admin(
            AuthzObject.sync_channel(channel_id), user_id=actor_user_id
        ):
            raise WsCommandError(
                "forbidden",
                "No permission to manage channel members.",
                error_code="forbidden",
            )
        await SyncChannelMember.ensure_member(
            channel_id, member_user_id, company_id=company_id
        )
        try:
            await self._channel_access.set_member(
                channel_id, user_id=member_user_id, relation=role
            )
        except Exception:
            _ = await SyncChannelMember.delete_by_user(
                channel_id, member_user_id, company_id=company_id
            )
            raise
        recipients = await self._channel_access.list_member_user_ids(channel_id)
        await publish_events(
            [
                event_channel_member_added(
                    channel_id,
                    member_user_id,
                    company_id=company_id,
                    recipient_user_ids=recipients,
                ),
            ]
        )
        return ChannelMemberRead(user_id=member_user_id, role=role)

    async def list_members(
        self, *, channel_id: str, user_id: str, company_id: str
    ) -> ListResponse[ChannelMemberRead]:
        channel = await SyncChannel.get(channel_id)
        if channel is None or channel.company_id != company_id:
            raise WsCommandError("not_found", "Channel not found.", error_code="not_found")
        if not await self._authz.can_view(
            AuthzObject.sync_channel(channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "No access to channel.", error_code="forbidden")
        rows = await self._channel_access.list_member_rows_by_user_id_asc(channel_id)
        return ListResponse[ChannelMemberRead](
            items=[ChannelMemberRead(user_id=uid, role=member_role) for uid, member_role in rows]
        )

    async def list_company_members_by_name_asc(
        self,
        *,
        company_id: str,
        user_id: str,
        limit: int,
        offset: int,
    ) -> OffsetPage[CompanyMemberRead]:
        company = await Company.get(company_id)
        if company is None:
            raise WsCommandError("not_found", "Company not found.", error_code="not_found")
        all_member_uids = [uid for uid in company.members if uid != user_id]
        total = len(all_member_uids)
        member_uids = all_member_uids[offset : offset + limit]
        settings = get_settings()
        redis_url = settings.database.redis_url
        if not redis_url:
            raise WsCommandError(
                "internal", "database.redis_url is not set.", error_code="internal"
            )
        presence_map, users_by_id = await asyncio.gather(
            batch_peer_presence(redis_url, member_uids),
            User.get_many(member_uids),
        )
        items: list[CompanyMemberRead] = []
        for uid in member_uids:
            roles_raw = company.members[uid]
            member_user = users_by_id.get(uid)
            if member_user is None:
                raise WsCommandError(
                    "internal",
                    f"Member {uid} is listed in the company, but the user was not found.",
                    error_code="internal",
                )
            pr = presence_map[uid]
            items.append(
                CompanyMemberRead(
                    user_id=uid,
                    name=member_user.name,
                    roles=list(roles_raw),
                    avatar_url=member_user.avatar_url,
                    is_online=pr.is_online,
                    last_seen_at=pr.last_seen_at,
                )
            )
        items.sort(key=lambda member: member.name.casefold())
        return OffsetPage[CompanyMemberRead](
            items=items, total=total, limit=limit, offset=offset
        )

    async def list_shared_channels(
        self,
        *,
        company_id: str,
        user_id: str,
        peer_user_id: str,
        limit: int,
        offset: int,
    ) -> OffsetPage[ChannelRead]:
        company = await Company.get(company_id)
        if company is None:
            raise WsCommandError("not_found", "Company not found.", error_code="not_found")
        if peer_user_id not in company.members:
            raise WsCommandError(
                "not_found", "User is not in the company.", error_code="not_found"
            )
        if peer_user_id == user_id:
            candidates = await SyncChannel.list_member_channels_by_type_and_name_asc(
                user_id,
                namespace=None,
                limit=limit,
                offset=offset,
                company_id=company_id,
            )
            channels = await self.filter_visible(candidates, user_id=user_id)
        else:
            candidates = await SyncChannel.list_for_both_members_by_type_and_name_asc(
                user_id,
                peer_user_id,
                limit=limit,
                offset=offset,
                company_id=company_id,
            )
            channels = await self.filter_visible(
                candidates,
                user_id=user_id,
                peer_user_id=peer_user_id,
            )
        channel_ids = [channel.channel_id for channel in channels]
        summaries = await SyncMessage.channel_lane_summaries_by_channel_id_asc_and_sent_at_desc(
            company_id=company_id,
            channel_ids=channel_ids,
            viewer_user_id=user_id,
        )
        items: list[ChannelRead] = []
        for channel in channels:
            items.append(
                await channel_read_from_entity(
                    channel,
                    viewer_user_id=user_id,
                    channel_access=self._channel_access,
                    resolve_user=True,
                    company_id=company_id,
                    lane_summary=summaries[channel.channel_id],
                )
            )
        return OffsetPage[ChannelRead](
            items=items, total=len(items), limit=limit, offset=offset
        )


