"""Экспорт сущностей CRM в CSV/JSON как ephemeral файл Files API."""

from __future__ import annotations

import csv
import io
import json
from typing import Literal

from pydantic import Field

from apps.crm.services.crm_work_item_service import CrmWorkItemService
from apps.crm.services.entity_response_enrichment import build_entity_responses_with_semantic_index
from apps.crm.services.entity_service import EntityService
from core.context import resolve_namespace_or_raise
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.models import FileRecord
from core.files.registry import default_retention_for_source
from core.files.service import FilesService
from core.models import StrictBaseModel
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.rag.factory import get_rag_provider
from core.types import JsonObject

EXPORT_PAGE_SIZE = 500
EXPORT_MAX_ROWS = 10000
ExportFormat = Literal["csv", "json"]

_CSV_HEADER = ("entity_id", "entity_type", "name", "description", "status", "tags", "created_at")
_CONTENT_TYPES: dict[ExportFormat, str] = {"csv": "text/csv", "json": "application/json"}


class CrmEntitiesExportPayload(StrictBaseModel):
    export_format: ExportFormat = "json"
    entity_type: str | None = None
    entity_subtype: str | None = None
    namespace: str | None = None
    status: str | None = None
    limit: int = Field(default=5000, ge=1, le=EXPORT_MAX_ROWS)


async def export_entities_to_file(
    entity_service: EntityService,
    crm_work_item_service: CrmWorkItemService,
    files_service: FilesService,
    payload: CrmEntitiesExportPayload,
) -> FileRecord:
    """Постранично собирает сущности (ACL учитывается в `list_entities`) и кладёт выгрузку в S3."""
    filters: JsonObject | None = None
    filter_field_types: dict[str, str] = {}
    if payload.status:
        filters = {"field": "status", "op": "$eq", "value": payload.status}
        filter_field_types = await entity_service.resolve_filter_field_types(
            namespace=resolve_namespace_or_raise(payload.namespace),
            entity_type=payload.entity_type,
            entity_subtype=payload.entity_subtype,
            filters=filters,
        )

    buffer = io.StringIO()
    csv_writer = csv.writer(buffer)
    if payload.export_format == "csv":
        csv_writer.writerow(_CSV_HEADER)
    else:
        _ = buffer.write("[\n")
    first_json_row = True
    remaining = payload.limit
    cursor: str | None = None
    while remaining > 0:
        batch, cursor, has_more = await entity_service.list_entities(
            entity_type=payload.entity_type,
            entity_subtype=payload.entity_subtype,
            namespace=payload.namespace,
            filters=filters,
            filter_field_types=filter_field_types,
            limit=min(EXPORT_PAGE_SIZE, remaining),
            cursor=cursor,
        )
        if payload.export_format == "csv":
            for entity in batch:
                csv_writer.writerow(
                    [
                        entity.entity_id,
                        entity.entity_type,
                        entity.name,
                        entity.description or "",
                        entity.status,
                        ",".join(entity.tags or []),
                        entity.created_at.isoformat() if entity.created_at else "",
                    ]
                )
        else:
            enriched = await build_entity_responses_with_semantic_index(
                get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
                batch,
                crm_work_item_service=crm_work_item_service,
            )
            for entity_response in enriched:
                _ = buffer.write("" if first_json_row else ",\n")
                first_json_row = False
                _ = buffer.write(json.dumps(entity_response.model_dump(mode="json"), ensure_ascii=False))
        remaining -= len(batch)
        if not has_more or cursor is None:
            break
    if payload.export_format == "json":
        _ = buffer.write("\n]")

    spec = FileCreateSpec(
        source_kind=FileSourceKind.GENERATED_EPHEMERAL,
        source_ref=FileSourceRef(),
        retention=default_retention_for_source(FileSourceKind.GENERATED_EPHEMERAL),
        post_create=FilePostCreate(is_public=False),
    )
    return await files_service.create(
        spec,
        buffer.getvalue().encode("utf-8"),
        original_name=f"entities.{payload.export_format}",
        content_type=_CONTENT_TYPES[payload.export_format],
    )
