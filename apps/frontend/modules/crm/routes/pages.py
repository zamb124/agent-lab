"""
CRM Main Pages - главные страницы приложения
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from typing import Optional

from ._base import templates

router = APIRouter(tags=["crm-pages"])


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


@router.get("/notes/{note_id}", response_class=HTMLResponse)
async def crm_note_detail(request: Request, note_id: str):
    """Страница просмотра Note"""
    return templates.TemplateResponse(
        "crm/crm_base.html",
        {"request": request, "current_page": "crm_note_detail", "note_id": note_id}
    )


@router.get("/notes/database", response_class=HTMLResponse)
async def crm_note_database(request: Request):
    """Страница Note Database"""
    return templates.TemplateResponse(
        "crm/crm_base.html",
        {"request": request, "current_page": "crm_note_database"}
    )


@router.get("/entities", response_class=HTMLResponse)
async def crm_entities(request: Request, type: Optional[str] = None):
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


@router.get("/access-requests", response_class=HTMLResponse)
async def crm_access_requests(request: Request):
    """Страница Access Requests"""
    return templates.TemplateResponse(
        "crm/crm_base.html",
        {"request": request, "current_page": "crm_access_requests"}
    )


@router.get("/profile", response_class=HTMLResponse)
async def crm_profile(request: Request):
    """Страница Profile"""
    return templates.TemplateResponse(
        "crm/crm_base.html",
        {"request": request, "current_page": "crm_profile"}
    )

