"""Сценарии приглашения, принятия, отказа и выхода из звонка Sync."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from apps.sync.events import (
    event_call_admin_changed,
    event_call_recording_stopped,
    event_call_signal,
    event_message_created,
)
from apps.sync.models.call import SyncCall
from apps.sync.models.call_participant import SyncCallParticipant
from apps.sync.models.calls import (
    CallRead,
    CallsAcceptPayload,
    CallsDeclinePayload,
    CallsHangupPayload,
    CallsInvitePayload,
    CallsSignalPayload,
    TurnCredentials,
)
from apps.sync.models.channel import SyncChannel
from apps.sync.models.meetings import CallRecordingRead, SyncCallRecording
from apps.sync.models.messages import (
    CallBoundaryContent,
    MessageContentModel,
    MessageContentType,
    MessageCreate,
    MessageRead,
)
from apps.sync.realtime.call_handlers import (
    call_read_from_entities,
    handle_call_accept,
    handle_call_decline,
    handle_call_hangup,
    handle_call_invite,
)
from apps.sync.realtime.handlers import (
    channel_recipient_user_ids,
    maybe_start_speech_to_chat_poll,
)
from apps.sync.services.livekit_client import LiveKitClient
from apps.sync.services.message_service import SyncMessageService, send_message
from apps.sync.services.recording_service import SyncCallRecordingService
from apps.sync.services.sync_channel_access_service import SyncChannelAccessService
from apps.sync.services.turn import generate_turn_credentials
from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.billing.service import BillingService
from core.config import BaseSettings, get_settings
from core.events import publish_events
from core.events.contract import PlatformEvent
from core.files.service import FilesService
from core.logging import get_logger
from core.pagination import ListResponse
from core.platform_brand.resolver import resolve_context_host, resolve_livekit_public_url
from core.utils.domain import is_local
from core.websocket import WsCommandError

logger = get_logger(__name__)


def livekit_client(settings: BaseSettings, billing_service: BillingService) -> LiveKitClient:
    return LiveKitClient(
        url=settings.calls.livekit_url,
        api_key=settings.calls.livekit_api_key,
        api_secret=settings.calls.livekit_api_secret,
        billing_service=billing_service,
    )


def livekit_public_url(settings: BaseSettings) -> str:
    host = resolve_context_host()
    if host is not None and not is_local(host):
        try:
            return resolve_livekit_public_url(host)
        except ValueError as exc:
            logger.info(
                "sync_livekit_public_url_host_unresolved",
                host=host,
                error=str(exc),
            )
    configured = settings.calls.livekit_public_url or settings.calls.livekit_url
    if str(configured).strip() == "":
        raise ValueError("calls.livekit_public_url or calls.livekit_url must be configured")
    return str(configured).strip()


async def _post_call_boundary_message(
    *,
    channel_id: str,
    call_id: str,
    phase: Literal["started", "ended"],
    sender_user_id: str,
    company_id: str,
) -> MessageRead:
    if phase == "ended":
        recordings = await SyncCallRecording.list_by_created_at_desc_for_call(call_id, company_id)
        has_recording = any(recording.status == "uploaded" for recording in recordings)
        boundary_data = CallBoundaryContent(
            call_id=call_id, phase=phase, has_recording=has_recording
        )
    else:
        boundary_data = CallBoundaryContent(call_id=call_id, phase=phase)
    body = MessageCreate(
        thread_id=None,
        parent_message_id=None,
        contents=[
            MessageContentModel(
                type=MessageContentType.CALL_BOUNDARY,
                data=boundary_data,
                order=0,
            )
        ],
        mentioned_user_ids=None,
        call_id=call_id,
    )
    return await send_message(
        channel_id,
        body,
        actor_user_id=sender_user_id,
        company_id=company_id,
        resolve_user=True,
    )


class SyncCallService:
    """Приглашение, принятие, отказ и выход из звонка."""

    def __init__(
        self,
        authz: AuthzService,
        channel_access: SyncChannelAccessService,
        call_recording_service: SyncCallRecordingService,
        files_service: FilesService,
        message_service: SyncMessageService,
        billing_service: BillingService,
    ) -> None:
        self._authz: AuthzService = authz
        self._channel_access: SyncChannelAccessService = channel_access
        self._recordings: SyncCallRecordingService = call_recording_service
        self._files: FilesService = files_service
        self._messages: SyncMessageService = message_service
        self._billing_service: BillingService = billing_service

    async def invite(
        self,
        payload: CallsInvitePayload,
        *,
        user_id: str,
        company_id: str,
    ) -> CallRead:
        try:
            out, events = await handle_call_invite(
                payload,
                actor_user_id=user_id,
                company_id=company_id,
                channel_access=self._channel_access,
                authz=self._authz,
                billing_service=self._billing_service,
                resolve_user=True,
            )
        except PermissionError as exc:
            raise WsCommandError("forbidden", str(exc), error_code="forbidden") from exc
        member_rows = await self._channel_access.list_member_rows_by_user_id_asc(out.channel_id)
        member_ids = [uid for uid, _role in member_rows]
        started_read = await _post_call_boundary_message(
            channel_id=out.channel_id,
            call_id=out.call_id,
            phase="started",
            sender_user_id=out.created_by_user_id,
            company_id=company_id,
        )
        invite_channel = await SyncChannel.get(out.channel_id)
        if invite_channel is None:
            raise WsCommandError(
                "not_found",
                f"Channel {out.channel_id} not found.",
                error_code="not_found",
            )
        events.append(
            event_message_created(
                started_read,
                company_id=company_id,
                recipient_user_ids=member_ids,
                channel_type=invite_channel.type,
            ),
        )
        if len(member_ids) <= 1:
            now = datetime.now(UTC)
            await SyncCall.mark_call_status(out.call_id, "active", started_at=now)
            solo_call = await SyncCall.require_company_call(out.call_id, company_id)
            await maybe_start_speech_to_chat_poll(
                call_id=solo_call.call_id,
                company_id=company_id,
                channel_id=solo_call.channel_id,
                livekit_room_name=solo_call.livekit_room_name,
            )
        await publish_events(events)
        return out

    async def accept(
        self,
        payload: CallsAcceptPayload,
        *,
        user_id: str,
        company_id: str,
    ) -> CallRead:
        try:
            out, events, became_active = await handle_call_accept(
                payload,
                actor_user_id=user_id,
                company_id=company_id,
                channel_access=self._channel_access,
            )
        except ValueError as exc:
            raise WsCommandError("conflict", str(exc), error_code="conflict") from exc
        if became_active:
            await maybe_start_speech_to_chat_poll(
                call_id=out.call_id,
                company_id=company_id,
                channel_id=out.channel_id,
                livekit_room_name=out.livekit_room_name,
            )
        await publish_events(events)
        return out

    async def decline(
        self,
        payload: CallsDeclinePayload,
        *,
        user_id: str,
        company_id: str,
    ) -> CallRead:
        try:
            out, events = await handle_call_decline(
                payload,
                actor_user_id=user_id,
                company_id=company_id,
                channel_access=self._channel_access,
            )
        except ValueError as exc:
            raise WsCommandError("conflict", str(exc), error_code="conflict") from exc
        await publish_events(events)
        return out

    async def hangup(
        self,
        payload: CallsHangupPayload,
        *,
        user_id: str,
        company_id: str,
    ) -> CallRead:
        auto_stopped: PlatformEvent | None = None
        call = await SyncCall.require_company_call(payload.call_id, company_id)
        stopped_recording = await self._recordings.stop_if_started_by_actor(
            call=call,
            company_id=company_id,
            actor_user_id=user_id,
        )
        if stopped_recording is not None:
            recipients = await channel_recipient_user_ids(self._channel_access, call.channel_id)
            auto_stopped = event_call_recording_stopped(
                stopped_recording,
                company_id=company_id,
                recipient_user_ids=recipients,
            )
        try:
            out, events, fully_ended = await handle_call_hangup(
                payload,
                actor_user_id=user_id,
                company_id=company_id,
                channel_access=self._channel_access,
                files_service=self._files,
                message_service=self._messages,
                billing_service=self._billing_service,
            )
        except ValueError as exc:
            raise WsCommandError("conflict", str(exc), error_code="conflict") from exc
        if auto_stopped is not None:
            events.append(auto_stopped)
        if fully_ended:
            boundary_read = await _post_call_boundary_message(
                channel_id=out.channel_id,
                call_id=out.call_id,
                phase="ended",
                sender_user_id=out.created_by_user_id,
                company_id=company_id,
            )
            recipients = await channel_recipient_user_ids(
                self._channel_access, out.channel_id
            )
            hangup_channel = await SyncChannel.get(out.channel_id)
            if hangup_channel is None:
                raise WsCommandError(
                    "not_found",
                    f"Channel {out.channel_id} not found.",
                    error_code="not_found",
                )
            events.append(
                event_message_created(
                    boundary_read,
                    company_id=company_id,
                    recipient_user_ids=recipients,
                    channel_type=hangup_channel.type,
                ),
            )
        await publish_events(events)
        return out

    async def get_call(self, *, call_id: str, company_id: str) -> CallRead:
        try:
            call = await SyncCall.require_company_call(call_id, company_id)
        except ValueError as exc:
            raise WsCommandError("not_found", str(exc), error_code="not_found") from exc
        participants = await SyncCallParticipant.list_unordered_for_call(call_id)
        return call_read_from_entities(call, participants)

    async def list_recordings(
        self,
        *,
        call_id: str,
        company_id: str,
        user_id: str,
    ) -> ListResponse[CallRecordingRead]:
        call = await SyncCall.require_company_call(call_id, company_id)
        if not await self._authz.can_view(
            AuthzObject.sync_channel(call.channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "No access to the call.", error_code="forbidden")
        rows = await SyncCallRecording.list_by_created_at_desc_for_call(call_id, company_id)
        return ListResponse[CallRecordingRead](
            items=[CallRecordingRead.model_validate(row.model_dump()) for row in rows]
        )

    async def token(
        self,
        *,
        call_id: str,
        company_id: str,
        user_id: str,
    ) -> tuple[str, str]:
        settings = get_settings()
        try:
            call = await SyncCall.require_company_call(call_id, company_id)
        except ValueError as exc:
            raise WsCommandError("not_found", str(exc), error_code="not_found") from exc
        if call.mode != "sfu":
            raise WsCommandError(
                "forbidden",
                f"Call {call_id} is not an SFU call.",
                error_code="forbidden",
            )
        if not call.livekit_room_name:
            raise WsCommandError(
                "forbidden",
                f"Call {call_id} has no LiveKit room.",
                error_code="forbidden",
            )
        if not await self._authz.can_view(
            AuthzObject.sync_channel(call.channel_id), user_id=user_id
        ):
            raise WsCommandError(
                "forbidden",
                f"No access to call channel {call_id}.",
                error_code="forbidden",
            )
        access_token = livekit_client(settings, self._billing_service).generate_token(
            room_name=call.livekit_room_name, identity=user_id
        )
        return access_token, livekit_public_url(settings)

    async def turn_credentials(self, *, user_id: str) -> TurnCredentials:
        settings = get_settings()
        return generate_turn_credentials(
            user_id=user_id,
            turn_host=settings.calls.turn_host,
            turn_port=settings.calls.turn_port,
            turn_secret=settings.calls.turn_secret,
            ttl=settings.calls.turn_credential_ttl,
        )

    async def transfer_admin(
        self,
        *,
        call_id: str,
        target_user_id: str,
        user_id: str,
        company_id: str,
    ) -> CallRead:
        call = await SyncCall.require_company_call(call_id, company_id)
        if call.created_by_user_id != user_id:
            raise WsCommandError(
                "forbidden",
                "Only the current meeting admin can transfer admin.",
                error_code="forbidden",
            )
        if not await self._authz.can_view(
            AuthzObject.sync_channel(call.channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "No access to the call.", error_code="forbidden")
        if not await self._authz.can_view(
            AuthzObject.sync_channel(call.channel_id), user_id=target_user_id
        ):
            raise WsCommandError(
                "forbidden", "New admin is not a channel member.", error_code="forbidden"
            )
        if target_user_id.startswith("guest:"):
            raise WsCommandError(
                "forbidden", "Cannot assign a guest as meeting admin.", error_code="forbidden"
            )
        participants = await SyncCallParticipant.list_unordered_for_call(call.call_id)
        target_participant = next(
            (item for item in participants if item.user_id == target_user_id), None
        )
        if target_participant is None:
            raise WsCommandError(
                "not_found", "New admin is not among call participants.", error_code="not_found"
            )
        if target_participant.status != "joined":
            raise WsCommandError(
                "forbidden",
                "New admin must be an active call participant.",
                error_code="forbidden",
            )
        await SyncCall.assign_admin(call.call_id, target_user_id)
        updated_call = await SyncCall.require_company_call(call.call_id, company_id)
        updated_participants = await SyncCallParticipant.list_unordered_for_call(call.call_id)
        out = call_read_from_entities(updated_call, updated_participants)
        recipients = await channel_recipient_user_ids(self._channel_access, out.channel_id)
        await publish_events(
            [
                event_call_admin_changed(
                    out, company_id=company_id, recipient_user_ids=recipients
                ),
            ]
        )
        return out

    async def signal(
        self,
        payload: CallsSignalPayload,
        *,
        user_id: str,
        company_id: str,
    ) -> None:
        event = event_call_signal(
            payload.call_id,
            payload.signal_type,
            payload.data,
            company_id=company_id,
            recipient_user_ids=[payload.target_user_id],
            target_user_id=payload.target_user_id,
            sender_user_id=user_id,
        )
        await publish_events([event])
