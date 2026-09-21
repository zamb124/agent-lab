"""Lifecycle операции Documents: item mapping, events, shares."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.office.container import OfficeContainer
from apps.office.db.models import OfficeDocumentBinding
from apps.office.models.api import OfficeDocumentItem, OfficeDocumentRagIndexStatus
from core.context import get_context
from core.files.create_spec import FileSourceKind
from core.files.retention import FileRetentionKind
from core.logging import get_logger
from core.models.identity_models import User
from core.rag.indexable import effective_rag_file_category, is_rag_indexable_file_category
from core.types import JsonObject

logger = get_logger(__name__)


async def binding_to_item(
    container: OfficeContainer,
    row: OfficeDocumentBinding,
    users_by_id: dict[str, User] | None = None,
    *,
    rag_index_status: OfficeDocumentRagIndexStatus | None = None,
    resolve_rag_index_status: bool = True,
) -> OfficeDocumentItem:
    resolved_rag_status: OfficeDocumentRagIndexStatus | None = rag_index_status
    if resolve_rag_index_status:
        status_by_file_id = await _rag_index_status_by_file_id(container, [row])
        resolved_rag_status = status_by_file_id.get(row.file_id)
    author = users_by_id.get(row.created_by_user_id) if users_by_id else None
    if author is None:
        loaded = await container.user_repository.get(row.created_by_user_id)
        if loaded is not None:
            author = loaded
    if author is not None:
        display_name = author.name
        avatar_url = author.avatar_url
    else:
        display_name = row.created_by_user_id
        avatar_url = None
    file_record = await container.file_repository.get(row.file_id)
    if file_record is None:
        logger.warning(
            "office.binding_file_missing",
            file_id=row.file_id,
            catalog_id=row.catalog_id,
            company_id=row.company_id,
        )
        return OfficeDocumentItem(
            file_id=row.file_id,
            catalog_id=row.catalog_id,
            title=row.title,
            file_category=row.file_category,
            onlyoffice_document_type=row.onlyoffice_document_type,
            file_availability="missing",
            file_size=0,
            file_expires_at=None,
            created_at=row.created_at,
            updated_at=row.updated_at,
            created_by_user_id=row.created_by_user_id,
            created_by_display_name=display_name,
            created_by_avatar_url=avatar_url,
            rag_index_status=resolved_rag_status,
        )
    file_record = await container.files_service.promote_retention(
        row.file_id,
        retention_kind=FileRetentionKind.OFFICE_DOCUMENT,
        source_kind=FileSourceKind.OFFICE_DOCUMENT,
    )
    return OfficeDocumentItem(
        file_id=row.file_id,
        catalog_id=row.catalog_id,
        title=row.title,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
        file_availability="available",
        file_size=file_record.file_size,
        file_expires_at=file_record.expires_at,
        created_at=row.created_at,
        updated_at=file_record.updated_at,
        created_by_user_id=row.created_by_user_id,
        created_by_display_name=display_name,
        created_by_avatar_url=avatar_url,
        rag_index_status=resolved_rag_status,
    )


async def _rag_index_status_by_file_id(
    container: OfficeContainer,
    rows: list[OfficeDocumentBinding],
) -> dict[str, OfficeDocumentRagIndexStatus | None]:
    """Per-file RAG status: null если каталог без индекса; иначе ready/pending/failed/absent.

    ``absent`` — только non-indexable категории; indexable без status-row → ``pending``.
    """
    if not rows:
        return {}
    context = get_context()
    if context is None:
        raise ValueError("Request context is missing")
    if context.active_company is None:
        raise ValueError("No active company")
    company_id = context.active_company.company_id
    workspace_namespace = context.active_namespace.strip()
    if workspace_namespace == "":
        raise ValueError("active_namespace is required")

    catalog_ids = {row.catalog_id for row in rows}
    enabled_catalog_ids: set[str] = set()
    for catalog_id in catalog_ids:
        catalog = await container.catalog_repository.get(
            catalog_id,
            company_id,
            workspace_namespace,
        )
        if catalog is not None and catalog.rag_index_enabled:
            enabled_catalog_ids.add(catalog_id)

    status_by_file_id: dict[str, OfficeDocumentRagIndexStatus | None] = {
        row.file_id: None for row in rows
    }
    indexable_rows: list[OfficeDocumentBinding] = []
    for row in rows:
        if row.catalog_id not in enabled_catalog_ids:
            continue
        file_record = await container.file_repository.get(row.file_id)
        document_name = file_record.original_name if file_record is not None else row.title
        if not is_rag_indexable_file_category(
            effective_rag_file_category(
                file_category=row.file_category,
                document_name=document_name,
            )
        ):
            status_by_file_id[row.file_id] = "absent"
            continue
        indexable_rows.append(row)

    if not indexable_rows:
        return status_by_file_id

    buckets = await container.catalog_rag_index_service.batch_status_buckets(
        [row.file_id for row in indexable_rows],
    )
    for row in indexable_rows:
        # Indexable file in enabled catalog: no RAG status row yet means queued/pending,
        # not "absent" (absent is for non-indexable categories only).
        bucket = buckets[row.file_id]
        status_by_file_id[row.file_id] = "pending" if bucket == "absent" else bucket
    return status_by_file_id


async def bindings_to_items(
    container: OfficeContainer,
    rows: list[OfficeDocumentBinding],
) -> list[OfficeDocumentItem]:
    user_ids = {row.created_by_user_id for row in rows}
    users_by_id: dict[str, User] = {}
    for uid in user_ids:
        loaded = await container.user_repository.get(uid)
        if loaded is not None:
            users_by_id[uid] = loaded
    rag_status_by_file_id = await _rag_index_status_by_file_id(container, rows)
    items: list[OfficeDocumentItem] = []
    for row in rows:
        items.append(
            await binding_to_item(
                container,
                row,
                users_by_id,
                rag_index_status=rag_status_by_file_id.get(row.file_id),
                resolve_rag_index_status=False,
            )
        )
    return items


async def record_document_event(
    container: OfficeContainer,
    *,
    file_id: str,
    company_id: str,
    event_type: str,
    user_id: str,
    payload: JsonObject | None = None,
) -> None:
    event_payload: JsonObject = payload if payload is not None else {}
    _ = await container.document_event_repository.append(
        file_id=file_id,
        company_id=company_id,
        event_type=event_type,
        user_id=user_id,
        payload=event_payload,
    )


def share_expires_at(expires_in_hours: int | None) -> datetime | None:
    if expires_in_hours is None:
        return None
    return datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
