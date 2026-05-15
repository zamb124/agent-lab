"""
API для работы с entities.

Единый endpoint для всех типов entities.
"""

from typing import Annotated, cast

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from starlette.responses import Response

from apps.crm.api.tasks import active_task_conflict
from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.db.models import CRMEntity
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import (
    AIAnalysisDraftPatchRequest,
    AIAnalysisDraftStored,
    BulkCardsRequest,
    BulkCreateRequest,
    BulkCreateResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkErrorItem,
    BulkUpdateRequest,
    BulkUpdateResponse,
    EntityCreate,
    EntityMergeRequest,
    EntityMergeResponse,
    EntityResponse,
    EntitySearchQueryRequest,
    EntityTimelineBoundsResponse,
    EntityUpdate,
    NoteAnalysisDraftRepairQueuedResponse,
    NoteMarkdownFormatQueuedResponse,
    SearchMentionsRequest,
)
from apps.crm.services.crm_note_ws_broadcast import broadcast_crm_note_event
from apps.crm.services.entity_response_enrichment import build_entity_responses_with_semantic_index
from apps.crm.services.entity_service import DraftVersionConflictError, SchemaValidationError
from apps.crm.services.task_service import ActiveTaskExistsError
from apps.crm.types import JsonObject
from core.clients import ServiceClient
from core.context import get_context
from core.i18n.service import t
from core.pagination import CursorPage
from core.websocket.publisher import Notification, NotificationType, notify_user

router = APIRouter(prefix="/entities", tags=["Entities"])

type MentionSearchItem = dict[str, str | float | None]
type MentionSearchResponse = dict[str, list[MentionSearchItem]]


def _auth_user_company_or_401() -> tuple[str, str]:
    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return ctx.user.user_id, ctx.active_company.company_id


async def _single_entity_response(
    *,
    repo: EntityRepository,
    entity: CRMEntity,
) -> EntityResponse:
    items = await build_entity_responses_with_semantic_index(repo, [entity])
    return items[0]


@router.get("/person-entity/self", response_model=EntityResponse)
async def get_person_entity_for_current_user(
    container: ContainerDep,
):
    """Сущность contact, соответствующая текущему пользователю (для голоса «Я»)."""
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Not authenticated")
    person_id = await container.user_person_service.get_or_create_person_entity_id(
        ctx.user.user_id,
        ctx.active_company.company_id,
    )
    entity = await container.entity_repository.get(person_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Person entity not found")
    return await _single_entity_response(repo=container.entity_repository, entity=entity)


@router.post("", response_model=EntityResponse)
async def create_entity(
    data: EntityCreate,
    container: ContainerDep,
):
    """Создать новую entity"""
    try:
        entity = await container.entity_service.create_entity(
            entity_type=data.entity_type,
            name=data.name,
            description=data.description,
            entity_subtype=data.entity_subtype,
            namespace=data.namespace,
            attributes=data.attributes,
            tags=data.tags,
            attachment_ids=data.attachment_ids,
            user_id=data.user_id,
            note_date=data.note_date,
            due_date=data.due_date,
            priority=data.priority,
            assignees=data.assignees,
            voice_entity_id=data.voice_entity_id,
            context_entity_id=data.context_entity_id,
            voice_entity_in_payload="voice_entity_id" in data.model_fields_set,
            context_entity_in_payload="context_entity_id" in data.model_fields_set,
        )
    except SchemaValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.field_errors)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return await _single_entity_response(repo=container.entity_repository, entity=entity)


@router.post("/bulk", response_model=BulkCreateResponse)
async def bulk_create_entities(
    body: BulkCreateRequest,
    container: ContainerDep,
):
    """Batch создание сущностей (до 200)."""
    if len(body.items) > 200:
        raise HTTPException(status_code=422, detail="Maximum 200 items per batch")

    created_entities: list[CRMEntity] = []
    errors: list[BulkErrorItem] = []
    for idx, item in enumerate(body.items):
        try:
            entity = await container.entity_service.create_entity(
                entity_type=item.entity_type,
                name=item.name,
                description=item.description,
                entity_subtype=item.entity_subtype,
                namespace=item.namespace,
                attributes=item.attributes,
                tags=item.tags,
                user_id=item.user_id,
                note_date=item.note_date,
                due_date=item.due_date,
                priority=item.priority,
                assignees=item.assignees,
            )
            created_entities.append(entity)
        except (ValueError, SchemaValidationError) as exc:
            errors.append(BulkErrorItem(index=idx, error=str(exc)))
    created = await build_entity_responses_with_semantic_index(
        container.entity_repository,
        created_entities,
    )
    return BulkCreateResponse(created=created, errors=errors)


@router.put("/bulk", response_model=BulkUpdateResponse)
async def bulk_update_entities(
    body: BulkUpdateRequest,
    container: ContainerDep,
):
    """Batch обновление сущностей (до 200)."""
    if len(body.items) > 200:
        raise HTTPException(status_code=422, detail="Maximum 200 items per batch")

    updated_entities: list[CRMEntity] = []
    errors: list[BulkErrorItem] = []
    for idx, item in enumerate(body.items):
        try:
            entity = await container.entity_service.update_entity(item.entity_id, item.updates)
            updated_entities.append(entity)
        except ValueError as exc:
            errors.append(BulkErrorItem(index=idx, entity_id=item.entity_id, error=str(exc)))
    updated = await build_entity_responses_with_semantic_index(
        container.entity_repository,
        updated_entities,
    )
    return BulkUpdateResponse(updated=updated, errors=errors)


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_entities(
    body: BulkDeleteRequest,
    container: ContainerDep,
):
    """Batch удаление сущностей (до 200)."""
    if len(body.entity_ids) > 200:
        raise HTTPException(status_code=422, detail="Maximum 200 items per batch")

    deleted: list[str] = []
    errors: list[BulkErrorItem] = []
    for idx, entity_id in enumerate(body.entity_ids):
        try:
            success = await container.entity_service.delete_entity(entity_id)
            if success:
                deleted.append(entity_id)
            else:
                errors.append(
                    BulkErrorItem(index=idx, entity_id=entity_id, error="Entity not found")
                )
        except ValueError as exc:
            errors.append(BulkErrorItem(index=idx, entity_id=entity_id, error=str(exc)))
    return BulkDeleteResponse(deleted=deleted, errors=errors)


@router.post("/merge", response_model=EntityMergeResponse)
async def merge_entities(
    body: EntityMergeRequest,
    container: ContainerDep,
):
    """Слияние двух сущностей: survivor сохраняет id, source удаляется, связи переносятся."""
    survivor = await container.entity_service.get_entity(body.survivor_entity_id.strip())
    source = await container.entity_service.get_entity(body.source_entity_id.strip())
    if survivor is None:
        raise HTTPException(status_code=404, detail="Survivor entity not found")
    if source is None:
        raise HTTPException(status_code=404, detail="Source entity not found")

    user_id, company_id = _auth_user_company_or_401()
    if not await container.access_control_service.can_write_entity(survivor, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")
    if not await container.access_control_service.can_write_entity(source, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        merged, merged_from_id = await container.entity_service.merge_entities(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        filtered = await container.access_control_service.filter_fields(merged, user_id, company_id)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied")

    status_by_id = await container.entity_repository.batch_semantic_text_index_status([merged])
    merge_entity_resp = EntityResponse.model_validate(filtered).model_copy(
        update={"semantic_text_index_status": status_by_id.get(merged.entity_id)},
    )
    return EntityMergeResponse(
        entity=merge_entity_resp,
        merged_from_entity_id=merged_from_id,
    )


@router.get("/aggregate")
async def aggregate_entities(
    container: ContainerDep,
    namespace: Annotated[str | None, Query()] = None,
):
    """Фасетная агрегация: количество по типам, статусам, месяцам создания."""
    facets = await container.entity_service.aggregate_facets(namespace=namespace)
    return facets


async def _execute_entity_query(
    *,
    container: ContainerDep,
    body: EntitySearchQueryRequest,
) -> CursorPage[EntityResponse]:
    filters_dict = (
        body.filters.model_dump(by_alias=True, exclude_none=True)
        if body.filters is not None
        else None
    )
    namespace_name = body.namespace or "default"
    filter_field_types = await container.entity_service.resolve_filter_field_types(
        namespace=namespace_name,
        entity_type=body.entity_type,
        entity_subtype=body.entity_subtype,
        filters=filters_dict,
    )

    if body.query is None or body.query.strip() == "":
        entities, next_cursor, has_more = await container.entity_service.list_entities(
            entity_type=body.entity_type,
            entity_subtype=body.entity_subtype,
            namespace=body.namespace,
            filters=filters_dict,
            filter_field_types=filter_field_types,
            limit=body.limit,
            cursor=body.cursor,
        )
        items = await build_entity_responses_with_semantic_index(
            container.entity_repository,
            entities,
        )
        return CursorPage[EntityResponse](
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    if body.cursor is not None:
        raise HTTPException(status_code=422, detail="cursor is not supported for search query mode")

    query = body.query.strip()
    if body.search_mode == "hybrid":
        results = await container.entity_service.hybrid_search(
            query=query,
            entity_type=body.entity_type,
            entity_subtype=body.entity_subtype,
            namespace=body.namespace,
            filters=filters_dict,
            filter_field_types=filter_field_types,
            limit=body.limit,
        )
        entities_only = [row[0] for row in results]
        items = await build_entity_responses_with_semantic_index(
            container.entity_repository,
            entities_only,
        )
        for resp, (_, score, match_type) in zip(items, results):
            resp.score = score
            resp.match_type = match_type
        return CursorPage[EntityResponse](items=items, next_cursor=None, has_more=False)

    if body.search_mode == "text":
        results = await container.entity_service.text_search(
            query=query,
            entity_type=body.entity_type,
            entity_subtype=body.entity_subtype,
            namespace=body.namespace,
            filters=filters_dict,
            filter_field_types=filter_field_types,
            limit=body.limit,
        )
        entities_only = [row[0] for row in results]
        items = await build_entity_responses_with_semantic_index(
            container.entity_repository,
            entities_only,
        )
        for resp, (_, score) in zip(items, results):
            resp.score = score
            resp.match_type = "text"
        return CursorPage[EntityResponse](items=items, next_cursor=None, has_more=False)

    results = await container.entity_service.search_entities(
        query=query,
        entity_type=body.entity_type,
        entity_subtype=body.entity_subtype,
        namespace=body.namespace,
        filters=filters_dict,
        filter_field_types=filter_field_types,
        limit=body.limit,
    )
    entities_only = [row[0] for row in results]
    items = await build_entity_responses_with_semantic_index(
        container.entity_repository,
        entities_only,
    )
    for resp, (_, score) in zip(items, results):
        resp.score = score
        resp.match_type = "semantic"
    return CursorPage[EntityResponse](items=items, next_cursor=None, has_more=False)


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
    import csv
    import io
    import json as json_lib

    from fastapi.responses import StreamingResponse

    filters_arg = None
    filter_field_types: dict[str, str] = {}
    if status:
        filters_arg = {"field": "status", "op": "$eq", "value": status}
        filter_field_types = await container.entity_service.resolve_filter_field_types(
            namespace=namespace or "default",
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


@router.get("/search", response_model=CursorPage[EntityResponse])
async def search_entities(
    container: ContainerDep,
):
    _ = container
    raise HTTPException(status_code=410, detail="Use POST /crm/api/v1/entities/query")


@router.post("/query", response_model=CursorPage[EntityResponse])
async def query_entities(
    body: EntitySearchQueryRequest,
    container: ContainerDep,
):
    """Единый POST endpoint для листинга и поиска сущностей по DSL-фильтрам."""
    try:
        return await _execute_entity_query(container=container, body=body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/timeline/bounds", response_model=EntityTimelineBoundsResponse)
async def get_entities_timeline_bounds(
    container: ContainerDep,
    entity_type: Annotated[str | None, Query()] = None,
    entity_subtype: Annotated[str | None, Query()] = None,
    namespace: Annotated[str | None, Query(description="Фильтр по namespace")] = None,
):
    """Получить границы timeline по created_at."""
    bounds = await container.entity_service.get_timeline_bounds(
        entity_type=entity_type,
        entity_subtype=entity_subtype,
        namespace=namespace,
    )
    return EntityTimelineBoundsResponse.model_validate(bounds)


@router.patch("/notes/{note_id}/analysis-draft", response_model=AIAnalysisDraftStored)
async def patch_note_analysis_draft(
    note_id: str,
    body: AIAnalysisDraftPatchRequest,
    container: ContainerDep,
):
    note = await container.entity_service.get_entity(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Entity not found")
    user_id, company_id = _auth_user_company_or_401()
    if not await container.access_control_service.can_write_entity(note, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        return await container.entity_service.patch_analysis_draft(note_id, body)
    except DraftVersionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/notes/{note_id}/analysis-draft", status_code=204)
async def delete_note_analysis_draft(
    note_id: str,
    container: ContainerDep,
) -> Response:
    """Удалить черновик AI-анализа и связанные поля ошибки из заметки."""
    note = await container.entity_service.get_entity(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Entity not found")
    user_id, company_id = _auth_user_company_or_401()
    if not user_id or not await container.access_control_service.can_write_entity(
        note, user_id, company_id
    ):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        await container.entity_service.discard_note_analysis_draft(note_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=204)


@router.delete("/notes/{note_id}/analysis-error", status_code=204)
async def delete_note_analysis_error(
    note_id: str,
    container: ContainerDep,
) -> Response:
    """Сбросить последнее сообщение об ошибке применения черновика (черновик не удаляется)."""
    note = await container.entity_service.get_entity(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Entity not found")
    user_id, company_id = _auth_user_company_or_401()
    if not user_id or not await container.access_control_service.can_write_entity(
        note, user_id, company_id
    ):
        raise HTTPException(status_code=403, detail="Access denied")
    await container.entity_service.clear_note_analysis_error(note_id)
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
    """Поставить в очередь AI-починку черновика (ветка CRM flow draft_repair, TaskIQ)."""
    note = await container.entity_service.get_entity(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Entity not found")
    user_id, company_id = _auth_user_company_or_401()
    if not user_id or not await container.access_control_service.can_write_entity(
        note, user_id, company_id
    ):
        raise HTTPException(status_code=403, detail="Access denied")
    raw_attrs = note.attributes or {}
    if not isinstance(raw_attrs.get("ai_analysis_draft"), dict):
        raise HTTPException(status_code=422, detail="У заметки нет черновика ai_analysis_draft")
    summary_raw = raw_attrs.get("ai_analysis_last_error")
    summary_ok = isinstance(summary_raw, str) and summary_raw.strip() != ""
    failures_raw = raw_attrs.get("ai_analysis_apply_failures")
    failures_ok = isinstance(failures_raw, list) and len(cast(list[object], failures_raw)) > 0
    if not summary_ok and not failures_ok:
        raise HTTPException(
            status_code=422,
            detail="Нет сохранённой ошибки применения черновика",
        )

    ctx = get_context()
    if ctx is None or not ctx.auth_token:
        raise HTTPException(status_code=401, detail="Authorization required")

    namespace = note.namespace or "default"

    note_date_iso = note.note_date.isoformat() if note.note_date is not None else None
    await broadcast_crm_note_event(
        company_id=company_id,
        namespace=namespace,
        note_id=note_id,
        note_date_iso=note_date_iso,
        action="updated",
        company_repository=container.company_repository,
        access_grant_repository=container.access_grant_repository,
        skip_notification_center=True,
        draft_repair={"phase": "started"},
    )

    try:
        row = await container.task_service.start_note_analysis_draft_repair(note_id=note_id)
    except ActiveTaskExistsError as exc:
        raise active_task_conflict(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return NoteAnalysisDraftRepairQueuedResponse(
        note_id=note_id,
        task_id=row.task_id,
        queued=True,
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
    """Поставить в очередь преобразование текста заметки в Markdown (TaskIQ + LitServe)."""
    note = await container.entity_service.get_entity(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Entity not found")
    user_id, company_id = _auth_user_company_or_401()
    if not await container.access_control_service.can_write_entity(note, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        row = await container.task_service.start_note_markdown_format(
            note_id=note_id,
            expected_updated_at_iso=note.updated_at.isoformat(),
        )
    except ActiveTaskExistsError as exc:
        raise active_task_conflict(exc) from exc
    except ValueError as exc:
        detail = str(exc)
        if detail == "Заметка не найдена":
            raise HTTPException(status_code=404, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc

    return NoteMarkdownFormatQueuedResponse(note_id=note_id, task_id=row.task_id)


@router.get("/{entity_id}")
async def get_entity(
    entity_id: str,
    container: ContainerDep,
):
    """Получить entity по ID с проверкой доступа"""
    entity = await container.entity_service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    user_id, company_id = _auth_user_company_or_401()

    if not await container.access_control_service.can_read_entity(entity, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        filtered = await container.access_control_service.filter_fields(entity, user_id, company_id)
        if isinstance(filtered, CRMEntity):
            return await _single_entity_response(repo=container.entity_repository, entity=filtered)
        return filtered
    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied")


@router.put("/{entity_id}", response_model=EntityResponse)
async def update_entity(
    entity_id: str,
    data: EntityUpdate,
    container: ContainerDep,
):
    """Обновить entity с проверкой прав"""
    entity = await container.entity_service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    user_id, company_id = _auth_user_company_or_401()

    if not await container.access_control_service.can_write_entity(entity, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    updates = data.model_dump(exclude_none=True)
    updates.pop("voice_entity_id", None)
    updates.pop("context_entity_id", None)
    if "entity_subtype" in data.model_fields_set:
        updates["entity_subtype"] = data.entity_subtype
    try:
        updated = await container.entity_service.update_entity(
            entity_id,
            updates,
            voice_entity_id=data.voice_entity_id,
            voice_entity_in_payload="voice_entity_id" in data.model_fields_set,
            context_entity_id=data.context_entity_id,
            context_entity_in_payload="context_entity_id" in data.model_fields_set,
        )
    except SchemaValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.field_errors)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return await _single_entity_response(repo=container.entity_repository, entity=updated)


@router.delete("/{entity_id}")
async def delete_entity(
    entity_id: str,
    container: ContainerDep,
):
    """Каскадное удаление entity"""
    entity = await container.entity_service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    user_id, company_id = _auth_user_company_or_401()

    if not await container.access_control_service.can_write_entity(entity, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    success = await container.entity_service.delete_entity(entity_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"success": True}


@router.get("", response_model=CursorPage[EntityResponse])
async def list_entities(
    container: ContainerDep,
):
    _ = container
    raise HTTPException(status_code=410, detail="Use POST /crm/api/v1/entities/query")


@router.post("/daily-summary")
async def get_daily_summary(
    request: JsonObject,
    container: ContainerDep,
):
    """Получить AI саммари заметок за день"""
    date_raw = request.get("date")
    if not isinstance(date_raw, str) or not date_raw:
        raise HTTPException(status_code=400, detail="date is required")
    namespace_raw = request.get("namespace")
    namespace = namespace_raw if isinstance(namespace_raw, str) else None
    force_rebuild = request.get("force_rebuild") is True
    summary = await container.entity_service.get_daily_summary_cached(
        date_str=date_raw,
        namespace=namespace,
        force_rebuild=force_rebuild,
    )
    return summary


@router.post("/period-summary")
async def get_period_summary(
    request: JsonObject,
    container: ContainerDep,
):
    """Сводка заметок за диапазон дат (merge дневных сводок)."""
    date_from_raw = request.get("date_from")
    date_to_raw = request.get("date_to")
    if not isinstance(date_from_raw, str) or not isinstance(date_to_raw, str):
        raise HTTPException(status_code=400, detail="date_from and date_to are required")
    namespace_raw = request.get("namespace")
    namespace = namespace_raw if isinstance(namespace_raw, str) else None
    force_rebuild = request.get("force_rebuild") is True
    summary: dict[str, object] = await container.entity_service.get_period_summary_cached(
        date_from=date_from_raw,
        date_to=date_to_raw,
        namespace=namespace,
        force_rebuild=force_rebuild,
    )
    ctx = get_context()
    if summary.get("period_truncated") is True and ctx and ctx.user:
        max_d_raw = summary.get("period_summary_max_days")
        req_d_raw = summary.get("requested_period_days")
        if not isinstance(max_d_raw, int) or not isinstance(req_d_raw, int):
            raise HTTPException(
                status_code=500, detail="Invalid period summary truncation metadata"
            )
        max_d = max_d_raw
        req_d = req_d_raw
        await notify_user(
            user_id=ctx.user.user_id,
            notification=Notification(
                type=NotificationType.SYSTEM,
                title=t("crm.notifications.period_summary_range_clamped_title"),
                title_i18n_key="crm:notifications.period_summary_range_clamped_title",
                message=t(
                    "crm.notifications.period_summary_range_clamped_message",
                    max_days=max_d,
                    requested_days=req_d,
                ),
                message_i18n_key="crm:notifications.period_summary_range_clamped_message",
                message_i18n_vars={
                    "max_days": max_d,
                    "requested_days": req_d,
                },
                service="crm",
                data={
                    "event": "crm.period_summary.range_clamped",
                    "requested_date_from": summary["requested_date_from"],
                    "requested_date_to": summary["requested_date_to"],
                    "effective_date_from": summary["date_from"],
                    "effective_date_to": summary["date_to"],
                    "period_summary_max_days": max_d,
                    "requested_period_days": req_d,
                    "max_days": max_d,
                    "requested_days": req_d,
                },
            ),
        )
    return summary


@router.post("/cards/bulk")
async def get_entity_cards_bulk(
    body: BulkCardsRequest,
    container: ContainerDep,
) -> JsonObject:
    """Batch-загрузка карточек для списка entity_id за один запрос."""
    cards = cast(object, await container.entity_service.get_bulk_entity_cards(body.entity_ids))
    if not isinstance(cards, dict):
        raise HTTPException(status_code=500, detail="Invalid cards payload")
    return cast(JsonObject, cards)


@router.get("/{entity_id}/card")
async def get_entity_card(
    entity_id: str,
    container: ContainerDep,
):
    """
    Получить полную карточку entity с контекстом:
    - Данные entity
    - Все relationships
    - Связанные entities
    - Attachments
    """
    try:
        entity = await container.entity_service.get_entity(entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        ctx = get_context()
        user_id = ctx.user.user_id if ctx and ctx.user else None
        company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
        if not await container.access_control_service.can_read_entity(entity, user_id, company_id):
            raise HTTPException(status_code=403, detail="Access denied")
        card = await container.entity_service.get_entity_card(entity_id)
        return card
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/voice-input")
async def voice_input(
    container: ContainerDep,
    file: Annotated[UploadFile, File()],
    language: Annotated[str | None, Query()] = None,
):
    """Голосовой ввод заметок — транскрипция через voice service."""
    _ = container
    _ = language
    file_name = file.filename or "voice-input"
    mime_type = file.content_type or "application/octet-stream"
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Пустой аудиофайл.")

    client = ServiceClient()
    raw_data = cast(
        object,
        await client.post(
            "voice",
            "/voice/api/v1/transcribe",
            files={"file": (file_name, audio_bytes, mime_type)},
        ),
    )
    if not isinstance(raw_data, dict):
        raise HTTPException(status_code=502, detail="Invalid voice service response")
    data = cast(JsonObject, raw_data)
    text_raw = data.get("text")
    provider_raw = data.get("provider")
    if not isinstance(text_raw, str) or not isinstance(provider_raw, str):
        raise HTTPException(status_code=502, detail="Invalid voice service response")
    return {
        "text": text_raw,
        "stt": {"provider": provider_raw, "text": text_raw, "status": "done"},
    }


@router.post("/search/mentions", response_model=dict)
async def search_mentions(
    request: SearchMentionsRequest,
    container: ContainerDep,
) -> MentionSearchResponse:
    """Real-time поиск упоминаний entities в тексте для подсветки"""
    text = request.text
    if not text or len(text) < 3:
        empty: list[MentionSearchItem] = []
        return {"entities": empty}

    entities = await container.entity_service.search_mentions(
        text, namespace=request.namespace, limit=20
    )
    return {
        "entities": [
            {
                "entity_id": e.entity_id,
                "entity_type": e.entity_type,
                "name": e.name,
                "description": e.description,
                "relevance": e.relevance,
            }
            for e in entities
        ]
    }


@router.get("/{entity_id}/relationships")
async def get_entity_relationships(
    entity_id: str,
    container: ContainerDep,
):
    """Получить все relationships для entity"""
    repo = container.relationship_repository

    entity = await container.entity_service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    user_id, company_id = _auth_user_company_or_401()
    if not await container.access_control_service.can_read_entity(entity, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    relationships = await repo.get_by_entity(entity_id)
    return {
        "relationships": [
            {
                "relationship_id": r.relationship_id,
                "source_entity_id": r.source_entity_id,
                "target_entity_id": r.target_entity_id,
                "relationship_type": r.relationship_type,
                "namespace": r.namespace,
                "weight": r.weight,
                "confidence": r.confidence,
                "attributes": r.attributes or {},
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "company_id": r.company_id,
            }
            for r in relationships
        ]
    }


@router.get("/{entity_id}/exclusive-related")
async def get_exclusive_related_entities(
    entity_id: str,
    container: ContainerDep,
):
    """Получить список сущностей, которые будут удалены каскадно при удалении заметки"""
    entity = await container.entity_service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    if entity.entity_type != NOTE_ROOT_ENTITY_TYPE_ID:
        raise HTTPException(status_code=400, detail="Only notes have exclusive related entities")

    user_id, company_id = _auth_user_company_or_401()
    if not await container.access_control_service.can_write_entity(entity, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    exclusive_entities = await container.entity_service.get_exclusive_related_entities_for_note(
        entity_id
    )
    return {"entities": exclusive_entities}
