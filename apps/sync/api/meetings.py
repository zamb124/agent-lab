"""REST API для встреч Sync (записи, транскрипты, экспорт)."""

from __future__ import annotations

import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from apps.sync.container import get_sync_container
from apps.sync.models.meetings import (
    CallMeetingDetailsRead,
    CallMeetingListFilters,
    CallMeetingRead,
    CallRecordingRead,
    CallSpeakerSegmentRead,
    ExportMeetingToCrmRequest,
)
from apps.sync.realtime.command_dispatch import dispatch_sync_command
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.tasks import sync_transcribe_recording_task
from core.context import get_context

router = APIRouter()


def _is_public_http_url(url: str | None) -> bool:
    if not isinstance(url, str) or url == "":
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not isinstance(host, str) or host == "":
        return False
    if host in ("localhost", "127.0.0.1", "::1", "livekit"):
        return False
    if host.endswith(".local"):
        return False
    if "." not in host:
        return False
    return True


@router.get("/")
async def list_meetings(
    channel_id: str | None = None,
    space_id: str | None = None,
    limit: int = 50,
) -> list[CallMeetingRead]:
    filters = CallMeetingListFilters(channel_id=channel_id, space_id=space_id, limit=limit)
    context = get_context()
    company_id = context.active_company.company_id
    user_id = context.user.user_id
    container = get_sync_container()

    rows = await container.call_meeting_repository.list_meetings(
        company_id=company_id,
        channel_id=filters.channel_id,
        space_id=filters.space_id,
        limit=filters.limit,
    )
    visible: list[CallMeetingRead] = []
    for row in rows:
        if not await container.channel_repository.is_member(row.channel_id, user_id, company_id=company_id):
            continue
        transcript_storage_url = None
        transcript_download_url = None
        if row.transcript_text_file_id is not None:
            transcript_file = await container.sync_file_repository.get(row.transcript_text_file_id)
            if transcript_file is not None:
                if _is_public_http_url(transcript_file.storage_url):
                    transcript_storage_url = transcript_file.storage_url
                transcript_download_url = (
                    f"/sync/api/v1/files/download/{transcript_file.file_id}"
                )
        visible.append(
            CallMeetingRead(
                meeting_id=row.meeting_id,
                call_id=row.call_id,
                recording_id=row.recording_id,
                channel_id=row.channel_id,
                space_id=row.space_id,
                transcript_file_id=row.transcript_file_id,
                transcript_text_file_id=row.transcript_text_file_id,
                transcript_text_storage_url=transcript_storage_url,
                transcript_text_download_url=transcript_download_url,
                summary_json=row.summary_json or {},
                export_status=row.export_status,
                export_target_namespace=row.export_target_namespace,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    return visible


@router.get("/{meeting_id}")
async def get_meeting(meeting_id: str) -> CallMeetingDetailsRead:
    context = get_context()
    container = get_sync_container()
    company_id = context.active_company.company_id
    user_id = context.user.user_id
    row = await container.call_meeting_repository.get(meeting_id)
    if row is None or row.company_id != company_id:
        raise HTTPException(status_code=404, detail="Встреча не найдена.")
    if not await container.channel_repository.is_member(row.channel_id, user_id, company_id=company_id):
        raise HTTPException(status_code=403, detail="Нет доступа к встрече.")

    recording = None
    if row.recording_id is not None:
        rec = await container.call_recording_repository.get(row.recording_id)
        if rec is not None and rec.company_id == company_id:
            raw_file_storage_url = None
            raw_file_download_url = None
            if rec.raw_file_id is not None:
                raw_file = await container.sync_file_repository.get(rec.raw_file_id)
                if raw_file is not None:
                    if _is_public_http_url(raw_file.storage_url):
                        raw_file_storage_url = raw_file.storage_url
                    raw_file_download_url = f"/sync/api/v1/files/download/{raw_file.file_id}"
            recording = CallRecordingRead(
                recording_id=rec.recording_id,
                call_id=rec.call_id,
                channel_id=rec.channel_id,
                space_id=rec.space_id,
                status=rec.status,
                provider_job_id=rec.provider_job_id,
                raw_file_id=rec.raw_file_id,
                raw_file_storage_url=raw_file_storage_url,
                raw_file_download_url=raw_file_download_url,
                started_at=rec.started_at,
                ended_at=rec.ended_at,
                created_at=rec.created_at,
                error=rec.error,
            )
    transcript_storage_url = None
    transcript_download_url = None
    if row.transcript_text_file_id is not None:
        transcript_file = await container.sync_file_repository.get(row.transcript_text_file_id)
        if transcript_file is not None:
            if _is_public_http_url(transcript_file.storage_url):
                transcript_storage_url = transcript_file.storage_url
            transcript_download_url = f"/sync/api/v1/files/download/{transcript_file.file_id}"
    segments_rows = await container.call_speaker_segment_repository.list_for_meeting(meeting_id, company_id)
    segments = [
        CallSpeakerSegmentRead(
            segment_id=s.segment_id,
            meeting_id=s.meeting_id,
            speaker_identity=s.speaker_identity,
            speaker_type=s.speaker_type,
            speaker_user_id=s.speaker_user_id,
            speaker_guest_name=s.speaker_guest_name,
            started_ms=s.started_ms,
            ended_ms=s.ended_ms,
            text=s.text,
            created_at=s.created_at,
        )
        for s in segments_rows
    ]
    return CallMeetingDetailsRead(
        meeting=CallMeetingRead(
            meeting_id=row.meeting_id,
            call_id=row.call_id,
            recording_id=row.recording_id,
            channel_id=row.channel_id,
            space_id=row.space_id,
            transcript_file_id=row.transcript_file_id,
            transcript_text_file_id=row.transcript_text_file_id,
            transcript_text_storage_url=transcript_storage_url,
            transcript_text_download_url=transcript_download_url,
            summary_json=row.summary_json or {},
            export_status=row.export_status,
            export_target_namespace=row.export_target_namespace,
            created_at=row.created_at,
            updated_at=row.updated_at,
        ),
        recording=recording,
        segments=segments,
    )


@router.get("/{meeting_id}/transcript")
async def get_meeting_transcript(meeting_id: str) -> dict[str, str]:
    context = get_context()
    company_id = context.active_company.company_id
    user_id = context.user.user_id
    container = get_sync_container()
    row = await container.call_meeting_repository.get(meeting_id)
    if row is None or row.company_id != company_id:
        raise HTTPException(status_code=404, detail="Встреча не найдена.")
    if not await container.channel_repository.is_member(row.channel_id, user_id, company_id=company_id):
        raise HTTPException(status_code=403, detail="Нет доступа к встрече.")
    if row.transcript_text_file_id is None:
        raise HTTPException(status_code=404, detail="Транскрипт ещё не готов.")
    file_row = await container.sync_file_repository.get(row.transcript_text_file_id)
    if file_row is None:
        raise HTTPException(status_code=404, detail="Файл транскрипта не найден.")
    return {"file_id": file_row.file_id, "storage_url": file_row.storage_url or ""}


@router.post("/{meeting_id}/export/crm")
async def export_meeting_to_crm(meeting_id: str, body: ExportMeetingToCrmRequest) -> CallMeetingRead:
    context = get_context()
    cmd = CommandEnvelope(
        id=uuid.uuid4().hex,
        actor_user_id=context.user.user_id,
        company_id=context.active_company.company_id,
        type="call.meeting.export_to_crm",
        payload={"meeting_id": meeting_id, "namespace": body.namespace},
    )
    out = await dispatch_sync_command(cmd)
    if not out.get("ok"):
        raise RuntimeError(f"Command failed: {out.get('error_detail')}")
    return CallMeetingRead.model_validate(out["result"])


@router.post("/{meeting_id}/retry-processing")
async def retry_meeting_processing(meeting_id: str) -> CallMeetingRead:
    context = get_context()
    company_id = context.active_company.company_id
    user_id = context.user.user_id
    container = get_sync_container()
    row = await container.call_meeting_repository.get(meeting_id)
    if row is None or row.company_id != company_id:
        raise HTTPException(status_code=404, detail="Встреча не найдена.")
    if not await container.channel_repository.is_member(row.channel_id, user_id, company_id=company_id):
        raise HTTPException(status_code=403, detail="Нет доступа к встрече.")
    if row.recording_id is None:
        raise HTTPException(status_code=400, detail="Для встречи отсутствует запись.")

    await container.call_meeting_repository.set_export_status(
        row.meeting_id,
        status="pending",
        target_namespace=row.export_target_namespace,
    )
    await sync_transcribe_recording_task.kiq(
        meeting_id=row.meeting_id,
        company_id=company_id,
        actor_user_id=user_id,
    )
    updated = await container.call_meeting_repository.get(row.meeting_id)
    if updated is None:
        raise RuntimeError("Встреча не найдена после постановки retry.")
    transcript_storage_url = None
    transcript_download_url = None
    if updated.transcript_text_file_id is not None:
        transcript_file = await container.sync_file_repository.get(updated.transcript_text_file_id)
        if transcript_file is not None:
            if _is_public_http_url(transcript_file.storage_url):
                transcript_storage_url = transcript_file.storage_url
            transcript_download_url = f"/sync/api/v1/files/download/{transcript_file.file_id}"
    return CallMeetingRead(
        meeting_id=updated.meeting_id,
        call_id=updated.call_id,
        recording_id=updated.recording_id,
        channel_id=updated.channel_id,
        space_id=updated.space_id,
        transcript_file_id=updated.transcript_file_id,
        transcript_text_file_id=updated.transcript_text_file_id,
        transcript_text_storage_url=transcript_storage_url,
        transcript_text_download_url=transcript_download_url,
        summary_json=updated.summary_json or {},
        export_status=updated.export_status,
        export_target_namespace=updated.export_target_namespace,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )

