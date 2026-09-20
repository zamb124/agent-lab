"""
API для работы с entities.

Единый endpoint для всех типов entities.
"""

import csv
import io
import json as json_lib
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from starlette.responses import Response

from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import (
    AIAnalysisDraftPatchRequest,
    AIAnalysisDraftStored,
    BulkCardsRequest,
    BulkCreateRequest,
    BulkCreateResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkUpdateRequest,
    BulkUpdateResponse,
    DailySummaryRequest,
    EntityCreate,
    EntityMergeRequest,
    EntityMergeResponse,
    EntityResponse,
    EntitySearchQueryRequest,
    EntityTimelineBoundsResponse,
    EntityUpdate,
    NoteAnalysisDraftRepairQueuedResponse,
    NoteMarkdownFormatQueuedResponse,
    PeriodSummaryRequest,
    SearchMentionsRequest,
)
from apps.crm.realtime.operations import (
    CrmEmptyPayload,
    CrmEntitiesAggregatePayload,
    CrmEntitiesTimelineBoundsPayload,
    CrmEntityIdPayload,
    CrmEntityRelationshipsResponse,
    CrmEntityUpdatePayload,
    CrmExclusiveRelatedResponse,
    CrmNoteAnalysisDraftSavePayload,
    CrmNoteIdPayload,
    op_entities_aggregate,
    op_entities_bulk_create,
    op_entities_bulk_delete,
    op_entities_bulk_update,
    op_entities_card,
    op_entities_cards_bulk,
    op_entities_create,
    op_entities_daily_summary,
    op_entities_exclusive_related,
    op_entities_item,
    op_entities_mentions_search,
    op_entities_merge,
    op_entities_period_summary,
    op_entities_person_self,
    op_entities_query,
    op_entities_relationships,
    op_entities_remove,
    op_entities_timeline_bounds,
    op_entities_update,
    op_notes_analysis_draft_discard,
    op_notes_analysis_draft_repair,
    op_notes_analysis_draft_save,
    op_notes_analysis_error_dismiss,
    op_notes_markdown_format,
)
from apps.crm.services.entity_response_enrichment import build_entity_responses_with_semantic_index
from core.context import require_context, resolve_namespace_or_raise
from core.pagination import CursorPage, ListResponse
from core.types import JsonObject

router = APIRouter(prefix="/entities", tags=["Entities"])


@router.get("/person-entity/self", response_model=EntityResponse)
async def get_person_entity_for_current_user(
    container: ContainerDep,
) -> EntityResponse:
    return await op_entities_person_self(
        CrmEmptyPayload(),
        user=require_context().user,
        container=container,
    )


@router.post("", response_model=EntityResponse)
async def create_entity(
    data: EntityCreate,
    container: ContainerDep,
) -> EntityResponse:
    return await op_entities_create(
        data, user=require_context().user, container=container
    )


@router.post("/bulk", response_model=BulkCreateResponse)
async def bulk_create_entities(
    body: BulkCreateRequest,
    container: ContainerDep,
) -> BulkCreateResponse:
    return await op_entities_bulk_create(
        body, user=require_context().user, container=container
    )


@router.put("/bulk", response_model=BulkUpdateResponse)
async def bulk_update_entities(
    body: BulkUpdateRequest,
    container: ContainerDep,
) -> BulkUpdateResponse:
    return await op_entities_bulk_update(
        body, user=require_context().user, container=container
    )


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_entities(
    body: BulkDeleteRequest,
    container: ContainerDep,
) -> BulkDeleteResponse:
    return await op_entities_bulk_delete(
        body, user=require_context().user, container=container
    )


@router.post("/merge", response_model=EntityMergeResponse)
async def merge_entities(
    body: EntityMergeRequest,
    container: ContainerDep,
) -> EntityMergeResponse:
    return await op_entities_merge(
        body, user=require_context().user, container=container
    )


@router.get("/aggregate")
async def aggregate_entities(
    container: ContainerDep,
    namespace: Annotated[str | None, Query()] = None,
) -> JsonObject:
    return await op_entities_aggregate(
        CrmEntitiesAggregatePayload(namespace=namespace),
        user=require_context().user,
        container=container,
    )


_EXPORT_PAGE_SIZE = 500
_EXPORT_MAX_ROWS = 10000


@router.get("/export")
async def export_entities(
    container: ContainerDep,
    format: Annotated[str, Query(description="csv | json")] = "json",
    entity_type: Annotated[str | None, Query()] = None,
    entity_subtype: Annotated[str | None, Query()] = None,
    namespace: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=_EXPORT_MAX_ROWS)] = 5000,
):
    """Streaming export сущностей постраничными чанками (не материализует весь список в памяти)."""
    filters_arg: JsonObject | None = None
    filter_field_types: dict[str, str] = {}
    if status:
        filters_arg = {"field": "status", "op": "$eq", "value": status}
        filter_field_types = await container.entity_service.resolve_filter_field_types(
            namespace=resolve_namespace_or_raise(namespace),
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            filters=filters_arg,
        )

    if format == "csv":

        async def _csv_generator():
            header_buf = io.StringIO()
            csv.writer(header_buf).writerow(
                ["entity_id", "entity_type", "name", "description", "status", "tags", "created_at"]
            )
            yield header_buf.getvalue()

            remaining = limit
            cursor: str | None = None
            while remaining > 0:
                page_size = min(_EXPORT_PAGE_SIZE, remaining)
                batch, cursor, has_more = await container.entity_service.list_entities(
                    entity_type=entity_type,
                    entity_subtype=entity_subtype,
                    namespace=namespace,
                    filters=filters_arg,
                    filter_field_types=filter_field_types,
                    limit=page_size,
                    cursor=cursor,
                )
                for e in batch:
                    row_buf = io.StringIO()
                    csv.writer(row_buf).writerow(
                        [
                            e.entity_id,
                            e.entity_type,
                            e.name,
                            e.description or "",
                            e.status,
                            ",".join(e.tags or []),
                            e.created_at.isoformat() if e.created_at else "",
                        ]
                    )
                    yield row_buf.getvalue()
                remaining -= len(batch)
                if not has_more or cursor is None:
                    break

        return StreamingResponse(
            _csv_generator(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=entities.csv"},
        )

    async def _json_generator():
        yield "[\n"
        first = True
        remaining = limit
        cursor: str | None = None
        while remaining > 0:
            page_size = min(_EXPORT_PAGE_SIZE, remaining)
            batch, cursor, has_more = await container.entity_service.list_entities(
                entity_type=entity_type,
                entity_subtype=entity_subtype,
                namespace=namespace,
                filters=filters_arg,
                filter_field_types=filter_field_types,
                limit=page_size,
                cursor=cursor,
            )
            enriched_batch = await build_entity_responses_with_semantic_index(
                container.entity_repository,
                batch,
                crm_work_item_service=container.crm_work_item_service,
            )
            for resp in enriched_batch:
                prefix = "" if first else ",\n"
                first = False
                yield prefix + json_lib.dumps(
                    resp.model_dump(mode="json"),
                    ensure_ascii=False,
                )
            remaining -= len(batch)
            if not has_more or cursor is None:
                break
        yield "\n]"

    return StreamingResponse(
        _json_generator(),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=entities.json"},
    )


@router.post("/query", response_model=CursorPage[EntityResponse])
async def query_entities(
    body: EntitySearchQueryRequest,
    container: ContainerDep,
) -> CursorPage[EntityResponse]:
    return await op_entities_query(
        body, user=require_context().user, container=container
    )


@router.get("/timeline/bounds", response_model=EntityTimelineBoundsResponse)
async def get_entities_timeline_bounds(
    container: ContainerDep,
    entity_type: Annotated[str | None, Query()] = None,
    entity_subtype: Annotated[str | None, Query()] = None,
    namespace: Annotated[str | None, Query(description="Фильтр по namespace")] = None,
) -> EntityTimelineBoundsResponse:
    return await op_entities_timeline_bounds(
        CrmEntitiesTimelineBoundsPayload(
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
        ),
        user=require_context().user,
        container=container,
    )


@router.patch("/notes/{note_id}/analysis-draft", response_model=AIAnalysisDraftStored)
async def patch_note_analysis_draft(
    note_id: str,
    body: AIAnalysisDraftPatchRequest,
    container: ContainerDep,
) -> AIAnalysisDraftStored:
    return await op_notes_analysis_draft_save(
        CrmNoteAnalysisDraftSavePayload.model_validate(
            {"note_id": note_id, **body.model_dump()}
        ),
        user=require_context().user,
        container=container,
    )


@router.delete("/notes/{note_id}/analysis-draft", status_code=204)
async def delete_note_analysis_draft(
    note_id: str,
    container: ContainerDep,
) -> Response:
    await op_notes_analysis_draft_discard(
        CrmNoteIdPayload(note_id=note_id),
        user=require_context().user,
        container=container,
    )
    return Response(status_code=204)


@router.delete("/notes/{note_id}/analysis-error", status_code=204)
async def delete_note_analysis_error(
    note_id: str,
    container: ContainerDep,
) -> Response:
    await op_notes_analysis_error_dismiss(
        CrmNoteIdPayload(note_id=note_id),
        user=require_context().user,
        container=container,
    )
    return Response(status_code=204)


@router.post(
    "/notes/{note_id}/analysis-draft-repair",
    status_code=202,
    response_model=NoteAnalysisDraftRepairQueuedResponse,
)
async def queue_note_analysis_draft_repair(
    note_id: str,
    container: ContainerDep,
) -> NoteAnalysisDraftRepairQueuedResponse:
    return await op_notes_analysis_draft_repair(
        CrmNoteIdPayload(note_id=note_id),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/notes/{note_id}/format-markdown",
    status_code=202,
    response_model=NoteMarkdownFormatQueuedResponse,
)
async def request_note_markdown_format(
    note_id: str,
    container: ContainerDep,
) -> NoteMarkdownFormatQueuedResponse:
    return await op_notes_markdown_format(
        CrmNoteIdPayload(note_id=note_id),
        user=require_context().user,
        container=container,
    )


@router.get("/{entity_id}")
async def get_entity(
    entity_id: str,
    container: ContainerDep,
) -> EntityResponse | JsonObject:
    return await op_entities_item(
        CrmEntityIdPayload(entity_id=entity_id),
        user=require_context().user,
        container=container,
    )


@router.put("/{entity_id}", response_model=EntityResponse)
async def update_entity(
    entity_id: str,
    data: EntityUpdate,
    container: ContainerDep,
) -> EntityResponse:
    return await op_entities_update(
        CrmEntityUpdatePayload.model_validate(
            {"entity_id": entity_id, **data.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        container=container,
    )


@router.delete("/{entity_id}", status_code=204)
async def delete_entity(
    entity_id: str,
    container: ContainerDep,
) -> Response:
    await op_entities_remove(
        CrmEntityIdPayload(entity_id=entity_id),
        user=require_context().user,
        container=container,
    )
    return Response(status_code=204)


@router.post("/daily-summary")
async def get_daily_summary(
    request: DailySummaryRequest,
    container: ContainerDep,
):
    return await op_entities_daily_summary(
        request, user=require_context().user, container=container
    )


@router.post("/period-summary")
async def get_period_summary(
    request: PeriodSummaryRequest,
    container: ContainerDep,
):
    return await op_entities_period_summary(
        request, user=require_context().user, container=container
    )


@router.post("/cards/bulk")
async def get_entity_cards_bulk(
    body: BulkCardsRequest,
    container: ContainerDep,
) -> dict[str, JsonObject]:
    return await op_entities_cards_bulk(
        body, user=require_context().user, container=container
    )


@router.get("/{entity_id}/card")
async def get_entity_card(
    entity_id: str,
    container: ContainerDep,
) -> JsonObject:
    return await op_entities_card(
        CrmEntityIdPayload(entity_id=entity_id),
        user=require_context().user,
        container=container,
    )


@router.post("/search/mentions", response_model=ListResponse[EntityResponse])
async def search_mentions(
    request: SearchMentionsRequest,
    container: ContainerDep,
) -> ListResponse[EntityResponse]:
    return await op_entities_mentions_search(
        request,
        user=require_context().user,
        container=container,
    )


@router.get("/{entity_id}/relationships", response_model=CrmEntityRelationshipsResponse)
async def get_entity_relationships(
    entity_id: str,
    container: ContainerDep,
) -> CrmEntityRelationshipsResponse:
    return await op_entities_relationships(
        CrmEntityIdPayload(entity_id=entity_id),
        user=require_context().user,
        container=container,
    )


@router.get("/{entity_id}/exclusive-related", response_model=CrmExclusiveRelatedResponse)
async def get_exclusive_related_entities(
    entity_id: str,
    container: ContainerDep,
) -> CrmExclusiveRelatedResponse:
    return await op_entities_exclusive_related(
        CrmEntityIdPayload(entity_id=entity_id),
        user=require_context().user,
        container=container,
    )
