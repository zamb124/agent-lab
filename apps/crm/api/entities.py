"""
API для работы с entities.

Единый endpoint для всех типов entities.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, Body, File, HTTPException, Query, UploadFile
from core.pagination import CursorPage
from apps.crm.models.api import (
    EntityCreate,
    EntityUpdate,
    EntityResponse,
    EntityTimelineBoundsResponse,
    EntityMergeRequest,
    EntityMergeResponse,
    AIAnalyzeResponse,
    AIAnalysisDraftApplyResult,
    AIAnalysisDraftPatchRequest,
    AIAnalysisDraftStored,
    NoteProcessingConfig,
    NoteProcessingResult,
    SearchMentionsRequest,
    EntitySearchQueryRequest,
    BulkCreateRequest,
    BulkCreateResponse,
    BulkUpdateRequest,
    BulkUpdateResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkErrorItem,
    BulkCardsRequest,
)
from apps.crm.db.models import CRMEntity
from apps.crm.config import get_crm_settings
from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.taskiq_analyze_errors import (
    parse_mentioned_entity_short_description_from_task_message,
    parse_validation_from_task_message,
)
from apps.crm.services.entity_service import DraftVersionConflictError, SchemaValidationError
from apps.crm.dependencies import ContainerDep
from core.clients import ServiceClient
from core.context import get_context
from core.i18n.service import t
from core.websocket.publisher import notify_user, Notification, NotificationType
from taskiq.exceptions import TaskiqResultTimeoutError

router = APIRouter(prefix="/entities", tags=["Entities"])


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
    return EntityResponse.model_validate(entity)


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
    return EntityResponse.model_validate(entity)


@router.post("/bulk", response_model=BulkCreateResponse)
async def bulk_create_entities(
    body: BulkCreateRequest,
    container: ContainerDep,
):
    """Batch создание сущностей (до 200)."""
    if len(body.items) > 200:
        raise HTTPException(status_code=422, detail="Maximum 200 items per batch")

    created = []
    errors = []
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
            created.append(EntityResponse.model_validate(entity))
        except (ValueError, SchemaValidationError) as exc:
            errors.append(BulkErrorItem(index=idx, error=str(exc)))
    return BulkCreateResponse(created=created, errors=errors)


@router.put("/bulk", response_model=BulkUpdateResponse)
async def bulk_update_entities(
    body: BulkUpdateRequest,
    container: ContainerDep,
):
    """Batch обновление сущностей (до 200)."""
    if len(body.items) > 200:
        raise HTTPException(status_code=422, detail="Maximum 200 items per batch")

    updated = []
    errors = []
    for idx, item in enumerate(body.items):
        try:
            entity = await container.entity_service.update_entity(item.entity_id, item.updates)
            updated.append(EntityResponse.model_validate(entity))
        except ValueError as exc:
            errors.append(BulkErrorItem(index=idx, entity_id=item.entity_id, error=str(exc)))
    return BulkUpdateResponse(updated=updated, errors=errors)


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_entities(
    body: BulkDeleteRequest,
    container: ContainerDep,
):
    """Batch удаление сущностей (до 200)."""
    if len(body.entity_ids) > 200:
        raise HTTPException(status_code=422, detail="Maximum 200 items per batch")

    deleted = []
    errors = []
    for idx, entity_id in enumerate(body.entity_ids):
        try:
            success = await container.entity_service.delete_entity(entity_id)
            if success:
                deleted.append(entity_id)
            else:
                errors.append(BulkErrorItem(index=idx, entity_id=entity_id, error="Entity not found"))
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

    ctx = get_context()
    user_id = ctx.user.user_id if ctx and ctx.user else None
    company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
    if not user_id or not await container.access_control_service.can_write_entity(survivor, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")
    if not user_id or not await container.access_control_service.can_write_entity(source, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        merged, merged_from_id = await container.entity_service.merge_entities(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        filtered = await container.access_control_service.filter_fields(merged, user_id, company_id)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied")
    return EntityMergeResponse(
        entity=EntityResponse.model_validate(filtered),
        merged_from_entity_id=merged_from_id,
    )


@router.get("/aggregate")
async def aggregate_entities(
    container: ContainerDep,
    namespace: Optional[str] = Query(None),
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
        return CursorPage[EntityResponse](
            items=[EntityResponse.model_validate(e) for e in entities],
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
        items = []
        for entity, score, match_type in results:
            resp = EntityResponse.model_validate(entity)
            resp.score = score
            resp.match_type = match_type
            items.append(resp)
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
        items = []
        for entity, score in results:
            resp = EntityResponse.model_validate(entity)
            resp.score = score
            resp.match_type = "text"
            items.append(resp)
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
    items = []
    for entity, score in results:
        resp = EntityResponse.model_validate(entity)
        resp.score = score
        resp.match_type = "semantic"
        items.append(resp)
    return CursorPage[EntityResponse](items=items, next_cursor=None, has_more=False)


_EXPORT_PAGE_SIZE = 500
_EXPORT_MAX_ROWS = 10000


@router.get("/export")
async def export_entities(
    container: ContainerDep,
    format: str = Query("json", description="csv | json"),
    entity_type: Optional[str] = Query(None),
    entity_subtype: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(5000, le=_EXPORT_MAX_ROWS),
):
    """Streaming export сущностей постраничными чанками (не материализует весь список в памяти)."""
    import csv
    import io
    import json as json_lib
    from fastapi.responses import StreamingResponse

    filters_arg = None
    filter_field_types: Dict[str, str] = {}
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
            cursor: Optional[str] = None
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
                    csv.writer(row_buf).writerow([
                        e.entity_id, e.entity_type, e.name, e.description or "",
                        e.status, ",".join(e.tags or []),
                        e.created_at.isoformat() if e.created_at else "",
                    ])
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
        cursor: Optional[str] = None
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
                prefix = "" if first else ",\n"
                first = False
                yield prefix + json_lib.dumps(
                    EntityResponse.model_validate(e).model_dump(mode="json"),
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
    entity_type: Optional[str] = Query(None),
    entity_subtype: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None, description="Фильтр по namespace"),
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
    ctx = get_context()
    user_id = ctx.user.user_id if ctx and ctx.user else None
    company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
    if not user_id or not await container.access_control_service.can_write_entity(note, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        return await container.entity_service.patch_analysis_draft(note_id, body)
    except DraftVersionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc




@router.get("/{entity_id}")
async def get_entity(
    entity_id: str,
    container: ContainerDep,
):
    """Получить entity по ID с проверкой доступа"""
    entity = await container.entity_service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    ctx = get_context()
    user_id = ctx.user.user_id if ctx and ctx.user else None
    company_id = ctx.active_company.company_id if ctx and ctx.active_company else None

    if not await container.access_control_service.can_read_entity(entity, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        filtered = await container.access_control_service.filter_fields(entity, user_id, company_id)
        if isinstance(filtered, CRMEntity):
            return EntityResponse.model_validate(filtered)
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

    ctx = get_context()
    user_id = ctx.user.user_id if ctx and ctx.user else None
    company_id = ctx.active_company.company_id if ctx and ctx.active_company else None

    if not user_id or not await container.access_control_service.can_write_entity(entity, user_id, company_id):
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
    return EntityResponse.model_validate(updated)


@router.delete("/{entity_id}")
async def delete_entity(
    entity_id: str,
    container: ContainerDep,
):
    """Каскадное удаление entity"""
    entity = await container.entity_service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    ctx = get_context()
    user_id = ctx.user.user_id if ctx and ctx.user else None
    company_id = ctx.active_company.company_id if ctx and ctx.active_company else None

    if not user_id or not await container.access_control_service.can_write_entity(entity, user_id, company_id):
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
    request: Dict[str, Any],
    container: ContainerDep,
):
    """Получить AI саммари заметок за день"""
    date_str = request.get("date")
    if date_str is None:
        raise HTTPException(status_code=400, detail="date is required")
    namespace = request.get("namespace")
    force_rebuild = request.get("force_rebuild") is True
    summary = await container.entity_service.get_daily_summary_cached(
        date_str=date_str,
        namespace=namespace,
        force_rebuild=force_rebuild,
    )
    return summary


@router.post("/period-summary")
async def get_period_summary(
    request: Dict[str, Any],
    container: ContainerDep,
):
    """Сводка заметок за диапазон дат (merge дневных сводок)."""
    date_from = request.get("date_from")
    date_to = request.get("date_to")
    if date_from is None or date_to is None:
        raise HTTPException(status_code=400, detail="date_from and date_to are required")
    namespace = request.get("namespace")
    force_rebuild = request.get("force_rebuild") is True
    summary = await container.entity_service.get_period_summary_cached(
        date_from=date_from,
        date_to=date_to,
        namespace=namespace,
        force_rebuild=force_rebuild,
    )
    ctx = get_context()
    if summary.get("period_truncated") is True and ctx and ctx.user:
        max_d = summary["period_summary_max_days"]
        req_d = summary["requested_period_days"]
        await notify_user(
            user_id=ctx.user.user_id,
            notification=Notification(
                type=NotificationType.SYSTEM,
                title=t("crm.notifications.period_summary_range_clamped_title"),
                message=t(
                    "crm.notifications.period_summary_range_clamped_message",
                    max_days=max_d,
                    requested_days=req_d,
                ),
                service="crm",
                data={
                    "event": "crm.period_summary.range_clamped",
                    "requested_date_from": summary["requested_date_from"],
                    "requested_date_to": summary["requested_date_to"],
                    "effective_date_from": summary["date_from"],
                    "effective_date_to": summary["date_to"],
                    "period_summary_max_days": max_d,
                    "requested_period_days": req_d,
                },
            ),
        )
    return summary


@router.post("/cards/bulk")
async def get_entity_cards_bulk(
    body: BulkCardsRequest,
    container: ContainerDep,
) -> Dict[str, Any]:
    """Batch-загрузка карточек для списка entity_id за один запрос."""
    return await container.entity_service.get_bulk_entity_cards(body.entity_ids)


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
    file: UploadFile = File(...),
    language: str | None = Query(default=None),
):
    """Голосовой ввод заметок — транскрипция через voice service."""
    _ = container
    file_name = file.filename or "voice-input"
    mime_type = file.content_type or "application/octet-stream"
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Пустой аудиофайл.")

    client = ServiceClient()
    data = await client.post(
        "voice",
        "/voice/api/v1/transcribe",
        files={"file": (file_name, audio_bytes, mime_type)},
    )
    return {
        "text": data["text"],
        "stt": {"provider": data["provider"], "text": data["text"], "status": "done"},
    }


@router.post("/search/mentions", response_model=Dict)
async def search_mentions(
    request: SearchMentionsRequest,
    container: ContainerDep,
):
    """Real-time поиск упоминаний entities в тексте для подсветки"""
    text = request.text
    if not text or len(text) < 3:
        return {"entities": []}
    
    entities = await container.entity_service.search_mentions(text, namespace=request.namespace, limit=20)
    return {
        "entities": [
            {
                "entity_id": e.entity_id,
                "entity_type": e.entity_type,
                "name": e.name,
                "description": e.description,
                "relevance": e.relevance
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
    ctx = get_context()
    user_id = ctx.user.user_id if ctx and ctx.user else None
    company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
    if not await container.access_control_service.can_read_entity(entity, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    relationships = await repo.get_by_entity(entity_id)
    return {"relationships": [
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
    ]}


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
    
    ctx = get_context()
    user_id = ctx.user.user_id if ctx and ctx.user else None
    company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
    if not await container.access_control_service.can_write_entity(entity, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    exclusive_entities = await container.entity_service.get_exclusive_related_entities_for_note(entity_id)
    return {"entities": exclusive_entities}
