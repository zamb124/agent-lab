"""
Router для CRM UI - standalone интерфейс Networkle
"""

import logging
from typing import Optional
import json
from datetime import date

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

from apps.frontend.core.template_loader import get_templates
from core.http import get_httpx_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crm", tags=["crm-pages"])
templates = get_templates()


async def fetch_crm_data(endpoint: str, request: Request, method: str = "GET", json_data: dict = None) -> dict | list:
    """Fetch data from CRM backend"""
    import os
    
    # Сначала проверяем переменную окружения (для тестов)
    base_url = os.environ.get("TEST_CRM_SERVICE_URL")
    if not base_url:
        # Потом берём из settings приложения
        settings = request.app.state.settings
        base_url = getattr(settings.server, "crm_service_url", "http://localhost:8003")
    
    url = f"{base_url}/crm/api/v1{endpoint}"
    
    # Получаем данные авторизации из context (уже разобран AuthMiddleware)
    context = getattr(request.state, "context", None)
    auth_token = request.cookies.get("auth_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    
    # company_id из context или headers
    company_id = ""
    if context and context.active_company:
        company_id = context.active_company.company_id
    if not company_id:
        company_id = request.headers.get("X-Company-Id", "")
    
    headers = {}
    if company_id:
        headers["X-Company-Id"] = company_id
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    
    logger.debug(f"CRM request: {url}, headers: {list(headers.keys())}, token: {'yes' if auth_token else 'no'}, company: {company_id}")
    
    async with get_httpx_client(timeout=30.0, use_proxy_from_config=False) as client:
        if method == "POST":
            response = await client.post(url, headers=headers, json=json_data or {})
        elif method == "PUT":
            response = await client.put(url, headers=headers, json=json_data or {})
        elif method == "DELETE":
            response = await client.delete(url, headers=headers)
        else:
            response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


# === Main Pages ===

@router.get("/", response_class=HTMLResponse)
async def crm_dashboard(request: Request):
    """Главная страница CRM Dashboard"""
    return templates.TemplateResponse(
        "crm/crm_base.html",
        {"request": request, "current_page": "crm_dashboard"}
    )


@router.get("/notes", response_class=HTMLResponse)
async def crm_notes(request: Request):
    """Страница Notes"""
    return templates.TemplateResponse(
        "crm/crm_base.html",
        {"request": request, "current_page": "crm_notes"}
    )


@router.get("/notes/database", response_class=HTMLResponse)
async def crm_note_database(request: Request):
    """Страница Note Database"""
    return templates.TemplateResponse(
        "crm/crm_base.html",
        {"request": request, "current_page": "crm_note_database"}
    )


@router.get("/entities", response_class=HTMLResponse)
async def crm_entities(request: Request, type: Optional[str] = Query(None)):
    """Страница Entities"""
    return templates.TemplateResponse(
        "crm/crm_base.html",
        {"request": request, "current_page": "crm_entities", "entity_type": type}
    )


@router.get("/entities/{entity_id}", response_class=HTMLResponse)
async def crm_entity_detail(request: Request, entity_id: str):
    """Страница Entity Detail"""
    return templates.TemplateResponse(
        "crm/crm_base.html",
        {"request": request, "current_page": "crm_entity_detail", "entity_id": entity_id}
    )


@router.get("/tasks", response_class=HTMLResponse)
async def crm_tasks(request: Request):
    """Страница Tasks"""
    return templates.TemplateResponse(
        "crm/crm_base.html",
        {"request": request, "current_page": "crm_tasks"}
    )


@router.get("/graph", response_class=HTMLResponse)
async def crm_graph(request: Request):
    """Страница Knowledge Graph"""
    return templates.TemplateResponse(
        "crm/crm_base.html",
        {"request": request, "current_page": "crm_graph"}
    )


@router.get("/settings", response_class=HTMLResponse)
async def crm_settings(request: Request):
    """Страница Settings"""
    return templates.TemplateResponse(
        "crm/crm_base.html",
        {"request": request, "current_page": "crm_settings"}
    )


# === Partials (HTMX) ===

@router.get("/partials/dashboard", response_class=HTMLResponse)
async def partial_dashboard(request: Request):
    """Dashboard partial"""
    stats = await fetch_crm_data("/tasks/stats", request)
    return templates.TemplateResponse(
        "crm/partials/_dashboard.html",
        {"request": request, "stats": stats}
    )


@router.get("/partials/notes", response_class=HTMLResponse)
async def partial_notes(request: Request):
    """Notes list partial"""
    notes = await fetch_crm_data("/notes", request)
    return templates.TemplateResponse(
        "crm/partials/_notes.html",
        {"request": request, "notes": notes if isinstance(notes, list) else [], "today": str(date.today())}
    )


@router.post("/partials/notes", response_class=HTMLResponse)
async def create_note_and_analyze(request: Request, note_id: Optional[str] = Query(None)):
    """Create/update note, analyze with AI, create entities with pending status"""
    form_data = await request.form()
    note_data = {
        "title": form_data.get("title", ""),
        "content": form_data.get("content", ""),
        "note_type": form_data.get("note_type", "freeform"),
        "note_date": form_data.get("note_date", str(date.today()))
    }
    
    if note_id:
        note = await fetch_crm_data(f"/notes/{note_id}", request, method="PUT", json_data=note_data)
    else:
        note = await fetch_crm_data("/notes", request, method="POST", json_data=note_data)
    
    created_note_id = note.get("note_id") or note.get("id")
    
    # AI анализ
    analysis = await fetch_crm_data(f"/notes/{created_note_id}/analyze", request, method="POST", json_data={
        "extract_entities": True,
        "generate_summary": True,
        "create_tasks": True
    })
    
    # Создаём сущности сразу со статусом pending
    created_entities = []
    for entity_data in analysis.get("extracted_entities", []):
        entity_create = {
            "type": entity_data.get("type", "person"),
            "name": entity_data.get("name", ""),
            "description": entity_data.get("description"),
            "attributes": entity_data.get("attributes", {}),
            "status": "pending",
            "source_note_id": created_note_id
        }
        created_entity = await fetch_crm_data("/entities", request, method="POST", json_data=entity_create)
        created_entities.append(created_entity)
        
        # Линкуем к заметке
        entity_id = created_entity.get("entity_id") or created_entity.get("id")
        if entity_id:
            await fetch_crm_data(f"/notes/{created_note_id}/link/{entity_id}", request, method="POST")
    
    return templates.TemplateResponse(
        "crm/partials/_ai_suggestions.html",
        {
            "request": request,
            "note": note,
            "summary": analysis.get("summary", ""),
            "entities": created_entities,
            "tasks": analysis.get("created_tasks", []),
            "relationships": analysis.get("extracted_relationships", [])
        }
    )


@router.post("/partials/entities/{entity_id}/approve", response_class=HTMLResponse)
async def approve_entity(request: Request, entity_id: str):
    """Approve entity - change status from pending to approved"""
    await fetch_crm_data(f"/entities/{entity_id}/status?status=approved", request, method="PUT")
    
    # Возвращаем обновлённую сущность
    entity = await fetch_crm_data(f"/entities/{entity_id}", request)
    return templates.TemplateResponse(
        "crm/partials/_entity_badge.html",
        {"request": request, "entity": entity}
    )


@router.post("/partials/entities/{entity_id}/reject", response_class=HTMLResponse)
async def reject_entity(request: Request, entity_id: str):
    """Reject entity - change status to rejected"""
    await fetch_crm_data(f"/entities/{entity_id}/status?status=rejected", request, method="PUT")
    return HTMLResponse("")  # Удаляем из UI


@router.post("/partials/notes/close-modal", response_class=HTMLResponse)
async def close_modal_and_refresh(request: Request):
    """Close modal and refresh notes list"""
    notes = await fetch_crm_data("/notes", request)
    return templates.TemplateResponse(
        "crm/partials/_notes.html",
        {"request": request, "notes": notes if isinstance(notes, list) else [], "today": str(date.today())}
    )


@router.get("/partials/notes/database", response_class=HTMLResponse)
async def partial_notes_database(request: Request):
    """Notes database partial"""
    notes = await fetch_crm_data("/notes", request)
    return templates.TemplateResponse(
        "crm/partials/_notes_database.html",
        {"request": request, "notes": notes if isinstance(notes, list) else []}
    )


@router.get("/partials/entities", response_class=HTMLResponse)
async def partial_entities(request: Request, type: Optional[str] = Query(None)):
    """Entities list partial"""
    endpoint = f"/entities?entity_type={type}" if type else "/entities"
    entities = await fetch_crm_data(endpoint, request)
    entity_types = await fetch_crm_data("/entity-types", request)
    return templates.TemplateResponse(
        "crm/partials/_entities.html",
        {
            "request": request,
            "entities": entities if isinstance(entities, list) else [],
            "entity_types": entity_types if isinstance(entity_types, list) else [],
            "current_type": type
        }
    )


@router.get("/partials/entity/{entity_id}", response_class=HTMLResponse)
async def partial_entity_detail(request: Request, entity_id: str):
    """Entity detail partial"""
    entity = await fetch_crm_data(f"/entities/{entity_id}", request)
    relationships = await fetch_crm_data(f"/relationships/entity/{entity_id}", request)
    return templates.TemplateResponse(
        "crm/partials/_entity_detail.html",
        {
            "request": request,
            "entity": entity,
            "relationships": relationships if isinstance(relationships, list) else []
        }
    )


@router.get("/partials/tasks", response_class=HTMLResponse)
async def partial_tasks(request: Request):
    """Tasks list partial"""
    tasks = await fetch_crm_data("/tasks", request)
    stats = await fetch_crm_data("/tasks/stats", request)
    return templates.TemplateResponse(
        "crm/partials/_tasks.html",
        {
            "request": request,
            "tasks": tasks if isinstance(tasks, list) else [],
            "stats": stats
        }
    )


@router.get("/partials/tasks-sidebar", response_class=HTMLResponse)
async def partial_tasks_sidebar(request: Request):
    """Tasks sidebar widget partial"""
    overdue = await fetch_crm_data("/tasks/overdue", request)
    today = await fetch_crm_data("/tasks/due-today", request)
    week = await fetch_crm_data("/tasks/due-this-week", request)
    return templates.TemplateResponse(
        "crm/partials/_tasks_sidebar.html",
        {
            "request": request,
            "overdue": overdue if isinstance(overdue, list) else [],
            "today": today if isinstance(today, list) else [],
            "upcoming": week if isinstance(week, list) else []
        }
    )


@router.get("/partials/tasks-count", response_class=HTMLResponse)
async def partial_tasks_count(request: Request):
    """Tasks count for badge"""
    stats = await fetch_crm_data("/tasks/stats", request)
    count = stats.get("pending", 0) + stats.get("overdue", 0) if isinstance(stats, dict) else 0
    return HTMLResponse(str(count))


@router.get("/partials/graph", response_class=HTMLResponse)
async def partial_graph(request: Request):
    """Knowledge Graph partial"""
    graph = await fetch_crm_data("/graph", request)
    relationship_types = await fetch_crm_data("/graph/relationship-types", request)
    return templates.TemplateResponse(
        "crm/partials/_graph.html",
        {
            "request": request,
            "graph": graph,
            "relationship_types": relationship_types if isinstance(relationship_types, list) else []
        }
    )


@router.get("/partials/search", response_class=HTMLResponse)
async def partial_search(request: Request, q: str = Query("")):
    """Search results partial"""
    if not q or len(q) < 2:
        return HTMLResponse("")
    
    search_result = await fetch_crm_data("/entities/search", request, method="POST", json_data={"query": q})
    results = search_result.get("results", []) if isinstance(search_result, dict) else []
    return templates.TemplateResponse(
        "crm/partials/_search_results.html",
        {
            "request": request,
            "query": q,
            "results": results
        }
    )


# === Modals ===

@router.get("/partials/note-modal", response_class=HTMLResponse)
async def partial_note_modal(request: Request, note_id: Optional[str] = Query(None)):
    """Note create/edit modal"""
    note = None
    if note_id:
        note = await fetch_crm_data(f"/notes/{note_id}", request)
        logger.debug(f"Loaded note: {note}")
    return templates.TemplateResponse(
        "crm/partials/_note_modal.html",
        {"request": request, "note": note, "today": str(date.today())}
    )


@router.get("/partials/entity-modal", response_class=HTMLResponse)
async def partial_entity_modal_new(request: Request):
    """New entity modal"""
    entity_types = await fetch_crm_data("/entity-types", request)
    return templates.TemplateResponse(
        "crm/partials/_entity_modal.html",
        {
            "request": request,
            "entity": None,
            "entity_types": entity_types if isinstance(entity_types, list) else [],
            "relationships": []
        }
    )


@router.get("/partials/entity-modal/{entity_id}", response_class=HTMLResponse)
async def partial_entity_modal(request: Request, entity_id: str):
    """Entity detail modal"""
    entity = await fetch_crm_data(f"/entities/{entity_id}", request)
    relationships = await fetch_crm_data(f"/relationships/entity/{entity_id}", request)
    entity_types = await fetch_crm_data("/entity-types", request)
    return templates.TemplateResponse(
        "crm/partials/_entity_modal.html",
        {
            "request": request,
            "entity": entity,
            "entity_types": entity_types if isinstance(entity_types, list) else [],
            "relationships": relationships if isinstance(relationships, list) else []
        }
    )


@router.get("/partials/ai-suggestions-modal", response_class=HTMLResponse)
async def partial_ai_suggestions_modal(request: Request, data: str = Query("")):
    """AI suggestions modal after note analysis"""
    analysis = json.loads(data) if data else {}
    return templates.TemplateResponse(
        "crm/partials/_ai_suggestions.html",
        {"request": request, "analysis": analysis}
    )


@router.get("/partials/ai-suggestions", response_class=HTMLResponse)
async def partial_ai_suggestions(request: Request, data: str = Query("")):
    """AI suggestions modal after note analysis"""
    analysis = json.loads(data) if data else {}
    return templates.TemplateResponse(
        "crm/partials/_ai_suggestions.html",
        {"request": request, "analysis": analysis}
    )


@router.get("/partials/settings", response_class=HTMLResponse)
async def partial_settings(request: Request):
    """Settings partial"""
    entity_types = await fetch_crm_data("/entity-types", request)
    return templates.TemplateResponse(
        "crm/partials/_settings.html",
        {
            "request": request,
            "entity_types": entity_types if isinstance(entity_types, list) else []
        }
    )
