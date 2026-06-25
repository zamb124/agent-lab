"""Retention contract for FileRecord."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from core.config import get_settings
from core.models.base import StrictBaseModel


class FileRetentionKind(StrEnum):
    PERMANENT = "permanent"
    FLOW_SESSION = "flow_session"
    FLOW_ASSET = "flow_asset"
    CRM_ENTITY = "crm_entity"
    CRM_KNOWLEDGE_IMPORT = "crm_knowledge_import"
    WORK_ITEM = "work_item"
    SYNC_MESSAGE_ATTACHMENT = "sync_message_attachment"
    SYNC_CHANNEL_ASSET = "sync_channel_asset"
    SYNC_CALL_RECORDING = "sync_call_recording"
    SYNC_SPEECH_SEGMENT = "sync_speech_segment"
    CALENDAR_EVENT_ATTACHMENT = "calendar_event_attachment"
    BROWSER_ARTIFACT = "browser_artifact"
    GENERATED_EPHEMERAL = "generated_ephemeral"
    RAG_DOCUMENT = "rag_document"
    OFFICE_DOCUMENT = "office_document"
    PLATFORM_DEFAULT = "platform_default"


class FileRetentionSpec(StrictBaseModel):
    kind: FileRetentionKind
    ttl_seconds: int | None = None


def resolve_retention_ttl_seconds(spec: FileRetentionSpec) -> int:
    """0 = permanent; >0 = seconds from created_at."""
    if spec.ttl_seconds is not None:
        if spec.ttl_seconds < 0:
            raise ValueError("FileRetentionSpec.ttl_seconds must be >= 0")
        if spec.kind != FileRetentionKind.PERMANENT and spec.ttl_seconds == 0:
            raise ValueError("ttl_seconds=0 requires kind=permanent")
        if spec.kind == FileRetentionKind.PERMANENT and spec.ttl_seconds != 0:
            raise ValueError("kind=permanent requires ttl_seconds=0 or omit ttl_seconds")
        return spec.ttl_seconds

    settings = get_settings()
    retention = settings.files.retention
    kind = spec.kind
    if kind == FileRetentionKind.PERMANENT:
        return 0
    if kind == FileRetentionKind.FLOW_SESSION:
        return retention.flow_session_ttl_seconds
    if kind == FileRetentionKind.SYNC_SPEECH_SEGMENT:
        return retention.sync_speech_segment_ttl_seconds
    if kind == FileRetentionKind.BROWSER_ARTIFACT:
        return retention.browser_artifact_ttl_seconds
    if kind == FileRetentionKind.GENERATED_EPHEMERAL:
        return retention.generated_ephemeral_ttl_seconds
    if kind in {
        FileRetentionKind.FLOW_ASSET,
        FileRetentionKind.CRM_ENTITY,
        FileRetentionKind.CRM_KNOWLEDGE_IMPORT,
        FileRetentionKind.WORK_ITEM,
        FileRetentionKind.SYNC_MESSAGE_ATTACHMENT,
        FileRetentionKind.SYNC_CHANNEL_ASSET,
        FileRetentionKind.SYNC_CALL_RECORDING,
        FileRetentionKind.CALENDAR_EVENT_ATTACHMENT,
        FileRetentionKind.OFFICE_DOCUMENT,
    }:
        return 0
    if kind == FileRetentionKind.RAG_DOCUMENT:
        return retention.default_ttl_seconds
    if kind == FileRetentionKind.PLATFORM_DEFAULT:
        return retention.default_ttl_seconds
    raise ValueError(f"unsupported FileRetentionKind: {kind}")


RetentionPolicy = Literal["finite", "permanent"]
