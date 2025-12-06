"""
CRM Tasks - задачи partials и API
"""

import json
import logging
from typing import Optional
from datetime import date

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

from ._base import templates, fetch_crm_data

logger = logging.getLogger(__name__)
router = APIRouter(tags=["crm-tasks"])


# === Partials ===

@router.get("/partials/tasks", response_class=HTMLResponse)
async def partial_tasks(
    request: Request,
    status: Optional[str] = Query(None, alias="task-status-filter"),
    priority: Optional[str] = Query(None, alias="task-priority-filter"),
    search: Optional[str] = Query(None, alias="task-search")
):
    """Tasks list partial with filters"""
    params = []
    if status:
        params.append(f"status={status}")
    if priority:
        params.append(f"priority={priority}")
    if search:
        params.append(f"q={search}")
    
    query_string = "&".join(params)
    endpoint = f"/tasks?{query_string}" if query_string else "/tasks"
    
    tasks = await fetch_crm_data(endpoint, request)
    stats = await fetch_crm_data("/tasks/stats", request)
    
    return templates.TemplateResponse(
        "crm/partials/_tasks.html",
        {
            "request": request,
            "tasks": tasks if isinstance(tasks, list) else [],
            "stats": stats,
            "filter_status": status,
            "filter_priority": priority,
            "search_query": search
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


@router.get("/partials/task-modal", response_class=HTMLResponse)
async def partial_task_modal(request: Request, task_id: Optional[str] = Query(None)):
    """Task create/edit modal"""
    task = None
    linked_entity = None
    
    if task_id:
        task = await fetch_crm_data(f"/tasks/{task_id}", request)
        if task and task.get("linked_entity_id"):
            try:
                linked_entity = await fetch_crm_data(f"/entities/{task['linked_entity_id']}", request)
            except Exception:
                pass
    
    return templates.TemplateResponse(
        "crm/partials/_task_modal.html",
        {
            "request": request,
            "task": task,
            "linked_entity": linked_entity,
            "today": str(date.today())
        }
    )


# === API ===

@router.post("/api/tasks", response_class=HTMLResponse)
async def create_or_update_task(request: Request, task_id: Optional[str] = Query(None)):
    """Create or update task via JSON"""
    body = await request.json()
    
    tags = body.get("tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            tags = []
    
    assignees = body.get("assignees", [])
    if isinstance(assignees, str):
        try:
            assignees = json.loads(assignees)
        except (json.JSONDecodeError, TypeError):
            assignees = []
    
    data = {
        "title": body.get("title"),
        "description": body.get("description") or None,
        "priority": body.get("priority", "medium"),
        "due_date": body.get("due_date") or None,
        "linked_entity_id": body.get("linked_entity_id") or None,
        "tags": tags,
        "assignees": assignees,
    }
    
    if task_id:
        if body.get("status"):
            data["status"] = body.get("status")
        await fetch_crm_data(f"/tasks/{task_id}", request, method="PUT", json_data=data)
    else:
        await fetch_crm_data("/tasks", request, method="POST", json_data=data)
    
    return await partial_tasks(request)


@router.post("/api/tasks/{task_id}/complete", response_class=HTMLResponse)
async def complete_task(request: Request, task_id: str):
    """Complete task"""
    await fetch_crm_data(f"/tasks/{task_id}/complete", request, method="POST")
    return HTMLResponse('<script>htmx.trigger(document.body, "taskUpdated")</script>')


@router.delete("/api/tasks/{task_id}", response_class=HTMLResponse)
async def delete_task(request: Request, task_id: str):
    """Delete task"""
    await fetch_crm_data(f"/tasks/{task_id}", request, method="DELETE")
    return await partial_tasks(request)

