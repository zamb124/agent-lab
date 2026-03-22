"""
API для управления ресурсами компаний.
"""

from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apps.flows.src.tasks.company_init_tasks import init_company_resources
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/company", tags=["company"])


class InitCompanyRequest(BaseModel):
    """Запрос инициализации компании"""
    company_id: str
    company_name: str = ""
    subdomain: str = ""


class InitCompanyResponse(BaseModel):
    """Ответ инициализации компании"""
    task_id: str
    status: str
    message: str


@router.post("/init", response_model=InitCompanyResponse)
async def init_company(request: InitCompanyRequest) -> InitCompanyResponse:
    """
    Инициализирует агенты и тулы для новой компании.
    
    Запускает TaskIQ задачу которая загружает:
    - Public агенты со всеми зависимостями (из кода)
    - Public тулы (из кода)
    
    Args:
        request: company_id и company_name
        
    Returns:
        task_id для отслеживания выполнения
    """
    logger.info(f"Запрос инициализации компании: {request.company_id}")
    
    # Запрещаем инициализацию system через API
    if request.company_id == "system":
        raise HTTPException(
            status_code=400,
            detail="System namespace инициализируется автоматически при старте"
        )
    
    try:
        # Запускаем TaskIQ задачу
        task = await init_company_resources.kiq(
            company_id=request.company_id,
            company_name=request.company_name,
            subdomain=request.subdomain
        )
        
        logger.info(f"Задача инициализации запущена: task_id={task.task_id}")
        
        return InitCompanyResponse(
            task_id=task.task_id,
            status="scheduled",
            message=f"Инициализация компании {request.company_id} запланирована"
        )
        
    except Exception as e:
        logger.error(f"Ошибка запуска инициализации: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Не удалось запустить инициализацию: {str(e)}"
        )

