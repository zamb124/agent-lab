"""Default retention and placement per FileSourceKind."""

from __future__ import annotations

from dataclasses import dataclass

from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.retention import FileRetentionKind, FileRetentionSpec


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
