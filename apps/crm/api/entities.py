"""
API для работы с entities.

Единый endpoint для всех типов entities.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from apps.crm.models.api import (
    EntityCreate,
    EntityUpdate,
    EntityResponse,
    EntityTimelineBoundsResponse,
    AIAnalyzeRequest,
    AIAnalyzeResponse,
    SearchMentionsRequest,
    RelationshipResponse,
)
from apps.crm.db.models import CRMEntity
from apps.crm.services.entity_service import EntityService
from apps.crm.services.access_control_service import AccessControlService
from apps.crm.dependencies import get_entity_service, get_access_control_service
from core.clients.stt_client import STTClientFactory
from core.context import get_context
from core.websocket.publisher import notify_user, Notification, NotificationType

router = APIRouter(prefix="/entities", tags=["Entities"])


@router.post("", response_model=EntityResponse)
async def create_entity(
    data: EntityCreate,
    service: EntityService = Depends(get_entity_service)
):
    """Создать новую entity"""
    try:
        entity = await service.create_entity(
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
            assignees=data.assignees
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return EntityResponse.model_validate(entity)


@router.get("/search", response_model=List[EntityResponse])
async def search_entities(
    query: str = Query(...),
    entity_type: Optional[str] = Query(None),
    entity_subtype: Optional[str] = Query(None),
    limit: int = Query(10, le=100),
    service: EntityService = Depends(get_entity_service)
):
    """Семантический поиск entities"""
    entities = await service.search_entities(
        query=query,
        entity_type=entity_type,
        entity_subtype=entity_subtype,
        limit=limit
    )
    return [EntityResponse.model_validate(e) for e in entities]


@router.get("/timeline/bounds", response_model=EntityTimelineBoundsResponse)
async def get_entities_timeline_bounds(
    entity_type: Optional[str] = Query(None),
    entity_subtype: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None, description="Фильтр по namespace"),
    service: EntityService = Depends(get_entity_service),
):
    """Получить границы timeline по created_at."""
    bounds = await service.get_timeline_bounds(
        entity_type=entity_type,
        entity_subtype=entity_subtype,
        namespace=namespace,
    )
    return EntityTimelineBoundsResponse.model_validate(bounds)


@router.get("/{entity_id}")
async def get_entity(
    entity_id: str,
    service: EntityService = Depends(get_entity_service),
    access_control: AccessControlService = Depends(get_access_control_service)
):
    """Получить entity по ID с проверкой доступа"""
    entity = await service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Проверка доступа через AccessGrants
    ctx = get_context()
    user_id = ctx.user.user_id if ctx and ctx.user else None
    company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
    
    if not await access_control.can_read_entity(entity, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Фильтрация полей (полный доступ → entity, публичный → dict с ограниченными полями)
    try:
        filtered = await access_control.filter_fields(entity, user_id, company_id)
        if isinstance(filtered, CRMEntity):
            return EntityResponse.model_validate(filtered)
        return filtered
    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied")


@router.put("/{entity_id}", response_model=EntityResponse)
async def update_entity(
    entity_id: str,
    data: EntityUpdate,
    service: EntityService = Depends(get_entity_service),
    access_control: AccessControlService = Depends(get_access_control_service)
):
    """Обновить entity с проверкой прав"""
    entity = await service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Проверка прав на запись
    ctx = get_context()
    user_id = ctx.user.user_id if ctx and ctx.user else None
    company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
    
    if not user_id or not await access_control.can_write_entity(entity, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Обновление
    updates = data.model_dump(exclude_none=True)
    try:
        updated = await service.update_entity(entity_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return EntityResponse.model_validate(updated)


@router.delete("/{entity_id}")
async def delete_entity(
    entity_id: str,
    service: EntityService = Depends(get_entity_service)
):
    """Каскадное удаление entity"""
    success = await service.delete_entity(entity_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"success": True}


@router.get("", response_model=List[EntityResponse])
async def list_entities(
    entity_type: Optional[str] = Query(None),
    entity_subtype: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None, description="Фильтр по namespace"),
    tags: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    created_at_from: Optional[datetime] = Query(None, description="Фильтр created_at >= value"),
    created_at_to: Optional[datetime] = Query(None, description="Фильтр created_at <= value"),
    limit: int = Query(100, le=1000),
    service: EntityService = Depends(get_entity_service)
):
    """Получить список entities с фильтрацией"""
    filters = {}
    if tags:
        filters["tags"] = {"$contains": tags}
    if user_id:
        filters["user_id"] = user_id
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
    
    entities = await service.list_entities(
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
    note_id: Optional[str] = Query(None, description="ID заметки для нотификации"),
    check_duplicates: bool = Query(True, description="Проверять дубликаты entities"),
    service: EntityService = Depends(get_entity_service)
):
    """AI анализ текста с извлечением entities и relationships"""
    try:
        result = await service.analyze_text_with_ai(request, check_duplicates=check_duplicates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    
    context = get_context()
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
    service: EntityService = Depends(get_entity_service)
):
    """Получить AI саммари заметок за день"""
    date_str = request.get("date")
    if date_str is None:
        raise HTTPException(status_code=400, detail="date is required")
    namespace = request.get("namespace")
    force_rebuild = request.get("force_rebuild") is True
    summary = await service.get_daily_summary_cached(
        date_str=date_str,
        namespace=namespace,
        force_rebuild=force_rebuild,
    )
    return summary


@router.get("/{entity_id}/card")
async def get_entity_card(
    entity_id: str,
    service: EntityService = Depends(get_entity_service),
    access_control: AccessControlService = Depends(get_access_control_service)
):
    """
    Получить полную карточку entity с контекстом:
    - Данные entity
    - Все relationships
    - Связанные entities
    - Attachments
    """
    try:
        entity = await service.get_entity(entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        ctx = get_context()
        user_id = ctx.user.user_id if ctx and ctx.user else None
        company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
        if not await access_control.can_read_entity(entity, user_id, company_id):
            raise HTTPException(status_code=403, detail="Access denied")
        card = await service.get_entity_card(entity_id)
        return card
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/voice-input")
async def voice_input(
    file: UploadFile = File(...),
    language: str | None = Query(default=None),
):
    """Голосовой ввод заметок с единым STT-контрактом."""
    file_name = file.filename or "voice-input"
    mime_type = file.content_type or "application/octet-stream"
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Пустой аудиофайл.")

    stt_client = STTClientFactory.create_client()
    stt_result = await stt_client.transcribe_audio(
        audio_bytes=audio_bytes,
        file_name=file_name,
        mime_type=mime_type,
        language=language,
    )
    if stt_result.status.value != "done":
        raise HTTPException(
            status_code=422,
            detail=f"Неуспешный статус STT: {stt_result.status.value}",
        )
    if stt_result.text.strip() == "":
        raise HTTPException(status_code=422, detail="STT вернул пустую транскрипцию.")

    return {
        "text": stt_result.text,
        "stt": stt_result.model_dump(),
    }


@router.post("/search/mentions", response_model=Dict)
async def search_mentions(
    request: SearchMentionsRequest,
    service: EntityService = Depends(get_entity_service)
):
    """Real-time поиск упоминаний entities в тексте для подсветки"""
    text = request.text
    if not text or len(text) < 3:
        return {"entities": []}
    
    entities = await service.search_mentions(text, limit=20)
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
    service: EntityService = Depends(get_entity_service),
    access_control: AccessControlService = Depends(get_access_control_service)
):
    """Получить все relationships для entity"""
    from apps.crm.container import get_crm_container

    container = get_crm_container()
    repo = container.relationship_repository

    entity = await service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    ctx = get_context()
    user_id = ctx.user.user_id if ctx and ctx.user else None
    company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
    if not await access_control.can_read_entity(entity, user_id, company_id):
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

