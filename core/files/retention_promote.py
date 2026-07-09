"""Upgrade FileRecord retention to permanent domain kinds (never downgrade)."""

from __future__ import annotations

from datetime import UTC, datetime

from core.files.create_spec import FileSourceKind
from core.files.models import FileRecord
from core.files.retention import FileRetentionKind
from core.types import JsonObject

_PROMOTION_TARGETS: frozenset[FileRetentionKind] = frozenset(
    {
        FileRetentionKind.OFFICE_DOCUMENT,
        FileRetentionKind.CRM_ENTITY,
        FileRetentionKind.CRM_KNOWLEDGE_IMPORT,
        FileRetentionKind.WORK_ITEM,
        FileRetentionKind.FLOW_ASSET,
        FileRetentionKind.CALENDAR_EVENT_ATTACHMENT,
    }
)

_SOURCE_KIND_BY_RETENTION: dict[FileRetentionKind, FileSourceKind] = {
    FileRetentionKind.OFFICE_DOCUMENT: FileSourceKind.OFFICE_DOCUMENT,
    FileRetentionKind.CRM_ENTITY: FileSourceKind.CRM_ENTITY,
    FileRetentionKind.CRM_KNOWLEDGE_IMPORT: FileSourceKind.PLATFORM_AUXILIARY,
    FileRetentionKind.WORK_ITEM: FileSourceKind.PLATFORM_AUXILIARY,
    FileRetentionKind.FLOW_ASSET: FileSourceKind.FLOW_ASSET,
    FileRetentionKind.CALENDAR_EVENT_ATTACHMENT: FileSourceKind.CALENDAR_EVENT,
}


def _record_is_permanent(record: FileRecord) -> bool:
    return record.expires_at is None


def promote_file_retention_record(
    record: FileRecord,
    *,
    retention_kind: FileRetentionKind,
    source_kind: FileSourceKind | None = None,
) -> tuple[FileRecord, bool]:
    if retention_kind not in _PROMOTION_TARGETS:
        raise ValueError(f"retention promotion unsupported for kind: {retention_kind}")

    effective_source_kind = (
        source_kind if source_kind is not None else _SOURCE_KIND_BY_RETENTION[retention_kind]
    )
    if _record_is_permanent(record) and record.retention_kind == retention_kind.value:
        metadata_source = record.metadata.get("source_kind")
        if isinstance(metadata_source, str) and metadata_source == effective_source_kind.value:
            return record, False

    metadata: JsonObject = dict(record.metadata)
    metadata["source_kind"] = effective_source_kind.value
    promoted = record.model_copy(
        update={
            "retention_kind": retention_kind.value,
            "expires_at": None,
            "metadata": metadata,
            "updated_at": datetime.now(UTC),
        }
    )
    return promoted, True
