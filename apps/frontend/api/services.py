"""
API для проверки статуса микросервисов
"""
import logging
import time
from typing import List
from fastapi import APIRouter, HTTPException
from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import ServiceStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("/status", response_model=List[ServiceStatus])
async def get_services_status(container: ContainerDep):
    """
    Получить статус всех микросервисов
    
    Returns:
        Список сервисов с их статусом
    """
    services_config = [
        {"name": "flows", "url": "/flows/api/v1/health"},
        {"name": "crm", "url": "/crm/api/v1/health"},
        {"name": "rag", "url": "/rag/api/health"},
    ]
    
    statuses = []
    service_client = container.service_client
    
    for service_conf in services_config:
        service_name = service_conf["name"]
        health_url = service_conf["url"]
        
        try:
            start_time = time.time()
            response = await service_client.get(service_name, health_url)
            response_time = (time.time() - start_time) * 1000
            
            display_url = "/flows" if service_name == "flows" else f"/{service_name}"
            status = ServiceStatus(
                name=service_name,
                status="healthy",
                url=display_url,
                response_time=round(response_time, 2)
            )
        except Exception as e:
            logger.warning(f"Сервис {service_name} недоступен: {e}")
            display_url = "/flows" if service_name == "flows" else f"/{service_name}"
            status = ServiceStatus(
                name=service_name,
                status="unhealthy",
                url=display_url,
                response_time=None
            )
        
        statuses.append(status)
    
    return statuses


