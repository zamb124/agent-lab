"""
CRM Templates - шаблоны заметок
"""

import logging
from typing import Optional
from datetime import date

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

from ._base import templates, fetch_crm_data

logger = logging.getLogger(__name__)
router = APIRouter(tags=["crm-templates"])


@router.get("/partials/templates-list", response_class=HTMLResponse)
async def partial_templates_list(request: Request):
    """Templates list partial"""
    templates_list = await fetch_crm_data("/notes/templates", request)
    return templates.TemplateResponse(
        "crm/partials/_templates_list.html",
        {
            "request": request,
            "templates": templates_list if isinstance(templates_list, list) else []
        }
    )


@router.get("/partials/template-modal", response_class=HTMLResponse)
async def partial_template_modal(request: Request, template_id: Optional[str] = Query(None)):
    """Template create/edit modal"""
    template = None
    if template_id:
        template = await fetch_crm_data(f"/notes/{template_id}", request)
    
    return templates.TemplateResponse(
        "crm/partials/_template_modal.html",
        {
            "request": request,
            "template": template
        }
    )


@router.post("/api/templates", response_class=HTMLResponse)
async def create_or_update_template(request: Request, template_id: Optional[str] = Query(None)):
    """Create or update template via JSON"""
    body = await request.json()
    
    data = {
        "title": body.get("title"),
        "content": body.get("content", ""),
        "note_type": body.get("note_type", "freeform"),
        "note_date": str(date.today()),
        "is_template": True,
        "status": "published"
    }
    
    if template_id:
        await fetch_crm_data(f"/notes/{template_id}", request, method="PUT", json_data=data)
    else:
        await fetch_crm_data("/notes", request, method="POST", json_data=data)
    
    templates_list = await fetch_crm_data("/notes/templates", request)
    return templates.TemplateResponse(
        "crm/partials/_templates_list.html",
        {
            "request": request,
            "templates": templates_list if isinstance(templates_list, list) else []
        }
    )


@router.delete("/api/templates/{template_id}", response_class=HTMLResponse)
async def delete_template(request: Request, template_id: str):
    """Delete template"""
    await fetch_crm_data(f"/notes/{template_id}", request, method="DELETE")
    
    templates_list = await fetch_crm_data("/notes/templates", request)
    return templates.TemplateResponse(
        "crm/partials/_templates_list.html",
        {
            "request": request,
            "templates": templates_list if isinstance(templates_list, list) else []
        }
    )

