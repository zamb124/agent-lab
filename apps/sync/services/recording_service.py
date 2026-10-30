"""Сценарий записи звонка Sync в LiveKit egress и S3."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import uuid4

from livekit.api.twirp_client import TwirpError, TwirpErrorCode

from apps.sync.events import event_call_recording_started, event_call_recording_stopped
from apps.sync.models.call import SyncCall
from apps.sync.models.channel import SyncChannel
from apps.sync.models.meetings import CallRecordingRead, SyncCallRecording
from apps.sync.realtime.handlers import channel_recipient_user_ids
from apps.sync.realtime.livekit_sdk_boundary import read_livekit_egress_id
from apps.sync.realtime.task_names import SYNC_FINALIZE_RECORDING
from apps.sync.services.livekit_client import LiveKitClient
from apps.sync.services.livekit_usage_spans import trace_livekit_egress_composite_usage
from apps.sync.services.sync_channel_access_service import SyncChannelAccessService
from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.config import get_settings
from core.events import publish_events
from core.files.create_spec import FileSourceKind
from core.files.object_store.gate import FileGate
from core.logging import get_logger
from core.tasks import enqueue
from core.websocket import WsCommandError

logger = get_logger(__name__)


def normalize_s3_egress_endpoint(endpoint_url: str | None) -> str | None:
    if endpoint_url is None:
        return None
    trimmed = endpoint_url.strip()
    if trimmed == "":
        return None
    parsed = urlparse(trimmed)
    if parsed.scheme == "":
        return trimmed
    if parsed.netloc == "":
        raise ValueError(f"Invalid endpoint_url for S3 egress: {endpoint_url}")
    hostname = parsed.hostname
    if hostname is None or hostname == "":
        raise ValueError(f"Invalid hostname in endpoint_url for S3 egress: {endpoint_url}")
    if hostname == "localhost" or hostname == "127.0.0.1":
        hostname = "host.docker.internal"
    if parsed.port is None:
        netloc = hostname
    else:
        netloc = f"{hostname}:{parsed.port}"
    return f"{parsed.scheme}://{netloc}"

def build_livekit_recording_client() -> LiveKitClient:
    settings = get_settings()
    return LiveKitClient(
        url=settings.calls.livekit_url,
        api_key=settings.calls.livekit_api_key,
        api_secret=settings.calls.livekit_api_secret,
    )

async def stop_and_finalize_recording(
    *,
    call: SyncCall,
    recording: SyncCallRecording,
    company_id: str,
    actor_user_id: str,
) -> CallRecordingRead:
    if recording.provider_job_id is None or recording.provider_job_id == "":
        raise ValueError(
            f"Recording {recording.recording_id} has no provider_job_id; cannot stop egress."
        )
    settings = get_settings()
    if settings.recording_max_duration_seconds <= 0:
        raise ValueError("recording_max_duration_seconds must be greater than 0.")
    if recording.started_at is not None:
        max_end_at = recording.started_at + timedelta(seconds=settings.recording_max_duration_seconds)
        logger.info(
            "call.recording.stop",
            call_id=call.call_id,
            recording_id=recording.recording_id,
            started_at=recording.started_at.isoformat(),
            max_end_at=max_end_at.isoformat(),
            now=datetime.now(UTC).isoformat(),
        )
    livekit_client = build_livekit_recording_client()
    logger.info(
        "call.recording.stop",
        call_id=call.call_id,
        recording_id=recording.recording_id,
        egress_id=recording.provider_job_id,
    )
    try:
        _ = await livekit_client.stop_egress(
            egress_id=recording.provider_job_id,
            company_id=company_id,
            user_id=actor_user_id,
        )
    except TwirpError as exc:
        if exc.code in (TwirpErrorCode.NOT_FOUND, TwirpErrorCode.FAILED_PRECONDITION):
            logger.warning(
                "call.recording.stop",
                call_id=call.call_id,
                recording_id=recording.recording_id,
                egress_id=recording.provider_job_id,
                code=exc.code,
                message=str(exc),
            )
        else:
            raise
    await SyncCallRecording.mark_call_recording_status(
        recording.recording_id,
        status="uploaded",
        ended_at=datetime.now(UTC),
    )
    updated_recording = await SyncCallRecording.get(recording.recording_id)
    if updated_recording is None:
        raise RuntimeError("Recording disappeared after update.")
    if call.livekit_room_name is not None and call.livekit_room_name != "":
        if recording.started_by_user_id is None:
            raise RuntimeError("Recording started_by_user_id is required for egress billing trace")
        await trace_livekit_egress_composite_usage(
            company_id=company_id,
            user_id=recording.started_by_user_id,
            call_id=call.call_id,
            recording_id=updated_recording.recording_id,
            livekit_room_name=call.livekit_room_name,
            egress_id=recording.provider_job_id,
            started_at=recording.started_at,
            ended_at=updated_recording.ended_at,
        )
    _ = await enqueue(
        SYNC_FINALIZE_RECORDING,
        recording_id=updated_recording.recording_id,
        company_id=company_id,
        actor_user_id=actor_user_id,
        background_kind="sync_call",
    )
    return CallRecordingRead.model_validate(updated_recording.model_dump())


class SyncCallRecordingService:
    """Старт и останов записи звонка."""

    def __init__(
        self,
        authz: AuthzService,
        channel_access: SyncChannelAccessService,
    ) -> None:
        self._authz: AuthzService = authz
        self._channel_access: SyncChannelAccessService = channel_access

    async def stop_if_started_by_actor(
        self,
        *,
        call: SyncCall,
        company_id: str,
        actor_user_id: str,
    ) -> CallRecordingRead | None:
        active = await SyncCallRecording.active_for_call(call.call_id, company_id)
        if active is None or active.started_by_user_id != actor_user_id:
            return None
        return await stop_and_finalize_recording(
            call=call,
            recording=active,
            company_id=company_id,
            actor_user_id=actor_user_id,
        )

    async def start(
        self,
        *,
        call_id: str,
        company_id: str,
        user_id: str,
    ) -> CallRecordingRead:
        call = await SyncCall.require_company_call(call_id, company_id)
        if call.status == "ended":
            raise WsCommandError(
                "forbidden",
                "Cannot start recording for an ended call.",
                error_code="forbidden",
            )
        if call.created_by_user_id != user_id:
            raise WsCommandError(
                "forbidden",
                "Only the meeting admin can start recording.",
                error_code="forbidden",
            )
        if call.livekit_room_name is None or call.livekit_room_name == "":
            raise WsCommandError(
                "forbidden",
                f"Call {call.call_id} has no livekit_room_name.",
                error_code="forbidden",
            )
        if not await self._authz.can_view(
            AuthzObject.sync_channel(call.channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "No access to the call.", error_code="forbidden")
        active = await SyncCallRecording.active_for_call(call_id, company_id)
        if active is not None:
            raise WsCommandError(
                "forbidden", "Recording is already running.", error_code="forbidden"
            )
        channel_entity = await SyncChannel.get(call.channel_id)
        if channel_entity is None:
            raise WsCommandError(
                "not_found",
                f"Channel {call.channel_id} not found.",
                error_code="not_found",
            )
        settings = get_settings()
        if settings.recording_max_duration_seconds <= 0:
            raise WsCommandError(
                "internal",
                "recording_max_duration_seconds must be greater than 0.",
                error_code="internal",
            )
        if not settings.s3.enabled:
            raise WsCommandError(
                "internal",
                "S3 is disabled: call recording to S3 is unavailable.",
                error_code="internal",
            )
        try:
            egress_target = await FileGate().egress_target(
                company_id,
                FileSourceKind.SYNC_CALL_RECORDING,
            )
        except Exception as exc:
            raise WsCommandError(
                "internal",
                f"S3 egress target resolution failed: {exc}",
                error_code="internal",
            ) from exc
        recording_id = uuid4().hex
        egress_filepath = f"sync-recordings/{company_id}/{call.call_id}/{recording_id}.mp4"
        livekit_client = build_livekit_recording_client()
        await livekit_client.create_room(
            call.livekit_room_name, company_id=company_id, user_id=user_id
        )
        egress_info = await livekit_client.start_room_composite_egress_to_s3(
            room_name=call.livekit_room_name,
            filepath=egress_filepath,
            s3_access_key=egress_target.access_key_id,
            s3_secret_key=egress_target.secret_access_key,
            s3_region=egress_target.region_name,
            s3_bucket=egress_target.bucket_name,
            company_id=company_id,
            user_id=user_id,
            s3_endpoint=normalize_s3_egress_endpoint(egress_target.endpoint_url),
            audio_only=(call.call_type == "audio"),
        )
        provider_job_id = read_livekit_egress_id(egress_info)
        logger.info(
            "call.recording.start",
            call_id=call.call_id,
            recording_id=recording_id,
            room=call.livekit_room_name,
            egress_id=provider_job_id,
            audio_only=call.call_type == "audio",
        )
        recording = SyncCallRecording(
            recording_id=recording_id,
            call_id=call.call_id,
            company_id=company_id,
            channel_id=call.channel_id,
            namespace=channel_entity.namespace,
            status="recording",
            started_by_user_id=user_id,
            provider_job_id=provider_job_id,
            storage_id=egress_target.storage_id,
            started_at=datetime.now(UTC),
        )
        _ = await SyncCallRecording.set(recording)
        out = CallRecordingRead.model_validate(recording.model_dump())
        recipients = await channel_recipient_user_ids(self._channel_access, call.channel_id)
        await publish_events(
            [
                event_call_recording_started(
                    out, company_id=company_id, recipient_user_ids=recipients
                ),
            ]
        )
        return out

    async def stop(
        self,
        *,
        call_id: str,
        company_id: str,
        user_id: str,
    ) -> CallRecordingRead:
        call = await SyncCall.require_company_call(call_id, company_id)
        if not await self._authz.can_view(
            AuthzObject.sync_channel(call.channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "No access to the call.", error_code="forbidden")
        active = await SyncCallRecording.active_for_call(call_id, company_id)
        if active is None:
            raise WsCommandError(
                "not_found", "Active recording not found.", error_code="not_found"
            )
        is_meeting_admin = call.created_by_user_id == user_id
        is_recording_starter = active.started_by_user_id == user_id
        if not is_meeting_admin and not is_recording_starter:
            raise WsCommandError(
                "forbidden",
                "Only the meeting admin or the user who started recording can stop it.",
                error_code="forbidden",
            )
        out = await stop_and_finalize_recording(
            call=call,
            recording=active,
            company_id=company_id,
            actor_user_id=user_id,
        )
        recipients = await channel_recipient_user_ids(self._channel_access, call.channel_id)
        await publish_events(
            [
                event_call_recording_stopped(
                    out, company_id=company_id, recipient_user_ids=recipients
                ),
            ]
        )
        return out
