"""
Frontend API для административных операций с компаниями.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from core.context import get_context
from apps.agents.container import get_agents_container

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.delete("/company/{company_id}")
async def delete_company(company_id: str):
    """
    Удалить компанию и все её данные.
    
    Требования:
    - Пользователь должен иметь роль admin в удаляемой компании
    - У пользователя должно быть больше 1 компании (нельзя удалить последнюю)
    
    Удаление выполняется асинхронно через TaskIQ.
    """
    context = get_context()
    if not context or not context.user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    user = context.user
    
    if company_id not in user.companies:
        raise HTTPException(status_code=403, detail="У вас нет доступа к этой компании")
    
    user_roles = user.companies.get(company_id, [])
    if "admin" not in user_roles:
        raise HTTPException(status_code=403, detail="Для удаления компании требуется роль admin")
    
    if len(user.companies) <= 1:
        raise HTTPException(
            status_code=400, 
            detail="Нельзя удалить единственную компанию. Создайте новую компанию перед удалением."
        )
    
    container = get_agents_container()
    company_repo = container.company_repository
    
    company = await company_repo.get(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Компания не найдена")
    
    if company.status == "deleting":
        raise HTTPException(status_code=400, detail="Компания уже удаляется")
    
    company.status = "deleting"
    company.updated_at = datetime.now(timezone.utc)
    await company_repo.set(company)
    
    from apps.agents.tasks.company_tasks import delete_company_task
    await delete_company_task.kiq(company_id, user.user_id)
    
    logger.info(f"Запущено удаление компании {company_id} пользователем {user.user_id}")
    
    return {
        "status": "deleting",
        "message": f"Удаление компании '{company.name}' запущено. Это может занять некоторое время.",
        "company_id": company_id,
    }

