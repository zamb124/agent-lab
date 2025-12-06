"""
CRM Sharing - поиск пользователей и компаний для shared_with
"""

import json
import logging
from typing import List, Dict, Any

from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from apps.agents.container import get_agents_container
from ._base import fetch_crm_data

logger = logging.getLogger(__name__)
router = APIRouter(tags=["crm-sharing"])


@router.put("/api/sharing/{resource_type}/{resource_id}", response_class=JSONResponse)
async def update_sharing(
    request: Request,
    resource_type: str,  # "note" или "entity"
    resource_id: str,
):
    """Обновить visibility и shared_with для note или entity."""
    if resource_type not in ("note", "entity"):
        return JSONResponse(content={"success": False}, status_code=400)
    
    body = await request.json()
    endpoint = f"/{'notes' if resource_type == 'note' else 'entities'}/{resource_id}"
    
    # Получаем текущий объект
    current = await fetch_crm_data(endpoint, request)
    if not current:
        return JSONResponse(content={"success": False}, status_code=404)
    
    # Конвертируем shared_with из [{type, id, name}] в [id] для CRM backend
    shared_with_raw = body.get("shared_with", [])
    shared_with_ids = []
    for item in shared_with_raw:
        if isinstance(item, dict):
            shared_with_ids.append(item.get("id", ""))
        else:
            shared_with_ids.append(item)
    
    # Обновляем только sharing поля
    current["visibility"] = body.get("visibility", "private")
    current["shared_with"] = shared_with_ids
    
    result = await fetch_crm_data(endpoint, request, method="PUT", json_data=current)
    
    return JSONResponse(content={"success": bool(result)})


@router.get("/api/sharing/search", response_class=JSONResponse)
async def search_shareable(
    request: Request,
    q: str = Query(..., min_length=2, description="Поиск по email или названию компании"),
):
    """
    Поиск пользователей по email и компаний по названию.
    Возвращает список для автодополнения в shared_with.
    """
    container = get_agents_container()
    results: List[Dict[str, Any]] = []
    query_lower = q.lower()
    
    # Поиск пользователей по email в user_providers
    try:
        storage = container.shared_storage
        async with storage._get_session() as session:
            # Фильтрация по email в SQL
            sql = text("""
                SELECT 
                    substring(key from 16) as user_id,
                    value as providers_json
                FROM users
                WHERE key LIKE 'user_providers:%'
                  AND value::text ILIKE :pattern
                LIMIT 50
            """)
            result = await session.execute(sql, {"pattern": f"%{q}%"})
            rows = result.fetchall()
            
            for row in rows:
                user_id = row[0]
                try:
                    providers = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                    for provider_id, info in providers.items():
                        email = info.get("email", "")
                        if email and query_lower in email.lower():
                            # Получаем данные пользователя
                            user = await container.user_repository.get(user_id)
                            if user:
                                # Находим название компании
                                company_name = ""
                                if user.active_company_id:
                                    company = await container.company_repository.get(user.active_company_id)
                                    if company:
                                        company_name = company.name
                                
                                results.append({
                                    "type": "user",
                                    "id": user_id,
                                    "email": email,
                                    "name": user.name,
                                    "company_name": company_name,
                                    "avatar_url": info.get("avatar_url", ""),
                                })
                            break
                except (json.JSONDecodeError, TypeError):
                    continue
    except Exception as e:
        logger.error(f"Ошибка поиска пользователей: {e}")
    
    # Поиск компаний по названию (компании хранятся в таблице storage)
    try:
        storage = container.shared_storage
        async with storage._get_session() as session:
            # Фильтруем по имени в SQL чтобы LIMIT работал правильно
            sql = text("""
                SELECT 
                    substring(key from 9) as company_id,
                    value
                FROM storage
                WHERE key LIKE 'company:%'
                  AND key NOT LIKE 'company:%:%'
                  AND value::text ILIKE :pattern
                LIMIT 20
            """)
            result = await session.execute(sql, {"pattern": f"%{q}%"})
            rows = result.fetchall()
            
            for row in rows:
                company_id = row[0]
                try:
                    company_data = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                    company_name = company_data.get("name", "")
                    if company_name and query_lower in company_name.lower():
                        members_count = len(company_data.get("members", {}) or {})
                        results.append({
                            "type": "company",
                            "id": company_id,
                            "name": company_name,
                            "members_count": members_count,
                        })
                except (json.JSONDecodeError, TypeError):
                    continue
    except Exception as e:
        logger.error(f"Ошибка поиска компаний: {e}")
    
    # Сортировка: сначала точные совпадения, потом частичные
    def sort_key(item):
        name = item.get("email", "") or item.get("name", "")
        name_lower = name.lower()
        if name_lower == query_lower:
            return (0, name)
        if name_lower.startswith(query_lower):
            return (1, name)
        return (2, name)
    
    results.sort(key=sort_key)
    
    return JSONResponse(content=results[:20])

