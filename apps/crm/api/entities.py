"""
API для работы с entities.

Единый endpoint для всех типов entities.
"""

from typing import Annotated

from fastapi import APIRouter, Query
from starlette.responses import Response

from apps.crm.di import Di
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
    op_entities_export,
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
from apps.crm.services.entity_export import (
    EXPORT_MAX_ROWS,
    CrmEntitiesExportPayload,
    ExportFormat,
)
from core.context import require_context
from core.files.models import FileRecord
from core.pagination import CursorPage, ListResponse
from core.types import JsonObject
from core.websocket import EmptyPayload

router = APIRouter(prefix="/entities", tags=["Entities"])


@router.get("/person-entity/self", response_model=EntityResponse)
async def get_person_entity_for_current_user(
    di: Di,
) -> EntityResponse:
    return await op_entities_person_self(
        EmptyPayload(),
        user=require_context().user,
        di=di,
    )


@router.post("", response_model=EntityResponse)
async def create_entity(
    data: EntityCreate,
    di: Di,
) -> EntityResponse:
    return await op_entities_create(
        data, user=require_context().user, di=di
    )


@router.post("/bulk", response_model=BulkCreateResponse)
async def bulk_create_entities(
    body: BulkCreateRequest,
    di: Di,
) -> BulkCreateResponse:
    return await op_entities_bulk_create(
        body, user=require_context().user, di=di
    )


@router.put("/bulk", response_model=BulkUpdateResponse)
async def bulk_update_entities(
    body: BulkUpdateRequest,
    di: Di,
) -> BulkUpdateResponse:
    return await op_entities_bulk_update(
        body, user=require_context().user, di=di
    )


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_entities(
    body: BulkDeleteRequest,
    di: Di,
) -> BulkDeleteResponse:
    return await op_entities_bulk_delete(
        body, user=require_context().user, di=di
    )


@router.post("/merge", response_model=EntityMergeResponse)
async def merge_entities(
    body: EntityMergeRequest,
    di: Di,
) -> EntityMergeResponse:
    return await op_entities_merge(
        body, user=require_context().user, di=di
    )


@router.get("/aggregate")
async def aggregate_entities(
    di: Di,
    namespace: Annotated[str | None, Query()] = None,
) -> JsonObject:
    return await op_entities_aggregate(
        CrmEntitiesAggregatePayload(namespace=namespace),
        user=require_context().user,
        di=di,
    )


@router.get("/export", response_model=FileRecord)
async def export_entities(
    di: Di,
    export_format: Annotated[ExportFormat, Query()] = "json",
    entity_type: Annotated[str | None, Query()] = None,
    entity_subtype: Annotated[str | None, Query()] = None,
    namespace: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=EXPORT_MAX_ROWS)] = 5000,
) -> FileRecord:
    return await op_entities_export(
        CrmEntitiesExportPayload(
            export_format=export_format,
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            status=status,
            limit=limit,
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/query", response_model=CursorPage[EntityResponse])
async def query_entities(
    body: EntitySearchQueryRequest,
    di: Di,
) -> CursorPage[EntityResponse]:
    return await op_entities_query(
        body, user=require_context().user, di=di
    )


@router.get("/timeline/bounds", response_model=EntityTimelineBoundsResponse)
async def get_entities_timeline_bounds(
    di: Di,
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
        di=di,
    )


@router.patch("/notes/{note_id}/analysis-draft", response_model=AIAnalysisDraftStored)
async def patch_note_analysis_draft(
    note_id: str,
    body: AIAnalysisDraftPatchRequest,
    di: Di,
) -> AIAnalysisDraftStored:
    return await op_notes_analysis_draft_save(
        CrmNoteAnalysisDraftSavePayload.model_validate(
            {"note_id": note_id, **body.model_dump()}
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/notes/{note_id}/analysis-draft", status_code=204)
async def delete_note_analysis_draft(
    note_id: str,
    di: Di,
) -> Response:
    await op_notes_analysis_draft_discard(
        CrmNoteIdPayload(note_id=note_id),
        user=require_context().user,
        di=di,
    )
    return Response(status_code=204)


@router.delete("/notes/{note_id}/analysis-error", status_code=204)
async def delete_note_analysis_error(
    note_id: str,
    di: Di,
) -> Response:
    await op_notes_analysis_error_dismiss(
        CrmNoteIdPayload(note_id=note_id),
        user=require_context().user,
        di=di,
    )
    return Response(status_code=204)


@router.post(
    "/notes/{note_id}/analysis-draft-repair",
    status_code=202,
    response_model=NoteAnalysisDraftRepairQueuedResponse,
)
async def queue_note_analysis_draft_repair(
    note_id: str,
    di: Di,
) -> NoteAnalysisDraftRepairQueuedResponse:
    return await op_notes_analysis_draft_repair(
        CrmNoteIdPayload(note_id=note_id),
        user=require_context().user,
        di=di,
    )


@router.post(
    "/notes/{note_id}/format-markdown",
    status_code=202,
    response_model=NoteMarkdownFormatQueuedResponse,
)
async def request_note_markdown_format(
    note_id: str,
    di: Di,
) -> NoteMarkdownFormatQueuedResponse:
    return await op_notes_markdown_format(
        CrmNoteIdPayload(note_id=note_id),
        user=require_context().user,
        di=di,
    )


@router.get("/{entity_id}")
async def get_entity(
    entity_id: str,
    di: Di,
) -> EntityResponse | JsonObject:
    return await op_entities_item(
        CrmEntityIdPayload(entity_id=entity_id),
        user=require_context().user,
        di=di,
    )


@router.put("/{entity_id}", response_model=EntityResponse)
async def update_entity(
    entity_id: str,
    data: EntityUpdate,
    di: Di,
) -> EntityResponse:
    return await op_entities_update(
        CrmEntityUpdatePayload.model_validate(
            {"entity_id": entity_id, **data.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/{entity_id}", status_code=204)
async def delete_entity(
    entity_id: str,
    di: Di,
) -> Response:
    await op_entities_remove(
        CrmEntityIdPayload(entity_id=entity_id),
        user=require_context().user,
        di=di,
    )
    return Response(status_code=204)


@router.post("/daily-summary")
async def get_daily_summary(
    request: DailySummaryRequest,
    di: Di,
):
    return await op_entities_daily_summary(
        request, user=require_context().user, di=di
    )


@router.post("/period-summary")
async def get_period_summary(
    request: PeriodSummaryRequest,
    di: Di,
):
    return await op_entities_period_summary(
        request, user=require_context().user, di=di
    )


@router.post("/cards/bulk")
async def get_entity_cards_bulk(
    body: BulkCardsRequest,
    di: Di,
) -> dict[str, JsonObject]:
    return await op_entities_cards_bulk(
        body, user=require_context().user, di=di
    )


@router.get("/{entity_id}/card")
async def get_entity_card(
    entity_id: str,
    di: Di,
) -> JsonObject:
    return await op_entities_card(
        CrmEntityIdPayload(entity_id=entity_id),
        user=require_context().user,
        di=di,
    )


@router.post("/search/mentions", response_model=ListResponse[EntityResponse])
async def search_mentions(
    request: SearchMentionsRequest,
    di: Di,
) -> ListResponse[EntityResponse]:
    return await op_entities_mentions_search(
        request,
        user=require_context().user,
        di=di,
    )


@router.get("/{entity_id}/relationships", response_model=CrmEntityRelationshipsResponse)
async def get_entity_relationships(
    entity_id: str,
    di: Di,
) -> CrmEntityRelationshipsResponse:
    return await op_entities_relationships(
        CrmEntityIdPayload(entity_id=entity_id),
        user=require_context().user,
        di=di,
    )


@router.get("/{entity_id}/exclusive-related", response_model=CrmExclusiveRelatedResponse)
async def get_exclusive_related_entities(
    entity_id: str,
    di: Di,
) -> CrmExclusiveRelatedResponse:
    return await op_entities_exclusive_related(
        CrmEntityIdPayload(entity_id=entity_id),
        user=require_context().user,
        di=di,
    )
