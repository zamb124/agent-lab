"""Default retention and Docs placement per FileSourceKind."""

from __future__ import annotations

from dataclasses import dataclass

from core.context import resolve_namespace_or_raise
from core.documents.placement import DocsPlacement, DocsPlacementAnchor, DocsPlacementSourceKind
from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.retention import FileRetentionKind, FileRetentionSpec

DOCS_PLACEMENT_EXEMPT_SOURCE_KINDS: frozenset[FileSourceKind] = frozenset(
    {
        FileSourceKind.OFFICE_DOCUMENT,
        FileSourceKind.GENERATED_EPHEMERAL,
        FileSourceKind.PLATFORM_AUXILIARY,
    }
)


@dataclass(frozen=True, slots=True)
class FileSourceDefaults:
    retention_kind: FileRetentionKind


FILE_SOURCE_DEFAULTS: dict[FileSourceKind, FileSourceDefaults] = {
    FileSourceKind.CRM_ENTITY: FileSourceDefaults(retention_kind=FileRetentionKind.CRM_ENTITY),
    FileSourceKind.FLOW_SESSION: FileSourceDefaults(retention_kind=FileRetentionKind.FLOW_SESSION),
    FileSourceKind.FLOW_ASSET: FileSourceDefaults(retention_kind=FileRetentionKind.FLOW_ASSET),
    FileSourceKind.WORK_ITEM: FileSourceDefaults(retention_kind=FileRetentionKind.WORK_ITEM),
    FileSourceKind.SYNC_MESSAGE: FileSourceDefaults(
        retention_kind=FileRetentionKind.SYNC_MESSAGE_ATTACHMENT
    ),
    FileSourceKind.SYNC_CALL_RECORDING: FileSourceDefaults(
        retention_kind=FileRetentionKind.SYNC_CALL_RECORDING
    ),
    FileSourceKind.SYNC_SPEECH_SEGMENT: FileSourceDefaults(
        retention_kind=FileRetentionKind.SYNC_SPEECH_SEGMENT
    ),
    FileSourceKind.SYNC_CHANNEL_ASSET: FileSourceDefaults(
        retention_kind=FileRetentionKind.SYNC_CHANNEL_ASSET
    ),
    FileSourceKind.BROWSER_ARTIFACT: FileSourceDefaults(
        retention_kind=FileRetentionKind.BROWSER_ARTIFACT
    ),
    FileSourceKind.RAG_DOCUMENT: FileSourceDefaults(retention_kind=FileRetentionKind.RAG_DOCUMENT),
    FileSourceKind.OFFICE_DOCUMENT: FileSourceDefaults(
        retention_kind=FileRetentionKind.OFFICE_DOCUMENT
    ),
    FileSourceKind.CALENDAR_EVENT: FileSourceDefaults(
        retention_kind=FileRetentionKind.CALENDAR_EVENT_ATTACHMENT
    ),
    FileSourceKind.MAIL_MESSAGE: FileSourceDefaults(
        retention_kind=FileRetentionKind.MAIL_ATTACHMENT
    ),
    FileSourceKind.WIKI_PAGE: FileSourceDefaults(retention_kind=FileRetentionKind.WIKI_PAGE),
    FileSourceKind.PLATFORM_AUXILIARY: FileSourceDefaults(
        retention_kind=FileRetentionKind.PLATFORM_DEFAULT
    ),
    FileSourceKind.GENERATED_EPHEMERAL: FileSourceDefaults(
        retention_kind=FileRetentionKind.GENERATED_EPHEMERAL
    ),
}


def default_retention_for_source(source_kind: FileSourceKind) -> FileRetentionSpec:
    defaults = FILE_SOURCE_DEFAULTS.get(source_kind)
    if defaults is None:
        raise ValueError(f"no default retention for FileSourceKind: {source_kind}")
    return FileRetentionSpec(kind=defaults.retention_kind)


def is_docs_placement_exempt(source_kind: FileSourceKind) -> bool:
    return source_kind in DOCS_PLACEMENT_EXEMPT_SOURCE_KINDS


SOURCE_KIND_TO_DOCS_PLACEMENT: dict[FileSourceKind, DocsPlacementSourceKind] = {
    FileSourceKind.CRM_ENTITY: "crm_entity",
    FileSourceKind.FLOW_SESSION: "flow_session",
    FileSourceKind.FLOW_ASSET: "flow_asset",
    FileSourceKind.WORK_ITEM: "work_item",
    FileSourceKind.SYNC_MESSAGE: "sync_message",
    FileSourceKind.SYNC_CALL_RECORDING: "sync_call_recording",
    FileSourceKind.SYNC_SPEECH_SEGMENT: "sync_speech_segment",
    FileSourceKind.SYNC_CHANNEL_ASSET: "sync_channel_asset",
    FileSourceKind.BROWSER_ARTIFACT: "browser_artifact",
    FileSourceKind.RAG_DOCUMENT: "rag_document",
    FileSourceKind.CALENDAR_EVENT: "calendar_event",
    FileSourceKind.MAIL_MESSAGE: "mail_message",
    FileSourceKind.WIKI_PAGE: "wiki_page",
}


def _placement_source_kind(source_kind: FileSourceKind) -> DocsPlacementSourceKind:
    mapped = SOURCE_KIND_TO_DOCS_PLACEMENT.get(source_kind)
    if mapped is None:
        raise ValueError(f"no DocsPlacement mapping for FileSourceKind: {source_kind}")
    return mapped


def source_ref_to_placement_anchor(
    source_kind: FileSourceKind,
    source_ref: FileSourceRef,
) -> DocsPlacementAnchor:
    return DocsPlacementAnchor(
        source_kind=_placement_source_kind(source_kind),
        entity_id=source_ref.entity_id,
        entity_type=source_ref.entity_type,
        entity_title=source_ref.entity_title,
        import_id=source_ref.import_id,
        flow_id=source_ref.flow_id,
        flow_slug=source_ref.flow_slug,
        session_id=source_ref.session_id,
        work_item_id=source_ref.work_item_id,
        work_queue_id=source_ref.work_queue_id,
        board_id=source_ref.board_id,
        channel_id=source_ref.channel_id,
        message_id=source_ref.message_id,
        call_id=source_ref.call_id,
        recording_id=source_ref.recording_id,
        event_id=source_ref.event_id,
        browser_session_id=source_ref.browser_session_id,
        namespace_id=source_ref.namespace_id,
        mailbox_binding_id=source_ref.mailbox_binding_id,
        mail_uid=source_ref.mail_uid,
        mailbox_email=source_ref.mailbox_email,
        mail_subject=source_ref.mail_subject,
        wiki_page_id=source_ref.wiki_page_id,
    )


def default_docs_placement(
    source_kind: FileSourceKind,
    source_ref: FileSourceRef,
    *,
    title: str | None = None,
    namespace: str | None = None,
) -> DocsPlacement | None:
    """Build auto DocsPlacement for durable sources. Exempt kinds → None."""
    if is_docs_placement_exempt(source_kind):
        return None
    resolved_namespace = resolve_namespace_or_raise(namespace)
    anchor = source_ref_to_placement_anchor(source_kind, source_ref)
    return DocsPlacement(
        namespace=resolved_namespace,
        file_id="",
        title=title,
        anchor=anchor,
    )


def build_file_create_spec(
    *,
    source_kind: FileSourceKind,
    source_ref: FileSourceRef,
    retention: FileRetentionSpec | None = None,
    **kwargs: object,
) -> FileCreateSpec:
    effective_retention = retention if retention is not None else default_retention_for_source(source_kind)
    fields = {
        "source_kind": source_kind,
        "source_ref": source_ref,
        "retention": effective_retention,
        **kwargs,
    }
    return FileCreateSpec.model_validate(fields)
