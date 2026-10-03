"""Сценарии ссылок на звонок Sync и входа гостя."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from apps.sync.constants import CHANNEL_TYPE_CALENDAR_MEETING
from apps.sync.models.call import SyncCall
from apps.sync.models.call_link import SyncCallLink
from apps.sync.models.call_participant import SyncCallParticipant
from apps.sync.models.calls import (
    CallLinkCreate,
    CallLinkInfo,
    CallLinkRead,
    CallScheduledLinkRead,
    CallsJoinAcceptPayload,
    CallsJoinInfoPayload,
    CallsLinksListPayload,
    CallsLinksRemovePayload,
    CallsLinksUpdatePayload,
    JoinResponse,
)
from apps.sync.models.channel import SyncChannel
from apps.sync.models.channel_member import SyncChannelMember
from apps.sync.services.call_service import livekit_client, livekit_public_url
from apps.sync.services.channel_service import SyncChannelService
from apps.sync.services.sync_channel_access_service import SyncChannelAccessService
from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.config import get_settings
from core.models.identity_models import User
from core.pagination import OffsetPage
from core.short_links.models import PlatformShortLink
from core.short_links.service import ShortLinkService
from core.websocket import WsCommandError


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

def _ttl_hours_from_schedule(scheduled_end: datetime, now: datetime) -> int:
    delta = _as_utc(scheduled_end) - _as_utc(now)
    hours = int(delta.total_seconds() / 3600.0) + 2
    return max(1, min(168, hours))


class SyncCallLinkService:
    """Ссылки на звонок и вход по ссылке."""

    def __init__(
        self,
        authz: AuthzService,
        channel_access: SyncChannelAccessService,
        short_links: ShortLinkService,
        channels: SyncChannelService,
    ) -> None:
        self._authz: AuthzService = authz
        self._channel_access: SyncChannelAccessService = channel_access
        self._short_links: ShortLinkService = short_links
        self._channels: SyncChannelService = channels

    async def _participant_names_for_call(self, call: SyncCall) -> dict[str, str]:
        out: dict[str, str] = {}
        member_ids = await self._channel_access.list_member_user_ids(
            call.channel_id
        )
        for uid in member_ids:
            u = await User.get(uid)
            out[uid] = u.name if u is not None else uid

        for participant_row in await SyncCallParticipant.list_for_call(call.call_id):
            uid = participant_row.user_id
            if uid in out:
                continue
            if uid.startswith("guest:"):
                parts = uid.split(":", 2)
                out[uid] = parts[2] if len(parts) >= 3 else "Гость"
            else:
                u = await User.get(uid)
                out[uid] = u.name if u is not None else uid
        return out
    async def _mint_join_short_url(
        self, link_token: str, expires_at: datetime, company_id: str
    ) -> str:
        return await self._short_links.mint_sync_call_join(
            link_token, expires_at, company_id
        )
    async def _reconcile_calendar_meeting_channel_members(
        self,
        *,
        channel_id: str,
        company_id: str,
        link_creator_user_id: str,
        calendar_member_user_ids: list[str],
    ) -> None:
        access = self._channel_access
        desired_guests = {
            uid for uid in calendar_member_user_ids if uid and uid != link_creator_user_id
        }
        for uid in sorted(desired_guests):
            await SyncChannelMember.ensure_channel_member_row(
                channel_id, uid, company_id=company_id
            )
            await access.set_member(channel_id, user_id=uid, relation="member")
        current = await access.list_member_user_ids(channel_id)
        desired = {link_creator_user_id} | desired_guests
        for uid in current:
            if uid not in desired:
                _ = await SyncChannelMember.delete_channel_member(
                    channel_id, uid, company_id=company_id
                )
                await access.remove_member(channel_id, user_id=uid)
    async def list_links(
        self,
        payload: CallsLinksListPayload,
        *,
        user: User,
        company_id: str,
    ) -> OffsetPage[CallScheduledLinkRead]:
        rows = await SyncCallLink.list_scheduled_calendar_links_for_user(
            company_id,
            user.user_id,
            range_start=payload.start_at,
            range_end=payload.end_at,
            channel_id=payload.channel_id,
        )
        out: list[CallScheduledLinkRead] = []
        for row in rows:
            if row.scheduled_start_at is None or row.scheduled_end_at is None:
                continue
            if row.calendar_event_id is None:
                continue
            join_url = await self._mint_join_short_url( row.link_token, row.expires_at, row.company_id
            )
            out.append(
                CallScheduledLinkRead(
                    link_token=row.link_token,
                    channel_id=row.channel_id,
                    title=row.title,
                    scheduled_start_at=row.scheduled_start_at,
                    scheduled_end_at=row.scheduled_end_at,
                    calendar_event_id=row.calendar_event_id,
                    join_url=join_url,
                    expires_at=row.expires_at,
                )
            )
        page = out[payload.offset : payload.offset + payload.limit]
        return OffsetPage[CallScheduledLinkRead](
            items=page, total=len(out), limit=payload.limit, offset=payload.offset
        )
    async def create_link(
        self,
        body: CallLinkCreate,
        *,
        user: User,
        company_id: str,
    ) -> CallLinkRead:
        actor_id = user.user_id

        channel_id: str
        attached_call_id: str | None = None
        calendar_title: str | None = None
        cal_start: datetime | None = None
        cal_end: datetime | None = None
        cal_event_id: str | None = None
        ttl_hours = body.ttl_hours
        is_persistent_channel_link = False

        if body.calendar_event_id:
            scheduled_title = body.scheduled_title
            scheduled_start_at = body.scheduled_start_at
            scheduled_end_at = body.scheduled_end_at
            calendar_member_user_ids = body.calendar_member_user_ids
            if (
                scheduled_title is None
                or scheduled_start_at is None
                or scheduled_end_at is None
                or calendar_member_user_ids is None
            ):
                message = (
                    "calendar_event_id требует scheduled_title, scheduled_start_at, "
                    "scheduled_end_at и calendar_member_user_ids."
                )
                raise WsCommandError(
                    "ws_invalid_payload",
                    message,
                          error_code='ws_invalid_payload',
                      )
            dup = await SyncCallLink.find_by_calendar_event(
                company_id, body.calendar_event_id
            )
            if dup is not None:
                raise WsCommandError(
                    "conflict", "A link already exists for this calendar event.",
                          error_code='conflict',
                      )
            channel_id = uuid4().hex
            ch = SyncChannel(
                channel_id=channel_id,
                company_id=company_id,
                namespace="default",
                type=CHANNEL_TYPE_CALENDAR_MEETING,
                name=scheduled_title.strip(),
                is_private=False,
                created_at=datetime.now(UTC),
                created_by_user_id=actor_id,
                pinned_message_ids=[],
            )
            _ = await SyncChannel.set(ch)
            member_ids = [uid for uid in calendar_member_user_ids if uid and uid != actor_id]
            await SyncChannelMember.ensure_channel_member_row(
                channel_id, actor_id, company_id=company_id
            )
            for uid in member_ids:
                await SyncChannelMember.ensure_channel_member_row(
                    channel_id, uid, company_id=company_id
                )
            try:
                await self._channel_access.sync_channel_created(
                    channel_id,
                    company_id=company_id,
                    owner_user_id=actor_id,
                    member_user_ids=member_ids,
                )
            except Exception:
                _ = await SyncChannel.delete_by_id(channel_id)
                raise
            now = datetime.now(UTC)
            ttl_hours = _ttl_hours_from_schedule(scheduled_end_at, now)
            expires_at = now + timedelta(hours=ttl_hours)
            calendar_title = scheduled_title.strip()
            cal_start = scheduled_start_at
            cal_end = scheduled_end_at
            cal_event_id = body.calendar_event_id
        else:
            if body.channel_id is None:
                raise WsCommandError(
                    "ws_invalid_payload",
                    "channel_id is required for a link without calendar_event_id.",
                          error_code='ws_invalid_payload',
                      )
            channel_id = body.channel_id
            if not await self._authz.can_view(
                AuthzObject.sync_channel(channel_id), user_id=actor_id
            ):
                raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
            expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)
            if body.call_id:
                existing = await SyncCall.require_company_call(body.call_id, company_id)
                if existing.channel_id != channel_id:
                    raise WsCommandError(
                        "ws_invalid_payload", "Call belongs to another channel.",
                              error_code='ws_invalid_payload',
                          )
                if existing.status not in ("ringing", "active"):
                    raise WsCommandError(
                        "forbidden",
                        "Conference link is available only for an active or incoming call.",
                              error_code='forbidden',
                          )
                if existing.mode != "sfu":
                    raise WsCommandError(
                        "forbidden", "Guest link is supported only for SFU calls.",
                              error_code='forbidden',
                          )
                if not existing.livekit_room_name:
                    raise WsCommandError("forbidden", "Call has no LiveKit room.", error_code='forbidden')
                attached_call_id = existing.call_id
            else:
                ch = await SyncChannel.get(channel_id)
                if ch is None:
                    raise WsCommandError("not_found", "Channel not found.", error_code='not_found')
                if ch.type == CHANNEL_TYPE_CALENDAR_MEETING:
                    raise WsCommandError(
                        "ws_invalid_payload",
                        "A persistent link for a calendar meeting channel is not created via channel_id.",
                              error_code='ws_invalid_payload',
                          )
                existing_p = await SyncCallLink.find_persistent_for_channel(
                    company_id, channel_id
                )
                if body.reuse_channel_link:
                    if existing_p is not None:
                        await SyncCallLink.set_expires_at(existing_p.link_token, expires_at)
                        join_url = await self._mint_join_short_url(
                            existing_p.link_token, expires_at, company_id
                        )
                        return CallLinkRead(
                            link_token=existing_p.link_token,
                            channel_id=channel_id,
                            call_type="video",
                            expires_at=expires_at,
                            join_url=join_url,
                            title=existing_p.title,
                            scheduled_start_at=existing_p.scheduled_start_at,
                            scheduled_end_at=existing_p.scheduled_end_at,
                            calendar_event_id=existing_p.calendar_event_id,
                        )
                else:
                    if existing_p is not None:
                        _ = await PlatformShortLink.delete_sync_by_link_token(existing_p.link_token)
                        deleted = await SyncCallLink.delete_in_company(
                            company_id, existing_p.link_token
                        )
                        if not deleted:
                            raise WsCommandError("internal", "Failed to replace the persistent link.", error_code='internal')
                is_persistent_channel_link = True

        link_token = uuid4().hex
        link = SyncCallLink(
            link_token=link_token,
            channel_id=channel_id,
            company_id=company_id,
            call_id=attached_call_id,
            call_type="video",
            created_by_user_id=actor_id,
            expires_at=expires_at,
            title=calendar_title,
            scheduled_start_at=cal_start,
            scheduled_end_at=cal_end,
            calendar_event_id=cal_event_id,
            is_persistent_channel_link=is_persistent_channel_link,
        )
        _ = await SyncCallLink.set(link)

        join_url = await self._mint_join_short_url( link_token, expires_at, company_id)
        return CallLinkRead(
            link_token=link_token,
            channel_id=channel_id,
            call_type="video",
            expires_at=expires_at,
            join_url=join_url,
            title=calendar_title,
            scheduled_start_at=cal_start,
            scheduled_end_at=cal_end,
            calendar_event_id=cal_event_id,
        )
    async def update_link(
        self,
        payload: CallsLinksUpdatePayload,
        *,
        user: User,
        company_id: str,
    ) -> CallLinkRead:
        body = payload.body
        link = await SyncCallLink.require_company_call_link(
            payload.link_token, company_id
        )
        if link.calendar_event_id is None:
            raise WsCommandError(
                "forbidden", "Patch is supported only for calendar links.",
                      error_code='forbidden',
                  )
        if not await self._authz.can_view(
            AuthzObject.sync_channel(link.channel_id), user_id=user.user_id
        ):
            raise WsCommandError("forbidden", "No access to the link.", error_code='forbidden')

        raw_start = body.scheduled_start_at if body.scheduled_start_at is not None else link.scheduled_start_at
        raw_end = body.scheduled_end_at if body.scheduled_end_at is not None else link.scheduled_end_at
        if raw_start is None or raw_end is None:
            raise WsCommandError("ws_invalid_payload", "Link must have schedule bounds.", error_code='ws_invalid_payload')
        new_start = _as_utc(raw_start)
        new_end = _as_utc(raw_end)
        if new_start >= new_end:
            raise WsCommandError("ws_invalid_payload", "Invalid meeting interval.", error_code='ws_invalid_payload')

        new_title = body.scheduled_title if body.scheduled_title is not None else link.title
        now = datetime.now(UTC)
        new_expires = now + timedelta(hours=_ttl_hours_from_schedule(new_end, now))

        await SyncCallLink.update_calendar_call_link(
            payload.link_token,
            company_id,
            title=new_title,
            scheduled_start_at=new_start,
            scheduled_end_at=new_end,
            expires_at=new_expires,
        )
        if body.scheduled_title is not None:
            ch = await SyncChannel.get(link.channel_id)
            if ch is None or ch.company_id != company_id:
                raise WsCommandError("not_found", "Link channel not found.", error_code='not_found')
            name = body.scheduled_title.strip()
            if name == "":
                raise WsCommandError("ws_invalid_payload", "scheduled_title must not be empty.", error_code='ws_invalid_payload')
            _ = await SyncChannel.rename_channel(ch, name)
        if body.calendar_member_user_ids is not None:
            await self._reconcile_calendar_meeting_channel_members(
                        channel_id=link.channel_id,
                company_id=company_id,
                link_creator_user_id=link.created_by_user_id,
                calendar_member_user_ids=body.calendar_member_user_ids,
            )
        updated = await SyncCallLink.require_company_call_link(
            payload.link_token, company_id
        )
        join_url = await self._mint_join_short_url(
            payload.link_token, updated.expires_at, company_id
        )
        return CallLinkRead(
            link_token=updated.link_token,
            channel_id=updated.channel_id,
            call_type="video",
            expires_at=updated.expires_at,
            join_url=join_url,
            title=updated.title,
            scheduled_start_at=updated.scheduled_start_at,
            scheduled_end_at=updated.scheduled_end_at,
            calendar_event_id=updated.calendar_event_id,
        )
    async def remove_link(
        self,
        payload: CallsLinksRemovePayload,
        *,
        user: User,
        company_id: str,
    ) -> None:
        link = await SyncCallLink.require_company_call_link(
            payload.link_token, company_id
        )
        if link.calendar_event_id is None:
            raise WsCommandError(
                "forbidden", "Delete via this contract is only for calendar links.",
                      error_code='forbidden',
                  )
        can_admin = await self._authz.can_admin(
            AuthzObject.sync_channel(link.channel_id), user_id=user.user_id
        )
        if link.created_by_user_id != user.user_id and not can_admin:
            raise WsCommandError("forbidden", "No permission to delete this link.", error_code='forbidden')
        channel_id = link.channel_id
        deleted = await SyncCallLink.delete_in_company(
            company_id, payload.link_token
        )
        if not deleted:
            raise WsCommandError("not_found", "Link not found.", error_code='not_found')
        _ = await PlatformShortLink.delete_sync_by_link_token(payload.link_token)
        ch = await SyncChannel.get(channel_id)
        if ch is not None and ch.company_id == company_id and ch.type == CHANNEL_TYPE_CALENDAR_MEETING:
            await self._channel_access.sync_channel_deleted(channel_id)
            _ = await SyncChannel.delete_by_id(channel_id)
        return None
    async def join_info(self, payload: CallsJoinInfoPayload) -> CallLinkInfo:
        try:
            link = await SyncCallLink.require_active_call_link(payload.link_token)
        except ValueError as exc:
            raise WsCommandError("not_found", str(exc), error_code='not_found') from exc

        channel = await SyncChannel.get(link.channel_id)
        channel_name = channel.name if channel else None

        creator_name = link.created_by_user_id
        creator_avatar_url: str | None = None
        creator = await User.get(link.created_by_user_id)
        if creator is not None:
            creator_name = creator.name
            creator_avatar_url = creator.avatar_url

        return CallLinkInfo(
            link_token=payload.link_token,
            company_id=link.company_id,
            channel_id=link.channel_id,
            channel_name=channel_name,
            creator_display_name=creator_name,
            creator_avatar_url=creator_avatar_url,
            call_type="video",
            expires_at=link.expires_at,
        )
    async def join_accept(
        self,
        payload: CallsJoinAcceptPayload,
        *,
        user: User,
    ) -> JoinResponse:
        settings = get_settings()
        try:
            link = await SyncCallLink.require_active_call_link(payload.link_token)
        except ValueError as exc:
            raise WsCommandError("not_found", str(exc), error_code='not_found') from exc

        is_authenticated = user.user_id not in ("anonymous", "")

        participant_identity: str
        if is_authenticated:
            participant_identity = user.user_id
        else:
            if payload.body is None or not payload.body.guest_name.strip():
                raise WsCommandError(
                    "ws_invalid_payload",
                    "guest_name is required for guest join.",
                          error_code='ws_invalid_payload',
                      )
            safe_name = payload.body.guest_name.strip().replace(":", "_")
            participant_identity = f"guest:{uuid4().hex[:8]}:{safe_name}"

        if link.call_id:
            call = await SyncCall.require_company_call(link.call_id, link.company_id)
            if call.status == "ended":
                livekit_room = call.livekit_room_name
                if not livekit_room:
                    raise WsCommandError(
                        "internal",
                        "Ended call has no LiveKit room.",
                              error_code='internal',
                          )
                await livekit_client(settings).create_room(
                    livekit_room,
                    company_id=link.company_id,
                    user_id=participant_identity,
                )
                new_call = SyncCall(
                    call_id=uuid4().hex,
                    company_id=link.company_id,
                    channel_id=link.channel_id,
                    mode="sfu",
                    call_type="video",
                    status="active",
                    livekit_room_name=livekit_room,
                    started_at=datetime.now(UTC),
                    created_by_user_id=link.created_by_user_id,
                )
                _ = await SyncCall.set(new_call)
                await SyncCallLink.attach_call(payload.link_token, new_call.call_id)
                call = new_call
        else:
            livekit_room_name = f"link-{payload.link_token[:16]}"
            await livekit_client(settings).create_room(
                livekit_room_name,
                company_id=link.company_id,
                user_id=participant_identity,
            )
            call = SyncCall(
                call_id=uuid4().hex,
                company_id=link.company_id,
                channel_id=link.channel_id,
                mode="sfu",
                call_type="video",
                status="active",
                livekit_room_name=livekit_room_name,
                started_at=datetime.now(UTC),
                created_by_user_id=link.created_by_user_id,
            )
            _ = await SyncCall.set(call)
            await SyncCallLink.attach_call(payload.link_token, call.call_id)

        if not call.livekit_room_name:
            raise WsCommandError("internal", "Call has no LiveKit room.", error_code='internal')

        token = livekit_client(settings).generate_token(
            room_name=call.livekit_room_name, identity=participant_identity
        )
        participant_names = await self._participant_names_for_call(call)

        return JoinResponse(
            call_id=call.call_id,
            call_type="video",
            livekit_token=token,
            livekit_url=livekit_public_url(settings),
            participant_identity=participant_identity,
            meeting_admin_user_id=call.created_by_user_id,
            mode="sfu",
            participant_names=participant_names,
        )
