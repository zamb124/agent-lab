"""
CRM API Proxy - прокси к бэкенду CRM
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, Query, Body
from fastapi.responses import JSONResponse

from core.http import get_httpx_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crm", tags=["crm-api"])

CRM_API_BASE = "/crm/api/v1"


async def proxy_request(
    request: Request,
    method: str,
    endpoint: str,
    body: Optional[dict] = None
) -> JSONResponse:
    """Проксирует запрос к CRM бэкенду"""
    import os
    
    # URL CRM сервиса
    base_url = os.environ.get("TEST_CRM_SERVICE_URL")
    if not base_url:
        settings = request.app.state.settings
        base_url = getattr(settings.server, "crm_service_url", "http://localhost:8003")
    
    url = f"{base_url}{CRM_API_BASE}{endpoint}"
    
    # Авторизация из cookies или headers
    context = getattr(request.state, "context", None)
    auth_token = request.cookies.get("auth_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    
    company_id = ""
    if context and context.active_company:
        company_id = context.active_company.company_id
    if not company_id:
        company_id = request.headers.get("X-Company-Id", "")
    
    headers = {"Content-Type": "application/json"}
    if company_id:
        headers["X-Company-Id"] = company_id
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    
    async with get_httpx_client(timeout=30.0, use_proxy_from_config=False) as client:
        if method == "GET":
            response = await client.get(url, headers=headers, params=dict(request.query_params))
        elif method == "POST":
            response = await client.post(url, headers=headers, json=body)
        elif method == "PUT":
            response = await client.put(url, headers=headers, json=body)
        elif method == "DELETE":
            response = await client.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        response.raise_for_status()
        return JSONResponse(response.json(), status_code=response.status_code)


# === Notes ===

@router.get("/notes")
async def list_notes(
    request: Request,
    skip: int = Query(0),
    limit: int = Query(50),
    note_type: Optional[str] = Query(None)
):
    """Список заметок"""
    return await proxy_request(request, "GET", "/notes")


@router.get("/notes/{note_id}")
async def get_note(request: Request, note_id: str):
    """Получить заметку"""
    return await proxy_request(request, "GET", f"/notes/{note_id}")


@router.post("/notes")
async def create_note(request: Request, body: dict = Body(...)):
    """Создать заметку"""
    return await proxy_request(request, "POST", "/notes", body)


@router.put("/notes/{note_id}")
async def update_note(request: Request, note_id: str, body: dict = Body(...)):
    """Обновить заметку"""
    return await proxy_request(request, "PUT", f"/notes/{note_id}", body)


@router.delete("/notes/{note_id}")
async def delete_note(request: Request, note_id: str):
    """Удалить заметку"""
    return await proxy_request(request, "DELETE", f"/notes/{note_id}")


@router.post("/notes/{note_id}/analyze")
async def analyze_note(request: Request, note_id: str):
    """AI анализ заметки"""
    return await proxy_request(request, "POST", f"/notes/{note_id}/analyze")


@router.post("/notes/{note_id}/entities/{entity_id}")
async def link_entity_to_note(request: Request, note_id: str, entity_id: str):
    """Связать сущность с заметкой"""
    return await proxy_request(request, "POST", f"/notes/{note_id}/entities/{entity_id}")


@router.delete("/notes/{note_id}/entities/{entity_id}")
async def unlink_entity_from_note(request: Request, note_id: str, entity_id: str):
    """Отвязать сущность от заметки"""
    return await proxy_request(request, "DELETE", f"/notes/{note_id}/entities/{entity_id}")


# === Entities ===

@router.get("/entities")
async def list_entities(
    request: Request,
    entity_type: Optional[str] = Query(None),
    skip: int = Query(0),
    limit: int = Query(50)
):
    """Список сущностей"""
    return await proxy_request(request, "GET", "/entities")


@router.get("/entities/{entity_id}")
async def get_entity(request: Request, entity_id: str):
    """Получить сущность"""
    return await proxy_request(request, "GET", f"/entities/{entity_id}")


@router.post("/entities")
async def create_entity(request: Request, body: dict = Body(...)):
    """Создать сущность"""
    return await proxy_request(request, "POST", "/entities", body)


@router.put("/entities/{entity_id}")
async def update_entity(request: Request, entity_id: str, body: dict = Body(...)):
    """Обновить сущность"""
    return await proxy_request(request, "PUT", f"/entities/{entity_id}", body)


@router.delete("/entities/{entity_id}")
async def delete_entity(request: Request, entity_id: str):
    """Удалить сущность"""
    return await proxy_request(request, "DELETE", f"/entities/{entity_id}")


@router.post("/entities/search")
async def search_entities(request: Request, body: dict = Body(...)):
    """Семантический поиск сущностей"""
    return await proxy_request(request, "POST", "/entities/search", body)


@router.get("/entities/{entity_id}/duplicates")
async def find_duplicates(request: Request, entity_id: str):
    """Найти дубликаты сущности"""
    return await proxy_request(request, "GET", f"/entities/{entity_id}/duplicates")


# === Entity Types ===

@router.get("/entity-types")
async def list_entity_types(request: Request):
    """Список типов сущностей"""
    return await proxy_request(request, "GET", "/entity-types")


@router.get("/entity-types/{type_id}")
async def get_entity_type(request: Request, type_id: str):
    """Получить тип сущности"""
    return await proxy_request(request, "GET", f"/entity-types/{type_id}")


# === Relationships ===

@router.get("/relationships")
async def list_relationships(request: Request):
    """Список связей"""
    return await proxy_request(request, "GET", "/relationships")


@router.get("/relationships/entity/{entity_id}")
async def get_entity_relationships(request: Request, entity_id: str):
    """Связи сущности"""
    return await proxy_request(request, "GET", f"/relationships/entity/{entity_id}")


@router.post("/relationships")
async def create_relationship(request: Request, body: dict = Body(...)):
    """Создать связь"""
    return await proxy_request(request, "POST", "/relationships", body)


@router.delete("/relationships/{relationship_id}")
async def delete_relationship(request: Request, relationship_id: str):
    """Удалить связь"""
    return await proxy_request(request, "DELETE", f"/relationships/{relationship_id}")


# === Tasks ===

@router.get("/tasks")
async def list_tasks(request: Request):
    """Список задач"""
    return await proxy_request(request, "GET", "/tasks")


@router.get("/tasks/my")
async def my_tasks(request: Request):
    """Мои задачи"""
    return await proxy_request(request, "GET", "/tasks/my")


@router.get("/tasks/overdue")
async def overdue_tasks(request: Request):
    """Просроченные задачи"""
    return await proxy_request(request, "GET", "/tasks/overdue")


@router.get("/tasks/today")
async def today_tasks(request: Request):
    """Задачи на сегодня"""
    return await proxy_request(request, "GET", "/tasks/today")


@router.get("/tasks/week")
async def week_tasks(request: Request):
    """Задачи на неделю"""
    return await proxy_request(request, "GET", "/tasks/week")


@router.get("/tasks/stats")
async def tasks_stats(request: Request):
    """Статистика задач"""
    return await proxy_request(request, "GET", "/tasks/stats")


@router.get("/tasks/{task_id}")
async def get_task(request: Request, task_id: str):
    """Получить задачу"""
    return await proxy_request(request, "GET", f"/tasks/{task_id}")


@router.post("/tasks")
async def create_task(request: Request, body: dict = Body(...)):
    """Создать задачу"""
    return await proxy_request(request, "POST", "/tasks", body)


@router.put("/tasks/{task_id}")
async def update_task(request: Request, task_id: str, body: dict = Body(...)):
    """Обновить задачу"""
    return await proxy_request(request, "PUT", f"/tasks/{task_id}", body)


@router.post("/tasks/{task_id}/complete")
async def complete_task(request: Request, task_id: str):
    """Завершить задачу"""
    return await proxy_request(request, "POST", f"/tasks/{task_id}/complete")


@router.delete("/tasks/{task_id}")
async def delete_task(request: Request, task_id: str):
    """Удалить задачу"""
    return await proxy_request(request, "DELETE", f"/tasks/{task_id}")


# === Knowledge Graph ===

@router.get("/graph")
async def get_graph(request: Request):
    """Получить полный граф"""
    return await proxy_request(request, "GET", "/graph")


@router.get("/graph/entity/{entity_id}")
async def get_entity_graph(request: Request, entity_id: str, depth: int = Query(1)):
    """Граф вокруг сущности"""
    return await proxy_request(request, "GET", f"/graph/entity/{entity_id}")


@router.get("/graph/relationship-types")
async def get_relationship_types(request: Request):
    """Типы связей в графе"""
    return await proxy_request(request, "GET", "/graph/relationship-types")

