"""
CRM Notes - заметки partials и API
"""

import json
import logging
from typing import Optional
from datetime import date

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

from ._base import templates, fetch_crm_data

logger = logging.getLogger(__name__)
router = APIRouter(tags=["crm-notes"])


# === Partials ===

@router.get("/partials/notes", response_class=HTMLResponse)
async def partial_notes(
    request: Request,
    note_type: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
):
    """Notes list partial with filters"""
    params = []
    if note_type:
        params.append(f"note_type={note_type}")
    if user_id:
        params.append(f"user_id={user_id}")
    if entity_id:
        params.append(f"entity_id={entity_id}")
    if start_date:
        params.append(f"start_date={start_date}")
    if end_date:
        params.append(f"end_date={end_date}")
    if q:
        params.append(f"q={q}")
    
    endpoint = "/notes" + ("?" + "&".join(params) if params else "")
    notes = await fetch_crm_data(endpoint, request)
    entity_types = await fetch_crm_data("/entity-types", request)
    
    return templates.TemplateResponse(
        "crm/partials/_notes.html",
        {
            "request": request, 
            "notes": notes if isinstance(notes, list) else [], 
            "today": str(date.today()),
            "entity_types": entity_types if isinstance(entity_types, list) else [],
            "filters": {
                "note_type": note_type,
                "user_id": user_id,
                "entity_id": entity_id,
                "start_date": start_date,
                "end_date": end_date,
                "q": q,
            }
        }
    )


@router.get("/partials/notes/{note_id}/suggestions", response_class=HTMLResponse)
async def get_note_suggestions(request: Request, note_id: str):
    """Get cached AI suggestions for a note"""
    entity_types = await fetch_crm_data("/entity-types", request)
    return templates.TemplateResponse(
        "crm/partials/_note_suggestions.html",
        {
            "request": request,
            "note_id": note_id,
            "entities": [],
            "tasks": [],
            "summary": "",
            "ai_error": None,
            "entity_types": entity_types if isinstance(entity_types, list) else []
        }
    )


@router.get("/partials/notes/{note_id}/linked-entities", response_class=HTMLResponse)
async def get_linked_entities(request: Request, note_id: str):
    """Get entities linked to a note"""
    note = await fetch_crm_data(f"/notes/{note_id}", request)
    
    entities = note.get("linked_entities") or []
    if not entities and note.get("linked_entity_ids"):
        for eid in note["linked_entity_ids"]:
            entity = await fetch_crm_data(f"/entities/{eid}", request)
            if entity:
                entities.append(entity)
    
    return templates.TemplateResponse(
        "crm/partials/_note_linked_entities.html",
        {
            "request": request,
            "note_id": note_id,
            "entities": entities
        }
    )


@router.get("/partials/notes/database", response_class=HTMLResponse)
async def partial_notes_database(request: Request):
    """Notes database partial"""
    notes = await fetch_crm_data("/notes", request)
    return templates.TemplateResponse(
        "crm/partials/_notes_database.html",
        {"request": request, "notes": notes if isinstance(notes, list) else []}
    )


@router.get("/partials/notes/{note_id}", response_class=HTMLResponse)
async def partial_note_view(request: Request, note_id: str):
    """View single note with AI suggestions"""
    note = await fetch_crm_data(f"/notes/{note_id}", request)
    
    entities = note.get("linked_entities") or []
    if not entities and note.get("linked_entity_ids"):
        for entity_id in note["linked_entity_ids"]:
            entity = await fetch_crm_data(f"/entities/{entity_id}", request)
            if entity:
                entities.append(entity)
    
    return templates.TemplateResponse(
        "crm/partials/_note_view.html",
        {
            "request": request,
            "note": note,
            "entities": entities
        }
    )


@router.delete("/partials/notes/{note_id}/unlink/{entity_id}", response_class=HTMLResponse)
async def unlink_entity_from_note(request: Request, note_id: str, entity_id: str):
    """Unlink entity from note"""
    await fetch_crm_data(f"/notes/{note_id}/link/{entity_id}", request, method="DELETE")
    
    note = await fetch_crm_data(f"/notes/{note_id}", request)
    entities = note.get("linked_entities") or []
    
    if not entities and note.get("linked_entity_ids"):
        for eid in note["linked_entity_ids"]:
            entity = await fetch_crm_data(f"/entities/{eid}", request)
            if entity:
                entities.append(entity)
    
    return templates.TemplateResponse(
        "crm/partials/_note_linked_entities.html",
        {
            "request": request,
            "note_id": note_id,
            "entities": entities
        }
    )


@router.post("/partials/notes", response_class=HTMLResponse)
async def create_note(request: Request, note_id: Optional[str] = Query(None)):
    """Create/update note"""
    data = await request.json()
    
    is_template = str(data.get("is_template", "")).lower() == "true"
    
    shared_with = data.get("shared_with", [])
    if isinstance(shared_with, str):
        try:
            shared_with = json.loads(shared_with)
        except (json.JSONDecodeError, TypeError):
            shared_with = []
    
    # Обработка упомянутых сущностей через @mention
    mentioned_entity_ids = data.get("mentioned_entity_ids", [])
    if isinstance(mentioned_entity_ids, str):
        try:
            mentioned_entity_ids = json.loads(mentioned_entity_ids)
        except (json.JSONDecodeError, TypeError):
            mentioned_entity_ids = []
    
    note_data = {
        "title": data.get("title", ""),
        "content": data.get("content", ""),
        "note_type": data.get("note_type", "freeform"),
        "note_date": data.get("note_date", str(date.today())),
        "is_template": is_template,
        "status": "published",
        "visibility": data.get("visibility", "private"),
        "shared_with": shared_with if isinstance(shared_with, list) else [],
        "linked_entity_ids": mentioned_entity_ids if isinstance(mentioned_entity_ids, list) else []
    }
    
    is_new_note = not note_id
    is_from_modal = request.headers.get("HX-Target") == "#modal-container"
    
    if note_id:
        note = await fetch_crm_data(f"/notes/{note_id}", request, method="PUT", json_data=note_data)
    else:
        note = await fetch_crm_data("/notes", request, method="POST", json_data=note_data)
    
    created_note_id = note.get("note_id") or note.get("id")
    logger.info(f"Note created/updated: id={created_note_id}, title={note.get('title')}")
    
    # При создании новой заметки из модалки - редирект на полноэкранный режим
    if is_new_note and is_from_modal and created_note_id:
        from starlette.responses import Response
        response = Response(status_code=200)
        response.headers["HX-Redirect"] = f"/crm/notes/{created_note_id}"
        return response
    
    return templates.TemplateResponse(
        "crm/partials/_note_view.html",
        {
            "request": request,
            "note": note,
            "entities": [],
            "tasks": [],
            "summary": "",
            "ai_error": None,
            "analyzing": True
        }
    )


@router.post("/partials/notes/{note_id}/analyze", response_class=HTMLResponse)
async def analyze_note_async(request: Request, note_id: str):
    """Run AI analysis on note"""
    suggested_entities = []
    suggested_tasks = []
    suggested_relationships = []
    ai_error = None
    summary = ""
    
    note = await fetch_crm_data(f"/notes/{note_id}", request)
    linked_entities = note.get("linked_entities") or []
    linked_entity_ids = note.get("linked_entity_ids") or []
    
    if not linked_entities and linked_entity_ids:
        for eid in linked_entity_ids:
            entity = await fetch_crm_data(f"/entities/{eid}", request)
            if entity:
                linked_entities.append(entity)
    
    linked_names = {e.get("name", "").lower().strip() for e in linked_entities}
    
    # Передаём ID упомянутых сущностей в AI для создания связей
    analysis = await fetch_crm_data(f"/notes/{note_id}/analyze", request, method="POST", json_data={
        "extract_entities": True,
        "generate_summary": True,
        "create_tasks": True,
        "mentioned_entity_ids": linked_entity_ids
    })

    if not analysis:
        ai_error = "Analysis failed"
    elif analysis.get("error"):
        ai_error = analysis["error"]
    else:
        summary = analysis.get("summary", "")
        
        # Log what we received
        logger.info(f"Analysis result keys: {list(analysis.keys())}")
        logger.info(f"Extracted entities: {len(analysis.get('extracted_entities', []))}")
        logger.info(f"Extracted relationships: {len(analysis.get('extracted_relationships', []))}")
        
        for entity_data in analysis.get("extracted_entities", []):
            name = entity_data.get("name", "")
            entity_type = entity_data.get("type", "person")
            
            if name.lower().strip() in linked_names:
                continue
                
            if entity_type == "task":
                suggested_tasks.append({
                    "title": name,
                    "description": entity_data.get("description"),
                    "priority": entity_data.get("attributes", {}).get("priority", "medium"),
                    "deadline": entity_data.get("attributes", {}).get("deadline") or entity_data.get("attributes", {}).get("due_date"),
                })
            else:
                suggested_entities.append({
                    "type": entity_type,
                    "name": name,
                    "description": entity_data.get("description"),
                    "ai_description": entity_data.get("ai_description", ""),
                    "attributes": entity_data.get("attributes", {}),
                    "relevance": entity_data.get("relevance", 0.5),
                })

        for task_data in analysis.get("created_tasks", []):
            suggested_tasks.append(task_data)
        
        # Relationships from AI
        suggested_relationships = analysis.get("extracted_relationships", [])
        logger.info(f"Relationships from analysis: {suggested_relationships}")
    
    entity_types = await fetch_crm_data("/entity-types", request)
    return templates.TemplateResponse(
        "crm/partials/_note_suggestions.html",
        {
            "request": request,
            "note_id": note_id,
            "entities": suggested_entities,
            "tasks": suggested_tasks,
            "relationships": suggested_relationships,
            "summary": summary,
            "ai_error": ai_error,
            "entity_types": entity_types if isinstance(entity_types, list) else []
        }
    )


@router.post("/partials/notes/{note_id}/approve-suggestions", response_class=HTMLResponse)
async def approve_all_suggestions(request: Request, note_id: str):
    """Approve and import all suggestions"""
    created_entities = 0
    created_tasks = 0
    created_relationships = 0
    
    # Маппинг имя -> entity_id для создания связей
    name_to_id: dict[str, str] = {}
    
    try:
        data = await request.json()
        entities = data.get("entities", [])
        tasks = data.get("tasks", [])
        relationships = data.get("relationships", [])
        
        logger.info(f"Approve: {len(entities)} entities, {len(relationships)} relationships, {len(tasks)} tasks")
        
        # 1. Создаем entities и собираем маппинг name -> id
        for entity_data in entities:
            entity_create = {
                "name": entity_data.get("name"),
                "type": entity_data.get("type", "person"),
                "description": entity_data.get("description"),
                "ai_description": entity_data.get("ai_description", "Сущность извлечена из заметки"),
                "attributes": entity_data.get("attributes", {}),
                "status": "approved"
            }
            created_entity = await fetch_crm_data("/entities", request, method="POST", json_data=entity_create)
            
            if created_entity:
                entity_id = created_entity.get("entity_id") or created_entity.get("id")
                entity_name = entity_data.get("name", "").lower().strip()
            if entity_id:
                name_to_id[entity_name] = entity_id
                await fetch_crm_data(f"/notes/{note_id}/link/{entity_id}", request, method="POST")
                created_entities += 1
            else:
                logger.warning(f"Failed to create entity: {entity_data.get('name')}")
        
        # 2. Создаем relationships
        for rel_data in relationships:
            source_name = rel_data.get("source", "").lower().strip()
            target_name = rel_data.get("target", "").lower().strip()
            
            source_id = name_to_id.get(source_name)
            target_id = name_to_id.get(target_name)
            
            if source_id and target_id:
                rel_create = {
                    "source_entity_id": source_id,
                    "target_entity_id": target_id,
                    "relationship_type": rel_data.get("type", "related_to"),
                    "weight": rel_data.get("weight", 1.0),
                    "attributes": rel_data.get("attributes", {}),
                }
                result = await fetch_crm_data("/relationships", request, method="POST", json_data=rel_create)
                if result:
                    created_relationships += 1
                else:
                    logger.warning(f"Failed to create relationship: {source_name} -> {target_name}")
            else:
                logger.warning(f"Cannot create relationship - missing entities: {source_name} ({source_id}) -> {target_name} ({target_id})")
        
        # 3. Создаем tasks
        for task_data in tasks:
            task_create = {
                "title": task_data.get("title"),
                "priority": task_data.get("priority", "medium"),
                "status": "pending"
            }
            result = await fetch_crm_data("/tasks", request, method="POST", json_data=task_create)
            if result:
                created_tasks += 1
            else:
                logger.warning(f"Failed to create task: {task_data.get('title')}")
            
    except Exception as e:
        logger.warning(f"Error approving suggestions: {e}")
        entity_types = await fetch_crm_data("/entity-types", request)
        return templates.TemplateResponse(
            "crm/partials/_note_suggestions.html",
            {
                "request": request,
                "note_id": note_id,
                "entities": [],
                "tasks": [],
                "summary": "",
                "ai_error": f"Ошибка: {str(e)}",
                "entity_types": entity_types if isinstance(entity_types, list) else []
            }
        )
    
    messages = []
    if created_entities > 0:
        messages.append(f"Создано {created_entities} сущностей")
    if created_relationships > 0:
        messages.append(f"Создано {created_relationships} связей")
    if created_tasks > 0:
        messages.append(f"Создано {created_tasks} задач")
    
    entity_types = await fetch_crm_data("/entity-types", request)
    return templates.TemplateResponse(
        "crm/partials/_note_suggestions.html",
        {
            "request": request,
            "note_id": note_id,
            "entities": [],
            "tasks": [],
            "summary": "",
            "ai_error": None,
            "success_message": ". ".join(messages) if messages else "Импорт завершен",
            "entity_types": entity_types if isinstance(entity_types, list) else []
        }
    )


@router.post("/partials/notes/close-modal", response_class=HTMLResponse)
async def close_modal_and_refresh(request: Request):
    """Close modal and refresh notes list"""
    notes = await fetch_crm_data("/notes", request)
    entity_types = await fetch_crm_data("/entity-types", request)
    return templates.TemplateResponse(
        "crm/partials/_notes.html",
        {
            "request": request, 
            "notes": notes if isinstance(notes, list) else [], 
            "today": str(date.today()),
            "entity_types": entity_types if isinstance(entity_types, list) else [],
        }
    )


@router.get("/partials/daily-summary", response_class=HTMLResponse)
async def partial_daily_summary(request: Request, date: Optional[str] = Query(None)):
    """Daily summary partial"""
    from datetime import date as date_cls
    summary_date = date if date else str(date_cls.today())
    
    try:
        result = await fetch_crm_data(f"/notes/daily-summary/{summary_date}", request)
        summary = result.get("summary", "") if isinstance(result, dict) else ""
    except Exception as e:
        logger.warning(f"Failed to get daily summary: {e}")
        summary = ""
    
    return HTMLResponse(f"""
    <div class="crm-ai-suggestions" style="margin-bottom: 20px;">
        <div class="crm-ai-header" style="margin-bottom: 12px;">
            <div class="crm-ai-icon">
                <i class="ti ti-sparkles"></i>
            </div>
            <div>
                <div class="crm-ai-title">Саммари за {summary_date}</div>
            </div>
            <button type="button" 
                    class="crm-btn crm-btn-ghost crm-btn-sm" 
                    style="margin-left: auto;"
                    onclick="this.closest('#daily-summary-container').innerHTML = ''">
                <i class="ti ti-x"></i>
            </button>
        </div>
        <div class="crm-prose" data-markdown="{summary.replace('"', '&quot;')}">{summary}</div>
    </div>
    """)


@router.get("/partials/note-modal", response_class=HTMLResponse)
async def partial_note_modal(request: Request, note_id: Optional[str] = Query(None)):
    """Note create/edit modal"""
    note = None
    linked_entities = []
    
    if note_id:
        note = await fetch_crm_data(f"/notes/{note_id}", request)
        if note:
            linked_entities = note.get("linked_entities") or []
            if not linked_entities and note.get("linked_entity_ids"):
                for eid in note["linked_entity_ids"]:
                    entity = await fetch_crm_data(f"/entities/{eid}", request)
                    if entity:
                        linked_entities.append(entity)
    
    return templates.TemplateResponse(
        "crm/partials/_note_modal.html",
        {
            "request": request,
            "note": note,
            "linked_entities": linked_entities,
            "today": str(date.today())
        }
    )


@router.get("/partials/import-modal", response_class=HTMLResponse)
async def partial_import_modal(request: Request):
    """Import note modal"""
    return templates.TemplateResponse(
        "crm/partials/_import_modal.html",
        {"request": request}
    )


# === API ===

@router.post("/api/notes/import")
async def import_note_from_file(request: Request):
    """Import note from file"""
    import os
    import httpx
    
    form = await request.form()
    file = form.get("file")
    
    if not file:
        return HTMLResponse(
            '{"error": "No file provided"}',
            status_code=400,
            media_type="application/json"
        )
    
    base_url = os.environ.get("TEST_CRM_SERVICE_URL")
    if not base_url:
        settings = request.app.state.settings
        base_url = getattr(settings.server, "crm_service_url", "http://localhost:8003")
    
    url = f"{base_url}/crm/api/v1/notes/import"
    
    context = getattr(request.state, "context", None)
    auth_token = request.cookies.get("auth_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    
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
    
    file_content = await file.read()
    files = {"file": (file.filename, file_content, file.content_type)}
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, files=files)
        
        if response.status_code != 200:
            return HTMLResponse(
                f'{{"error": "Import failed: {response.text}"}}',
                status_code=response.status_code,
                media_type="application/json"
            )
        
        return response.json()


@router.get("/api/notes/{note_id}/export/{format}")
async def export_note(request: Request, note_id: str, format: str):
    """Export note to PDF/HTML"""
    import os
    import httpx
    from fastapi.responses import Response
    
    if format not in ["pdf", "html"]:
        return HTMLResponse('{"error": "Invalid format"}', status_code=400, media_type="application/json")
    
    base_url = os.environ.get("TEST_CRM_SERVICE_URL")
    if not base_url:
        settings = request.app.state.settings
        base_url = getattr(settings.server, "crm_service_url", "http://localhost:8003")
    
    url = f"{base_url}/crm/api/v1/export/note/{note_id}?format={format}"
    
    context = getattr(request.state, "context", None)
    auth_token = request.cookies.get("auth_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    
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
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, headers=headers)
        
        content_type = "application/pdf" if format == "pdf" else "text/html"
        return Response(
            content=response.content,
            media_type=content_type,
            headers=dict(response.headers)
        )


# === Attachments ===

@router.post("/api/notes/{note_id}/attachments")
async def upload_attachment(request: Request, note_id: str):
    """Upload file attachment to note"""
    import os
    import httpx
    
    form = await request.form()
    file = form.get("file")
    
    if not file:
        return HTMLResponse(
            '<div class="crm-alert crm-alert-error">No file provided</div>',
            status_code=400
        )
    
    base_url = os.environ.get("TEST_CRM_SERVICE_URL")
    if not base_url:
        settings = request.app.state.settings
        base_url = getattr(settings.server, "crm_service_url", "http://localhost:8003")
    
    url = f"{base_url}/crm/api/v1/notes/{note_id}/attachments"
    
    context = getattr(request.state, "context", None)
    auth_token = request.cookies.get("auth_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    
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
    
    file_content = await file.read()
    files = {"file": (file.filename, file_content, file.content_type)}
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, files=files)
        return response.json()


@router.delete("/api/notes/{note_id}/attachments/{file_id}")
async def remove_attachment(request: Request, note_id: str, file_id: str):
    """Remove attachment from note"""
    await fetch_crm_data(f"/notes/{note_id}/attachments/{file_id}", request, method="DELETE")
    return {"status": "deleted"}


@router.get("/api/notes/{note_id}/attachments", response_class=HTMLResponse)
async def get_attachments(request: Request, note_id: str):
    """Get note attachments - returns rendered HTML"""
    attachments = await fetch_crm_data(f"/notes/{note_id}/attachments", request)
    
    if not attachments or not isinstance(attachments, list):
        return HTMLResponse("")
    
    # Рендерим HTML для каждого файла
    html_parts = []
    for att in attachments:
        file_id = att.get("file_id", "")
        filename = att.get("original_name") or att.get("filename") or "file"
        file_size = att.get("file_size") or att.get("size") or 0
        content_type = att.get("content_type", "")
        
        # Получаем расширение
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        if not ext and "pdf" in content_type: ext = "pdf"
        elif not ext and "image" in content_type: ext = "img"
        elif not ext: ext = "file"
        
        # Определяем цвет
        colors = {
            'pdf': '#dc2626', 'doc': '#2563eb', 'docx': '#2563eb',
            'txt': '#6b7280', 'png': '#10b981', 'jpg': '#10b981', 
            'jpeg': '#10b981', 'gif': '#8b5cf6', 'xls': '#16a34a',
            'xlsx': '#16a34a', 'csv': '#16a34a'
        }
        color = colors.get(ext, '#6b7280')
        
        # Форматируем размер
        if file_size >= 1024 * 1024:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"
        elif file_size >= 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size} B"
            
        # Обрезаем имя если слишком длинное
        display_name = filename
        if len(display_name) > 12:
            display_name = display_name[:12] + "..."
        
        html_parts.append(f'''
            <div class="crm-file-icon" data-file-id="{file_id}" 
                 onclick="CRM.downloadAttachment('{note_id}', '{file_id}')">
                <div class="crm-file-icon-box" style="background: {color};">
                    <span class="crm-file-ext">{ext.upper()}</span>
                <button type="button" class="crm-file-del" 
                        onclick="event.preventDefault(); event.stopPropagation(); CRM.deleteAttachment('{note_id}', '{file_id}'); return false;"
                        title="Delete">
                    <i class="ti ti-x"></i>
                </button>
                <button type="button" class="crm-file-info-btn" 
                            onclick="event.preventDefault(); event.stopPropagation(); CRM.showFileContent('{note_id}', '{file_id}', this); return false;"
                            title="Content">
                        <i class="ti ti-file-text"></i>
                </button>
                </div>
                <span class="crm-file-name" title="{filename}">{display_name}</span>
                <span class="crm-file-size">{size_str}</span>
            </div>
        ''')
    
    return HTMLResponse("".join(html_parts))


@router.get("/api/notes/{note_id}/attachments/{file_id}/download")
async def download_attachment(request: Request, note_id: str, file_id: str):
    """Download attachment"""
    import os
    import httpx
    from fastapi.responses import Response
    
    base_url = os.environ.get("TEST_CRM_SERVICE_URL")
    if not base_url:
        settings = request.app.state.settings
        base_url = getattr(settings.server, "crm_service_url", "http://localhost:8003")
    
    url = f"{base_url}/crm/api/v1/notes/{note_id}/attachments/{file_id}/download"
    
    context = getattr(request.state, "context", None)
    auth_token = request.cookies.get("auth_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    
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
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, headers=headers)
        return Response(
            content=response.content,
            media_type=response.headers.get("content-type", "application/octet-stream"),
            headers=dict(response.headers)
        )


@router.get("/api/notes/{note_id}/attachments/{file_id}/content")
async def get_attachment_content(request: Request, note_id: str, file_id: str):
    """Get attachment content"""
    import os
    import httpx
    from fastapi.responses import Response
    
    base_url = os.environ.get("TEST_CRM_SERVICE_URL")
    if not base_url:
        settings = request.app.state.settings
        base_url = getattr(settings.server, "crm_service_url", "http://localhost:8003")
    
    url = f"{base_url}/crm/api/v1/notes/{note_id}/attachments/{file_id}/content"
    
    context = getattr(request.state, "context", None)
    auth_token = request.cookies.get("auth_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    
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
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, headers=headers)
        return Response(
            content=response.content,
            media_type=response.headers.get("content-type", "text/plain"),
            headers=dict(response.headers)
        )

