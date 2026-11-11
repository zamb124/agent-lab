"""Default retention and Docs placement per FileSourceKind."""

from __future__ import annotations

from dataclasses import dataclass

from core.documents.placement import DocumentPlacement
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.retention import FileRetentionKind, FileRetentionSpec
from core.types import JsonObject

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
    FileSourceKind.CODE_AGENT_SOURCE: FileSourceDefaults(
        retention_kind=FileRetentionKind.FLOW_ASSET
    ),
    FileSourceKind.PRODUCT: FileSourceDefaults(
        retention_kind=FileRetentionKind.PRODUCT
    ),
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


PLACED_SOURCE_KINDS: frozenset[FileSourceKind] = frozenset(
    kind for kind in FileSourceKind if kind not in DOCS_PLACEMENT_EXEMPT_SOURCE_KINDS
)


def build_file_create_spec(
    *,
    source_kind: FileSourceKind,
    source_ref: FileSourceRef,
    retention: FileRetentionSpec | None = None,
    placement: DocumentPlacement | None = None,
    post_create: FilePostCreate | None = None,
    metadata: JsonObject | None = None,
    tags: list[str] | None = None,
) -> FileCreateSpec:
    effective_retention = (
        retention if retention is not None else default_retention_for_source(source_kind)
    )
    return FileCreateSpec(
        source_kind=source_kind,
        source_ref=source_ref,
        retention=effective_retention,
        placement=placement,
        post_create=post_create,
        metadata=metadata,
        tags=tags,
    )
