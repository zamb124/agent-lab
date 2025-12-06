"""
CRM Entities - сущности partials и API
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, Response

from ._base import templates, fetch_crm_data

logger = logging.getLogger(__name__)
router = APIRouter(tags=["crm-entities"])


# === Partials ===

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
    """Entity detail modal"""
    entity = await fetch_crm_data(f"/entities/{entity_id}", request)
    relationships = await fetch_crm_data(f"/relationships/entity/{entity_id}", request)
    return templates.TemplateResponse(
        "crm/partials/_entity_modal.html",
        {
            "request": request,
            "entity": entity,
            "relationships": relationships if isinstance(relationships, list) else []
        }
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
    
    entity_notes = await fetch_crm_data(f"/notes?entity_id={entity_id}&limit=1", request)
    entity_tasks = await fetch_crm_data(f"/tasks?entity_id={entity_id}&limit=1", request)
    
    return templates.TemplateResponse(
        "crm/partials/_entity_modal.html",
        {
            "request": request,
            "entity": entity,
            "entity_types": entity_types if isinstance(entity_types, list) else [],
            "relationships": relationships if isinstance(relationships, list) else [],
            "entity_notes_count": len(entity_notes) if isinstance(entity_notes, list) else 0,
            "entity_tasks_count": len(entity_tasks) if isinstance(entity_tasks, list) else 0
        }
    )


@router.get("/partials/entity-notes/{entity_id}", response_class=HTMLResponse)
async def partial_entity_notes(request: Request, entity_id: str):
    """Entity notes tab content"""
    notes = await fetch_crm_data(f"/notes?entity_id={entity_id}", request)
    return templates.TemplateResponse(
        "crm/partials/_entity_notes.html",
        {
            "request": request,
            "entity_id": entity_id,
            "notes": notes if isinstance(notes, list) else []
        }
    )


@router.get("/partials/entity-tasks/{entity_id}", response_class=HTMLResponse)
async def partial_entity_tasks(request: Request, entity_id: str):
    """Entity tasks tab content"""
    tasks = await fetch_crm_data(f"/tasks?entity_id={entity_id}", request)
    return templates.TemplateResponse(
        "crm/partials/_entity_tasks.html",
        {
            "request": request,
            "entity_id": entity_id,
            "tasks": tasks if isinstance(tasks, list) else []
        }
    )


@router.get("/partials/entity-intelligence/{entity_id}", response_class=HTMLResponse)
async def partial_entity_intelligence(request: Request, entity_id: str):
    """AI-generated intelligence summary for entity"""
    entity = await fetch_crm_data(f"/entities/{entity_id}", request)
    notes = await fetch_crm_data(f"/notes?entity_id={entity_id}&limit=10", request)
    
    notes_list = notes if isinstance(notes, list) else []
    
    if notes_list:
        topics = []
        for note in notes_list[:5]:
            if note.get("title"):
                topics.append(note["title"])
        
        summary = f"{entity.get('name', 'This contact')} is a {'VIP ' if entity.get('attributes', {}).get('vip_score', 0) > 3 else ''}contact involved in {len(notes_list)} recorded interactions."
        if topics:
            summary += f" Recent topics include: {', '.join(topics[:3])}."
        last_note = notes_list[0] if notes_list else None
        if last_note:
            summary += f" Last interaction was on {last_note.get('created_at', '')[:10]}."
    else:
        summary = f"No interactions recorded yet for {entity.get('name', 'this contact')}. Add notes to build intelligence."
    
    return HTMLResponse(f'<p>{summary}</p>')


@router.get("/partials/entity-history/{entity_id}", response_class=HTMLResponse)
async def partial_entity_history(request: Request, entity_id: str):
    """Interaction history for entity"""
    notes = await fetch_crm_data(f"/notes?entity_id={entity_id}&limit=5", request)
    notes_list = notes if isinstance(notes, list) else []
    
    if not notes_list:
        return HTMLResponse('''
            <div class="crm-entity-empty-small">
                <i class="ti ti-history-off"></i>
                No interactions yet
            </div>
        ''')
    
    html_parts = ['<div class="crm-entity-history-list">']
    for note in notes_list:
        date = note.get("created_at", "")[:10] if note.get("created_at") else ""
        title = note.get("title") or "Untitled Note"
        content = note.get("content", "")[:150] + "..." if len(note.get("content", "")) > 150 else note.get("content", "")
        note_id = note.get("note_id") or note.get("id")
        
        html_parts.append(f'''
            <div class="crm-entity-history-item" 
                 hx-get="/crm/partials/notes/{note_id}"
                 hx-target="#crm-content"
                 hx-push-url="/crm/notes/{note_id}">
                <div class="crm-entity-history-date">{date}</div>
                <div class="crm-entity-history-content">
                    <div class="crm-entity-history-title">{title}</div>
                    <div class="crm-entity-history-text">{content}</div>
                </div>
            </div>
        ''')
    html_parts.append('</div>')
    
    html_parts.append('''
        <style>
        .crm-entity-history-list { display: flex; flex-direction: column; gap: 12px; }
        .crm-entity-history-item { 
            display: flex; gap: 16px; padding: 12px; 
            border-radius: 8px; cursor: pointer; transition: background 0.15s;
            border-left: 3px solid var(--crm-primary, #6366f1);
        }
        .crm-entity-history-item:hover { background: var(--crm-bg, #f3f4f6); }
        .crm-entity-history-date { 
            font-size: 12px; color: var(--crm-text-secondary, #6b7280); 
            white-space: nowrap; min-width: 80px;
        }
        .crm-entity-history-title { font-weight: 500; color: var(--crm-text, #1f2937); margin-bottom: 4px; }
        .crm-entity-history-text { font-size: 13px; color: var(--crm-text-secondary, #6b7280); line-height: 1.5; }
        </style>
    ''')
    
    return HTMLResponse(''.join(html_parts))


@router.post("/partials/entities/{entity_id}/approve", response_class=HTMLResponse)
async def approve_entity(request: Request, entity_id: str):
    """Approve entity"""
    await fetch_crm_data(f"/entities/{entity_id}/status?status=approved", request, method="PUT")
    entity = await fetch_crm_data(f"/entities/{entity_id}", request)
    return templates.TemplateResponse(
        "crm/partials/_entity_badge.html",
        {"request": request, "entity": entity}
    )


@router.post("/partials/entities/{entity_id}/reject", response_class=HTMLResponse)
async def reject_entity(request: Request, entity_id: str):
    """Reject entity"""
    await fetch_crm_data(f"/entities/{entity_id}/status?status=rejected", request, method="PUT")
    return HTMLResponse("")


# === API ===

@router.get("/api/v1/entities/autocomplete")
async def autocomplete_entities(
    request: Request, 
    q: str = Query(..., min_length=1), 
    limit: int = Query(10, ge=1, le=50)
):
    """Autocomplete entities for @mentions"""
    result = await fetch_crm_data(f"/entities/autocomplete?q={q}&limit={limit}", request)
    return result if isinstance(result, list) else []


@router.put("/api/entities/{entity_id}", response_class=HTMLResponse)
async def update_entity(request: Request, entity_id: str):
    """Update entity via API"""
    body = await request.json()
    
    result = await fetch_crm_data(f"/entities/{entity_id}", request, method="PUT", json_data=body)
    
    if result:
        return HTMLResponse("""
            <script>
                CRM.closeModal();
                CRM.showNotification('Entity saved', 'success');
                htmx.trigger(document.body, 'entityUpdated');
            </script>
        """)
    else:
        return HTMLResponse("""
            <div class="crm-notification crm-notification-error">
                Failed to save entity
            </div>
        """, status_code=400)


@router.post("/api/entities", response_class=HTMLResponse)
async def create_entity_api(request: Request):
    """Create entity via API"""
    body = await request.json()
    
    result = await fetch_crm_data("/entities", request, method="POST", json_data=body)
    
    if result:
        return HTMLResponse("""
            <script>
                CRM.closeModal();
                CRM.showNotification('Entity created', 'success');
                htmx.trigger(document.body, 'entityUpdated');
            </script>
        """)
    else:
        return HTMLResponse("""
            <div class="crm-notification crm-notification-error">
                Failed to create entity
            </div>
        """, status_code=400)


@router.delete("/api/entities/{entity_id}", response_class=HTMLResponse)
async def delete_entity_api(request: Request, entity_id: str):
    """Delete entity via API"""
    await fetch_crm_data(f"/entities/{entity_id}", request, method="DELETE")
    
    return HTMLResponse("""
        <script>
            CRM.closeModal();
            CRM.showNotification('Entity deleted', 'success');
            htmx.trigger(document.body, 'entityUpdated');
        </script>
    """)


@router.get("/api/entities/{entity_id}/export/{format}")
async def export_entity(request: Request, entity_id: str, format: str):
    """Export entity as PDF or HTML"""
    import os
    import httpx
    
    if format not in ["pdf", "html"]:
        return HTMLResponse("Invalid format", status_code=400)
    
    base_url = os.environ.get("TEST_CRM_SERVICE_URL")
    if not base_url:
        settings = request.app.state.settings
        base_url = getattr(settings.server, "crm_service_url", "http://localhost:8003")
    
    url = f"{base_url}/crm/api/v1/export/entity/{entity_id}?format={format}"
    
    context = getattr(request.state, "context", None)
    auth_token = request.cookies.get("auth_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    company_id = ""
    if context and context.active_company:
        company_id = context.active_company.company_id
    
    headers = {}
    if company_id:
        headers["X-Company-Id"] = company_id
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, headers=headers)
        
        if response.status_code == 200:
            content_type = "application/pdf" if format == "pdf" else "text/html"
            return Response(
                content=response.content,
                media_type=content_type,
                headers={
                    "Content-Disposition": f'attachment; filename="entity-{entity_id}.{format}"'
                }
            )
        return HTMLResponse("Export failed", status_code=response.status_code)

