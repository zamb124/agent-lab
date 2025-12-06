"""
CRM Dashboard Partials
"""

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

from ._base import templates, fetch_crm_data

router = APIRouter(tags=["crm-dashboard"])


@router.get("/partials/dashboard", response_class=HTMLResponse)
async def partial_dashboard(request: Request):
    """Dashboard partial"""
    stats = await fetch_crm_data("/tasks/stats", request)
    
    pending_requests = 0
    pending_data = await fetch_crm_data("/access-requests/pending-count", request)
    pending_requests = pending_data.get("count", 0) if isinstance(pending_data, dict) else 0
    
    return templates.TemplateResponse(
        "crm/partials/_dashboard.html",
        {
            "request": request, 
            "stats": stats,
            "pending_requests": pending_requests
        }
    )


@router.get("/partials/priority-tasks", response_class=HTMLResponse)
async def partial_priority_tasks(request: Request):
    """Priority tasks (overdue + today) for dashboard"""
    overdue = await fetch_crm_data("/tasks/overdue", request)
    today = await fetch_crm_data("/tasks/due-today", request)
    
    all_tasks = []
    for task in (overdue if isinstance(overdue, list) else []):
        task["is_overdue"] = True
        all_tasks.append(task)
    for task in (today if isinstance(today, list) else []):
        task["is_today"] = True
        all_tasks.append(task)
    
    priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
    all_tasks.sort(key=lambda t: (priority_order.get(t.get("priority", "medium"), 2), not t.get("is_overdue", False)))
    
    return templates.TemplateResponse(
        "crm/partials/_priority_tasks.html",
        {
            "request": request,
            "tasks": all_tasks[:10]
        }
    )


@router.get("/partials/recent-notes", response_class=HTMLResponse)
async def partial_recent_notes(request: Request, limit: int = Query(5)):
    """Recent notes for dashboard widget"""
    notes = await fetch_crm_data(f"/notes?limit={limit}", request)
    return templates.TemplateResponse(
        "crm/partials/_recent_notes.html",
        {
            "request": request,
            "notes": notes if isinstance(notes, list) else []
        }
    )


@router.get("/partials/recent-entities", response_class=HTMLResponse)
async def partial_recent_entities(request: Request, limit: int = Query(5)):
    """Recent entities for dashboard widget"""
    entities = await fetch_crm_data(f"/entities?limit={limit}", request)
    return templates.TemplateResponse(
        "crm/partials/_recent_entities.html",
        {
            "request": request,
            "entities": entities if isinstance(entities, list) else []
        }
    )


@router.get("/partials/pending-access-requests", response_class=HTMLResponse)
async def partial_pending_access_requests(request: Request):
    """Pending access requests for dashboard widget"""
    requests_data = await fetch_crm_data("/access-requests/incoming", request)
    pending = [r for r in (requests_data if isinstance(requests_data, list) else []) if r.get("status") == "pending"]
    return templates.TemplateResponse(
        "crm/partials/_pending_access_requests.html",
        {
            "request": request,
            "requests": pending[:5]
        }
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

