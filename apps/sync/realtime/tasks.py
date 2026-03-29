"""TaskIQ задачи realtime слоя Sync."""

from __future__ import annotations

from typing import Any

from apps.sync.container import get_sync_container
from apps.sync.db.models import SyncCallSpeakerSegment, SyncFile
from apps.sync.models.meetings import CallMeetingRead
from apps.sync.realtime.broker import broker
from apps.sync.realtime.command_dispatch import dispatch_sync_command
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.events import (
    event_call_export_crm_done,
    event_call_export_crm_failed,
    event_call_summary_ready,
    event_call_summary_failed,
    event_call_transcript_failed,
    event_call_transcript_ready,
)
from apps.sync.realtime.publish_events import publish_realtime_events
from core.clients.a2a_client import A2AClient
from core.config import get_settings
from core.logging import get_logger
from core.utils.tokens import get_token_service

logger = get_logger(__name__)


async def build_call_transcript_text(meeting_id: str, source_url: str) -> str:
    """Строит текст транскрипта из источника записи."""
    return (
        f"Транскрипт встречи {meeting_id}\n"
        f"Источник: {source_url}\n"
        "speaker:user:system: Начат автоматический pipeline транскрипции."
    )


def _build_interservice_auth_headers(actor_user_id: str, company_id: str) -> dict[str, str]:
    """Строит auth заголовки для межсервисных вызовов из worker-задач."""
    token = get_token_service().create_token(actor_user_id, company_id=company_id)
    return {
        "Authorization": f"Bearer {token}",
        "X-Company-Id": company_id,
        "X-User-Id": actor_user_id,
    }


@broker.task
async def handle_command(cmd: dict[str, Any]) -> dict[str, Any]:
    """Обработка realtime команды в sync-worker."""
    command = CommandEnvelope.model_validate(cmd)
    logger.info(
        "task handle_command started: id=%s type=%s actor=%s company=%s",
        command.id, command.type, command.actor_user_id, command.company_id,
    )
    return await dispatch_sync_command(command)


@broker.task
async def sync_finalize_recording_task(recording_id: str, company_id: str, actor_user_id: str) -> None:
    """Финализирует запись: создает raw файл, встречу и запускает транскрипцию."""
    container = get_sync_container()
    recording = await container.call_recording_repository.get(recording_id)
    if recording is None or recording.company_id != company_id:
        raise ValueError(f"Запись {recording_id} не найдена.")
    call = await container.call_repository.get_call(recording.call_id, company_id)
    if call.livekit_room_name is None:
        raise ValueError(f"У звонка {call.call_id} отсутствует livekit_room_name.")

    settings = get_settings()
    provider_job_id = recording.provider_job_id or f"egress-{recording.recording_id}"
    raw_file_id = recording.raw_file_id or recording.recording_id
    raw_storage_url = (
        f"{settings.calls.livekit_url.rstrip('/')}/egress/{call.livekit_room_name}/{provider_job_id}.mp4"
    )
    raw_file = SyncFile(
        file_id=raw_file_id,
        company_id=company_id,
        original_name=f"{recording.recording_id}.mp4",
        mime_type="video/mp4",
        size_bytes=0,
        storage_url=raw_storage_url,
        checksum=None,
    )
    existing_raw = await container.file_repository.get(raw_file_id)
    if existing_raw is None:
        await container.file_repository.create(raw_file)

    await container.call_recording_repository.mark_status(
        recording.recording_id,
        status="uploaded",
        provider_job_id=provider_job_id,
        raw_file_id=raw_file_id,
    )

    meeting = await container.call_meeting_repository.get_by_recording(recording.recording_id, company_id)
    if meeting is None:
        from uuid import uuid4
        from datetime import UTC, datetime
        meeting = await container.call_meeting_repository.create(
            container.call_meeting_repository.model_class(
                meeting_id=uuid4().hex,
                call_id=recording.call_id,
                recording_id=recording.recording_id,
                company_id=company_id,
                channel_id=recording.channel_id,
                space_id=recording.space_id,
                summary_json={},
                export_status="pending",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )

    await sync_transcribe_recording_task.kiq(
        meeting_id=meeting.meeting_id,
        company_id=company_id,
        actor_user_id=actor_user_id,
    )


@broker.task
async def sync_transcribe_recording_task(meeting_id: str, company_id: str, actor_user_id: str) -> None:
    """Создает текст транскрипта и сегменты речи, затем запускает summary."""
    container = get_sync_container()
    meeting = await container.call_meeting_repository.get(meeting_id)
    if meeting is None or meeting.company_id != company_id:
        raise ValueError(f"Встреча {meeting_id} не найдена.")
    try:
        if meeting.recording_id is None:
            raise ValueError(f"У встречи {meeting_id} отсутствует recording_id.")
        recording = await container.call_recording_repository.get(meeting.recording_id)
        if recording is None or recording.company_id != company_id:
            raise ValueError(f"Запись {meeting.recording_id} не найдена.")
        if recording.raw_file_id is None:
            raise ValueError(f"У записи {recording.recording_id} отсутствует raw_file_id.")
        raw_file = await container.file_repository.get(recording.raw_file_id)
        if raw_file is None:
            raise ValueError(f"Файл {recording.raw_file_id} не найден.")

        transcript_text = await build_call_transcript_text(
            meeting_id=meeting.meeting_id,
            source_url=raw_file.storage_url,
        )
        if transcript_text.strip() == "":
            raise ValueError(f"Пустой транскрипт для встречи {meeting.meeting_id}.")
        transcript_file_id = f"{meeting.meeting_id}-transcript-txt"
        transcript_file = SyncFile(
            file_id=transcript_file_id,
            company_id=company_id,
            original_name=f"{meeting.meeting_id}.txt",
            mime_type="text/plain",
            size_bytes=len(transcript_text.encode("utf-8")),
            storage_url=f"sync://meetings/{meeting.meeting_id}/transcript.txt",
            checksum=None,
        )
        if await container.file_repository.get(transcript_file_id) is None:
            await container.file_repository.create(transcript_file)

        from datetime import UTC, datetime
        from sqlalchemy import update
        async with container.sync_db.session() as session:
            await session.execute(
                update(container.call_meeting_repository.model_class)
                .where(container.call_meeting_repository.model_class.meeting_id == meeting.meeting_id)
                .values(
                    transcript_file_id=transcript_file_id,
                    transcript_text_file_id=transcript_file_id,
                    updated_at=datetime.now(UTC),
                )
            )
            await session.commit()
        updated_meeting = await container.call_meeting_repository.get(meeting.meeting_id)
        if updated_meeting is None:
            raise RuntimeError(f"Встреча {meeting.meeting_id} не найдена после записи транскрипта.")
        meeting_payload = CallMeetingRead(
            meeting_id=updated_meeting.meeting_id,
            call_id=updated_meeting.call_id,
            recording_id=updated_meeting.recording_id,
            channel_id=updated_meeting.channel_id,
            space_id=updated_meeting.space_id,
            transcript_file_id=updated_meeting.transcript_file_id,
            transcript_text_file_id=updated_meeting.transcript_text_file_id,
            summary_json=updated_meeting.summary_json or {},
            export_status=updated_meeting.export_status,
            export_target_namespace=updated_meeting.export_target_namespace,
            created_at=updated_meeting.created_at,
            updated_at=updated_meeting.updated_at,
        )
        await publish_realtime_events([event_call_transcript_ready(meeting_payload)])

        segments = [
            SyncCallSpeakerSegment(
                segment_id=f"{meeting.meeting_id}-seg-1",
                meeting_id=meeting.meeting_id,
                company_id=company_id,
                speaker_identity="system",
                speaker_type="user",
                speaker_user_id="system",
                speaker_guest_name=None,
                started_ms=0,
                ended_ms=1500,
                text="Начат автоматический pipeline транскрипции.",
            )
        ]
        await container.call_speaker_segment_repository.replace_for_meeting(
            meeting_id=meeting.meeting_id,
            company_id=company_id,
            segments=segments,
        )
        await sync_summarize_transcript_task.kiq(
            meeting_id=meeting.meeting_id,
            company_id=company_id,
            actor_user_id=actor_user_id,
        )
    except Exception as exc:
        failed_meeting = await container.call_meeting_repository.get(meeting_id)
        if failed_meeting is not None:
            await container.call_meeting_repository.set_export_status(
                failed_meeting.meeting_id,
                status="failed",
                target_namespace=failed_meeting.export_target_namespace,
            )
            failed_meeting = await container.call_meeting_repository.get(meeting_id)
        if failed_meeting is not None:
            failed_payload = CallMeetingRead(
                meeting_id=failed_meeting.meeting_id,
                call_id=failed_meeting.call_id,
                recording_id=failed_meeting.recording_id,
                channel_id=failed_meeting.channel_id,
                space_id=failed_meeting.space_id,
                transcript_file_id=failed_meeting.transcript_file_id,
                transcript_text_file_id=failed_meeting.transcript_text_file_id,
                summary_json=failed_meeting.summary_json or {},
                export_status=failed_meeting.export_status,
                export_target_namespace=failed_meeting.export_target_namespace,
                created_at=failed_meeting.created_at,
                updated_at=failed_meeting.updated_at,
            )
            await publish_realtime_events(
                [event_call_transcript_failed(failed_payload, str(exc))]
            )
        raise


@broker.task
async def sync_summarize_transcript_task(meeting_id: str, company_id: str, actor_user_id: str) -> None:
    """Строит summary через Flows A2A skill и при необходимости запускает автоэкспорт в CRM."""
    container = get_sync_container()
    meeting = await container.call_meeting_repository.get(meeting_id)
    if meeting is None or meeting.company_id != company_id:
        raise ValueError(f"Встреча {meeting_id} не найдена.")
    try:
        if meeting.transcript_text_file_id is None:
            raise ValueError(f"У встречи {meeting_id} отсутствует transcript_text_file_id.")
        transcript_file = await container.file_repository.get(meeting.transcript_text_file_id)
        if transcript_file is None:
            raise ValueError(f"Файл {meeting.transcript_text_file_id} не найден.")

        settings = get_settings()
        flows_url = settings.server.get_flows_service_url()
        if not isinstance(flows_url, str) or flows_url == "":
            raise ValueError("service_urls.flows не задан.")
        flows_a2a_url = f"{flows_url.rstrip('/')}/flows/api/v1/crm"
        auth_headers = _build_interservice_auth_headers(
            actor_user_id=actor_user_id,
            company_id=company_id,
        )

        a2a_timeout_seconds = settings.summary_a2a_timeout_seconds
        if a2a_timeout_seconds <= 0:
            raise ValueError("summary_a2a_timeout_seconds должен быть больше 0.")
        a2a = A2AClient(timeout=a2a_timeout_seconds)
        response = await a2a.send_task(
            base_url=flows_a2a_url,
            skill_id="call_summary",
            content=(
                "Сформируй структурированное summary по встрече.\n"
                f"meeting_id={meeting.meeting_id}\n"
                f"transcript_ref={transcript_file.storage_url}"
            ),
            metadata={"meeting_id": meeting.meeting_id, "company_id": company_id},
            auth_headers=auth_headers,
        )

        summary = {
            "short_summary": response.get("response", ""),
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "risks": [],
        }
        await container.call_meeting_repository.update_summary(meeting.meeting_id, summary)
        after_summary = await container.call_meeting_repository.get(meeting.meeting_id)
        if after_summary is None:
            raise RuntimeError(f"Встреча {meeting.meeting_id} не найдена после summary.")
        summary_payload = CallMeetingRead(
            meeting_id=after_summary.meeting_id,
            call_id=after_summary.call_id,
            recording_id=after_summary.recording_id,
            channel_id=after_summary.channel_id,
            space_id=after_summary.space_id,
            transcript_file_id=after_summary.transcript_file_id,
            transcript_text_file_id=after_summary.transcript_text_file_id,
            summary_json=after_summary.summary_json or {},
            export_status=after_summary.export_status,
            export_target_namespace=after_summary.export_target_namespace,
            created_at=after_summary.created_at,
            updated_at=after_summary.updated_at,
        )
        await publish_realtime_events([event_call_summary_ready(summary_payload)])

        if meeting.space_id is not None:
            space = await container.space_repository.get(meeting.space_id)
            if space is not None and (space.auto_export_summary_to_crm or space.auto_export_transcript_to_crm):
                if space.namespace is None:
                    raise ValueError("Для автоэкспорта встречи требуется namespace пространства.")
                await sync_export_meeting_to_crm_task.kiq(
                    meeting_id=meeting.meeting_id,
                    company_id=company_id,
                    actor_user_id=actor_user_id,
                    namespace=space.namespace,
                )
    except Exception as exc:
        failed_meeting = await container.call_meeting_repository.get(meeting_id)
        if failed_meeting is not None:
            await container.call_meeting_repository.set_export_status(
                failed_meeting.meeting_id,
                status="failed",
                target_namespace=failed_meeting.export_target_namespace,
            )
            failed_meeting = await container.call_meeting_repository.get(meeting_id)
        if failed_meeting is not None:
            failed_payload = CallMeetingRead(
                meeting_id=failed_meeting.meeting_id,
                call_id=failed_meeting.call_id,
                recording_id=failed_meeting.recording_id,
                channel_id=failed_meeting.channel_id,
                space_id=failed_meeting.space_id,
                transcript_file_id=failed_meeting.transcript_file_id,
                transcript_text_file_id=failed_meeting.transcript_text_file_id,
                summary_json=failed_meeting.summary_json or {},
                export_status=failed_meeting.export_status,
                export_target_namespace=failed_meeting.export_target_namespace,
                created_at=failed_meeting.created_at,
                updated_at=failed_meeting.updated_at,
            )
            await publish_realtime_events(
                [event_call_summary_failed(failed_payload, str(exc))]
            )
        raise


@broker.task
async def sync_export_meeting_to_crm_task(
    meeting_id: str,
    company_id: str,
    actor_user_id: str,
    namespace: str,
) -> None:
    """Экспортирует встречу в CRM как note:call."""
    if not isinstance(namespace, str) or namespace.strip() == "":
        raise ValueError("namespace обязателен.")
    container = get_sync_container()
    meeting = await container.call_meeting_repository.get(meeting_id)
    if meeting is None or meeting.company_id != company_id:
        raise ValueError(f"Встреча {meeting_id} не найдена.")
    recording = None
    if meeting.recording_id is not None:
        recording = await container.call_recording_repository.get(meeting.recording_id)
    call_participants = await container.call_repository.list_participants(meeting.call_id)
    registered_users: list[dict[str, str]] = []
    guests: list[dict[str, str]] = []
    for participant in call_participants:
        identity = participant.user_id
        if identity.startswith("guest:"):
            parts = identity.split(":", 2)
            guests.append(
                {
                    "guest_identity": identity,
                    "guest_name": parts[2] if len(parts) >= 3 else "guest",
                }
            )
        else:
            registered_users.append(
                {
                    "user_id": identity,
                    "display_name": identity,
                }
            )
    segments = await container.call_speaker_segment_repository.list_for_meeting(meeting.meeting_id, company_id)
    speaker_segments = [
        {
            "speaker_identity": s.speaker_identity,
            "speaker_type": s.speaker_type,
            "speaker_user_id": s.speaker_user_id,
            "speaker_guest_name": s.speaker_guest_name,
            "started_ms": s.started_ms,
            "ended_ms": s.ended_ms,
            "text": s.text,
        }
        for s in segments
    ]

    from core.clients import ServiceClient

    service_client = ServiceClient()
    auth_headers = _build_interservice_auth_headers(
        actor_user_id=actor_user_id,
        company_id=company_id,
    )
    payload = {
        "entity_type": "note",
        "entity_subtype": "call",
        "name": f"Встреча {meeting.meeting_id}",
        "description": "Автоматически экспортировано из Sync.",
        "namespace": namespace,
        "attributes": {
            "meeting_id": meeting.meeting_id,
            "call_id": meeting.call_id,
            "channel_id": meeting.channel_id,
            "space_id": meeting.space_id,
            "recording_id": meeting.recording_id,
            "raw_file_id": recording.raw_file_id if recording is not None else None,
            "transcript_file_id": meeting.transcript_file_id,
            "summary": meeting.summary_json,
            "participants": {
                "registered_users": registered_users,
                "guests": guests,
            },
            "speaker_segments": speaker_segments,
        },
    }
    try:
        await service_client.post(
            "crm",
            "/crm/api/v1/entities/",
            json=payload,
            headers=auth_headers,
        )
    except Exception:
        await container.call_meeting_repository.set_export_status(
            meeting.meeting_id,
            status="failed",
            target_namespace=namespace,
        )
        failed = await container.call_meeting_repository.get(meeting.meeting_id)
        if failed is None:
            raise RuntimeError("Встреча пропала после ошибки экспорта.")
        await publish_realtime_events(
            [
                event_call_export_crm_failed(
                    CallMeetingRead(
                        meeting_id=failed.meeting_id,
                        call_id=failed.call_id,
                        recording_id=failed.recording_id,
                        channel_id=failed.channel_id,
                        space_id=failed.space_id,
                        transcript_file_id=failed.transcript_file_id,
                        transcript_text_file_id=failed.transcript_text_file_id,
                        summary_json=failed.summary_json or {},
                        export_status=failed.export_status,
                        export_target_namespace=failed.export_target_namespace,
                        created_at=failed.created_at,
                        updated_at=failed.updated_at,
                    )
                )
            ]
        )
        raise
    await container.call_meeting_repository.set_export_status(
        meeting.meeting_id,
        status="done",
        target_namespace=namespace,
    )
    done = await container.call_meeting_repository.get(meeting.meeting_id)
    if done is None:
        raise RuntimeError("Встреча пропала после экспорта.")
    await publish_realtime_events(
        [
            event_call_export_crm_done(
                CallMeetingRead(
                    meeting_id=done.meeting_id,
                    call_id=done.call_id,
                    recording_id=done.recording_id,
                    channel_id=done.channel_id,
                    space_id=done.space_id,
                    transcript_file_id=done.transcript_file_id,
                    transcript_text_file_id=done.transcript_text_file_id,
                    summary_json=done.summary_json or {},
                    export_status=done.export_status,
                    export_target_namespace=done.export_target_namespace,
                    created_at=done.created_at,
                    updated_at=done.updated_at,
                )
            )
        ]
    )
