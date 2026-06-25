"""Docs placement contract for Office explorer auto-catalog."""

from __future__ import annotations

from typing import Literal

from core.files.retention import FileRetentionSpec
from core.models.base import StrictBaseModel

DocsPlacementSourceKind = Literal[
    "crm_entity",
    "crm_knowledge_import",
    "flow_session",
    "flow_asset",
    "work_item",
    "work_item_comment",
    "work_item_resolution",
    "sync_channel_message",
    "sync_call_recording",
    "sync_speech_segment",
    "sync_channel_asset",
    "calendar_event",
    "browser_session",
    "rag_namespace",
    "office_manual",
    "manual",
]


class DocsPlacementAnchor(StrictBaseModel):
    source_kind: DocsPlacementSourceKind
    entity_id: str | None = None
    entity_type: str | None = None
    entity_title: str | None = None
    import_id: str | None = None
    flow_id: str | None = None
    flow_slug: str | None = None
    session_id: str | None = None
    work_item_id: str | None = None
    comment_id: str | None = None
    channel_id: str | None = None
    message_id: str | None = None
    call_id: str | None = None
    recording_id: str | None = None
    event_id: str | None = None
    browser_session_id: str | None = None
    namespace_id: str | None = None


class DocsPlacement(StrictBaseModel):
    namespace: str
    file_id: str
    title: str | None = None
    path_segments: list[str] | None = None
    anchor: DocsPlacementAnchor | None = None
    retention: FileRetentionSpec | None = None


class DocsBindResult(StrictBaseModel):
    binding_id: str
    catalog_id: str
    created: bool
    catalog_path: list[str]
