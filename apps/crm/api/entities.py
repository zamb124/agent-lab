"""
API для работы с entities.

Единый endpoint для всех типов entities.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import ValidationError

from apps.crm.models.api import (
    EntityCreate,
    EntityUpdate,
    EntityResponse,
    EntityTimelineBoundsResponse,
    EntityMergeRequest,
    EntityMergeResponse,
    AIAnalyzeRequest,
    AIAnalyzeResponse,
    AIAnalysisDraftApplyResult,
    AIAnalysisDraftPatchRequest,
    AIAnalysisDraftStored,
    SearchMentionsRequest,
    RelationshipResponse,
)
from apps.crm.db.models import CRMEntity
from apps.crm.config import get_crm_settings
from apps.crm.taskiq_analyze_errors import parse_validation_from_task_message
from apps.crm.services.entity_service import DraftVersionConflictError
from apps.crm.dependencies import ContainerDep
from apps.crm_worker.tasks.analysis_tasks import (
    analyze_text_with_ai_task,
    apply_analysis_draft_task,
)
from core.files.media.transcriber import MediaTranscriber
from core.context import get_context
from core.i18n.service import t
from core.websocket.publisher import notify_user, Notification, NotificationType
from taskiq.exceptions import TaskiqResultTimeoutError

router = APIRouter(prefix="/entities", tags=["Entities"])


def build_crm_entity_filters_from_query(
    *,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    tags: Optional[str] = None,
    user_id: Optional[str] = None,
    substring_search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    created_at_from: Optional[datetime] = None,
    created_at_to: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Общие фильтры списка и семантического поиска (без дублирования логики)."""
    filters: Dict[str, Any] = {}
    if status:
        filters["status"] = status
    if priority:
        filters["priority"] = priority
    if tags:
        filters["tags"] = {"$contains": tags}
    if user_id:
        filters["user_id"] = user_id
    if substring_search:
        filters["search"] = substring_search
    if date_from:
        filters["note_date"] = {"$gte": date_from}
    if date_to:
        if "note_date" in filters:
            filters["note_date"]["$lte"] = date_to
        else:
            filters["note_date"] = {"$lte": date_to}
    if created_at_from:
        filters["created_at"] = {"$gte": created_at_from}
    if created_at_to:
        if "created_at" in filters:
            filters["created_at"]["$lte"] = created_at_to
        else:
            filters["created_at"] = {"$lte": created_at_to}
    return filters


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
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return EntityResponse.model_validate(entity)


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


@router.get("/search", response_model=List[EntityResponse])
async def search_entities(
    container: ContainerDep,
    query: str = Query(...),
    entity_type: Optional[str] = Query(None),
    entity_subtype: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None, description="Фильтр по namespace"),
    status: Optional[str] = Query(None, description="Как у списка: статус"),
    priority: Optional[str] = Query(None, description="Как у списка: приоритет"),
    tags: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    created_at_from: Optional[datetime] = Query(None, description="Фильтр created_at >= value"),
    created_at_to: Optional[datetime] = Query(None, description="Фильтр created_at <= value"),
    limit: int = Query(100, le=1000),
):
    """Семантический поиск entities (RAG + вектор); те же доп. фильтры, что у GET /entities (кроме подстроки ILIKE)."""
    filters = build_crm_entity_filters_from_query(
        status=status,
        priority=priority,
        tags=tags,
        user_id=user_id,
        substring_search=None,
        date_from=date_from,
        date_to=date_to,
        created_at_from=created_at_from,
        created_at_to=created_at_to,
    )
    entities = await container.entity_service.search_entities(
        query=query,
        entity_type=entity_type,
        entity_subtype=entity_subtype,
        namespace=namespace,
        filters=filters if filters else None,
        limit=limit,
    )
    return [EntityResponse.model_validate(e) for e in entities]


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


@router.post("/notes/{note_id}/analysis-draft/apply", response_model=AIAnalysisDraftApplyResult)
async def apply_note_analysis_draft(
    note_id: str,
    container: ContainerDep,
):
    note = await container.entity_service.get_entity(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Entity not found")
    ctx = get_context()
    user_id = ctx.user.user_id if ctx and ctx.user else None
    company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
    auth_token = ctx.auth_token if ctx else None
    if not user_id or not await container.access_control_service.can_write_entity(note, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")
    if not user_id or not company_id:
        raise HTTPException(status_code=500, detail="Контекст пользователя или компании отсутствует")
    settings = get_crm_settings()
    ns = note.namespace or "default"
    try:
        task = await apply_analysis_draft_task.kiq(
            note_id=note_id,
            company_id=company_id,
            namespace=ns,
            auth_token=auth_token,
            user_id=user_id,
        )
        res = await task.wait_result(timeout=settings.taskiq_sync_timeout_seconds)
    except TaskiqResultTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Таймаут применения черновика analyze в worker",
        ) from exc
    if res.is_err:
        raise HTTPException(status_code=422, detail=str(res.error))
    return AIAnalysisDraftApplyResult.model_validate(res.return_value)


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
    try:
        updated = await container.entity_service.update_entity(
            entity_id,
            updates,
            voice_entity_id=data.voice_entity_id,
            voice_entity_in_payload="voice_entity_id" in data.model_fields_set,
            context_entity_id=data.context_entity_id,
            context_entity_in_payload="context_entity_id" in data.model_fields_set,
        )
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


@router.get("", response_model=List[EntityResponse])
async def list_entities(
    container: ContainerDep,
    entity_type: Optional[str] = Query(None),
    entity_subtype: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None, description="Фильтр по namespace"),
    status: Optional[str] = Query(None, description="Фильтр по статусу (active, archived, ...)"),
    priority: Optional[str] = Query(None, description="Фильтр по приоритету (low, medium, high, urgent)"),
    tags: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Подстрока для поиска по name/description"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    created_at_from: Optional[datetime] = Query(None, description="Фильтр created_at >= value"),
    created_at_to: Optional[datetime] = Query(None, description="Фильтр created_at <= value"),
    limit: int = Query(100, le=1000),
):
    """Получить список entities с фильтрацией"""
    filters = build_crm_entity_filters_from_query(
        status=status,
        priority=priority,
        tags=tags,
        user_id=user_id,
        substring_search=search,
        date_from=date_from,
        date_to=date_to,
        created_at_from=created_at_from,
        created_at_to=created_at_to,
    )

    entities = await container.entity_service.list_entities(
        entity_type=entity_type,
        entity_subtype=entity_subtype,
        namespace=namespace,
        filters=filters if filters else None,
        limit=limit
    )
    return [EntityResponse.model_validate(e) for e in entities]


@router.post("/analyze", response_model=AIAnalyzeResponse)
async def analyze_text(
    request: AIAnalyzeRequest,
    container: ContainerDep,
    note_id: Optional[str] = Query(None, description="ID заметки для нотификации"),
    check_duplicates: bool = Query(True, description="Проверять дубликаты entities"),
):
    """AI анализ текста с извлечением entities и relationships"""
    _ = container
    context = get_context()
    auth_token = context.auth_token if context else None
    user_id_ctx = context.user.user_id if context and context.user else None
    company_id_ctx = context.active_company.company_id if context and context.active_company else None
    active_ns = context.active_namespace if context else "default"
    if not user_id_ctx or not company_id_ctx:
        raise HTTPException(status_code=500, detail="Контекст пользователя или компании отсутствует")
    settings = get_crm_settings()
    try:
        task = await analyze_text_with_ai_task.kiq(
            request_payload=request.model_dump(mode="json"),
            note_id=note_id,
            check_duplicates=check_duplicates,
            company_id=company_id_ctx,
            namespace=active_ns or "default",
            auth_token=auth_token,
            user_id=user_id_ctx,
            interface_language=context.language.value,
        )
        res = await task.wait_result(timeout=settings.taskiq_sync_timeout_seconds)
    except TaskiqResultTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Таймаут analyze в worker",
        ) from exc
    if res.is_err:
        err = res.error
        if isinstance(err, ValidationError):
            raise HTTPException(status_code=422, detail=err.errors())
        err_msg = str(err) if err else ""
        parsed = parse_validation_from_task_message(err_msg)
        if parsed is not None:
            raise HTTPException(status_code=422, detail=parsed)
        errors_fn = getattr(err, "errors", None)
        if callable(errors_fn):
            try:
                out = errors_fn()
            except Exception:
                out = None
            if out:
                raise HTTPException(status_code=422, detail=out)
        raise HTTPException(status_code=422, detail=err_msg or repr(err))
    try:
        result = AIAnalyzeResponse.model_validate(res.return_value)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    if note_id and context and context.user:
        suggestions_count = len(result.entities or []) + len(result.relationships or [])
        await notify_user(
            user_id=context.user.user_id,
            notification=Notification(
                type=NotificationType.TASK_COMPLETED,
                title="Анализ завершён",
                message=f"Найдено {suggestions_count} предложений",
                service="crm",
                data={"note_id": note_id, "analysis": result.model_dump()}
            )
        )
    
    return result


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
    """Голосовой ввод заметок с единым STT-контрактом."""
    _ = container
    file_name = file.filename or "voice-input"
    mime_type = file.content_type or "application/octet-stream"
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Пустой аудиофайл.")

    transcriber = MediaTranscriber()
    transcription = await transcriber.transcribe_audio(
        audio_bytes=audio_bytes,
        file_name=file_name,
        mime_type=mime_type,
        language=language,
    )
    return {
        "text": transcription.text,
        "stt": transcription.model_dump(),
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
    
    entities = await container.entity_service.search_mentions(text, limit=20)
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
            "attributes": r.attributes or {},
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "company_id": r.company_id,
        }
        for r in relationships
    ]}
