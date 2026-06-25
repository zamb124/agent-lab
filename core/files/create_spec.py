"""File create contract — единственный вход в FilesService."""

from __future__ import annotations

from enum import StrEnum

from pydantic import model_validator

from core.documents.placement import DocsPlacement
from core.files.retention import FileRetentionSpec
from core.models.base import StrictBaseModel
from core.types import JsonObject


class FileSourceKind(StrEnum):
    CRM_ENTITY = "crm_entity"
    FLOW_SESSION = "flow_session"
    FLOW_ASSET = "flow_asset"
    WORK_ITEM = "work_item"
    SYNC_MESSAGE = "sync_message"
    SYNC_CALL_RECORDING = "sync_call_recording"
    SYNC_SPEECH_SEGMENT = "sync_speech_segment"
    SYNC_CHANNEL_ASSET = "sync_channel_asset"
    BROWSER_ARTIFACT = "browser_artifact"
    RAG_DOCUMENT = "rag_document"
    OFFICE_DOCUMENT = "office_document"
    CALENDAR_EVENT = "calendar_event"
    PLATFORM_AUXILIARY = "platform_auxiliary"
    GENERATED_EPHEMERAL = "generated_ephemeral"


class FileSourceRef(StrictBaseModel):
    entity_id: str | None = None
    flow_id: str | None = None
    flow_slug: str | None = None
    session_id: str | None = None
    work_item_id: str | None = None
    channel_id: str | None = None
    message_id: str | None = None
    call_id: str | None = None
    recording_id: str | None = None
    namespace_id: str | None = None
    event_id: str | None = None
    browser_session_id: str | None = None
    import_id: str | None = None


class FilePostCreate(StrictBaseModel):
    rag_index_namespace: str | None = None
    rag_metadata: JsonObject | None = None
    is_public: bool = False


class FileCreateSpec(StrictBaseModel):
    source_kind: FileSourceKind
    source_ref: FileSourceRef
    retention: FileRetentionSpec
    placement: DocsPlacement | None = None
    post_create: FilePostCreate | None = None
    metadata: JsonObject | None = None
    tags: list[str] | None = None

    @model_validator(mode="after")
    def _validate_source_ref(self) -> FileCreateSpec:
        ref = self.source_ref
        kind = self.source_kind
        if kind in {FileSourceKind.CRM_ENTITY, FileSourceKind.OFFICE_DOCUMENT}:
            if not ref.entity_id:
                raise ValueError(f"source_ref.entity_id required for {kind}")
        if kind == FileSourceKind.RAG_DOCUMENT:
            if not ref.namespace_id:
                raise ValueError("source_ref.namespace_id required for rag_document")
        if kind == FileSourceKind.FLOW_SESSION:
            if not ref.session_id:
                raise ValueError("source_ref.session_id required for flow_session")
        if kind == FileSourceKind.BROWSER_ARTIFACT:
            if not ref.browser_session_id:
                raise ValueError("source_ref.browser_session_id required for browser_artifact")
        if kind == FileSourceKind.SYNC_MESSAGE:
            if not ref.channel_id:
                raise ValueError("source_ref.channel_id required for sync_message")
        if kind == FileSourceKind.WORK_ITEM:
            if not ref.work_item_id:
                raise ValueError("source_ref.work_item_id required for work_item")
        return self
