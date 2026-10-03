"""Сборка элемента списка Документов из FileRecord."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from apps.office.models.api import OfficeDocumentItem, OfficeDocumentRagIndexStatus
from apps.office.services.file_binding_metadata import resolve_binding_metadata
from core.context import get_context
from core.documents.catalog import DocumentCatalog
from core.files.create_spec import FileSourceKind
from core.files.models import FileRecord
from core.models.identity_models import User
from core.rag.indexable import effective_rag_file_category, is_rag_indexable_file_category

if TYPE_CHECKING:
    from apps.office.services.catalog_rag_index_service import OfficeCatalogRagIndexService


def document_title(record: FileRecord) -> str:
    """Отображаемое имя: для office-документов — `original_name` без расширения,
    для управляемых файлов (code-agent, вложения) — полное имя файла."""
    if record.source_kind == FileSourceKind.OFFICE_DOCUMENT:
        return Path(record.original_name).stem or record.original_name
    return record.original_name


async def _rag_index_status_by_file_id(
    catalog_rag_index_service: OfficeCatalogRagIndexService | None,
    records: list[FileRecord],
) -> dict[str, OfficeDocumentRagIndexStatus | None]:
    """Per-file RAG status: null если каталог без индекса; иначе ready/pending/failed/absent.

    ``absent`` — только non-indexable категории; indexable без status-row → ``pending``.
    """
    status_by_file_id: dict[str, OfficeDocumentRagIndexStatus | None] = {
        record.file_id: None for record in records
    }
    if not records or catalog_rag_index_service is None:
        return status_by_file_id
    context = get_context()
    if context is None or context.active_company is None:
        return status_by_file_id
    company_id = context.active_company.company_id
    workspace_namespace = context.active_namespace.strip()
    if workspace_namespace == "":
        return status_by_file_id

    catalog_ids = {
        record.catalog_id for record in records if record.catalog_id is not None
    }
    enabled_catalog_ids: set[str] = set()
    for catalog_id in catalog_ids:
        catalog = await DocumentCatalog.catalog_in_namespace(
            catalog_id,
            company_id,
            workspace_namespace,
        )
        if catalog is not None and catalog.rag_index_enabled:
            enabled_catalog_ids.add(catalog_id)

    indexable_file_ids: list[str] = []
    for record in records:
        if record.catalog_id is None or record.catalog_id not in enabled_catalog_ids:
            continue
        file_category, _office_type = resolve_binding_metadata(
            record.original_name,
            record.content_type.split(";", 1)[0].strip(),
        )
        if not is_rag_indexable_file_category(
            effective_rag_file_category(
                file_category=file_category,
                document_name=record.original_name,
            )
        ):
            status_by_file_id[record.file_id] = "absent"
            continue
        indexable_file_ids.append(record.file_id)

    if not indexable_file_ids:
        return status_by_file_id

    buckets = await catalog_rag_index_service.batch_status_buckets(indexable_file_ids)
    for file_id in indexable_file_ids:
        bucket = buckets[file_id]
        status_by_file_id[file_id] = "pending" if bucket == "absent" else bucket
    return status_by_file_id


async def records_to_items(
    records: list[FileRecord],
    catalog_rag_index_service: OfficeCatalogRagIndexService | None = None,
) -> list[OfficeDocumentItem]:
    rag_status_by_file_id = await _rag_index_status_by_file_id(
        catalog_rag_index_service,
        records,
    )
    items: list[OfficeDocumentItem] = []
    for record in records:
        if record.catalog_id is None:
            continue
        author_id = record.uploaded_by if record.uploaded_by else ""
        author = await User.get(author_id) if author_id else None
        display_name = author.name if author is not None else author_id
        avatar_url = author.avatar_url if author is not None else None
        file_category, onlyoffice_document_type = resolve_binding_metadata(
            record.original_name,
            record.content_type.split(";", 1)[0].strip(),
        )
        items.append(
            OfficeDocumentItem(
                file_id=record.file_id,
                catalog_id=record.catalog_id,
                title=document_title(record),
                file_category=file_category,
                onlyoffice_document_type=onlyoffice_document_type,
                file_availability="available",
                file_size=record.file_size,
                file_expires_at=record.expires_at,
                created_at=record.created_at,
                updated_at=record.updated_at,
                created_by_user_id=author_id,
                created_by_display_name=display_name,
                created_by_avatar_url=avatar_url,
                rag_index_status=rag_status_by_file_id.get(record.file_id),
            )
        )
    return items


def share_expires_at(expires_in_hours: int | None) -> datetime | None:
    if expires_in_hours is None:
        return None
    return datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
