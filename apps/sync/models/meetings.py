"""Pydantic модели записей звонков Sync."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

RecordingStatus = Literal["requested", "recording", "uploaded", "failed"]


class CallRecordingRead(BaseModel):
    recording_id: str
    call_id: str
    channel_id: str
    namespace: str
    started_by_user_id: str | None = None
    status: RecordingStatus
    provider_job_id: str | None = None
    raw_file_id: str | None = None
    raw_file_storage_url: str | None = None
    raw_file_download_url: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime
    error: str | None = None
