"""Pydantic модели встреч, записей и транскрипции Sync."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RecordingStatus = Literal["requested", "recording", "uploaded", "failed"]
ExportStatus = Literal["pending", "done", "failed"]
SpeakerType = Literal["user", "guest"]


class CallRecordingRead(BaseModel):
    recording_id: str
    call_id: str
    channel_id: str
    space_id: str | None = None
    status: RecordingStatus
    provider_job_id: str | None = None
    raw_file_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime
    error: str | None = None


class CallSpeakerSegmentRead(BaseModel):
    segment_id: str
    meeting_id: str
    speaker_identity: str
    speaker_type: SpeakerType
    speaker_user_id: str | None = None
    speaker_guest_name: str | None = None
    started_ms: int
    ended_ms: int
    text: str
    created_at: datetime


class CallMeetingRead(BaseModel):
    meeting_id: str
    call_id: str
    recording_id: str | None = None
    channel_id: str
    space_id: str | None = None
    transcript_file_id: str | None = None
    transcript_text_file_id: str | None = None
    summary_json: dict[str, Any] = Field(default_factory=dict)
    export_status: ExportStatus
    export_target_namespace: str | None = None
    created_at: datetime
    updated_at: datetime


class CallMeetingDetailsRead(BaseModel):
    meeting: CallMeetingRead
    recording: CallRecordingRead | None = None
    segments: list[CallSpeakerSegmentRead] = Field(default_factory=list)


class CallMeetingListFilters(BaseModel):
    channel_id: str | None = None
    space_id: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class ExportMeetingToCrmRequest(BaseModel):
    namespace: str | None = None

